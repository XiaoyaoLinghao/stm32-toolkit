"""VSCODE-TASKS ``ide task`` adapter tests.

The adapter is replayed from the *rendered* generated tasks through the public
CLI parser into fake workflow seams.  Firmware admission uses the real
``_load_fresh_firmware`` over synthetic build evidence; no probe worker,
backend, lease, attach or hardware is constructed.  Every tree is disposable
below ``tmp_path``.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

import stm32_toolkit.cli as cli_mod
import stm32_toolkit.ide_tasks as ide_mod
from stm32_toolkit.cli import main as cli_main
from stm32_toolkit.generation import plan_project_configuration
from stm32_toolkit.hardware_workflows import (
    FlashWorkflowRequest,
    HandoffBeginWorkflowRequest,
    HandoffEndWorkflowRequest,
)
from stm32_toolkit.ide_tasks import run_ide_task
from stm32_toolkit.project_model import load_project_model
from stm32_toolkit.result import OperationResult

from test_build_runner import prepare_project
from test_build_snapshot import snapshot_build
from test_flash import _publish_current_debug_build

LABELS = {
    "flash": "STM32 Toolkit: Flash Debug",
    "handoff-begin": "STM32 Toolkit: Handoff Begin Debug",
    "handoff-end": "STM32 Toolkit: Handoff End Debug",
}
CONFIRMATION_INPUTS = {
    "flash": "stm32tkFlashConfirmation",
    "handoff-begin": "stm32tkHandoffBeginConfirmation",
    "handoff-end": "stm32tkHandoffEndConfirmation",
}
OPERATIONS = {
    "flash": "stm32_flash",
    "handoff-begin": "stm32_debug_handoff_begin",
    "handoff-end": "stm32_debug_handoff_end",
}
PROBE = "probe-a"
SESSION = "session-a"
TICKET = "a" * 64


def _valid_project(tmp_path: Path) -> tuple[Path, dict]:
    root = prepare_project(tmp_path)
    identity = _publish_current_debug_build(root)
    return root, identity


def _data_root(tmp_path: Path) -> Path:
    data_root = tmp_path / "data"
    data_root.mkdir(exist_ok=True)
    return data_root


def _generated_task(plan, action: str) -> dict:
    payload = json.loads(
        next(
            entry for entry in plan.files if entry.path == ".vscode/tasks.json"
        ).after_bytes.decode("utf-8")
    )
    return next(
        task for task in payload["tasks"] if task["label"] == LABELS[action]
    )


def _generated_argv(
    root: Path,
    data_root: Path,
    action: str,
    *,
    confirmation: str | None = "authorize",
) -> list[str]:
    task = _generated_task(plan_project_configuration(load_project_model(root)), action)
    values = {
        "${workspaceFolder}": str(root),
        "${input:stm32tkDataRoot}": str(data_root),
        "${input:stm32tkSessionId}": SESSION,
        "${input:stm32tkProbeId}": PROBE,
        "${input:stm32tkHandoffTicket}": TICKET,
    }
    for name in CONFIRMATION_INPUTS.values():
        values["${input:" + name + "}"] = "deny"
    if confirmation is not None:
        values["${input:" + CONFIRMATION_INPUTS[action] + "}"] = confirmation
    return [values.get(argument, argument) for argument in task["args"]]


def _generated_build_argv(root: Path, label: str) -> list[str]:
    payload = json.loads(
        next(
            entry
            for entry in plan_project_configuration(load_project_model(root)).files
            if entry.path == ".vscode/tasks.json"
        ).after_bytes.decode("utf-8")
    )
    task = next(task for task in payload["tasks"] if task["label"] == label)
    assert task["command"] == "${config:stm32-toolkit.executablePath}"
    return [
        str(root) if argument == "${workspaceFolder}" else argument
        for argument in task["args"]
    ]


def _fresh(identity: dict):
    def admit(_root: Path) -> object:
        return SimpleNamespace(identity=identity)

    return admit


def _forbidden_workflow(_request: object) -> object:
    raise AssertionError("hardware workflow must not be called")


# ---------------------------------------------------------------------------
# rendered task replay through the public parser
# ---------------------------------------------------------------------------


def test_generated_flash_argv_replays_to_the_exact_workflow_request(
    tmp_path, monkeypatch, capsys
):
    root, identity = _valid_project(tmp_path)
    data_root = _data_root(tmp_path)
    recorded = []

    monkeypatch.setattr(ide_mod, "_FRESH_FIRMWARE", _fresh(identity))

    async def fake_flash(request):
        recorded.append(request)
        return OperationResult.success("stm32_flash", {"marker": "flash"})

    monkeypatch.setattr(ide_mod, "_FLASH", fake_flash)

    argv = _generated_argv(root, data_root, "flash")
    assert argv[0:5] == ["--project-root", str(root), "ide", "task", "flash"]
    assert cli_main(argv) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["operation"] == "stm32_flash"
    assert payload["data"] == {"marker": "flash"}

    assert len(recorded) == 1
    request = recorded[0]
    assert type(request) is FlashWorkflowRequest
    assert request.project_root == root
    assert request.data_root == data_root
    assert request.session_id == SESSION
    assert request.probe_id == PROBE
    assert request.expected_build_id == identity["buildId"]
    assert request.expected_elf_sha256 == identity["elfSha256"]
    assert request.authorized is True


def test_generated_handoff_begin_argv_replays_to_the_exact_workflow_request(
    tmp_path, monkeypatch, capsys
):
    root, identity = _valid_project(tmp_path)
    data_root = _data_root(tmp_path)
    recorded = []

    monkeypatch.setattr(ide_mod, "_FRESH_FIRMWARE", _fresh(identity))

    async def fake_begin(request):
        recorded.append(request)
        return OperationResult.success(
            "stm32_debug_handoff_begin", {"handoff": {"configuration": {}}}
        )

    monkeypatch.setattr(ide_mod, "_HANDOFF_BEGIN", fake_begin)

    assert cli_main(_generated_argv(root, data_root, "handoff-begin")) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["operation"] == "stm32_debug_handoff_begin"

    assert len(recorded) == 1
    request = recorded[0]
    assert type(request) is HandoffBeginWorkflowRequest
    assert request.expected_build_id == identity["buildId"]
    assert request.expected_elf_sha256 == identity["elfSha256"]
    assert request.probe_id == PROBE
    assert request.authorized is True


def test_generated_handoff_end_argv_replays_without_fresh_build(
    tmp_path, monkeypatch, capsys
):
    root, _identity = _valid_project(tmp_path)
    data_root = _data_root(tmp_path)
    recorded = []
    fresh_calls = []

    def fresh(_root: Path) -> object:
        fresh_calls.append(_root)
        raise AssertionError("handoff-end must not require a fresh build")

    monkeypatch.setattr(ide_mod, "_FRESH_FIRMWARE", fresh)

    async def fake_end(request):
        recorded.append(request)
        return OperationResult.success(
            "stm32_debug_handoff_end",
            {"ticket": TICKET, "handoff": {"configuration": {"live": False}}},
        )

    monkeypatch.setattr(ide_mod, "_HANDOFF_END", fake_end)

    assert cli_main(_generated_argv(root, data_root, "handoff-end")) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["data"]["ticket"] == TICKET
    assert payload["data"]["handoff"]["configuration"] == {"live": False}

    assert len(recorded) == 1
    request = recorded[0]
    assert type(request) is HandoffEndWorkflowRequest
    assert request.ticket == TICKET
    assert request.probe_id == PROBE
    assert request.project_root == root
    assert fresh_calls == []


def test_generated_build_argv_replays_into_the_build_workflow(
    tmp_path, monkeypatch, capsys
):
    root = prepare_project(tmp_path)
    calls: list[tuple[object, str, bool, int, bool]] = []

    def fake_build(project_root, *, preset, clean, timeout_seconds, authorized):
        calls.append((project_root, preset, clean, timeout_seconds, authorized))
        return OperationResult.success("build", {"preset": preset})

    monkeypatch.setattr(cli_mod, "build_firmware_workflow", fake_build)

    for label, preset in (
        ("STM32 Toolkit: Build Debug", "arm-debug"),
        ("STM32 Toolkit: Build Release", "arm-release"),
    ):
        argv = _generated_build_argv(root, label)
        assert argv[0:2] == ["--project-root", str(root)]
        assert "--json" in argv
        assert cli_main(argv) == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["ok"] is True
        assert payload["operation"] == "build"
        assert payload["data"] == {"preset": preset}

    # The CLI invocation is the user's explicit process action: exact root and
    # preset, no implicit clean, default timeout, authorized=True.
    assert calls == [
        (root, "arm-debug", False, 300, True),
        (root, "arm-release", False, 300, True),
    ]


# ---------------------------------------------------------------------------
# deny before any admission or hardware
# ---------------------------------------------------------------------------


def test_deny_is_the_default_and_precedes_admission_and_workflows(tmp_path):
    root, identity = _valid_project(tmp_path)
    data_root = _data_root(tmp_path)
    fresh_calls = []
    workflow_calls = []

    def fresh(_root: Path) -> object:
        fresh_calls.append(_root)
        return SimpleNamespace(identity=identity)

    def workflow(_request: object) -> object:
        workflow_calls.append(_request)
        return None

    for action in ("flash", "handoff-begin", "handoff-end"):
        result = asyncio.run(
            run_ide_task(
                action,
                project_root=root,
                data_root=data_root,
                session_id=SESSION,
                probe_id=PROBE,
                ticket=TICKET,
                fresh_firmware=fresh,
                flash=workflow,
                handoff_begin=workflow,
                handoff_end=workflow,
            )
        )
        assert result.ok is False
        assert result.code == "AUTHORIZATION_REQUIRED"
        assert result.operation == OPERATIONS[action]
        assert result.details["field"] == "confirmation"
        assert result.details["rule"] == "authorize"
        assert result.details["operation"] == OPERATIONS[action]
        assert result.details["task"] == action

    assert fresh_calls == []
    assert workflow_calls == []


def test_cli_generated_task_without_authorize_is_refused_before_admission(
    tmp_path, monkeypatch, capsys
):
    root, identity = _valid_project(tmp_path)
    data_root = _data_root(tmp_path)
    fresh_calls = []

    def fresh(_root: Path) -> object:
        fresh_calls.append(_root)
        return SimpleNamespace(identity=identity)

    monkeypatch.setattr(ide_mod, "_FRESH_FIRMWARE", fresh)
    monkeypatch.setattr(ide_mod, "_FLASH", _forbidden_workflow)

    # Omitted --confirmation is the generated default deny.
    argv = _generated_argv(root, data_root, "flash", confirmation=None)
    assert "--confirmation" in argv
    assert "deny" in argv
    assert cli_main(argv) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["code"] == "AUTHORIZATION_REQUIRED"
    assert payload["details"]["operation"] == "stm32_flash"
    assert payload["details"]["task"] == "flash"
    assert fresh_calls == []


def test_omitted_confirmation_option_is_deny_at_the_parser(
    tmp_path, monkeypatch, capsys
):
    root, identity = _valid_project(tmp_path)
    fresh_calls = []

    def fresh(_root: Path) -> object:
        fresh_calls.append(_root)
        return SimpleNamespace(identity=identity)

    monkeypatch.setattr(ide_mod, "_FRESH_FIRMWARE", fresh)
    monkeypatch.setattr(ide_mod, "_FLASH", _forbidden_workflow)

    argv = [
        "--project-root",
        str(root),
        "ide",
        "task",
        "flash",
        "--data-root",
        str(_data_root(tmp_path)),
        "--session-id",
        SESSION,
        "--probe",
        PROBE,
        "--json",
    ]
    assert "--confirmation" not in argv
    assert cli_main(argv) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["code"] == "AUTHORIZATION_REQUIRED"
    assert payload["details"]["field"] == "confirmation"
    assert payload["details"]["rule"] == "authorize"
    assert fresh_calls == []


@pytest.mark.parametrize(
    ("first", "second"), [("deny", "authorize"), ("authorize", "deny")]
)
def test_repeated_confirmation_is_rejected_by_the_parser(
    tmp_path, monkeypatch, capsys, first, second
):
    root, _identity = _valid_project(tmp_path)

    def fresh(_root: Path) -> object:
        raise AssertionError("parser rejection must precede admission")

    monkeypatch.setattr(ide_mod, "_FRESH_FIRMWARE", fresh)

    argv = [
        "--project-root",
        str(root),
        "ide",
        "task",
        "flash",
        "--data-root",
        str(_data_root(tmp_path)),
        "--session-id",
        SESSION,
        "--probe",
        PROBE,
        "--confirmation",
        first,
        "--confirmation",
        second,
        "--json",
    ]
    assert cli_main(argv) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "stm32-toolkit: invalid arguments" in captured.err


@pytest.mark.parametrize(
    "confirmation", [True, False, "AUTHORIZE", " authorize", "yes", 1, [], {}]
)
def test_confirmation_must_be_the_exact_literal(tmp_path, confirmation):
    root, _identity = _valid_project(tmp_path)
    result = asyncio.run(
        run_ide_task(
            "handoff-end",
            project_root=root,
            data_root=_data_root(tmp_path),
            session_id=SESSION,
            probe_id=PROBE,
            ticket=TICKET,
            confirmation=confirmation,
            handoff_end=_forbidden_workflow,
        )
    )
    assert result.ok is False
    assert result.code == "HARDWARE_INPUT_INVALID"
    assert result.details["field"] == "confirmation"
    assert result.details["rule"] == "value"


# ---------------------------------------------------------------------------
# evidence admission and preservation
# ---------------------------------------------------------------------------


def _stale(root: Path) -> None:
    elf = root / "build" / "arm-debug" / "firmware.elf"
    elf.write_bytes(elf.read_bytes() + b"\x00")


def _failed(root: Path) -> None:
    path = root / "artifacts" / "migration" / "build-result.json"
    payload = json.loads(path.read_text("utf-8"))
    payload["status"] = "failed"
    path.write_text(json.dumps(payload), encoding="utf-8")


def _malformed(root: Path) -> None:
    (root / "build" / "arm-debug" / "firmware-identity.json").write_bytes(b"{")


@pytest.mark.parametrize(
    ("tamper", "code", "details"),
    [
        (_stale, "FIRMWARE_INPUT_CHANGED", {"field": "elfSha256", "rule": "current"}),
        (
            _failed,
            "FIRMWARE_BUILD_REQUIRED",
            {"path": "artifacts/migration/build-result.json", "rule": "status"},
        ),
        (
            _malformed,
            "FIRMWARE_EVIDENCE_INVALID",
            {"path": "build/arm-debug/firmware-identity.json", "rule": "json"},
        ),
    ],
)
def test_invalid_current_evidence_is_refused_before_workflow(
    tmp_path, tamper, code, details
):
    root, _identity = _valid_project(tmp_path)
    tamper(root)
    calls = []

    def workflow(_request: object) -> object:
        calls.append(_request)
        return OperationResult.success("stm32_flash", {})

    result = asyncio.run(
        run_ide_task(
            "flash",
            project_root=root,
            data_root=_data_root(tmp_path),
            session_id=SESSION,
            probe_id=PROBE,
            confirmation="authorize",
            flash=workflow,
        )
    )
    assert result.ok is False
    assert result.code == code
    assert dict(result.details) == details
    assert calls == []


def test_snapshot_provenance_is_refused_before_workflow(tmp_path, monkeypatch):
    root, _identity, _record = snapshot_build(tmp_path, monkeypatch)
    calls = []

    def workflow(_request: object) -> object:
        calls.append(_request)
        return OperationResult.success("stm32_flash", {})

    result = asyncio.run(
        run_ide_task(
            "flash",
            project_root=root,
            data_root=_data_root(tmp_path),
            session_id=SESSION,
            probe_id=PROBE,
            confirmation="authorize",
            flash=workflow,
        )
    )
    assert result.ok is False
    assert result.code == "FIRMWARE_PROVENANCE_UNSUPPORTED"
    assert result.details["field"] == "sourceBaseline"
    assert result.details["rule"] == "input-snapshot-v1"
    assert calls == []


def test_fresh_pins_are_forwarded_exactly_for_both_hardware_routes(tmp_path):
    root = prepare_project(tmp_path)
    identity = {"buildId": "1" * 64, "elfSha256": "2" * 64}

    for action in ("flash", "handoff-begin"):
        recorded = []

        async def workflow(request):
            recorded.append(request)
            return OperationResult.success(OPERATIONS[action], {})

        result = asyncio.run(
            run_ide_task(
                action,
                project_root=root,
                data_root=_data_root(tmp_path),
                session_id=SESSION,
                probe_id=PROBE,
                confirmation="authorize",
                fresh_firmware=_fresh(identity),
                flash=workflow,
                handoff_begin=workflow,
            )
        )
        assert result.ok is True
        request = recorded[0]
        assert request.expected_build_id == identity["buildId"]
        assert request.expected_elf_sha256 == identity["elfSha256"]
        assert request.authorized is True
        assert request.session_id == SESSION
        assert request.probe_id == PROBE


def test_handoff_end_survives_stale_source_evidence(tmp_path):
    root, _identity = _valid_project(tmp_path)
    (root / "build" / "arm-debug" / "firmware.elf").write_bytes(b"stale")
    recorded = []

    async def fake_end(request):
        recorded.append(request)
        return OperationResult.success("stm32_debug_handoff_end", {"ticket": TICKET})

    result = asyncio.run(
        run_ide_task(
            "handoff-end",
            project_root=root,
            data_root=_data_root(tmp_path),
            session_id=SESSION,
            probe_id=PROBE,
            ticket=TICKET,
            confirmation="authorize",
            fresh_firmware=_forbidden_workflow,  # type: ignore[arg-type]
            handoff_end=fake_end,
        )
    )
    assert result.ok is True
    assert recorded[0].ticket == TICKET


# ---------------------------------------------------------------------------
# context validation, public failures and result integrity
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("field", "kwargs", "rule"),
    [
        ("project_root", {"project_root": Path("relative")}, "absolute"),
        ("data_root", {"data_root": "not-a-path"}, "type"),
        ("data_root", {"data_root": Path("relative")}, "absolute"),
        ("session_id", {"session_id": "bad/session"}, "format"),
        ("probe_id", {"probe_id": "bad probe"}, "identifier"),
        ("ticket", {"ticket": "short"}, "digest"),
    ],
)
def test_context_is_validated_before_admission(tmp_path, field, kwargs, rule):
    root, _identity = _valid_project(tmp_path)
    base = {
        "project_root": root,
        "data_root": _data_root(tmp_path),
        "session_id": SESSION,
        "probe_id": PROBE,
        "ticket": TICKET,
        "confirmation": "authorize",
    }
    base.update(kwargs)
    fresh_calls = []

    def fresh(_root: Path) -> object:
        fresh_calls.append(_root)
        raise AssertionError("admission must not run for invalid context")

    result = asyncio.run(
        run_ide_task(
            "handoff-end" if field == "ticket" else "flash",
            fresh_firmware=fresh,
            flash=_forbidden_workflow,
            handoff_end=_forbidden_workflow,
            **base,
        )
    )
    assert result.ok is False
    assert result.code == "HARDWARE_INPUT_INVALID"
    assert result.details["field"] == field
    assert result.details["rule"] == rule
    assert fresh_calls == []


def _patch_reparse(monkeypatch, target: Path) -> None:
    import stm32_toolkit.hardware_workflows as hardware_mod

    real_lstat = os.lstat

    def fake_lstat(path):
        metadata = real_lstat(path)
        if Path(path) == target:
            return SimpleNamespace(
                st_mode=metadata.st_mode,
                st_file_attributes=(
                    getattr(metadata, "st_file_attributes", 0) | 0x400
                ),
            )
        return metadata

    monkeypatch.setattr(hardware_mod.os, "lstat", fake_lstat)


def _data_root_stub(term: str, **kwargs):
    return asyncio.run(
        run_ide_task(
            term,
            **kwargs,
            fresh_firmware=_forbidden_workflow,  # type: ignore[arg-type]
            flash=_forbidden_workflow,
            handoff_begin=_forbidden_workflow,
            handoff_end=_forbidden_workflow,
        )
    )


@pytest.mark.parametrize("term", ["flash", "handoff-begin", "handoff-end"])
def test_data_root_inside_project_is_refused_before_admission(tmp_path, term):
    root, _identity = _valid_project(tmp_path)
    result = _data_root_stub(
        term,
        project_root=root,
        data_root=root / "machine-data",
        session_id=SESSION,
        probe_id=PROBE,
        ticket=TICKET,
        confirmation="authorize",
    )
    assert result.code == "HARDWARE_INPUT_INVALID"
    assert result.details["field"] == "data_root"
    assert result.details["rule"] == "outsideProjectRoot"


def test_data_root_file_component_is_refused_before_admission(tmp_path):
    root, _identity = _valid_project(tmp_path)
    plain = tmp_path / "plain-file"
    plain.write_bytes(b"not a directory\n")
    result = _data_root_stub(
        "flash",
        project_root=root,
        data_root=plain / "data",
        session_id=SESSION,
        probe_id=PROBE,
        confirmation="authorize",
    )
    assert result.code == "HARDWARE_INPUT_INVALID"
    assert result.details["field"] == "data_root"
    assert result.details["rule"] == "externalDirectory"
    assert result.details["guidance"]


def test_data_root_redirected_leaf_is_refused_before_admission(tmp_path, monkeypatch):
    root, _identity = _valid_project(tmp_path)
    data_root = _data_root(tmp_path)
    _patch_reparse(monkeypatch, data_root)
    result = _data_root_stub(
        "flash",
        project_root=root,
        data_root=data_root,
        session_id=SESSION,
        probe_id=PROBE,
        confirmation="authorize",
    )
    assert result.code == "HARDWARE_INPUT_INVALID"
    assert result.details["field"] == "data_root"
    assert result.details["rule"] == "externalDirectory"


def test_data_root_redirected_ancestor_is_refused_before_admission(
    tmp_path, monkeypatch
):
    root, _identity = _valid_project(tmp_path)
    ancestor = tmp_path / "reparse-parent"
    ancestor.mkdir()
    data_root = ancestor / "data"
    _patch_reparse(monkeypatch, ancestor)
    result = _data_root_stub(
        "flash",
        project_root=root,
        data_root=data_root,
        session_id=SESSION,
        probe_id=PROBE,
        confirmation="authorize",
    )
    assert result.code == "HARDWARE_INPUT_INVALID"
    assert result.details["field"] == "data_root"
    assert result.details["rule"] == "externalDirectory"


def test_unknown_task_is_refused(tmp_path):
    result = asyncio.run(
        run_ide_task(
            "rebuild",
            project_root=tmp_path,
            data_root=_data_root(tmp_path),
            session_id=SESSION,
            probe_id=PROBE,
        )
    )
    assert result.code == "HARDWARE_INPUT_INVALID"
    assert result.details["field"] == "task"


def test_cli_failure_is_bounded_json_with_nonzero_exit(tmp_path, capsys):
    empty = tmp_path / "empty"
    empty.mkdir()
    data_root = _data_root(tmp_path)

    assert (
        cli_main(
            [
                "--project-root",
                str(empty),
                "ide",
                "task",
                "flash",
                "--data-root",
                str(data_root),
                "--session-id",
                SESSION,
                "--probe",
                PROBE,
                "--confirmation",
                "authorize",
                "--json",
            ]
        )
        == 2
    )
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["ok"] is False
    assert payload["operation"] == "stm32_flash"
    assert payload["code"] == "FIRMWARE_EVIDENCE_INVALID"
    assert payload["details"]
    assert str(empty) not in captured.out
    assert str(empty) not in captured.err


def test_forwarded_result_is_returned_intact(tmp_path):
    root, identity = _valid_project(tmp_path)
    failure = OperationResult.failure(
        "stm32_flash",
        "FLASH_IMAGE_INVALID",
        "Firmware image is invalid",
        {"path": "build/arm-debug/firmware.elf", "rule": "segments"},
    )

    async def fake_flash(_request):
        return failure

    result = asyncio.run(
        run_ide_task(
            "flash",
            project_root=root,
            data_root=_data_root(tmp_path),
            session_id=SESSION,
            probe_id=PROBE,
            confirmation="authorize",
            fresh_firmware=_fresh(identity),
            flash=fake_flash,
        )
    )
    assert result is failure
    assert result.to_dict()["details"] == {
        "path": "build/arm-debug/firmware.elf",
        "rule": "segments",
    }
