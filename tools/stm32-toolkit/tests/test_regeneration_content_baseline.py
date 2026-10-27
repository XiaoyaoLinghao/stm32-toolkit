"""Git-optional regeneration identity and continuation.

These tests exercise the content-based CubeMX regeneration contract without a
Git prerequisite: genuine no-repository and unborn-HEAD roots go through
plan -> prepare -> apply with fake generator/build seams, optional Git metadata
stays truthful, and Git HEAD/dirty/availability changes between phases cannot
invalidate a prepared regeneration while the relevant bytes are unchanged.
Relevant content, environment, or authority changes still fail before effects.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from stm32_toolkit.creation_apply import _seed_native_managed_manifest
from stm32_toolkit.cubemx_project import parse_native_project, write_native_project_manifests
from stm32_toolkit.generation.creation import CreationRequest
from stm32_toolkit.generation.managed_files import canonical_json_bytes, model_sha256_for, sha256_hex
from stm32_toolkit.project_model import load_project_model
from stm32_toolkit.regeneration import (
    RegenerationWorkflowRequest,
    build_regeneration_plan,
    plan_regeneration,
)
from stm32_toolkit.regeneration_workflows import (
    RegenerationAuthorizationError,
    RegenerationAuthorizationStore,
    apply_regeneration_workflow,
    prepare_regeneration_workflow,
)
from stm32_toolkit.result import OperationResult

FIXTURE = Path(__file__).parent / "fixtures" / "cubemx-6.18" / "native-f429"

_NO_GIT_EVIDENCE = {
    "status": "unavailable",
    "code": "BUILD_GIT_INVALID",
    "rule": "head",
}


@pytest.fixture(autouse=True)
def _contain_git_discovery(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Never let a test workspace discover a repository above its temp root."""
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))


def _environment() -> SimpleNamespace:
    return SimpleNamespace(
        digest="a" * 64,
        cubemx_version="6.18.1-RC2",
        cubemx_sha256="b" * 64,
        package_name="STM32Cube_FW_F4",
        package_version="1.28.3",
        package_sha256="c" * 64,
    )


def _git(root: Path, *arguments: str) -> None:
    try:
        subprocess.run(
            ["git", *arguments],
            cwd=root,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        pytest.skip("git is unavailable")


def _commit(root: Path, message: str = "fixture") -> None:
    _git(root, "add", "-A")
    _git(
        root,
        "-c",
        "user.name=regen",
        "-c",
        "user.email=regen@example.com",
        "commit",
        "-q",
        "-m",
        message,
    )


def _project(tmp_path: Path, *, git: str = "none") -> tuple[Path, Path, SimpleNamespace]:
    """A persisted schema-3 CubeMX project with optional Git state.

    ``git="none"`` is a genuine no-repository root, ``git="unborn"`` is a
    repository whose HEAD has no commit, and ``git="committed"`` is a clean
    single-commit repository.
    """
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    destination = workspace / "generated"
    shutil.copytree(FIXTURE, destination)
    environment = _environment()
    creation = CreationRequest.from_ioc("STM32F429ZITx.ioc", "generated", framework="hal", language="c")
    model = parse_native_project(
        destination,
        request=creation,
        plan_id="d" * 64,
        action_digest="e" * 64,
        environment=environment,
    )
    write_native_project_manifests(destination, model)
    loaded = load_project_model(destination)
    _seed_native_managed_manifest(
        destination, model_sha256=model_sha256_for(loaded), inventory=model.files
    )
    (destination / "App").mkdir()
    (destination / "App" / "keep.txt").write_bytes(b"user bytes")
    (destination / "Tests").mkdir()
    (destination / "Tests" / "keep.txt").write_bytes(b"test bytes")
    if git in {"unborn", "committed"}:
        _git(workspace, "init", "-q")
    if git == "committed":
        _commit(workspace)
    return workspace, destination, environment


class _Adapter:
    """Fake CubeMX generator: copy the accepted fixture into the container."""

    def __init__(self, source: Path = FIXTURE) -> None:
        self.source = source
        self.calls = 0

    def generate(self, capability, context):
        self.calls += 1
        child = context.staging_dir / capability.request.destination
        shutil.copytree(self.source, child)
        return SimpleNamespace(project_root=child)


def _validator(candidate, *, request, plan_id, action_digest, environment):
    return parse_native_project(
        candidate,
        request=request,
        plan_id=plan_id,
        action_digest=action_digest,
        environment=environment,
    )


def _configure(root: Path) -> OperationResult[dict[str, object]]:
    return OperationResult.success("configure", {})


def _build(root: Path, preset: str) -> OperationResult[dict[str, object]]:
    return OperationResult.success("build", {"preset": preset})


def _tree_bytes(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _request(workspace: Path, tmp_path: Path, destination: str = "generated") -> RegenerationWorkflowRequest:
    return RegenerationWorkflowRequest(workspace, tmp_path / "data", "session", destination)


def _prepare(
    request: RegenerationWorkflowRequest,
    plan,
    environment: object,
    *,
    adapter: _Adapter | None = None,
    now: datetime | None = None,
):
    return prepare_regeneration_workflow(
        request,
        plan_id=plan.plan_id,
        action_digest=plan.action_digest,
        authorized=True,
        environment=environment,
        adapter=adapter or _Adapter(),
        validate_native=_validator,
        now=now,
    )


def _apply(
    request: RegenerationWorkflowRequest,
    prepared: OperationResult[dict[str, object]] | str,
    environment: object,
    *,
    adapter: _Adapter | None = None,
    now: datetime | None = None,
):
    digest = prepared if isinstance(prepared, str) else prepared.data["authorizationDigest"]
    return apply_regeneration_workflow(
        request,
        authorization_digest=digest,
        authorized=True,
        environment=environment,
        adapter=adapter or _Adapter(),
        validate_native=_validator,
        configure=_configure,
        build=_build,
        now=now,
    )


def _assert_user_bytes(destination: Path) -> None:
    assert (destination / "App" / "keep.txt").read_bytes() == b"user bytes"
    assert (destination / "Tests" / "keep.txt").read_bytes() == b"test bytes"


@pytest.mark.parametrize("git_state", ("none", "unborn"))
def test_git_free_project_completes_plan_prepare_apply(tmp_path: Path, git_state: str):
    workspace, destination, environment = _project(tmp_path, git=git_state)
    request = _request(workspace, tmp_path)
    before_project = _tree_bytes(destination)
    before_data = _tree_bytes(tmp_path / "data") if (tmp_path / "data").exists() else {}

    planned = plan_regeneration(request, environment=environment)

    assert planned.ok is True
    assert planned.operation == "project-regenerate-plan"
    assert planned.data["blockers"] == ()
    assert planned.data["gitHead"] is None
    assert planned.data["gitDirty"] is None
    assert planned.data["gitEvidence"] == _NO_GIT_EVIDENCE
    assert set(planned.data["gitEvidence"]) == {"status", "code", "rule"}
    assert _tree_bytes(destination) == before_project
    assert (_tree_bytes(tmp_path / "data") if (tmp_path / "data").exists() else {}) == before_data

    plan = build_regeneration_plan(request, environment=environment)
    adapter = _Adapter()
    prepared = _prepare(request, plan, environment, adapter=adapter)

    assert prepared.ok is True
    assert adapter.calls == 1
    assert prepared.data["gitHead"] is None
    assert prepared.data["gitDirty"] is None
    assert prepared.data["gitEvidence"] == _NO_GIT_EVIDENCE
    assert not list(workspace.glob(".stm32tk-regeneration-preview-*"))

    applied = _apply(
        request,
        prepared.data["authorizationDigest"],
        environment,
        adapter=_Adapter(),
    )

    assert applied.ok is True
    assert applied.operation == "project-regenerate-apply"
    assert applied.data["mutated"] is True
    _assert_user_bytes(destination)
    assert not list(workspace.glob(".stm32tk-regeneration-*"))
    assert not list(workspace.glob(".generated.regen-backup-*"))

    replay = _apply(request, prepared.data["authorizationDigest"], environment)
    assert replay.code == "REGENERATION_AUTHORIZATION_CONSUMED"
    assert replay.data is None
    _assert_user_bytes(destination)


def test_git_metadata_is_traceability_not_plan_identity(tmp_path: Path):
    workspace, _destination, environment = _project(tmp_path, git="none")
    request = _request(workspace, tmp_path)

    without_git = build_regeneration_plan(request, environment=environment)
    assert without_git.git_head is None
    assert without_git.git_dirty is None
    assert without_git.git_evidence == _NO_GIT_EVIDENCE

    _git(workspace, "init", "-q")
    _commit(workspace)
    committed = build_regeneration_plan(request, environment=environment)

    assert committed.git_head is not None
    assert len(committed.git_head) == 40
    assert committed.git_dirty is False
    assert committed.git_evidence is None
    assert committed.git_head != ""
    assert committed.project_state_digest == without_git.project_state_digest
    assert committed.plan_id == without_git.plan_id
    assert committed.action_digest == without_git.action_digest

    (workspace / "notes.txt").write_bytes(b"unrelated dirty sibling")
    dirty = build_regeneration_plan(request, environment=environment)

    assert dirty.git_head == committed.git_head
    assert dirty.git_dirty is True
    assert dirty.project_state_digest == without_git.project_state_digest
    assert dirty.plan_id == without_git.plan_id
    assert dirty.action_digest == without_git.action_digest


@pytest.mark.parametrize(
    "transition",
    [
        pytest.param("new-commit", id="new-commit"),
        pytest.param("dirty-only", id="dirty-only"),
        pytest.param("git-appears", id="git-appears"),
        pytest.param("git-disappears", id="git-disappears"),
    ],
)
def test_git_state_change_between_prepare_and_apply_is_accepted(
    tmp_path: Path, transition: str
):
    initial = "none" if transition == "git-appears" else "committed"
    workspace, destination, environment = _project(tmp_path, git=initial)
    request = _request(workspace, tmp_path)
    planned = build_regeneration_plan(request, environment=environment)
    prepared = _prepare(request, planned, environment, adapter=_Adapter())
    assert prepared.ok is True

    if transition == "new-commit":
        (workspace / "notes.txt").write_bytes(b"first")
        _commit(workspace, "second")
    elif transition == "dirty-only":
        (workspace / "notes.txt").write_bytes(b"unrelated dirty sibling")
    elif transition == "git-appears":
        _git(workspace, "init", "-q")
        _commit(workspace)
    elif transition == "git-disappears":
        (workspace / ".git").rename(workspace / ".git-disabled")
    else:  # pragma: no cover - parameter set is closed
        raise AssertionError(f"unknown transition: {transition}")

    replanned = build_regeneration_plan(request, environment=environment)
    assert replanned.project_state_digest == planned.project_state_digest
    assert replanned.plan_id == planned.plan_id
    assert replanned.action_digest == planned.action_digest

    if transition == "git-disappears":
        assert replanned.git_head is None
        assert replanned.git_dirty is None
        assert replanned.git_evidence == _NO_GIT_EVIDENCE
    elif transition == "new-commit":
        assert replanned.git_head != planned.git_head
        assert replanned.git_dirty is False
        assert replanned.git_evidence is None
    elif transition == "dirty-only":
        assert replanned.git_head == planned.git_head
        assert replanned.git_dirty is True
    else:
        assert planned.git_head is None
        assert replanned.git_head is not None
        assert replanned.git_dirty is False
        assert replanned.git_evidence is None

    applied = _apply(request, prepared, environment, adapter=_Adapter())

    assert applied.ok is True
    assert applied.data["mutated"] is True
    ownership = json.loads(
        (destination / ".stm32-toolkit" / "cubemx-ownership.json").read_text(encoding="utf-8")
    )
    assert ownership["planId"] == planned.plan_id
    _assert_user_bytes(destination)
    assert not list(workspace.glob(".stm32tk-regeneration-*"))


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        pytest.param("ioc", "REGENERATION_STATE_CHANGED", id="ioc"),
        pytest.param("source", "REGENERATION_USER_DRIFT", id="source"),
        pytest.param("managed-manifest", "REGENERATION_TOOLKIT_DRIFT", id="managed-manifest"),
        pytest.param("user", "REGENERATION_USER_DRIFT", id="user"),
    ],
)
def test_relevant_content_change_after_prepare_is_rejected(
    tmp_path: Path, mutation: str, expected_code: str
):
    workspace, destination, environment = _project(tmp_path, git="none")
    request = _request(workspace, tmp_path)
    planned = build_regeneration_plan(request, environment=environment)
    prepared = _prepare(request, planned, environment, adapter=_Adapter())
    assert prepared.ok is True

    if mutation == "ioc":
        target = destination / "STM32F429ZITx.ioc"
        target.write_bytes(target.read_bytes() + b"\n# drift\n")
    elif mutation == "source":
        target = destination / "Core" / "Src" / "main.c"
        target.write_bytes(target.read_bytes() + b"\n/* drift */\n")
    elif mutation == "managed-manifest":
        target = destination / ".stm32-toolkit" / "generated-files.json"
        payload = json.loads(target.read_text(encoding="utf-8"))
        assert payload["files"]
        payload["files"][0]["sha256"] = "f" * 64
        target.write_bytes(canonical_json_bytes(payload))
    elif mutation == "user":
        (destination / "App" / "keep.txt").write_bytes(b"modified user bytes")
    else:  # pragma: no cover - parameter set is closed
        raise AssertionError(f"unknown mutation: {mutation}")

    # Every relevant content change stays bound: the plan identity moves and
    # apply rejects before any generation.  A source/user byte change is
    # observed first through the content-state digest (existing typed order).
    replanned = build_regeneration_plan(request, environment=environment)
    assert replanned.plan_id != planned.plan_id
    assert replanned.project_state_digest != planned.project_state_digest
    before_apply = _tree_bytes(destination)
    adapter = _Adapter()

    result = _apply(request, prepared, environment, adapter=adapter)

    assert result.ok is False
    assert result.operation == "project-regenerate-apply"
    assert result.code == expected_code
    assert adapter.calls == 0
    assert _tree_bytes(destination) == before_apply
    assert not list(workspace.glob(".stm32tk-regeneration-*"))
    with pytest.raises(RegenerationAuthorizationError) as consumed:
        RegenerationAuthorizationStore(tmp_path / "data").peek(
            prepared.data["authorizationDigest"]
        )
    assert consumed.value.code == "REGENERATION_AUTHORIZATION_CONSUMED"


def test_execution_environment_change_after_prepare_is_rejected(tmp_path: Path):
    workspace, destination, environment = _project(tmp_path, git="none")
    request = _request(workspace, tmp_path)
    planned = build_regeneration_plan(request, environment=environment)
    prepared = _prepare(request, planned, environment, adapter=_Adapter())
    assert prepared.ok is True
    drifted = SimpleNamespace(**{**vars(environment), "digest": "d" * 64})
    before_apply = _tree_bytes(destination)
    adapter = _Adapter()

    result = _apply(request, prepared, drifted, adapter=adapter)

    assert result.ok is False
    assert result.code == "REGENERATION_GENERATOR_DRIFT"
    assert adapter.calls == 0
    assert _tree_bytes(destination) == before_apply
    assert not list(workspace.glob(".stm32tk-regeneration-*"))


def test_legacy_pending_plan_requires_fresh_plan_and_prepare(tmp_path: Path):
    workspace, destination, environment = _project(tmp_path, git="committed")
    request = _request(workspace, tmp_path)
    store = RegenerationAuthorizationStore(tmp_path / "data")
    planned = build_regeneration_plan(request, environment=environment)
    prepared = prepare_regeneration_workflow(
        request,
        plan_id=planned.plan_id,
        action_digest=planned.action_digest,
        authorized=True,
        environment=environment,
        store=store,
        adapter=_Adapter(),
        validate_native=_validator,
    )
    assert prepared.ok is True

    # A record issued before Git was removed from the identity carries the
    # old plan/state digests.  It must be rejected, not bypassed, and it is
    # consumed by the attempt so a fresh plan/prepare is mandatory.
    record = store.authorization_root / f"{prepared.data['authorizationDigest']}.json"
    payload = json.loads(record.read_text(encoding="utf-8"))
    payload["planId"] = "0" * 64
    payload["actionDigest"] = "0" * 64
    payload["projectStateDigest"] = "0" * 64
    canonical = {
        key: value
        for key, value in payload.items()
        if key not in {"authorizationDigest", "state"}
    }
    canonical["state"] = "prepared"
    legacy_digest = sha256_hex(canonical_json_bytes(canonical))
    payload["authorizationDigest"] = legacy_digest
    record.unlink()
    legacy_record = store.authorization_root / f"{legacy_digest}.json"
    legacy_record.write_bytes(canonical_json_bytes(payload))
    before_apply = _tree_bytes(destination)
    adapter = _Adapter()

    result = apply_regeneration_workflow(
        request,
        authorization_digest=legacy_digest,
        authorized=True,
        environment=environment,
        store=store,
        adapter=adapter,
        validate_native=_validator,
    )

    assert result.ok is False
    assert result.code == "REGENERATION_USER_DRIFT"
    assert adapter.calls == 0
    assert _tree_bytes(destination) == before_apply
    with pytest.raises(RegenerationAuthorizationError) as consumed:
        store.peek(legacy_digest)
    assert consumed.value.code == "REGENERATION_AUTHORIZATION_CONSUMED"

    fresh_plan = build_regeneration_plan(request, environment=environment)
    fresh_prepared = _prepare(request, fresh_plan, environment, adapter=_Adapter())
    assert fresh_prepared.ok is True
    applied = _apply(request, fresh_prepared, environment, adapter=_Adapter())
    assert applied.ok is True
    _assert_user_bytes(destination)


def test_expired_authorization_is_rejected_before_generation(tmp_path: Path):
    workspace, destination, environment = _project(tmp_path, git="none")
    request = _request(workspace, tmp_path)
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    planned = build_regeneration_plan(request, environment=environment, now=now)
    prepared = _prepare(request, planned, environment, adapter=_Adapter(), now=now)
    assert prepared.ok is True
    before_apply = _tree_bytes(destination)
    adapter = _Adapter()

    result = _apply(request, prepared, environment, adapter=adapter, now=now + timedelta(hours=2))

    assert result.ok is False
    assert result.code == "REGENERATION_AUTHORIZATION_EXPIRED"
    assert adapter.calls == 0
    assert _tree_bytes(destination) == before_apply
    assert not list(workspace.glob(".stm32tk-regeneration-*"))


def test_authorization_bound_to_another_destination_is_rejected(tmp_path: Path):
    workspace, destination, environment = _project(tmp_path, git="none")
    request = _request(workspace, tmp_path)
    planned = build_regeneration_plan(request, environment=environment)
    prepared = _prepare(request, planned, environment, adapter=_Adapter())
    assert prepared.ok is True
    (destination / "other").mkdir()
    other_request = _request(workspace, tmp_path, "generated/other")
    before_apply = _tree_bytes(destination)
    adapter = _Adapter()

    result = _apply(other_request, prepared, environment, adapter=adapter)

    assert result.ok is False
    assert result.code == "REGENERATION_AUTHORIZATION_INVALID"
    assert adapter.calls == 0
    assert _tree_bytes(destination) == before_apply


def test_unexpected_git_collector_error_is_not_availability_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    workspace, destination, environment = _project(tmp_path, git="none")
    request = _request(workspace, tmp_path)

    def raising_collector(project_root: Path, timeout_seconds: int = 30):
        raise RuntimeError("injected collector failure")

    monkeypatch.setattr(
        "stm32_toolkit.regeneration.collect_build_git_evidence", raising_collector
    )

    with pytest.raises(RuntimeError):
        build_regeneration_plan(request, environment=environment)

    planned = plan_regeneration(request, environment=environment)
    assert planned.ok is False
    assert planned.operation == "project-regenerate-plan"
    assert planned.code == "REGENERATION_PROJECT_INVALID"
    assert planned.data is None

    adapter = _Adapter()
    prepared = prepare_regeneration_workflow(
        request,
        plan_id="d" * 64,
        action_digest="e" * 64,
        authorized=True,
        environment=environment,
        adapter=adapter,
        validate_native=_validator,
    )

    assert prepared.ok is False
    assert prepared.operation == "project-regenerate-prepare"
    assert prepared.code == "REGENERATION_PROJECT_INVALID"
    assert adapter.calls == 0
    assert not (tmp_path / "data").exists()
    assert not list(workspace.glob(".stm32tk-regeneration-*"))
    assert (destination / "App" / "keep.txt").read_bytes() == b"user bytes"
