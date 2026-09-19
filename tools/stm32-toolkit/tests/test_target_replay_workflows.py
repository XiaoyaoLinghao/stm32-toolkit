"""Contract tests for the public Target replay workflow."""

from __future__ import annotations

from collections.abc import Mapping
from hashlib import sha256
import json
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest

import stm32_toolkit.testing_workflows as workflows
from stm32_toolkit.testing.replay import canonical_replay_json_bytes, calculate_replay_id
from stm32_toolkit.testing.target import TargetFrameDecoder, encode_frame
from test_build_runner import prepare_project


FIXTURES = Path(__file__).parent / "fixtures" / "vs03" / "target"
PROJECT_ID = UUID("123e4567-e89b-42d3-a456-426614174000")
_TARGET_ONLY_OVERRIDES = {
    "schemaVersion": 3,
    "testing": {
        "target": {
            "executable": "build/arm-debug/firmware.elf",
            "timeout_seconds": 10,
            "transport": {
                "kind": "memory-mailbox",
                "options": {"address": 0x20000000, "size": 4096},
            },
        }
    },
}


def _context(tmp_path: Path) -> workflows.TestingWorkflowContext:
    project_root = tmp_path / "project"
    project_root.mkdir()
    return workflows.TestingWorkflowContext(
        project_root=project_root,
        data_root=tmp_path / "data",
        session_id="replay-session",
    )


def _install_model(monkeypatch: pytest.MonkeyPatch, context: workflows.TestingWorkflowContext) -> None:
    model = SimpleNamespace(
        schema_version=3,
        logical_project_id=PROJECT_ID,
        testing=SimpleNamespace(host=None, target=object()),
    )
    monkeypatch.setattr(workflows, "_load_project_model", lambda _root: model)


def _real_context(tmp_path: Path, *, session_id: str) -> workflows.TestingWorkflowContext:
    project = prepare_project(
        tmp_path,
        overrides=_TARGET_ONLY_OVERRIDES,
        git_repo=False,
    )
    return workflows.TestingWorkflowContext(
        project_root=project,
        data_root=tmp_path / "data",
        session_id=session_id,
    )


def _json_containers(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _json_containers(member) for key, member in value.items()}
    if isinstance(value, tuple):
        return [_json_containers(member) for member in value]
    return value


def _contradictory_inventory_fixture(tmp_path: Path) -> tuple[Path, Path]:
    descriptor = json.loads(
        (FIXTURES / "failed-before.json").read_text(encoding="utf-8")
    )
    stream = bytes.fromhex(
        (FIXTURES / "failed-before.hex").read_text(encoding="ascii")
    )
    decoder = TargetFrameDecoder()
    frames = decoder.feed(stream)
    decoder.finish()
    first = frames[0]
    inventory = _json_containers(first.payload)
    assert isinstance(inventory, dict)
    identity = inventory["identity"]
    assert isinstance(identity, dict)
    identity["git_commit"] = "c" * 40
    inventory["identity"] = identity
    changed_stream = encode_frame(
        first.kind,
        first.sequence,
        inventory,
        version=first.version,
    ) + b"".join(frame.raw_bytes for frame in frames[1:])
    descriptor["stream"]["size_bytes"] = len(changed_stream)
    descriptor["stream"]["sha256"] = sha256(changed_stream).hexdigest()
    descriptor["replay_id"] = calculate_replay_id(descriptor)
    descriptor_path = tmp_path / "contradictory.json"
    descriptor_path.write_bytes(canonical_replay_json_bytes(descriptor))
    stream_path = tmp_path / "contradictory.hex"
    stream_path.write_text(changed_stream.hex(), encoding="ascii")
    return descriptor_path, stream_path


def test_target_replay_workflow_exposes_the_public_entrypoint():
    assert callable(getattr(workflows, "target_replay_run", None))


def test_target_replay_run_preserves_origin_and_import_identity_and_reloads(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    context = _context(tmp_path)
    _install_model(monkeypatch, context)

    def fail_if_physical_runner_is_constructed(**_kwargs: object):
        pytest.fail("Target replay must not construct a physical runner")

    monkeypatch.setattr(workflows, "_host_runner_factory", fail_if_physical_runner_is_constructed)
    result = workflows.target_replay_run(
        context,
        "vs03-failed-before",
        FIXTURES / "failed-before.json",
        FIXTURES / "failed-before.hex",
    )

    assert result.ok is True
    data = result.to_dict()["data"]
    assert data["run"]["run_id"] == "vs03-failed-before"
    assert data["run"]["identity"]["workspace_id"] != data["import_workspace_id"]
    assert data["execution_source"] == "replay"
    assert data["physical_transport_evidence"] is False
    shown = workflows.test_show(context, run_id="vs03-failed-before")
    assert shown.ok is True
    assert shown.to_dict()["data"] == {**data, "authoritative": True}

    retry = workflows.target_replay_run(
        workflows.TestingWorkflowContext(
            context.project_root, context.data_root, context.session_id
        ),
        "vs03-failed-before",
        FIXTURES / "failed-before.json",
        FIXTURES / "failed-before.hex",
    )
    assert retry.ok is True
    assert retry.to_dict()["data"] == data


def test_target_replay_run_binds_operation_id_to_frozen_run_and_fails_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    context = _context(tmp_path)
    _install_model(monkeypatch, context)
    result = workflows.target_replay_run(
        context,
        "wrong-operation-id",
        FIXTURES / "failed-before.json",
        FIXTURES / "failed-before.hex",
    )

    assert result.ok is False
    assert result.code == "TEST_PROTOCOL_INVALID"
    workspace = workflows.WorkspacePaths.from_roots(
        context.data_root, context.project_root, PROJECT_ID, context.session_id
    )
    assert not any((workspace.workspace_root / "evidence").rglob("*.json"))


@pytest.mark.parametrize(
    ("operation_id", "name", "state"),
    (("vs03-failed-before", "failed-before", "failed"), ("vs03-fixed-after", "fixed-after", "passed")),
)
def test_target_replay_run_executes_both_frozen_terminal_outcomes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    operation_id: str,
    name: str,
    state: str,
):
    context = _context(tmp_path)
    _install_model(monkeypatch, context)
    result = workflows.target_replay_run(
        context,
        operation_id,
        FIXTURES / f"{name}.json",
        FIXTURES / f"{name}.hex",
    )
    assert result.ok is True
    assert result.to_dict()["data"]["run"]["state"] == state


def test_target_replay_rejects_invalid_operation_id_before_loading_fixture(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    root = tmp_path_factory.mktemp("r")
    context = _real_context(root, session_id="replay-invalid-id")
    result = workflows.target_replay_run(
        context,
        "invalid/id",
        FIXTURES / "failed-before.json",
        FIXTURES / "failed-before.hex",
    )

    assert result.to_dict() == {
        "protocol": "stm32-toolkit/1",
        "ok": False,
        "operation": "test.target.replay",
        "code": "TEST_PROTOCOL_INVALID",
        "message": "Test protocol is invalid.",
        "data": None,
        "details": {},
    }
    assert not context.data_root.exists()


def test_target_replay_rejects_public_inventory_identity_contradiction(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    root = tmp_path_factory.mktemp("r")
    context = _real_context(root, session_id="replay-identity")
    descriptor_path, stream_path = _contradictory_inventory_fixture(root)
    result = workflows.target_replay_run(
        context,
        "vs03-failed-before",
        descriptor_path,
        stream_path,
    )

    assert result.to_dict() == {
        "protocol": "stm32-toolkit/1",
        "ok": False,
        "operation": "test.target.replay",
        "code": "TEST_PROTOCOL_INVALID",
        "message": "Test protocol is invalid.",
        "data": None,
        "details": {},
    }
    assert not any(path.is_file() for path in context.data_root.rglob("*"))
    assert not any(
        path.name in {"target-replay-input", "test-events"}
        for path in context.data_root.rglob("*")
    )
