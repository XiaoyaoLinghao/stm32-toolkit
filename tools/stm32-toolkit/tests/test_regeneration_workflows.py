from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from dataclasses import replace
from datetime import datetime, timezone, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from stm32_toolkit import regeneration_workflows
from stm32_toolkit.creation_apply import _seed_native_managed_manifest
from stm32_toolkit.cubemx_project import parse_native_project, write_native_project_manifests
from stm32_toolkit.generation.creation import CreationRequest
from stm32_toolkit.generation.managed_files import canonical_json_bytes, model_sha256_for, sha256_hex
from stm32_toolkit.project_model import load_project_model
from stm32_toolkit.regeneration import (
    MAX_FILE_BYTES,
    MAX_TOTAL_BYTES,
    RegenerationWorkflowRequest,
    build_regeneration_plan,
    build_regeneration_preview,
    classify_regeneration_project,
    plan_regeneration,
)
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


def _tree_bytes(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _root_state(root: Path) -> tuple[bool, dict[str, bytes]]:
    return (root.exists(), _tree_bytes(root) if root.exists() else {})


def _synchronize_managed_model_hash(destination: Path) -> None:
    model = load_project_model(destination)
    manifest = destination / ".stm32-toolkit" / "generated-files.json"
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["projectManifestSha256"] = model_sha256_for(model)
    manifest.write_bytes(canonical_json_bytes(payload))


def _write_streamed_bytes(path: Path, size: int, byte: bytes = b"x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    block = byte * min(1024 * 1024, size)
    remaining = size
    with path.open("wb") as handle:
        while remaining:
            count = min(len(block), remaining)
            handle.write(block[:count])
            remaining -= count


def _streamed_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _public_authorization_digest(payload: dict[str, object]) -> str:
    canonical = {key: value for key, value in payload.items() if key not in {"authorizationDigest", "state"}}
    canonical["state"] = "prepared"
    return sha256_hex(canonical_json_bytes(canonical))


def _rewrite_authorization_record(
    store: RegenerationAuthorizationStore,
    digest: str,
    mutate,
) -> tuple[str, Path, bytes]:
    old_path = store.authorization_root / f"{digest}.json"
    payload = json.loads(old_path.read_bytes().decode("utf-8"))
    mutate(payload)
    new_digest = _public_authorization_digest(payload)
    payload["authorizationDigest"] = new_digest
    serialized = canonical_json_bytes(payload)
    new_path = store.authorization_root / f"{new_digest}.json"
    old_path.unlink()
    new_path.write_bytes(serialized)
    return new_digest, new_path, serialized


def _valid_plan_and_preview(tmp_path: Path, *, now: datetime | None = None):
    workspace, _, environment = _project(tmp_path)
    request = RegenerationWorkflowRequest(workspace, tmp_path / "data", "session", "generated")
    plan = build_regeneration_plan(request, environment=environment, now=now)
    assert plan.blockers == ()
    snapshot = classify_regeneration_project(request)
    return plan, build_regeneration_preview(snapshot, snapshot)


@pytest.mark.parametrize(
    ("root_field", "root_value", "expected_message"),
    [
        pytest.param(
            "generatedDirectories",
            ["Core"],
            "generated ownership roots are not the closed Core/Drivers set",
            id="S5-F",
        ),
        pytest.param(
            "userDirectories",
            ["App"],
            "user ownership roots are not the closed App/Tests set",
            id="S5-G",
        ),
    ],
)
def test_plan_rejects_non_closed_ownership_roots(
    tmp_path: Path,
    root_field: str,
    root_value: list[str],
    expected_message: str,
):
    workspace, destination, environment = _project(tmp_path)
    project_manifest = destination / ".stm32-project.json"
    payload = json.loads(project_manifest.read_text(encoding="utf-8"))
    payload["generation"][root_field] = root_value
    project_manifest.write_bytes(canonical_json_bytes(payload))
    _synchronize_managed_model_hash(destination)
    request = RegenerationWorkflowRequest(workspace, tmp_path / "data", "session", "generated")
    before_project = _root_state(destination)
    before_data = _root_state(tmp_path / "data")

    result = plan_regeneration(request, environment=environment)

    assert result.ok is False
    assert result.operation == "project-regenerate-plan"
    assert result.code == "REGENERATION_PROJECT_INVALID"
    assert result.message == expected_message
    assert result.details == {}
    assert _root_state(destination) == before_project
    assert _root_state(tmp_path / "data") == before_data


def test_prepare_stops_on_missing_cubemx_file_before_adapter(tmp_path: Path):
    workspace, destination, environment = _project(tmp_path)
    (destination / "Core" / "Src" / "main.c").unlink()
    request = RegenerationWorkflowRequest(workspace, tmp_path / "data", "session", "generated")
    before_project = _root_state(destination)
    before_data = _root_state(tmp_path / "data")
    planned = plan_regeneration(request, environment=environment)
    assert planned.code == "OK"
    assert any(
        item["code"] == "REGENERATION_STATE_CHANGED" and item["path"] == "Core/Src/main.c"
        for item in planned.data["blockers"]
    )
    adapter = _Adapter(FIXTURE)

    result = prepare_regeneration_workflow(
        request,
        plan_id=planned.data["planId"],
        action_digest=planned.data["actionDigest"],
        authorized=True,
        environment=environment,
        adapter=adapter,
        validate_native=_validator,
    )

    assert result.code == "REGENERATION_STATE_CHANGED"
    assert result.message == "regeneration prerequisites are unavailable"
    assert adapter.calls == 0
    assert _root_state(destination) == before_project
    assert _root_state(tmp_path / "data") == before_data
    assert not list(workspace.glob(".stm32tk-regeneration-preview-*"))


def test_prepare_stops_on_user_root_regular_file_before_adapter(tmp_path: Path):
    workspace, destination, environment = _project(tmp_path)
    shutil.rmtree(destination / "App")
    (destination / "App").write_bytes(b"user root file")
    request = RegenerationWorkflowRequest(workspace, tmp_path / "data", "session", "generated")
    before_project = _root_state(destination)
    before_data = _root_state(tmp_path / "data")
    planned = plan_regeneration(request, environment=environment)
    assert planned.code == "OK"
    assert any(
        item["code"] == "REGENERATION_PATH_UNSAFE" and item["path"] == "App"
        for item in planned.data["blockers"]
    )
    adapter = _Adapter(FIXTURE)

    result = prepare_regeneration_workflow(
        request,
        plan_id=planned.data["planId"],
        action_digest=planned.data["actionDigest"],
        authorized=True,
        environment=environment,
        adapter=adapter,
        validate_native=_validator,
    )

    assert result.code == "REGENERATION_PATH_UNSAFE"
    assert result.message == "regeneration prerequisites are unavailable"
    assert adapter.calls == 0
    assert _root_state(destination) == before_project
    assert _root_state(tmp_path / "data") == before_data
    assert not list(workspace.glob(".stm32tk-regeneration-preview-*"))


def test_authorization_store_rejects_relative_data_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(RegenerationAuthorizationError) as caught:
        RegenerationAuthorizationStore(Path("relative-data-root"))

    assert caught.value.code == "REGENERATION_AUTHORIZATION_INVALID"
    assert caught.value.message == "authorization data root is invalid"
    assert not (tmp_path / "relative-data-root").exists()


def test_authorization_store_rejects_non_plan_with_valid_preview(tmp_path: Path):
    _, preview = _valid_plan_and_preview(tmp_path)
    store = RegenerationAuthorizationStore(tmp_path / "data")

    with pytest.raises(RegenerationAuthorizationError) as caught:
        store.prepare(plan=object(), preview=preview)

    assert caught.value.code == "REGENERATION_AUTHORIZATION_INVALID"
    assert caught.value.message == "authorization payload is invalid"
    assert not store.data_root.exists()


def test_authorization_store_rejects_publicly_replaced_plan_id(tmp_path: Path):
    plan, preview = _valid_plan_and_preview(tmp_path)
    bad_plan = replace(plan, plan_id="bad")
    store = RegenerationAuthorizationStore(plan.request.data_root)

    with pytest.raises(RegenerationAuthorizationError) as caught:
        store.prepare(plan=bad_plan, preview=preview)

    assert caught.value.code == "REGENERATION_AUTHORIZATION_INVALID"
    assert caught.value.message == "authorization digest is invalid"
    assert not store.data_root.exists()


def test_authorization_store_rejects_plan_expiring_at_injected_now(tmp_path: Path):
    fixed_now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    plan, preview = _valid_plan_and_preview(tmp_path, now=fixed_now)
    expiry = datetime.strptime(plan.expires_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    store = RegenerationAuthorizationStore(plan.request.data_root, now=lambda: expiry)

    with pytest.raises(RegenerationAuthorizationError) as caught:
        store.prepare(plan=plan, preview=preview)

    assert caught.value.code == "REGENERATION_AUTHORIZATION_EXPIRED"
    assert caught.value.message == "authorization has expired"
    assert not store.data_root.exists()


def test_authorization_store_rejects_oversized_nonce_before_record_write(tmp_path: Path):
    plan, preview = _valid_plan_and_preview(tmp_path)
    store = RegenerationAuthorizationStore(plan.request.data_root, nonce_factory=lambda: "n" * (64 * 1024))

    with pytest.raises(RegenerationAuthorizationError) as caught:
        store.prepare(plan=plan, preview=preview)

    assert caught.value.code == "REGENERATION_AUTHORIZATION_INVALID"
    assert caught.value.message == "authorization record is oversized"
    assert not store.data_root.exists()


def test_authorization_store_rejects_invalid_digest_in_peek_and_consume(tmp_path: Path):
    store = RegenerationAuthorizationStore(tmp_path / "data")

    with pytest.raises(RegenerationAuthorizationError) as peek_error:
        store.peek("bad")
    with pytest.raises(RegenerationAuthorizationError) as consume_error:
        store.consume("bad", authorized=True)

    assert peek_error.value.code == "REGENERATION_AUTHORIZATION_INVALID"
    assert peek_error.value.message == "authorization digest is invalid"
    assert consume_error.value.code == "REGENERATION_AUTHORIZATION_INVALID"
    assert consume_error.value.message == "authorization digest is invalid"
    assert not store.data_root.exists()


def test_authorization_store_preserves_raw_duplicate_record_on_peek_and_consume(tmp_path: Path):
    plan, preview = _valid_plan_and_preview(tmp_path)
    store = RegenerationAuthorizationStore(plan.request.data_root)
    authorization = store.prepare(plan=plan, preview=preview)
    record_path = authorization.record_path
    original = record_path.read_bytes().rstrip()
    malformed = original[:-1] + b',"nonce":"duplicate"}'
    record_path.write_bytes(malformed)
    before = _tree_bytes(store.authorization_root)

    with pytest.raises(RegenerationAuthorizationError) as peek_error:
        store.peek(authorization.authorization_digest)
    with pytest.raises(RegenerationAuthorizationError) as consume_error:
        store.consume(authorization.authorization_digest, authorized=True)

    assert peek_error.value.code == "REGENERATION_AUTHORIZATION_INVALID"
    assert peek_error.value.message == "authorization record is malformed"
    assert consume_error.value.code == "REGENERATION_AUTHORIZATION_INVALID"
    assert consume_error.value.message == "authorization record is malformed"
    assert _tree_bytes(store.authorization_root) == before
    assert record_path.read_bytes() == malformed


@pytest.mark.parametrize(
    "case_id",
    [
        pytest.param("S7-H", id="S7-H"),
        pytest.param("S7-I", id="S7-I"),
        pytest.param("S7-J", id="S7-J"),
        pytest.param("S7-K", id="S7-K"),
        pytest.param("S7-L", id="S7-L"),
    ],
)
def test_authorization_store_rejects_rebound_public_record_fields(tmp_path: Path, case_id: str):
    plan, preview = _valid_plan_and_preview(tmp_path)
    store = RegenerationAuthorizationStore(plan.request.data_root)
    authorization = store.prepare(plan=plan, preview=preview)
    other_root: Path | None = None
    if case_id == "S7-H":
        new_digest, _, _ = _rewrite_authorization_record(
            store,
            authorization.authorization_digest,
            lambda payload: payload.update(state="invalid"),
        )
    elif case_id == "S7-I":
        new_digest, _, _ = _rewrite_authorization_record(
            store,
            authorization.authorization_digest,
            lambda payload: payload.update(currentIocSha256="bad"),
        )
    elif case_id == "S7-J":
        new_digest, _, _ = _rewrite_authorization_record(
            store,
            authorization.authorization_digest,
            lambda payload: payload.update(destination=7),
        )
    elif case_id == "S7-K":
        new_digest, _, _ = _rewrite_authorization_record(
            store,
            authorization.authorization_digest,
            lambda payload: payload.update(workspaceRoot="relative"),
        )
    elif case_id == "S7-L":
        other_root = tmp_path / "other-data"
        other_root.mkdir()
        new_digest, _, _ = _rewrite_authorization_record(
            store,
            authorization.authorization_digest,
            lambda payload: payload.update(dataRoot=other_root.resolve().as_posix()),
        )
    else:
        raise AssertionError(f"unknown S7 case: {case_id}")
    before = _tree_bytes(store.authorization_root)

    with pytest.raises(RegenerationAuthorizationError) as caught:
        store.peek(new_digest)

    assert caught.value.code == "REGENERATION_AUTHORIZATION_INVALID"
    assert caught.value.message == "authorization record is malformed"
    assert _tree_bytes(store.authorization_root) == before
    if other_root is not None:
        assert _tree_bytes(other_root) == {}


def test_authorization_store_rejects_non_boolean_consume_without_state_change(tmp_path: Path):
    plan, preview = _valid_plan_and_preview(tmp_path)
    store = RegenerationAuthorizationStore(plan.request.data_root)
    authorization = store.prepare(plan=plan, preview=preview)
    before = _tree_bytes(store.authorization_root)

    with pytest.raises(RegenerationAuthorizationError) as integer_error:
        store.consume(authorization.authorization_digest, authorized=1)
    with pytest.raises(RegenerationAuthorizationError) as false_error:
        store.consume(authorization.authorization_digest, authorized=False)

    assert integer_error.value.code == "REGENERATION_AUTHORIZATION_REQUIRED"
    assert integer_error.value.message == "authorization must be the JSON boolean true"
    assert false_error.value.code == "REGENERATION_AUTHORIZATION_REQUIRED"
    assert false_error.value.message == "authorization must be the JSON boolean true"
    assert _tree_bytes(store.authorization_root) == before
    assert store.peek(authorization.authorization_digest).authorization_digest == authorization.authorization_digest


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


@pytest.mark.parametrize("mutation", ("unsafe-path", "duplicate"))
def test_prepare_rejects_invalid_candidate_ownership_manifest_before_authorization(
    tmp_path: Path, mutation: str
):
    workspace, destination, environment = _project(tmp_path)
    request = RegenerationWorkflowRequest(workspace, tmp_path / "data", "session", "generated")
    planned = plan_regeneration(request, environment=environment)
    before = _tree_bytes(destination)

    def invalid_validator(candidate, *, request, plan_id, action_digest, environment):
        parsed = parse_native_project(
            candidate,
            request=request,
            plan_id=plan_id,
            action_digest=action_digest,
            environment=environment,
        )
        write_native_project_manifests(candidate, parsed)
        manifest = candidate / ".stm32-toolkit" / "cubemx-ownership.json"
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        if mutation == "unsafe-path":
            payload["files"][0]["path"] = "../escape"
        else:
            payload["files"].append(dict(payload["files"][0]))
        manifest.write_text(
            json.dumps(payload, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        return SimpleNamespace(model=SimpleNamespace())

    result = prepare_regeneration_workflow(
        request,
        plan_id=planned.data["planId"],
        action_digest=planned.data["actionDigest"],
        authorized=True,
        environment=environment,
        adapter=_Adapter(FIXTURE),
        validate_native=invalid_validator,
    )

    assert result.code == "REGENERATION_OWNERSHIP_INVALID"
    assert _tree_bytes(destination) == before
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


def test_apply_rejects_ioc_drift_after_prepare_without_cube_mx_call(tmp_path: Path):
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

    ioc = destination / "STM32F429ZITx.ioc"
    ioc.write_bytes(ioc.read_bytes() + b"\n# authorized state drift\n")
    before_apply = _tree_bytes(destination)
    replay_adapter = _Adapter(FIXTURE)
    result = apply_regeneration_workflow(
        request,
        authorization_digest=prepared.data["authorizationDigest"],
        authorized=True,
        environment=environment,
        adapter=replay_adapter,
        validate_native=_validator,
    )

    assert result.code == "REGENERATION_STATE_CHANGED"
    assert replay_adapter.calls == 0
    assert _tree_bytes(destination) == before_apply
    assert not list(workspace.glob(".stm32tk-regeneration-*"))
    with pytest.raises(RegenerationAuthorizationError) as consumed:
        RegenerationAuthorizationStore(tmp_path / "data").peek(prepared.data["authorizationDigest"])
    assert consumed.value.code == "REGENERATION_AUTHORIZATION_CONSUMED"


def test_apply_rejects_execution_environment_drift_before_generation(tmp_path: Path):
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
    before_apply = _tree_bytes(destination)
    drifted = SimpleNamespace(**{**vars(environment), "digest": "d" * 64})
    replay_adapter = _Adapter(FIXTURE)
    result = apply_regeneration_workflow(
        request,
        authorization_digest=prepared.data["authorizationDigest"],
        authorized=True,
        environment=drifted,
        adapter=replay_adapter,
        validate_native=_validator,
    )
    assert result.code == "REGENERATION_GENERATOR_DRIFT"
    assert replay_adapter.calls == 0
    assert _tree_bytes(destination) == before_apply
    assert not list(workspace.glob(".stm32tk-regeneration-*"))
    with pytest.raises(RegenerationAuthorizationError) as consumed:
        RegenerationAuthorizationStore(tmp_path / "data").peek(prepared.data["authorizationDigest"])
    assert consumed.value.code == "REGENERATION_AUTHORIZATION_CONSUMED"


def test_apply_rejects_authorization_bound_destination_before_generation(tmp_path: Path):
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
    before_apply = _tree_bytes(destination)
    mismatched_request = RegenerationWorkflowRequest(workspace, tmp_path / "data", "session", "other")
    replay_adapter = _Adapter(FIXTURE)
    result = apply_regeneration_workflow(
        mismatched_request,
        authorization_digest=prepared.data["authorizationDigest"],
        authorized=True,
        environment=environment,
        adapter=replay_adapter,
        validate_native=_validator,
    )
    assert result.code == "REGENERATION_AUTHORIZATION_INVALID"
    assert replay_adapter.calls == 0
    assert _tree_bytes(destination) == before_apply
    assert not list(workspace.glob(".stm32tk-regeneration-*"))
    with pytest.raises(RegenerationAuthorizationError) as consumed:
        RegenerationAuthorizationStore(tmp_path / "data").peek(prepared.data["authorizationDigest"])
    assert consumed.value.code == "REGENERATION_AUTHORIZATION_CONSUMED"


def test_prepare_rejects_candidate_target_drift_before_authorization(tmp_path: Path):
    workspace, destination, environment = _project(tmp_path)
    candidate_source = tmp_path / "candidate-source"
    shutil.copytree(FIXTURE, candidate_source)
    candidate_ioc = candidate_source / "STM32F429ZITx.ioc"
    candidate_ioc.write_bytes(
        candidate_ioc.read_bytes().replace(
            b"Mcu.Name=STM32F429ZITx", b"Mcu.Name=STM32F407VGTx"
        )
    )
    before_prepare = _tree_bytes(destination)
    request = RegenerationWorkflowRequest(workspace, tmp_path / "data", "session", "generated")
    planned = plan_regeneration(request, environment=environment)
    candidate_adapter = _Adapter(candidate_source)
    result = prepare_regeneration_workflow(
        request,
        plan_id=planned.data["planId"],
        action_digest=planned.data["actionDigest"],
        authorized=True,
        environment=environment,
        adapter=candidate_adapter,
        validate_native=_validator,
    )

    assert result.code == "REGENERATION_PREVIEW_FAILED"
    assert candidate_adapter.calls == 1
    assert _tree_bytes(destination) == before_prepare
    assert not list(workspace.glob(".stm32tk-regeneration-*"))
    auth_root = tmp_path / "data" / "regeneration" / "authorizations"
    if auth_root.exists():
        assert not list(auth_root.glob("*.json"))


def test_prepare_rejects_candidate_linker_identity_drift_before_authorization(tmp_path: Path):
    workspace, destination, environment = _project(tmp_path)
    candidate_source = tmp_path / "candidate-source"
    shutil.copytree(FIXTURE, candidate_source)

    class LinkerChangingAdapter(_Adapter):
        def generate(self, capability, context):
            result = super().generate(capability, context)
            child = result.project_root
            original = child / "STM32F429xx_FLASH.ld"
            alternate = child / "alternate.ld"
            shutil.copy2(original, alternate)
            toolchain = child / "cmake" / "gcc-arm-none-eabi.cmake"
            toolchain.write_bytes(
                toolchain.read_bytes().replace(
                    b"STM32F429xx_FLASH.ld", b"alternate.ld"
                )
            )
            return result

    request = RegenerationWorkflowRequest(workspace, tmp_path / "data", "session", "generated")
    planned = plan_regeneration(request, environment=environment)
    before_prepare = _tree_bytes(destination)
    result = prepare_regeneration_workflow(
        request,
        plan_id=planned.data["planId"],
        action_digest=planned.data["actionDigest"],
        authorized=True,
        environment=environment,
        adapter=LinkerChangingAdapter(candidate_source),
        validate_native=_validator,
    )

    assert result.code == "REGENERATION_PREVIEW_FAILED"
    assert _tree_bytes(destination) == before_prepare
    assert not list(workspace.glob(".stm32tk-regeneration-preview-*"))
    auth_root = tmp_path / "data" / "regeneration" / "authorizations"
    if auth_root.exists():
        assert not list(auth_root.glob("*.json"))


def test_prepare_rejects_candidate_without_declared_ioc_identity(tmp_path: Path):
    workspace, destination, environment = _project(tmp_path)
    request = RegenerationWorkflowRequest(workspace, tmp_path / "data", "session", "generated")
    planned = plan_regeneration(request, environment=environment)
    before_prepare = _tree_bytes(destination)

    def invalid_validator(candidate, *, request, plan_id, action_digest, environment):
        parsed = parse_native_project(
            candidate,
            request=request,
            plan_id=plan_id,
            action_digest=action_digest,
            environment=environment,
        )
        write_native_project_manifests(candidate, parsed)
        manifest = candidate / ".stm32-toolkit" / "cubemx-ownership.json"
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        payload["files"] = [row for row in payload["files"] if not str(row["path"]).casefold().endswith(".ioc")]
        manifest.write_text(
            json.dumps(payload, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        return SimpleNamespace(model=SimpleNamespace())

    result = prepare_regeneration_workflow(
        request,
        plan_id=planned.data["planId"],
        action_digest=planned.data["actionDigest"],
        authorized=True,
        environment=environment,
        adapter=_Adapter(FIXTURE),
        validate_native=invalid_validator,
    )

    assert result.code == "REGENERATION_OWNERSHIP_INVALID"
    assert _tree_bytes(destination) == before_prepare
    assert not list(workspace.glob(".stm32tk-regeneration-preview-*"))
    auth_root = tmp_path / "data" / "regeneration" / "authorizations"
    if auth_root.exists():
        assert not list(auth_root.glob("*.json"))


def test_apply_configuration_failure_preserves_destination(tmp_path: Path):
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
    before_apply = _tree_bytes(destination)
    configure_calls: list[Path] = []
    build_calls: list[str] = []

    def configure(root: Path) -> OperationResult[None]:
        configure_calls.append(root)
        return OperationResult.failure("project-configuration-apply", "CONFIGURATION_FAILED", "injected configuration failure", {})

    def build(root: Path, preset: str) -> OperationResult[dict[str, str]]:
        build_calls.append(preset)
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

    assert result.code == "REGENERATION_CONFIGURATION_FAILED"
    assert len(configure_calls) == 1
    assert build_calls == []
    assert _tree_bytes(destination) == before_apply
    assert not list(workspace.glob(".stm32tk-regeneration-*"))
    with pytest.raises(RegenerationAuthorizationError) as consumed:
        RegenerationAuthorizationStore(tmp_path / "data").peek(prepared.data["authorizationDigest"])
    assert consumed.value.code == "REGENERATION_AUTHORIZATION_CONSUMED"


@pytest.mark.parametrize(
    ("failed_preset", "expected_code"),
    [
        ("arm-debug", "REGENERATION_DEBUG_BUILD_FAILED"),
        ("arm-release", "REGENERATION_RELEASE_BUILD_FAILED"),
    ],
)
def test_apply_supported_build_failure_preserves_destination_and_settles_roots(
    tmp_path: Path, failed_preset: str, expected_code: str
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
    before_apply = _tree_bytes(destination)
    build_calls: list[str] = []

    def configure(root: Path) -> OperationResult[dict[str, object]]:
        return OperationResult.success("configure", {})

    def build(root: Path, preset: str) -> OperationResult[dict[str, object]]:
        build_calls.append(preset)
        if preset == failed_preset:
            return OperationResult.failure("build", "BUILD_FAILED", "injected provider failure", {"preset": preset})
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

    assert result.code == expected_code
    assert build_calls == (["arm-debug"] if failed_preset == "arm-debug" else ["arm-debug", "arm-release"])
    assert _tree_bytes(destination) == before_apply
    assert not list(workspace.glob(".stm32tk-regeneration-*"))
    assert not list(workspace.glob(".generated.regen-backup-*"))
    with pytest.raises(RegenerationAuthorizationError) as consumed:
        RegenerationAuthorizationStore(tmp_path / "data").peek(prepared.data["authorizationDigest"])
    assert consumed.value.code == "REGENERATION_AUTHORIZATION_CONSUMED"


def test_apply_activation_failure_restores_old_tree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
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
    before_apply = _tree_bytes(destination)
    configure_calls: list[Path] = []
    build_calls: list[str] = []
    real_replace = regeneration_workflows.os.replace
    failed_forward = False

    def fail_forward_activation(source: object, target: object) -> None:
        nonlocal failed_forward
        source_path = Path(source)
        target_path = Path(target)
        if (
            not failed_forward
            and target_path == destination
            and source_path.name.startswith(".stm32tk-regeneration-activation-")
        ):
            failed_forward = True
            raise OSError("injected forward activation failure")
        real_replace(source, target)

    def configure(root: Path) -> OperationResult[dict[str, object]]:
        configure_calls.append(root)
        return OperationResult.success("configure", {})

    def build(root: Path, preset: str) -> OperationResult[dict[str, str]]:
        build_calls.append(preset)
        return OperationResult.success("build", {"preset": preset})

    monkeypatch.setattr(regeneration_workflows.os, "replace", fail_forward_activation)
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

    assert result.code == "REGENERATION_ACTIVATION_FAILED"
    assert failed_forward is True
    assert len(configure_calls) == 1
    assert build_calls == ["arm-debug", "arm-release"]
    assert _tree_bytes(destination) == before_apply
    assert not list(workspace.glob(".stm32tk-regeneration-*"))
    assert not list(workspace.glob(".generated.regen-backup-*"))
    with pytest.raises(RegenerationAuthorizationError) as consumed:
        RegenerationAuthorizationStore(tmp_path / "data").peek(prepared.data["authorizationDigest"])
    assert consumed.value.code == "REGENERATION_AUTHORIZATION_CONSUMED"


def test_prepare_rejects_non_path_candidate_root_before_authorization(tmp_path: Path):
    workspace, destination, environment = _project(tmp_path)
    request = RegenerationWorkflowRequest(workspace, tmp_path / "data", "session", "generated")
    planned = plan_regeneration(request, environment=environment)
    before_project = _root_state(destination)
    before_data = _root_state(tmp_path / "data")

    class BadRootAdapter:
        calls = 0

        def generate(self, capability, context):
            self.calls += 1
            return SimpleNamespace(project_root="not-a-path")

    adapter = BadRootAdapter()
    result = prepare_regeneration_workflow(
        request,
        plan_id=planned.data["planId"],
        action_digest=planned.data["actionDigest"],
        authorized=True,
        environment=environment,
        adapter=adapter,
        validate_native=_validator,
    )

    assert result.ok is False
    assert result.operation == "project-regenerate-prepare"
    assert result.code == "REGENERATION_PREVIEW_FAILED"
    assert result.message == "CubeMX did not return a project root"
    assert result.details == {}
    assert adapter.calls == 1
    assert _root_state(destination) == before_project
    assert _root_state(tmp_path / "data") == before_data
    assert not list(workspace.glob(".stm32tk-regeneration-preview-*"))
    auth_root = tmp_path / "data" / "regeneration" / "authorizations"
    if auth_root.exists():
        assert not list(auth_root.glob("*.json"))


def test_prepare_rejects_regular_file_candidate_root_before_authorization(tmp_path: Path):
    workspace, destination, environment = _project(tmp_path)
    request = RegenerationWorkflowRequest(workspace, tmp_path / "data", "session", "generated")
    planned = plan_regeneration(request, environment=environment)
    before_project = _root_state(destination)

    class FileRootAdapter:
        calls = 0

        def generate(self, capability, context):
            self.calls += 1
            candidate = context.staging_dir / capability.request.destination
            candidate.write_bytes(b"candidate is not a directory")
            return SimpleNamespace(project_root=candidate)

    adapter = FileRootAdapter()
    result = prepare_regeneration_workflow(
        request,
        plan_id=planned.data["planId"],
        action_digest=planned.data["actionDigest"],
        authorized=True,
        environment=environment,
        adapter=adapter,
        validate_native=_validator,
    )

    assert result.ok is False
    assert result.code == "REGENERATION_PREVIEW_FAILED"
    assert result.message == "CubeMX output root is invalid"
    assert result.details == {}
    assert adapter.calls == 1
    assert _root_state(destination) == before_project
    assert not list(workspace.glob(".stm32tk-regeneration-preview-*"))
    auth_root = tmp_path / "data" / "regeneration" / "authorizations"
    if auth_root.exists():
        assert not list(auth_root.glob("*.json"))


@pytest.mark.parametrize(
    "variant",
    [
        pytest.param("wrong-name", id="S8-C-wrong-name"),
        pytest.param("extra-sibling", id="S8-C-extra-sibling"),
    ],
)
def test_prepare_rejects_ambiguous_candidate_root_before_authorization(
    tmp_path: Path, variant: str
):
    workspace, destination, environment = _project(tmp_path)
    request = RegenerationWorkflowRequest(workspace, tmp_path / "data", "session", "generated")
    planned = plan_regeneration(request, environment=environment)
    before_project = _root_state(destination)

    class AmbiguousAdapter(_Adapter):
        def generate(self, capability, context):
            self.calls += 1
            name = "other" if variant == "wrong-name" else capability.request.destination
            child = context.staging_dir / name
            shutil.copytree(self.source, child)
            if variant == "extra-sibling":
                shutil.copytree(self.source, context.staging_dir / "sibling")
            return SimpleNamespace(project_root=child)

    adapter = AmbiguousAdapter(FIXTURE)
    result = prepare_regeneration_workflow(
        request,
        plan_id=planned.data["planId"],
        action_digest=planned.data["actionDigest"],
        authorized=True,
        environment=environment,
        adapter=adapter,
        validate_native=_validator,
    )

    assert result.ok is False
    assert result.code == "REGENERATION_PREVIEW_FAILED"
    assert result.message == "CubeMX output root is invalid"
    assert result.details == {}
    assert adapter.calls == 1
    assert _root_state(destination) == before_project
    assert not list(workspace.glob(".stm32tk-regeneration-preview-*"))
    auth_root = tmp_path / "data" / "regeneration" / "authorizations"
    if auth_root.exists():
        assert not list(auth_root.glob("*.json"))


def test_prepare_apply_missing_user_root_is_skipped_and_activated(tmp_path: Path):
    workspace, destination, environment = _project(tmp_path)
    shutil.rmtree(destination / "App")
    request = RegenerationWorkflowRequest(workspace, tmp_path / "data", "session", "generated")
    planned = plan_regeneration(request, environment=environment)
    assert planned.data["blockers"] == ()
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
        return OperationResult.success("configure", {})

    def build(root: Path, preset: str) -> OperationResult[dict[str, object]]:
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

    assert result.ok is True
    assert result.data["mutated"] is True
    assert not (destination / "App").exists()
    assert (destination / "Tests" / "keep.txt").read_bytes() == b"test bytes"
    assert not list(workspace.glob(".stm32tk-regeneration-*"))
    assert not list(workspace.glob(".generated.regen-backup-*"))
    with pytest.raises(RegenerationAuthorizationError) as consumed:
        RegenerationAuthorizationStore(tmp_path / "data").peek(prepared.data["authorizationDigest"])
    assert consumed.value.code == "REGENERATION_AUTHORIZATION_CONSUMED"


def test_apply_rejects_staged_user_root_file_before_activation(tmp_path: Path):
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
    before_apply = _root_state(destination)

    def configure(root: Path) -> OperationResult[dict[str, object]]:
        shutil.rmtree(root / "App")
        (root / "App").write_bytes(b"staged user root file")
        return OperationResult.success("configure", {})

    build_calls: list[str] = []

    def build(root: Path, preset: str) -> OperationResult[dict[str, object]]:
        build_calls.append(preset)
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

    assert result.ok is False
    assert result.operation == "project-regenerate-apply"
    assert result.code == "REGENERATION_USER_DRIFT"
    assert result.message == "user ownership root is not a directory"
    assert result.details == {"root": "App"}
    assert build_calls == ["arm-debug", "arm-release"]
    assert _root_state(destination) == before_apply
    assert not list(workspace.glob(".stm32tk-regeneration-*"))
    with pytest.raises(RegenerationAuthorizationError) as consumed:
        RegenerationAuthorizationStore(tmp_path / "data").peek(prepared.data["authorizationDigest"])
    assert consumed.value.code == "REGENERATION_AUTHORIZATION_CONSUMED"


def test_prepare_apply_preserves_nested_user_directory_and_bytes(tmp_path: Path):
    workspace, destination, environment = _project(tmp_path)
    nested = destination / "App" / "sub" / "keep.txt"
    nested.parent.mkdir(parents=True)
    nested.write_bytes(b"nested user bytes")
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
        return OperationResult.success("configure", {})

    def build(root: Path, preset: str) -> OperationResult[dict[str, object]]:
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

    assert result.ok is True
    assert (destination / "App" / "keep.txt").read_bytes() == b"user bytes"
    assert (destination / "App" / "sub" / "keep.txt").read_bytes() == b"nested user bytes"
    assert (destination / "Tests" / "keep.txt").read_bytes() == b"test bytes"
    assert not list(workspace.glob(".stm32tk-regeneration-*"))
    assert not list(workspace.glob(".generated.regen-backup-*"))


def test_apply_rejects_staged_user_aggregate_size_limit_with_real_streamed_files(tmp_path: Path):
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
    before_apply = _root_state(destination)
    build_calls: list[str] = []
    adapter = _Adapter(FIXTURE)

    def configure(root: Path) -> OperationResult[dict[str, object]]:
        baseline_total = sum(path.stat().st_size for path in root.rglob("*") if path.is_file())
        baseline_files = sum(1 for path in root.rglob("*") if path.is_file())
        payload_bytes = 8 * MAX_FILE_BYTES + 1
        assert baseline_total + payload_bytes <= 300 * 1024 * 1024
        assert baseline_total + payload_bytes > MAX_TOTAL_BYTES
        assert baseline_files + 9 < 200_000
        paths = [root / "App" / f"aggregate-{index:02d}.bin" for index in range(8)]
        paths.append(root / "App" / "aggregate-overflow.bin")
        for path in paths[:-1]:
            _write_streamed_bytes(path, MAX_FILE_BYTES)
        _write_streamed_bytes(paths[-1], 1)
        block = b"x" * (1024 * 1024)
        full_digest = hashlib.sha256()
        for _ in range(MAX_FILE_BYTES // len(block)):
            full_digest.update(block)
        expected_full_digest = full_digest.hexdigest()
        streamed_facts = {
            path.name: (path.stat().st_size, _streamed_sha256(path)) for path in paths
        }
        assert all(
            streamed_facts[path.name] == (MAX_FILE_BYTES, expected_full_digest)
            for path in paths[:-1]
        )
        assert streamed_facts[paths[-1].name] == (1, hashlib.sha256(b"x").hexdigest())
        return OperationResult.success("configure", {})

    def build(root: Path, preset: str) -> OperationResult[dict[str, object]]:
        build_calls.append(preset)
        return OperationResult.success("build", {"preset": preset})

    result = apply_regeneration_workflow(
        request,
        authorization_digest=prepared.data["authorizationDigest"],
        authorized=True,
        environment=environment,
        adapter=adapter,
        validate_native=_validator,
        configure=configure,
        build=build,
    )

    assert result.ok is False
    assert result.code == "REGENERATION_PATH_UNSAFE"
    assert result.message == "user-owned aggregate size exceeds its bound"
    assert result.details == {}
    assert build_calls == ["arm-debug", "arm-release"]
    assert _root_state(destination) == before_apply
    assert not list(workspace.glob(".stm32tk-regeneration-*"))
    with pytest.raises(RegenerationAuthorizationError) as consumed:
        RegenerationAuthorizationStore(tmp_path / "data").peek(prepared.data["authorizationDigest"])
    assert consumed.value.code == "REGENERATION_AUTHORIZATION_CONSUMED"


def test_prepare_rejects_regular_derived_root_before_authorization(tmp_path: Path):
    workspace, destination, environment = _project(tmp_path)
    request = RegenerationWorkflowRequest(workspace, tmp_path / "data", "session", "generated")
    planned = plan_regeneration(request, environment=environment)
    before_project = _root_state(destination)

    class DerivedFileAdapter(_Adapter):
        def generate(self, capability, context):
            result = super().generate(capability, context)
            (result.project_root / "build").write_bytes(b"derived file")
            return result

    adapter = DerivedFileAdapter(FIXTURE)
    result = prepare_regeneration_workflow(
        request,
        plan_id=planned.data["planId"],
        action_digest=planned.data["actionDigest"],
        authorized=True,
        environment=environment,
        adapter=adapter,
        validate_native=_validator,
    )

    assert result.ok is False
    assert result.code == "REGENERATION_PATH_UNSAFE"
    assert result.message == "derived output root is unsafe"
    assert result.details == {}
    assert adapter.calls == 1
    assert _root_state(destination) == before_project
    assert not list(workspace.glob(".stm32tk-regeneration-preview-*"))
    auth_root = tmp_path / "data" / "regeneration" / "authorizations"
    if auth_root.exists():
        assert not list(auth_root.glob("*.json"))


def test_prepare_removes_candidate_lock_without_touching_destination_lock(tmp_path: Path):
    workspace, destination, environment = _project(tmp_path)
    destination_lock = destination / ".stm32-toolkit" / "build.lock"
    destination_lock.write_bytes(b"destination lock")
    before_project = _root_state(destination)
    request = RegenerationWorkflowRequest(workspace, tmp_path / "data", "session", "generated")
    planned = plan_regeneration(request, environment=environment)

    class LockAdapter(_Adapter):
        def generate(self, capability, context):
            result = super().generate(capability, context)
            lock = result.project_root / ".stm32-toolkit" / "build.lock"
            lock.parent.mkdir(parents=True, exist_ok=True)
            lock.write_bytes(b"candidate lock")
            return result

    prepared = prepare_regeneration_workflow(
        request,
        plan_id=planned.data["planId"],
        action_digest=planned.data["actionDigest"],
        authorized=True,
        environment=environment,
        adapter=LockAdapter(FIXTURE),
        validate_native=_validator,
    )

    assert prepared.ok is True
    assert destination_lock.read_bytes() == b"destination lock"
    assert _root_state(destination) == before_project
    assert not list(workspace.glob(".stm32tk-regeneration-preview-*"))


def test_prepare_rejects_missing_candidate_metadata_before_authorization(tmp_path: Path):
    workspace, destination, environment = _project(tmp_path)
    request = RegenerationWorkflowRequest(workspace, tmp_path / "data", "session", "generated")
    planned = plan_regeneration(request, environment=environment)
    before_project = _root_state(destination)
    adapter = _Adapter(FIXTURE)

    result = prepare_regeneration_workflow(
        request,
        plan_id=planned.data["planId"],
        action_digest=planned.data["actionDigest"],
        authorized=True,
        environment=environment,
        adapter=adapter,
        validate_native=lambda **kwargs: SimpleNamespace(),
    )

    assert result.ok is False
    assert result.code == "REGENERATION_PREVIEW_FAILED"
    assert result.message == "CubeMX candidate metadata is unavailable"
    assert result.details == {}
    assert adapter.calls == 1
    assert _root_state(destination) == before_project
    assert not list(workspace.glob(".stm32tk-regeneration-preview-*"))
    auth_root = tmp_path / "data" / "regeneration" / "authorizations"
    if auth_root.exists():
        assert not list(auth_root.glob("*.json"))


@pytest.mark.parametrize(
    ("identity", "expected_message"),
    [
        pytest.param("framework", "CubeMX candidate framework differs from the project", id="S8-L"),
        pytest.param("language", "CubeMX candidate language differs from the project", id="S8-M"),
    ],
)
def test_prepare_rejects_candidate_framework_or_language_drift(
    tmp_path: Path, identity: str, expected_message: str
):
    workspace, destination, environment = _project(tmp_path)
    request = RegenerationWorkflowRequest(workspace, tmp_path / "data", "session", "generated")
    planned = plan_regeneration(request, environment=environment)
    before_project = _root_state(destination)
    adapter = _Adapter(FIXTURE)

    def alternate_validator(candidate, *, request, plan_id, action_digest, environment):
        ioc = candidate / request.source.value
        ioc_text = ioc.read_text(encoding="utf-8")
        if identity == "framework":
            ioc_text += "\nProjectManager.FrameworkMarker=LL_USART\n"
        else:
            ioc_text = ioc_text.replace("ProjectManager.Language=C", "ProjectManager.Language=C++")
        ioc.write_text(ioc_text, encoding="utf-8")
        alternate = CreationRequest.from_ioc(
            request.source.value,
            request.destination,
            framework="ll" if identity == "framework" else request.framework,
            language="cpp" if identity == "language" else request.language,
        )
        return parse_native_project(
            candidate,
            request=alternate,
            plan_id=plan_id,
            action_digest=action_digest,
            environment=environment,
        )

    result = prepare_regeneration_workflow(
        request,
        plan_id=planned.data["planId"],
        action_digest=planned.data["actionDigest"],
        authorized=True,
        environment=environment,
        adapter=adapter,
        validate_native=alternate_validator,
    )

    assert result.ok is False
    assert result.code == "REGENERATION_PREVIEW_FAILED"
    assert result.message == expected_message
    assert result.details == {}
    assert adapter.calls == 1
    assert _root_state(destination) == before_project
    assert not list(workspace.glob(".stm32tk-regeneration-preview-*"))
    auth_root = tmp_path / "data" / "regeneration" / "authorizations"
    if auth_root.exists():
        assert not list(auth_root.glob("*.json"))


def test_prepare_uses_built_in_parser_and_copies_user_roots(tmp_path: Path):
    workspace, destination, environment = _project(tmp_path)
    request = RegenerationWorkflowRequest(workspace, tmp_path / "data", "session", "generated")
    planned = plan_regeneration(request, environment=environment)
    before_project = _root_state(destination)
    adapter = _Adapter(FIXTURE)

    prepared = prepare_regeneration_workflow(
        request,
        plan_id=planned.data["planId"],
        action_digest=planned.data["actionDigest"],
        authorized=True,
        environment=environment,
        adapter=adapter,
    )

    assert prepared.ok is True
    assert adapter.calls == 1
    assert _root_state(destination) == before_project
    assert not list(workspace.glob(".stm32tk-regeneration-preview-*"))
    assert prepared.data["authorizationDigest"]
    auth_root = tmp_path / "data" / "regeneration" / "authorizations"
    assert len(list(auth_root.glob("*.json"))) == 1


def test_prepare_maps_generic_adapter_exception_and_cleans_roots(tmp_path: Path):
    workspace, destination, environment = _project(tmp_path)
    request = RegenerationWorkflowRequest(workspace, tmp_path / "data", "session", "generated")
    planned = plan_regeneration(request, environment=environment)
    before_project = _root_state(destination)

    class RaisingAdapter:
        calls = 0

        def generate(self, capability, context):
            self.calls += 1
            raise RuntimeError("adapter failure")

    adapter = RaisingAdapter()
    result = prepare_regeneration_workflow(
        request,
        plan_id=planned.data["planId"],
        action_digest=planned.data["actionDigest"],
        authorized=True,
        environment=environment,
        adapter=adapter,
        validate_native=_validator,
    )

    assert result.ok is False
    assert result.code == "REGENERATION_PREVIEW_FAILED"
    assert result.message == "CubeMX preview failed"
    assert result.details == {}
    assert adapter.calls == 1
    assert _root_state(destination) == before_project
    assert not list(workspace.glob(".stm32tk-regeneration-preview-*"))
    auth_root = tmp_path / "data" / "regeneration" / "authorizations"
    if auth_root.exists():
        assert not list(auth_root.glob("*.json"))


@pytest.mark.parametrize(
    "binding",
    [
        pytest.param("planId", id="S9-A-plan"),
        pytest.param("actionDigest", id="S9-A-action"),
    ],
)
def test_prepare_rejects_mismatched_plan_binding_before_adapter(tmp_path: Path, binding: str):
    workspace, destination, environment = _project(tmp_path)
    request = RegenerationWorkflowRequest(workspace, tmp_path / "data", "session", "generated")
    planned = plan_regeneration(request, environment=environment)
    before_project = _root_state(destination)
    before_data = _root_state(tmp_path / "data")
    adapter = _Adapter(FIXTURE)
    supplied_plan_id = "f" * 64 if binding == "planId" else planned.data["planId"]
    supplied_action_digest = "f" * 64 if binding == "actionDigest" else planned.data["actionDigest"]

    result = prepare_regeneration_workflow(
        request,
        plan_id=supplied_plan_id,
        action_digest=supplied_action_digest,
        authorized=True,
        environment=environment,
        adapter=adapter,
        validate_native=_validator,
    )

    assert result.ok is False
    assert result.operation == "project-regenerate-prepare"
    assert result.code == "REGENERATION_PLAN_CHANGED"
    assert result.message == "the regeneration plan changed since planning"
    assert result.details == {
        "currentPlanId": planned.data["planId"],
        "currentActionDigest": planned.data["actionDigest"],
    }
    assert adapter.calls == 0
    assert _root_state(destination) == before_project
    assert _root_state(tmp_path / "data") == before_data
    assert not list(workspace.glob(".stm32tk-regeneration-preview-*"))


def test_prepare_maps_oversized_public_authorization_record_and_cleans_roots(tmp_path: Path):
    workspace, destination, environment = _project(tmp_path)
    request = RegenerationWorkflowRequest(workspace, tmp_path / "data", "session", "generated")
    planned = plan_regeneration(request, environment=environment)
    before_project = _root_state(destination)
    before_data = _root_state(tmp_path / "data")
    store = RegenerationAuthorizationStore(
        tmp_path / "data", nonce_factory=lambda: "n" * (64 * 1024 + 1)
    )
    adapter = _Adapter(FIXTURE)

    result = prepare_regeneration_workflow(
        request,
        plan_id=planned.data["planId"],
        action_digest=planned.data["actionDigest"],
        authorized=True,
        environment=environment,
        store=store,
        adapter=adapter,
        validate_native=_validator,
    )

    assert result.ok is False
    assert result.operation == "project-regenerate-prepare"
    assert result.code == "REGENERATION_AUTHORIZATION_INVALID"
    assert result.message == "authorization record is oversized"
    assert result.details == {}
    assert adapter.calls == 1
    assert _root_state(destination) == before_project
    assert _root_state(tmp_path / "data") == before_data
    assert not list(workspace.glob(".stm32tk-regeneration-preview-*"))
    if store.authorization_root.exists():
        assert not list(store.authorization_root.glob("*.json"))


@pytest.mark.parametrize("authorized", [False, 1], ids=["S10-A-false", "S10-A-integer"])
def test_apply_requires_json_true_before_consuming_authorization(
    tmp_path: Path, authorized: object
):
    workspace, destination, environment = _project(tmp_path)
    request = RegenerationWorkflowRequest(workspace, tmp_path / "data", "session", "generated")
    planned = plan_regeneration(request, environment=environment)
    store = RegenerationAuthorizationStore(tmp_path / "data")
    prepared = prepare_regeneration_workflow(
        request,
        plan_id=planned.data["planId"],
        action_digest=planned.data["actionDigest"],
        authorized=True,
        environment=environment,
        store=store,
        adapter=_Adapter(FIXTURE),
        validate_native=_validator,
    )
    assert prepared.ok is True
    before_project = _root_state(destination)
    before_auth = _tree_bytes(store.authorization_root)
    adapter = _Adapter(FIXTURE)

    result = apply_regeneration_workflow(
        request,
        authorization_digest=prepared.data["authorizationDigest"],
        authorized=authorized,
        environment=environment,
        store=store,
        adapter=adapter,
        validate_native=_validator,
    )

    assert result.ok is False
    assert result.operation == "project-regenerate-apply"
    assert result.code == "REGENERATION_AUTHORIZATION_REQUIRED"
    assert result.message == "authorization must be the JSON boolean true"
    assert result.details == {}
    assert adapter.calls == 0
    assert _root_state(destination) == before_project
    assert _tree_bytes(store.authorization_root) == before_auth
    assert not list(workspace.glob(".stm32tk-regeneration-*"))
    assert store.peek(prepared.data["authorizationDigest"]).authorization_digest == prepared.data["authorizationDigest"]


def test_apply_rejects_persisted_ownership_binding_after_consuming_authorization(tmp_path: Path):
    workspace, destination, environment = _project(tmp_path)
    request = RegenerationWorkflowRequest(workspace, tmp_path / "data", "session", "generated")
    planned = plan_regeneration(request, environment=environment)
    store = RegenerationAuthorizationStore(tmp_path / "data")
    prepared = prepare_regeneration_workflow(
        request,
        plan_id=planned.data["planId"],
        action_digest=planned.data["actionDigest"],
        authorized=True,
        environment=environment,
        store=store,
        adapter=_Adapter(FIXTURE),
        validate_native=_validator,
    )
    assert prepared.ok is True
    digest, _, _ = _rewrite_authorization_record(
        store,
        prepared.data["authorizationDigest"],
        lambda payload: payload.update(ownershipManifestDigest="f" * 64),
    )
    before_apply = _root_state(destination)
    adapter = _Adapter(FIXTURE)

    result = apply_regeneration_workflow(
        request,
        authorization_digest=digest,
        authorized=True,
        environment=environment,
        store=store,
        adapter=adapter,
        validate_native=_validator,
    )

    assert result.ok is False
    assert result.operation == "project-regenerate-apply"
    assert result.code == "REGENERATION_STATE_CHANGED"
    assert result.message == "the authorized ownership manifest changed"
    assert result.details == {}
    assert adapter.calls == 0
    assert _root_state(destination) == before_apply
    assert not list(workspace.glob(".stm32tk-regeneration-*"))
    with pytest.raises(RegenerationAuthorizationError) as consumed:
        store.peek(digest)
    assert consumed.value.code == "REGENERATION_AUTHORIZATION_CONSUMED"


def test_apply_rejects_persisted_managed_manifest_drift_after_consuming_authorization(
    tmp_path: Path,
):
    workspace, destination, environment = _project(tmp_path)
    request = RegenerationWorkflowRequest(workspace, tmp_path / "data", "session", "generated")
    planned = plan_regeneration(request, environment=environment)
    store = RegenerationAuthorizationStore(tmp_path / "data")
    prepared = prepare_regeneration_workflow(
        request,
        plan_id=planned.data["planId"],
        action_digest=planned.data["actionDigest"],
        authorized=True,
        environment=environment,
        store=store,
        adapter=_Adapter(FIXTURE),
        validate_native=_validator,
    )
    assert prepared.ok is True
    managed = destination / ".stm32-toolkit" / "generated-files.json"
    payload = json.loads(managed.read_text(encoding="utf-8"))
    assert payload["files"]
    payload["files"][0]["sha256"] = "f" * 64
    managed.write_bytes(canonical_json_bytes(payload))
    before_apply = _root_state(destination)
    adapter = _Adapter(FIXTURE)

    result = apply_regeneration_workflow(
        request,
        authorization_digest=prepared.data["authorizationDigest"],
        authorized=True,
        environment=environment,
        store=store,
        adapter=adapter,
        validate_native=_validator,
    )

    assert result.ok is False
    assert result.operation == "project-regenerate-apply"
    assert result.code == "REGENERATION_TOOLKIT_DRIFT"
    assert result.message == "the authorized Toolkit manifest changed"
    assert result.details == {}
    assert adapter.calls == 0
    assert _root_state(destination) == before_apply
    assert not list(workspace.glob(".stm32tk-regeneration-*"))
    with pytest.raises(RegenerationAuthorizationError) as consumed:
        store.peek(prepared.data["authorizationDigest"])
    assert consumed.value.code == "REGENERATION_AUTHORIZATION_CONSUMED"


def test_apply_rejects_persisted_plan_binding_after_consuming_authorization(tmp_path: Path):
    workspace, destination, environment = _project(tmp_path)
    request = RegenerationWorkflowRequest(workspace, tmp_path / "data", "session", "generated")
    planned = plan_regeneration(request, environment=environment)
    store = RegenerationAuthorizationStore(tmp_path / "data")
    prepared = prepare_regeneration_workflow(
        request,
        plan_id=planned.data["planId"],
        action_digest=planned.data["actionDigest"],
        authorized=True,
        environment=environment,
        store=store,
        adapter=_Adapter(FIXTURE),
        validate_native=_validator,
    )
    assert prepared.ok is True
    digest, _, _ = _rewrite_authorization_record(
        store,
        prepared.data["authorizationDigest"],
        lambda payload: payload.update(planId="f" * 64, actionDigest="e" * 64),
    )
    before_apply = _root_state(destination)
    adapter = _Adapter(FIXTURE)

    result = apply_regeneration_workflow(
        request,
        authorization_digest=digest,
        authorized=True,
        environment=environment,
        store=store,
        adapter=adapter,
        validate_native=_validator,
    )

    assert result.ok is False
    assert result.operation == "project-regenerate-apply"
    assert result.code == "REGENERATION_PLAN_CHANGED"
    assert result.message == "the authorized regeneration plan changed"
    assert result.details == {}
    assert adapter.calls == 0
    assert _root_state(destination) == before_apply
    assert not list(workspace.glob(".stm32tk-regeneration-*"))
    with pytest.raises(RegenerationAuthorizationError) as consumed:
        store.peek(digest)
    assert consumed.value.code == "REGENERATION_AUTHORIZATION_CONSUMED"


def test_apply_uses_default_configure_and_successful_build_seams(tmp_path: Path):
    workspace, destination, environment = _project(tmp_path)
    request = RegenerationWorkflowRequest(workspace, tmp_path / "data", "session", "generated")
    planned = plan_regeneration(request, environment=environment)
    store = RegenerationAuthorizationStore(tmp_path / "data")
    prepared = prepare_regeneration_workflow(
        request,
        plan_id=planned.data["planId"],
        action_digest=planned.data["actionDigest"],
        authorized=True,
        environment=environment,
        store=store,
        adapter=_Adapter(FIXTURE),
        validate_native=_validator,
    )
    assert prepared.ok is True
    build_calls: list[str] = []

    def build(root: Path, preset: str) -> OperationResult[dict[str, object]]:
        build_calls.append(preset)
        return OperationResult.success("build", {"preset": preset})

    result = apply_regeneration_workflow(
        request,
        authorization_digest=prepared.data["authorizationDigest"],
        authorized=True,
        environment=environment,
        store=store,
        adapter=_Adapter(FIXTURE),
        validate_native=_validator,
        build=build,
    )

    assert result.ok is True
    assert result.operation == "project-regenerate-apply"
    assert result.code == "OK"
    assert result.data["mutated"] is True
    assert build_calls == ["arm-debug", "arm-release"]
    assert (destination / "App" / "keep.txt").read_bytes() == b"user bytes"
    assert (destination / "Tests" / "keep.txt").read_bytes() == b"test bytes"
    assert not list(workspace.glob(".stm32tk-regeneration-*"))
    assert not list(workspace.glob(".generated.regen-backup-*"))
    with pytest.raises(RegenerationAuthorizationError) as consumed:
        store.peek(prepared.data["authorizationDigest"])
    assert consumed.value.code == "REGENERATION_AUTHORIZATION_CONSUMED"


def test_apply_serializes_public_to_dict_configuration_failure_without_build(tmp_path: Path):
    workspace, destination, environment = _project(tmp_path)
    request = RegenerationWorkflowRequest(workspace, tmp_path / "data", "session", "generated")
    planned = plan_regeneration(request, environment=environment)
    store = RegenerationAuthorizationStore(tmp_path / "data")
    prepared = prepare_regeneration_workflow(
        request,
        plan_id=planned.data["planId"],
        action_digest=planned.data["actionDigest"],
        authorized=True,
        environment=environment,
        store=store,
        adapter=_Adapter(FIXTURE),
        validate_native=_validator,
    )
    assert prepared.ok is True
    before_apply = _root_state(destination)
    build_calls: list[str] = []
    adapter = _Adapter(FIXTURE)

    class ConfigureReport:
        def to_dict(self) -> dict[str, object]:
            return {"status": "ok", "attempt": 1}

    def build(root: Path, preset: str) -> OperationResult[dict[str, object]]:
        build_calls.append(preset)
        return OperationResult.success("build", {"preset": preset})

    result = apply_regeneration_workflow(
        request,
        authorization_digest=prepared.data["authorizationDigest"],
        authorized=True,
        environment=environment,
        store=store,
        adapter=adapter,
        validate_native=_validator,
        configure=lambda root: ConfigureReport(),
        build=build,
    )

    assert result.ok is False
    assert result.operation == "project-regenerate-apply"
    assert result.code == "REGENERATION_CONFIGURATION_FAILED"
    assert result.message == "project configuration failed"
    assert result.details == {"result": {"status": "ok", "attempt": 1}}
    assert build_calls == []
    assert adapter.calls == 1
    assert _root_state(destination) == before_apply
    assert not list(workspace.glob(".stm32tk-regeneration-*"))
    with pytest.raises(RegenerationAuthorizationError) as consumed:
        store.peek(prepared.data["authorizationDigest"])
    assert consumed.value.code == "REGENERATION_AUTHORIZATION_CONSUMED"


def test_apply_recursively_serializes_public_configuration_failure_payload(tmp_path: Path):
    workspace, destination, environment = _project(tmp_path)
    request = RegenerationWorkflowRequest(workspace, tmp_path / "data", "session", "generated")
    planned = plan_regeneration(request, environment=environment)
    store = RegenerationAuthorizationStore(tmp_path / "data")
    prepared = prepare_regeneration_workflow(
        request,
        plan_id=planned.data["planId"],
        action_digest=planned.data["actionDigest"],
        authorized=True,
        environment=environment,
        store=store,
        adapter=_Adapter(FIXTURE),
        validate_native=_validator,
    )
    assert prepared.ok is True
    before_apply = _root_state(destination)
    build_calls: list[str] = []
    adapter = _Adapter(FIXTURE)

    class Unsupported:
        pass

    configuration = {
        "items": [("tuple", 7), {"leaf": Unsupported()}],
        "scalar": "value",
        "unsupported": Unsupported(),
    }

    def build(root: Path, preset: str) -> OperationResult[dict[str, object]]:
        build_calls.append(preset)
        return OperationResult.success("build", {"preset": preset})

    result = apply_regeneration_workflow(
        request,
        authorization_digest=prepared.data["authorizationDigest"],
        authorized=True,
        environment=environment,
        store=store,
        adapter=adapter,
        validate_native=_validator,
        configure=lambda root: configuration,
        build=build,
    )

    assert result.ok is False
    assert result.operation == "project-regenerate-apply"
    assert result.code == "REGENERATION_CONFIGURATION_FAILED"
    assert result.message == "project configuration failed"
    assert result.details == {
        "result": {
            "items": [["tuple", 7], {"leaf": None}],
            "scalar": "value",
            "unsupported": None,
        }
    }
    assert build_calls == []
    assert adapter.calls == 1
    assert _root_state(destination) == before_apply
    assert not list(workspace.glob(".stm32tk-regeneration-*"))
    with pytest.raises(RegenerationAuthorizationError) as consumed:
        store.peek(prepared.data["authorizationDigest"])
    assert consumed.value.code == "REGENERATION_AUTHORIZATION_CONSUMED"
