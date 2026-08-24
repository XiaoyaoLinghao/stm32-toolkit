from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from stm32_toolkit import regeneration_workflows
from stm32_toolkit.creation_apply import _seed_native_managed_manifest
from stm32_toolkit.cubemx_project import parse_native_project, write_native_project_manifests
from stm32_toolkit.generation.creation import CreationRequest
from stm32_toolkit.generation.managed_files import model_sha256_for, sha256_hex
from stm32_toolkit.project_model import load_project_model
from stm32_toolkit.regeneration import RegenerationWorkflowRequest, plan_regeneration
from stm32_toolkit.result import OperationResult
from stm32_toolkit.regeneration_workflows import (
    RegenerationAuthorizationStore,
    RegenerationAuthorizationError,
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


class _CollisionValidator:
    """Return a non-native model after adding a CubeMX-owned user collision."""

    def __call__(self, candidate, *, request, plan_id, action_digest, environment):
        parsed = parse_native_project(candidate, request=request, plan_id=plan_id, action_digest=action_digest, environment=environment)
        write_native_project_manifests(candidate, parsed)
        loaded = load_project_model(candidate)
        _seed_native_managed_manifest(candidate, model_sha256=model_sha256_for(loaded), inventory=parsed.files)
        collision = b"cubemx bytes"
        path = candidate / "App" / "keep.txt"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(collision)
        manifest = candidate / ".stm32-toolkit" / "cubemx-ownership.json"
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        payload["files"] = [row for row in payload["files"] if row["path"] != "App/keep.txt"]
        payload["files"].append({"path": "App/keep.txt", "size": len(collision), "sha256": sha256_hex(collision)})
        manifest.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")), encoding="utf-8")
        return SimpleNamespace(model=SimpleNamespace())


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


@pytest.mark.parametrize("mutation_phase", ("configure", "debug"))
@pytest.mark.parametrize("root_name", ("App", "Tests"))
def test_apply_rejects_user_mutation_after_configure_or_build(
    tmp_path: Path,
    mutation_phase: str,
    root_name: str,
):
    workspace, destination, environment = _project(tmp_path)
    request = RegenerationWorkflowRequest(workspace, tmp_path / "data", "session", "generated")
    planned = plan_regeneration(request, environment=environment)
    prepared = prepare_regeneration_workflow(
        request,
        plan_id=planned.data["planId"],
        action_digest=planned.data["actionDigest"],
        authorized=True,
        environment=environment,
        adapter=_Adapter(FIXTURE),
        validate_native=_validator,
    )
    assert prepared.ok is True

    def configure(root: Path) -> OperationResult[dict[str, object]]:
        if mutation_phase == "configure":
            (root / root_name / "keep.txt").write_bytes(b"corrupted by configure")
        return OperationResult.success("configure", {})

    def build(root: Path, preset: str) -> OperationResult[dict[str, object]]:
        if mutation_phase == "debug" and preset == "arm-debug":
            (root / root_name / "keep.txt").write_bytes(b"corrupted by build")
        return OperationResult.success("build", {"preset": preset})

    result = apply_regeneration_workflow(
        request,
        authorization_digest=prepared.data["authorizationDigest"],
        authorized=True,
        environment=environment,
        adapter=_Adapter(FIXTURE),
        validate_native=_validator,
        configure=configure,
        build=build,
    )
    assert result.code == "REGENERATION_USER_DRIFT"
    assert (destination / "App" / "keep.txt").read_bytes() == b"user bytes"
    assert (destination / "Tests" / "keep.txt").read_bytes() == b"test bytes"
    with pytest.raises(RegenerationAuthorizationError) as consumed:
        RegenerationAuthorizationStore(tmp_path / "data").peek(prepared.data["authorizationDigest"])
    assert consumed.value.code == "REGENERATION_AUTHORIZATION_CONSUMED"


@pytest.mark.parametrize(
    ("relative", "expected"),
    (("CMakeLists.txt", "REGENERATION_TOOLKIT_DRIFT"), ("Core/Src/main.c", "REGENERATION_STATE_CHANGED")),
)
def test_snapshot_drift_respects_toolkit_precedence(tmp_path: Path, relative: str, expected: str):
    workspace, destination, environment = _project(tmp_path)
    target = destination.joinpath(*relative.split("/"))
    target.write_bytes(target.read_bytes() + b"\n/* drift */\n")
    request = RegenerationWorkflowRequest(workspace, tmp_path / "data", "session", "generated")
    planned = plan_regeneration(request, environment=environment)
    assert planned.code == "OK"
    assert tuple(item["code"] for item in planned.data["blockers"]) == (expected,)


def test_snapshot_missing_toolkit_file_has_only_toolkit_blocker(tmp_path: Path):
    workspace, destination, environment = _project(tmp_path)
    (destination / "CMakeLists.txt").unlink()
    request = RegenerationWorkflowRequest(workspace, tmp_path / "data", "session", "generated")
    planned = plan_regeneration(request, environment=environment)
    assert planned.code == "OK"
    assert tuple(item["code"] for item in planned.data["blockers"]) == ("REGENERATION_TOOLKIT_DRIFT",)
    assert tuple(item["path"] for item in planned.data["blockers"]) == ("CMakeLists.txt",)


def test_prepare_rejects_candidate_ownership_collision_before_authorization(tmp_path: Path):
    workspace, destination, environment = _project(tmp_path)
    request = RegenerationWorkflowRequest(workspace, tmp_path / "data", "session", "generated")
    planned = plan_regeneration(request, environment=environment)
    result = prepare_regeneration_workflow(
        request,
        plan_id=planned.data["planId"],
        action_digest=planned.data["actionDigest"],
        authorized=True,
        environment=environment,
        adapter=_Adapter(FIXTURE),
        validate_native=_CollisionValidator(),
    )
    assert result.code == "REGENERATION_STATE_CHANGED"
    assert (destination / "App" / "keep.txt").read_bytes() == b"user bytes"
    assert not list(workspace.glob(".stm32tk-regeneration-preview-*"))
    auth_root = tmp_path / "data" / "regeneration" / "authorizations"
    if auth_root.exists():
        assert not list(auth_root.glob("*.json"))


def test_authorization_record_tamper_is_rejected_by_peek_and_consume(tmp_path: Path):
    workspace, _, environment = _project(tmp_path)
    request = RegenerationWorkflowRequest(workspace, tmp_path / "data", "session", "generated")
    planned = plan_regeneration(request, environment=environment)
    prepared = prepare_regeneration_workflow(
        request,
        plan_id=planned.data["planId"],
        action_digest=planned.data["actionDigest"],
        authorized=True,
        environment=environment,
        adapter=_Adapter(FIXTURE),
        validate_native=_validator,
    )
    digest = prepared.data["authorizationDigest"]
    store = RegenerationAuthorizationStore(tmp_path / "data")
    record = store.authorization_root / f"{digest}.json"
    payload = json.loads(record.read_text(encoding="utf-8"))
    payload["planId"] = "f" * 64
    record.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    with pytest.raises(RegenerationAuthorizationError) as peek_error:
        store.peek(digest)
    assert peek_error.value.code == "REGENERATION_AUTHORIZATION_INVALID"
    with pytest.raises(RegenerationAuthorizationError) as consume_error:
        store.consume(digest, authorized=True)
    assert consume_error.value.code == "REGENERATION_AUTHORIZATION_INVALID"


def test_authorization_record_read_rejects_open_identity_change(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    workspace, _, environment = _project(tmp_path)
    request = RegenerationWorkflowRequest(workspace, tmp_path / "data", "session", "generated")
    planned = plan_regeneration(request, environment=environment)
    prepared = prepare_regeneration_workflow(
        request,
        plan_id=planned.data["planId"],
        action_digest=planned.data["actionDigest"],
        authorized=True,
        environment=environment,
        adapter=_Adapter(FIXTURE),
        validate_native=_validator,
    )
    digest = prepared.data["authorizationDigest"]
    store = RegenerationAuthorizationStore(tmp_path / "data")
    record = store.authorization_root / f"{digest}.json"
    replacement = tmp_path / "replacement-auth.json"
    replacement.write_bytes(record.read_bytes())
    real_open = regeneration_workflows.os.open

    def open_replacement(path, flags, *args, **kwargs):
        if Path(path) == record:
            return real_open(replacement, flags, *args, **kwargs)
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(regeneration_workflows.os, "open", open_replacement)
    with pytest.raises(RegenerationAuthorizationError) as caught:
        store.peek(digest)
    assert caught.value.code == "REGENERATION_AUTHORIZATION_INVALID"


def test_activation_rollback_preserves_old_tree_and_leaves_no_backup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    destination = tmp_path / "generated"
    staging = tmp_path / "staging"
    destination.mkdir()
    staging.mkdir()
    (destination / "keep.txt").write_bytes(b"old")
    (staging / "keep.txt").write_bytes(b"new")
    real_replace = regeneration_workflows.os.replace
    calls = 0

    def fail_activation(source, target):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected activation failure")
        return real_replace(source, target)

    monkeypatch.setattr(regeneration_workflows.os, "replace", fail_activation)
    with pytest.raises(regeneration_workflows.RegenerationError) as caught:
        regeneration_workflows._activation_replace(staging, destination, "attempt")
    assert caught.value.code == "REGENERATION_ACTIVATION_FAILED"
    assert (destination / "keep.txt").read_bytes() == b"old"
    assert (staging / "keep.txt").read_bytes() == b"new"
    assert not (tmp_path / ".generated.regen-backup-attempt").exists()


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
