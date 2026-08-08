from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from stm32_toolkit.cli import main
from stm32_toolkit.hardware_workflows import (
    FaultWorkflowRequest,
    FlashWorkflowRequest,
    HandoffBeginWorkflowRequest,
    HandoffEndWorkflowRequest,
    ProbeListWorkflowRequest,
    RegisterReadWorkflowRequest,
    VariableReadWorkflowRequest,
    VariableSampleWorkflowRequest,
)
from stm32_toolkit.result import OperationResult


BUILD_ID = "1" * 64
ELF_SHA = "2" * 64
TICKET = "3" * 64


def _context(project: Path, data: Path, session: str = "session-a") -> list[str]:
    return [
        "--project",
        str(project),
        "--data-root",
        str(data),
        "--session-id",
        session,
    ]


def _pins() -> list[str]:
    return [
        "--probe",
        "probe-a",
        "--expected-build-id",
        BUILD_ID,
        "--expected-elf-sha256",
        ELF_SHA,
    ]


def _success(operation: str = "hardware") -> OperationResult[object]:
    return OperationResult.success(operation, {"accepted": True})


@pytest.mark.parametrize(
    ("attribute", "argv", "expected_type", "expected"),
    [
        (
            "probe_list_workflow",
            lambda p, d: ["probe", "list", *_context(p, d)],
            ProbeListWorkflowRequest,
            {"session_id": "session-a"},
        ),
        (
            "flash_workflow",
            lambda p, d: ["flash", *_context(p, d), *_pins(), "--authorized"],
            FlashWorkflowRequest,
            {
                "probe_id": "probe-a",
                "expected_build_id": BUILD_ID,
                "expected_elf_sha256": ELF_SHA,
                "authorized": True,
            },
        ),
        (
            "handoff_begin_workflow",
            lambda p, d: [
                "debug",
                "handoff",
                "begin",
                *_context(p, d),
                *_pins(),
                "--authorized",
                "--watch",
                "counter",
                "--watch",
                "status",
            ],
            HandoffBeginWorkflowRequest,
            {"authorized": True, "previous_watch_selection": ("counter", "status")},
        ),
        (
            "handoff_end_workflow",
            lambda p, d: [
                "debug",
                "handoff",
                "end",
                *_context(p, d),
                "--probe",
                "probe-a",
                "--ticket",
                TICKET,
            ],
            HandoffEndWorkflowRequest,
            {"probe_id": "probe-a", "ticket": TICKET},
        ),
        (
            "variable_read_workflow",
            lambda p, d: [
                "read",
                "variable",
                *_context(p, d),
                *_pins(),
                "--expression",
                "counter",
                "--expression",
                "state.ready",
            ],
            VariableReadWorkflowRequest,
            {"expressions": ("counter", "state.ready")},
        ),
        (
            "variable_sample_workflow",
            lambda p, d: [
                "read",
                "sample",
                *_context(p, d),
                *_pins(),
                "--expression",
                "counter",
                "--interval-ms",
                "250",
                "--count",
                "4",
                "--duration-ms",
                "1000",
            ],
            VariableSampleWorkflowRequest,
            {
                "expressions": ("counter",),
                "interval_ms": 250,
                "count": 4,
                "duration_ms": 1000,
            },
        ),
        (
            "register_read_workflow",
            lambda p, d: [
                "read",
                "register",
                *_context(p, d),
                *_pins(),
                "--path",
                "GPIOA.IDR",
                "--acknowledge-access-risk",
            ],
            RegisterReadWorkflowRequest,
            {"paths": ("GPIOA.IDR",), "acknowledge_access_risk": True},
        ),
        (
            "fault_workflow",
            lambda p, d: ["fault", *_context(p, d), *_pins()],
            FaultWorkflowRequest,
            {"probe_id": "probe-a"},
        ),
    ],
)
def test_hardware_cli_maps_nested_argv_to_one_exact_workflow_request(
    monkeypatch,
    tmp_path: Path,
    capsys,
    attribute: str,
    argv: object,
    expected_type: type[object],
    expected: dict[str, object],
) -> None:
    project = tmp_path / "project"
    data = tmp_path / "runtime"
    project.mkdir()
    calls: list[object] = []

    async def accepted(request: object) -> OperationResult[object]:
        calls.append(request)
        return _success(attribute)

    monkeypatch.setattr(f"stm32_toolkit.cli.{attribute}", accepted)
    before = Path.cwd()
    assert main(argv(project, data)) == 0

    captured = capsys.readouterr()
    assert captured.err == ""
    payload = json.loads(captured.out)
    assert payload["ok"] is True
    assert payload["operation"] == attribute
    assert len(calls) == 1
    request = calls[0]
    assert type(request) is expected_type
    assert request.project_root == project
    assert request.data_root == data
    assert request.session_id == "session-a"
    for field, value in expected.items():
        assert getattr(request, field) == value
    assert Path.cwd() == before


@pytest.mark.parametrize(
    ("attribute", "argv"),
    [
        (
            "flash_workflow",
            lambda p, d: ["flash", *_context(p, d), *_pins()],
        ),
        (
            "handoff_begin_workflow",
            lambda p, d: ["debug", "handoff", "begin", *_context(p, d), *_pins()],
        ),
    ],
)
def test_omitted_authorization_reaches_intrusive_workflow_as_exact_false(
    monkeypatch, tmp_path: Path, capsys, attribute: str, argv: object
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    calls: list[object] = []

    async def reject(request: object) -> OperationResult[object]:
        calls.append(request)
        return OperationResult.failure(
            attribute,
            "AUTHORIZATION_REQUIRED",
            "Explicit authorization is required",
            {},
        )

    monkeypatch.setattr(f"stm32_toolkit.cli.{attribute}", reject)
    assert main(argv(project, tmp_path / "data")) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["code"] == "AUTHORIZATION_REQUIRED"
    assert len(calls) == 1
    assert calls[0].authorized is False


@pytest.mark.parametrize(
    "extra",
    [
        ["--target", "secret-target"],
        ["--svd", "C:/secret/device.svd"],
        ["--elf", "C:/secret/firmware.elf"],
        ["--address", "0x20000000"],
        ["--operation-level", "modify"],
        ["--token", "secret-token"],
        ["--lease", "secret-lease"],
        ["--authorized=true"],
    ],
)
def test_forbidden_hardware_overrides_are_grammar_errors_without_secret_echo(
    monkeypatch, tmp_path: Path, capsys, extra: list[str]
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    called = False

    async def forbidden(request: object) -> OperationResult[object]:
        nonlocal called
        called = True
        return _success()

    monkeypatch.setattr("stm32_toolkit.cli.flash_workflow", forbidden)
    assert main(["flash", *_context(project, tmp_path / "data"), *_pins(), *extra]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert called is False
    lowered = captured.err.lower()
    assert "secret" not in lowered
    assert str(project).lower() not in lowered


@pytest.mark.parametrize(
    "argv",
    [
        ["probe", "list"],
        ["flash"],
        ["debug", "handoff", "begin"],
        ["debug", "handoff", "end"],
        ["read", "variable"],
        ["read", "sample"],
        ["read", "register"],
        ["fault"],
        ["debug", "handoff-begin"],
        ["debug", "variables"],
    ],
)
def test_hardware_grammar_requires_context_and_rejects_flattened_aliases(
    argv: list[str], capsys
) -> None:
    assert main(argv) == 2
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize(
    ("arguments", "bad_value"),
    [
        (["--interval-ms", "0", "--count", "1"], "0"),
        (["--interval-ms", "3600001", "--count", "1"], "3600001"),
        (["--interval-ms", "100", "--count", "0"], "0"),
        (["--interval-ms", "100", "--duration-ms", "3600001"], "3600001"),
        (["--interval-ms", "100"], "100"),
    ],
)
def test_sample_grammar_requires_finite_bounded_controls(
    monkeypatch,
    tmp_path: Path,
    capsys,
    arguments: list[str],
    bad_value: str,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    called = False

    async def forbidden(request: object) -> OperationResult[object]:
        nonlocal called
        called = True
        return _success()

    monkeypatch.setattr("stm32_toolkit.cli.variable_sample_workflow", forbidden)
    argv = [
        "read",
        "sample",
        *_context(project, tmp_path / "data"),
        *_pins(),
        "--expression",
        "counter",
        *arguments,
    ]
    assert main(argv) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert called is False
    assert bad_value not in captured.err


def test_hardware_workflow_failure_is_one_json_document_and_exit_two(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    project = tmp_path / "project"
    project.mkdir()

    async def fail(request: object) -> OperationResult[object]:
        return OperationResult.failure(
            "stm32_fault_analyze", "PROBE_BUSY", "Probe is busy", {"probeId": "probe-a"}
        )

    monkeypatch.setattr("stm32_toolkit.cli.fault_workflow", fail)
    assert main(["fault", *_context(project, tmp_path / "data"), *_pins()]) == 2
    captured = capsys.readouterr()
    assert captured.err == ""
    payload = json.loads(captured.out)
    assert payload["ok"] is False
    assert payload["code"] == "PROBE_BUSY"


def test_hardware_internal_exception_is_sanitized_json_without_runtime_leak(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    project = tmp_path / "private-project"
    project.mkdir()

    async def explode(request: object) -> OperationResult[object]:
        raise RuntimeError(f"secret-token backend exploded at {project}")

    monkeypatch.setattr("stm32_toolkit.cli.probe_list_workflow", explode)
    assert main(["probe", "list", *_context(project, tmp_path / "private-data")]) == 2
    captured = capsys.readouterr()
    assert captured.err == ""
    payload = json.loads(captured.out)
    assert payload == {
        "protocol": "stm32-toolkit/1",
        "ok": False,
        "operation": "stm32_probe_list",
        "code": "HARDWARE_INTERNAL_ERROR",
        "message": "Hardware command failed",
        "data": None,
        "details": {},
    }
    assert "secret" not in captured.out.lower()
    assert str(project).lower() not in captured.out.lower()


def test_hardware_cancellation_propagates_without_stdout_or_stderr(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    project = tmp_path / "project"
    project.mkdir()

    async def cancel(request: object) -> OperationResult[object]:
        raise asyncio.CancelledError()

    monkeypatch.setattr("stm32_toolkit.cli.probe_list_workflow", cancel)
    with pytest.raises(asyncio.CancelledError):
        main(["probe", "list", *_context(project, tmp_path / "data")])
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_hardware_cli_does_not_change_or_write_project_files(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    marker = project / "main.c"
    marker.write_bytes(b"int main(void) { return 0; }\n")
    before = {path.name: path.read_bytes() for path in project.iterdir()}
    cwd = Path.cwd()

    async def accepted(request: object) -> OperationResult[object]:
        return _success("stm32_variable_read")

    monkeypatch.setattr("stm32_toolkit.cli.variable_read_workflow", accepted)
    assert main(
        [
            "read",
            "variable",
            *_context(project, tmp_path / "data"),
            *_pins(),
            "--expression",
            "counter",
            "--json",
        ]
    ) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True
    assert Path.cwd() == cwd
    assert {path.name: path.read_bytes() for path in project.iterdir()} == before
