from __future__ import annotations

import shutil
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path
from types import SimpleNamespace

from stm32_toolkit.creation_apply import _seed_native_managed_manifest
from stm32_toolkit.cubemx_project import parse_native_project, write_native_project_manifests
from stm32_toolkit.generation.creation import CreationRequest
from stm32_toolkit.generation.managed_files import model_sha256_for
from stm32_toolkit.project_model import load_project_model
from stm32_toolkit.regeneration import RegenerationWorkflowRequest, plan_regeneration
from stm32_toolkit.regeneration_workflows import (
    RegenerationAuthorizationStore,
    apply_regeneration_workflow,
    prepare_regeneration_workflow,
)


FIXTURE = Path(__file__).parent / "fixtures" / "cubemx-6.18" / "native-f429"


def _environment() -> SimpleNamespace:
    return SimpleNamespace(
        digest="a" * 64,
        cubemx_version="6.18.1-RC2",
        cubemx_sha256="b" * 64,
        package_name="STM32Cube_FW_F4",
        package_version="1.28.3",
        package_sha256="c" * 64,
    )


def _project(tmp_path: Path) -> tuple[Path, Path, SimpleNamespace]:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    destination = workspace / "generated"
    shutil.copytree(FIXTURE, destination)
    environment = _environment()
    creation = CreationRequest.from_ioc("STM32F429ZITx.ioc", "generated", framework="hal", language="c")
    model = parse_native_project(destination, request=creation, plan_id="d" * 64, action_digest="e" * 64, environment=environment)
    write_native_project_manifests(destination, model)
    loaded = load_project_model(destination)
    _seed_native_managed_manifest(destination, model_sha256=model_sha256_for(loaded), inventory=model.files)
    (destination / "App").mkdir()
    (destination / "App" / "keep.txt").write_bytes(b"user bytes")
    (destination / "Tests").mkdir()
    (destination / "Tests" / "keep.txt").write_bytes(b"test bytes")
    subprocess.run(["git", "init", "-q"], cwd=workspace, check=True)
    subprocess.run(["git", "add", "-A"], cwd=workspace, check=True)
    subprocess.run(["git", "-c", "user.name=regen", "-c", "user.email=regen@example.com", "commit", "-q", "-m", "fixture"], cwd=workspace, check=True)
    return workspace, destination, environment


class _Adapter:
    def __init__(self, source: Path):
        self.source = source
        self.calls = 0

    def generate(self, capability, context):
        self.calls += 1
        child = context.staging_dir / capability.request.destination
        shutil.copytree(self.source, child)
        return SimpleNamespace(project_root=child)


class _ChangingAdapter(_Adapter):
    def __init__(self, source: Path, *, mutate: bool = False, derived: bool = False):
        super().__init__(source)
        self.mutate = mutate
        self.derived = derived

    def generate(self, capability, context):
        result = super().generate(capability, context)
        child = result.project_root
        if self.mutate:
            target = child / "Core" / "Src" / "main.c"
            target.write_bytes(target.read_bytes() + b"\n/* changed on replay */\n")
        if self.derived:
            stale = child / "build" / "stale.txt"
            stale.parent.mkdir(parents=True)
            stale.write_bytes(b"stale")
        return result


def _validator(candidate, *, request, plan_id, action_digest, environment):
    return parse_native_project(candidate, request=request, plan_id=plan_id, action_digest=action_digest, environment=environment)


def test_prepare_issues_preview_bound_single_use_capability(tmp_path: Path):
    workspace, destination, environment = _project(tmp_path)
    request = RegenerationWorkflowRequest(workspace, tmp_path / "data", "session", "generated")
    planned = plan_regeneration(request, environment=environment)
    assert planned.ok is True
    assert planned.data["blockers"] == ()
    adapter = _Adapter(FIXTURE)
    prepared = prepare_regeneration_workflow(
        request,
        plan_id=planned.data["planId"],
        action_digest=planned.data["actionDigest"],
        authorized=True,
        environment=environment,
        adapter=adapter,
        validate_native=_validator,
    )
    assert prepared.ok is True
    assert adapter.calls == 1
    assert prepared.data["previewDigest"]
    assert not list(workspace.glob(".stm32tk-regeneration-preview-*"))

    applied = apply_regeneration_workflow(
        request,
        authorization_digest=prepared.data["authorizationDigest"],
        authorized=True,
        environment=environment,
        adapter=_Adapter(FIXTURE),
        validate_native=_validator,
        configure=lambda root: __import__("stm32_toolkit.result", fromlist=["OperationResult"]).OperationResult.success("configure", {}),
        build=lambda root, preset: __import__("stm32_toolkit.result", fromlist=["OperationResult"]).OperationResult.success("build", {"preset": preset}),
    )
    assert applied.ok is True
    assert (destination / "App" / "keep.txt").read_bytes() == b"user bytes"
    assert (destination / "Tests" / "keep.txt").read_bytes() == b"test bytes"

    replay = apply_regeneration_workflow(
        request,
        authorization_digest=prepared.data["authorizationDigest"],
        authorized=True,
        environment=environment,
        adapter=_Adapter(FIXTURE),
        validate_native=_validator,
    )
    assert replay.code == "REGENERATION_AUTHORIZATION_CONSUMED"


def test_prepare_requires_json_boolean_true_without_cube_mx_call(tmp_path: Path):
    workspace, _, environment = _project(tmp_path)
    request = RegenerationWorkflowRequest(workspace, tmp_path / "data", "session", "generated")
    planned = plan_regeneration(request, environment=environment)
    adapter = _Adapter(FIXTURE)
    result = prepare_regeneration_workflow(
        request,
        plan_id=planned.data["planId"],
        action_digest=planned.data["actionDigest"],
        authorized=1,
        environment=environment,
        adapter=adapter,
        validate_native=_validator,
    )
    assert result.code == "REGENERATION_AUTHORIZATION_REQUIRED"
    assert adapter.calls == 0


def test_apply_rejects_user_drift_after_prepare_without_second_generation(tmp_path: Path):
    workspace, destination, environment = _project(tmp_path)
    request = RegenerationWorkflowRequest(workspace, tmp_path / "data", "session", "generated")
    planned = plan_regeneration(request, environment=environment)
    adapter = _Adapter(FIXTURE)
    prepared = prepare_regeneration_workflow(
        request,
        plan_id=planned.data["planId"],
        action_digest=planned.data["actionDigest"],
        authorized=True,
        environment=environment,
        adapter=adapter,
        validate_native=_validator,
    )
    assert prepared.ok is True
    (destination / "App" / "keep.txt").write_bytes(b"drift")
    replay_adapter = _Adapter(FIXTURE)
    result = apply_regeneration_workflow(
        request,
        authorization_digest=prepared.data["authorizationDigest"],
        authorized=True,
        environment=environment,
        adapter=replay_adapter,
        validate_native=_validator,
    )
    assert result.code == "REGENERATION_USER_DRIFT"
    assert replay_adapter.calls == 0


def test_apply_rejects_changed_replay_preview_and_discards_derived_output(tmp_path: Path):
    workspace, destination, environment = _project(tmp_path)
    request = RegenerationWorkflowRequest(workspace, tmp_path / "data", "session", "generated")
    planned = plan_regeneration(request, environment=environment)
    prepared = prepare_regeneration_workflow(
        request,
        plan_id=planned.data["planId"],
        action_digest=planned.data["actionDigest"],
        authorized=True,
        environment=environment,
        adapter=_ChangingAdapter(FIXTURE, derived=True),
        validate_native=_validator,
    )
    assert prepared.ok is True
    changed = _ChangingAdapter(FIXTURE, mutate=True, derived=True)
    result = apply_regeneration_workflow(
        request,
        authorization_digest=prepared.data["authorizationDigest"],
        authorized=True,
        environment=environment,
        adapter=changed,
        validate_native=_validator,
    )
    assert result.code == "REGENERATION_PREVIEW_CHANGED"
    assert changed.calls == 1
    assert not (destination / "build" / "stale.txt").exists()
    assert (destination / "App" / "keep.txt").read_bytes() == b"user bytes"


def test_authorization_expiry_is_typed_and_single_use(tmp_path: Path):
    workspace, _, environment = _project(tmp_path)
    request = RegenerationWorkflowRequest(workspace, tmp_path / "data", "session", "generated")
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    planned = __import__("stm32_toolkit.regeneration", fromlist=["build_regeneration_plan"]).build_regeneration_plan(request, environment=environment, now=now)
    prepared = prepare_regeneration_workflow(
        request,
        plan_id=planned.plan_id,
        action_digest=planned.action_digest,
        authorized=True,
        environment=environment,
        adapter=_Adapter(FIXTURE),
        validate_native=_validator,
        now=now,
    )
    assert prepared.ok is True
    result = apply_regeneration_workflow(
        request,
        authorization_digest=prepared.data["authorizationDigest"],
        authorized=True,
        environment=environment,
        adapter=_Adapter(FIXTURE),
        validate_native=_validator,
        now=now + timedelta(hours=2),
    )
    assert result.code == "REGENERATION_AUTHORIZATION_EXPIRED"
