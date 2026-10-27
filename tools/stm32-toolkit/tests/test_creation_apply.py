from __future__ import annotations

import os
import hashlib
import shutil
import stat
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

import stm32_toolkit.creation_apply as creation_apply_module
from stm32_toolkit.creation_apply import CreationApplyError, CreationApplyRequest, apply_creation
from stm32_toolkit.creation_authorization import (
    CreationAuthorizationError,
    CreationAuthorizationStore,
    CreationPrepareRequest,
)
from stm32_toolkit.creation_environment import CreationEnvironmentError
from stm32_toolkit.cubemx_adapter import CubeMXAdapterError
from stm32_toolkit.generation.creation import CreationRequest
from stm32_toolkit.generation.managed_files import MANAGED_MANIFEST_PATH
from stm32_toolkit.result import OperationResult


def test_native_validation_seeds_existing_cubemx_targets_as_managed(tmp_path: Path):
    root = tmp_path / "generated"
    root.mkdir()
    (root / ".stm32-project.json").write_text("{}\n", encoding="utf-8")
    (root / "CMakeLists.txt").write_text("native cmake\n", encoding="utf-8")
    (root / "CMakePresets.json").write_text("{}\n", encoding="utf-8")
    inventory = tuple(
        (
            path.relative_to(root).as_posix(),
            path.stat().st_size,
            hashlib.sha256(path.read_bytes()).hexdigest(),
        )
        for path in sorted(root.rglob("*"))
        if path.is_file()
    )

    manifest = creation_apply_module._seed_native_managed_manifest(
        root,
        model_sha256="a" * 64,
        inventory=inventory,
    )

    payload = __import__("json").loads(manifest.read_text(encoding="utf-8"))
    assert [entry["path"] for entry in payload["files"]] == ["CMakeLists.txt", "CMakePresets.json"]
    assert all(entry["ownership"] == "managed" for entry in payload["files"])


def _authorization(tmp_path: Path):
    data = tmp_path / "data"
    request = CreationRequest.from_mcu("STM32F429ZITx", "generated", framework="hal", language="c")
    store = CreationAuthorizationStore(data, now=lambda: __import__("datetime").datetime(2026, 8, 23, 12, tzinfo=__import__("datetime").timezone.utc), nonce_factory=lambda: "nonce")
    prepared = store.prepare(CreationPrepareRequest(request, tmp_path, "a" * 64, "b" * 64, "c" * 64, "2026-08-23T13:00:00Z"))
    return data, store, prepared


class RecordingAdapter:
    def __init__(self, events: list[str]):
        self.events = events
        self.calls = 0

    def generate(self, capability, staging):
        self.calls += 1
        self.events.append("cubeMx")
        child = staging.staging_dir / "generated"
        child.mkdir()
        (child / "native.txt").write_text("generated", encoding="utf-8")
        return SimpleNamespace(invocations=1, project_root=child)


class ChildRootAdapter(RecordingAdapter):
    def generate(self, capability, staging):
        self.calls += 1
        child = staging.staging_dir / "generated"
        child.mkdir()
        (child / "native.txt").write_text("generated", encoding="utf-8")
        return SimpleNamespace(invocations=1, project_root=child)


class InvalidChildRootAdapter(RecordingAdapter):
    def __init__(self, events: list[str], shape: str):
        super().__init__(events)
        self.shape = shape

    def generate(self, capability, staging):
        self.calls += 1
        self.events.append("cubeMx")
        if self.shape == "missing-project-root":
            return SimpleNamespace(invocations=1, project_root=None)
        if self.shape == "unexpected-project-name":
            child = staging.staging_dir / "unexpected"
            child.mkdir()
            (child / "native.txt").write_text("generated", encoding="utf-8")
            return SimpleNamespace(invocations=1, project_root=child)
        child = staging.staging_dir / "generated"
        child.mkdir()
        (child / "native.txt").write_text("generated", encoding="utf-8")
        (staging.staging_dir / "unexpected-sibling").mkdir()
        return SimpleNamespace(invocations=1, project_root=child)


class ControlArtifactAdapter(RecordingAdapter):
    def generate(self, capability, staging):
        self.calls += 1
        child = staging.staging_dir / "generated"
        child.mkdir()
        (child / "native.c").write_text("int main(void) {}\n", encoding="utf-8")
        (child / ".stm32-project.json").write_text("{\"generatedBy\":\"test\"}\n", encoding="utf-8")
        (child / ".stm32-toolkit").mkdir()
        (child / ".stm32-toolkit" / "cubemx-ownership.json").write_text(
            '{"files":[{"path":"native.c"}]}\n', encoding="utf-8"
        )
        control_root = staging.staging_dir.parent / ".cube-control"
        control_root.mkdir(exist_ok=True)
        (control_root / "script").write_text(str(staging.staging_dir), encoding="utf-8")
        (control_root / ".stm32-toolkit-home").mkdir(exist_ok=True)
        shutil.rmtree(control_root)
        return SimpleNamespace(invocations=1, project_root=child)


class AbsolutePathAdapter(RecordingAdapter):
    def generate(self, capability, staging):
        self.calls += 1
        child = staging.staging_dir / "generated"
        child.mkdir()
        (child / "native.txt").write_text(str(staging.staging_dir.resolve()), encoding="utf-8")
        return SimpleNamespace(invocations=1, project_root=child)


def _validator(events: list[str]):
    def validate(staging, **kwargs):
        events.append("validate")
        return SimpleNamespace(ownership_manifest_path=".stm32-toolkit/cubemx-ownership.json", ownership_manifest_sha256="1" * 64)
    return validate


def test_apply_orders_one_generation_then_configure_and_two_builds_before_activation(tmp_path: Path):
    data, store, prepared = _authorization(tmp_path)
    events: list[str] = []
    result = apply_creation(
        CreationApplyRequest(tmp_path, data, prepared.authorization_digest, True),
        store=store,
        adapter=RecordingAdapter(events),
        validate_native=_validator(events),
        configure=lambda root: events.append("configure") or OperationResult.success("configure", {"planId": "p"}),
        build=lambda root, preset: events.append(f"build:{preset}") or OperationResult.success("build", {"preset": preset, "identity": preset}),
        on_activate=lambda: events.append("activate"),
    )
    assert result.ok is True
    assert result.data["mutated"] is True
    assert events == ["cubeMx", "validate", "configure", "build:arm-debug", "build:arm-release", "activate"]
    assert (tmp_path / "generated" / "native.txt").read_text(encoding="utf-8") == "generated"


def test_apply_relocates_validated_child_before_cleanup_configure_and_build(tmp_path: Path, monkeypatch):
    data, store, prepared = _authorization(tmp_path)
    events: list[tuple[str, Path | None]] = []
    generation_root: list[Path] = []
    validated_root: list[Path] = []

    class RootRecordingAdapter(RecordingAdapter):
        def generate(self, capability, staging):
            generation_root.append(staging.staging_dir)
            return super().generate(capability, staging)

    real_remove = creation_apply_module._remove_empty_container
    real_scan = creation_apply_module._assert_public_paths_are_portable

    def observe_remove(path: Path):
        events.append(("cleanup", path))
        return real_remove(path)

    def observe_scan(project_root, root, *, inventory=None):
        events.append(("scan", project_root))
        return real_scan(project_root, root, inventory=inventory)

    monkeypatch.setattr(creation_apply_module, "_remove_empty_container", observe_remove)
    monkeypatch.setattr(creation_apply_module, "_assert_public_paths_are_portable", observe_scan)

    def validate(project_root, **kwargs):
        validated_root.append(project_root)
        events.append(("validate", project_root))
        return SimpleNamespace(ownership_manifest_path="m", ownership_manifest_sha256="1" * 64)

    def configure(project_root):
        events.append(("configure", project_root))
        return OperationResult.success("configure", {})

    def build(project_root, preset):
        events.append((f"build:{preset}", project_root))
        return OperationResult.success("build", {"preset": preset})

    result = apply_creation(
        CreationApplyRequest(tmp_path, data, prepared.authorization_digest, True),
        store=store,
        adapter=RootRecordingAdapter([]),
        validate_native=validate,
        configure=configure,
        build=build,
    )

    assert result.ok is True
    assert generation_root and validated_root
    assert events[0] == ("validate", validated_root[0])
    assert events[1] == ("scan", generation_root[0] / "generated")
    cleanup_index = next(index for index, event in enumerate(events) if event[0] == "cleanup")
    configure_index = next(index for index, event in enumerate(events) if event[0] == "configure")
    assert cleanup_index < configure_index
    assert sum(event[0] == "cleanup" for event in events) == 1
    assert events[cleanup_index][1] == generation_root[0]
    configured_root = events[configure_index][1]
    assert configured_root is not None
    assert configured_root.name.startswith(".stm32tk-activation-")
    assert configured_root != generation_root[0]
    assert not generation_root[0].exists()
    assert not validated_root[0].exists()
    assert result.data["ownershipManifestPath"] == "m"


def test_activation_staging_collision_fails_before_cube_mx_and_preserves_collision(
    tmp_path: Path,
):
    data, store, prepared = _authorization(tmp_path)
    attempt_id = "activation-collision"
    collision = tmp_path / f".stm32tk-activation-{attempt_id}"
    collision.mkdir()
    (collision / "keep.txt").write_text("keep", encoding="utf-8")
    adapter = RecordingAdapter([])

    result = apply_creation(
        CreationApplyRequest(tmp_path, data, prepared.authorization_digest, True),
        store=store,
        adapter=adapter,
        validate_native=_validator([]),
        configure=lambda root: OperationResult.success("configure", {}),
        build=lambda root, preset: OperationResult.success("build", {}),
        attempt_id_factory=lambda: attempt_id,
    )

    assert result.ok is False
    assert result.code == "CREATION_ACTIVATION_FAILED"
    assert adapter.calls == 0
    assert (collision / "keep.txt").read_text(encoding="utf-8") == "keep"
    assert not list(tmp_path.glob(".stm32tk-creation-*"))


def test_relocation_failure_cleans_both_owned_roots_without_destination_mutation(
    tmp_path: Path, monkeypatch
):
    data, store, prepared = _authorization(tmp_path)
    real_replace = creation_apply_module.os.replace

    def fail_relocation(source, target):
        if Path(source).name == "generated" and Path(target).name.startswith(".stm32tk-activation-"):
            raise OSError("injected relocation failure")
        return real_replace(source, target)

    monkeypatch.setattr(creation_apply_module.os, "replace", fail_relocation)
    result = apply_creation(
        CreationApplyRequest(tmp_path, data, prepared.authorization_digest, True),
        store=store,
        adapter=RecordingAdapter([]),
        validate_native=_validator([]),
        configure=lambda root: OperationResult.success("configure", {}),
        build=lambda root, preset: OperationResult.success("build", {}),
    )

    assert result.ok is False
    assert result.code == "CREATION_ACTIVATION_FAILED"
    assert not (tmp_path / "generated").exists()
    assert not list(tmp_path.glob(".stm32tk-creation-*"))
    assert not list(tmp_path.glob(".stm32tk-activation-*"))


def test_configure_failure_after_relocation_cleans_activation_staging_and_generation_container(
    tmp_path: Path,
):
    data, store, prepared = _authorization(tmp_path)
    configured_roots: list[Path] = []

    def configure(root: Path):
        configured_roots.append(root)
        assert root.name.startswith(".stm32tk-activation-")
        return OperationResult.failure("configure", "FAIL", "failed", {})

    result = apply_creation(
        CreationApplyRequest(tmp_path, data, prepared.authorization_digest, True),
        store=store,
        adapter=RecordingAdapter([]),
        validate_native=_validator([]),
        configure=configure,
        build=lambda root, preset: OperationResult.success("build", {}),
    )

    assert result.ok is False
    assert result.code == "CREATION_CONFIGURATION_FAILED"
    assert configured_roots
    assert not (tmp_path / "generated").exists()
    assert not list(tmp_path.glob(".stm32tk-creation-*"))
    assert not list(tmp_path.glob(".stm32tk-activation-*"))


def test_activation_failure_after_build_cleans_both_owned_roots(tmp_path: Path, monkeypatch):
    data, store, prepared = _authorization(tmp_path)

    def fail_activation(staging, destination):
        assert staging.name.startswith(".stm32tk-activation-")
        raise CreationApplyError("CREATION_ACTIVATION_FAILED", "injected activation failure")

    monkeypatch.setattr(creation_apply_module, "_activate_absent", fail_activation)
    result = apply_creation(
        CreationApplyRequest(tmp_path, data, prepared.authorization_digest, True),
        store=store,
        adapter=RecordingAdapter([]),
        validate_native=_validator([]),
        configure=lambda root: OperationResult.success("configure", {}),
        build=lambda root, preset: OperationResult.success("build", {"preset": preset}),
    )

    assert result.ok is False
    assert result.code == "CREATION_ACTIVATION_FAILED"
    assert not (tmp_path / "generated").exists()
    assert not list(tmp_path.glob(".stm32tk-creation-*"))
    assert not list(tmp_path.glob(".stm32tk-activation-*"))


def test_empty_destination_is_replaced_only_after_both_builds(tmp_path: Path):
    (tmp_path / "generated").mkdir()
    data, store, prepared = _authorization(tmp_path)
    result = apply_creation(
        CreationApplyRequest(tmp_path, data, prepared.authorization_digest, True),
        store=store,
        adapter=RecordingAdapter([]),
        validate_native=lambda staging, **kwargs: SimpleNamespace(ownership_manifest_path="m", ownership_manifest_sha256="1" * 64),
        configure=lambda root: OperationResult.success("configure", {}),
        build=lambda root, preset: OperationResult.success("build", {"preset": preset}),
    )
    assert result.ok is True
    assert (tmp_path / "generated").is_dir()
    assert not list(tmp_path.glob(".generated.backup-*"))


def test_release_build_failure_leaves_destination_absent_and_cleans_staging(tmp_path: Path):
    data, store, prepared = _authorization(tmp_path)
    result = apply_creation(
        CreationApplyRequest(tmp_path, data, prepared.authorization_digest, True),
        store=store,
        adapter=RecordingAdapter([]),
        validate_native=lambda staging, **kwargs: SimpleNamespace(ownership_manifest_path="m", ownership_manifest_sha256="1" * 64),
        configure=lambda root: OperationResult.success("configure", {}),
        build=lambda root, preset: OperationResult.failure("build", "FAIL", "failed", {}) if preset == "arm-release" else OperationResult.success("build", {"preset": preset}),
    )
    assert result.ok is False
    assert result.code == "CREATION_RELEASE_BUILD_FAILED"
    assert not (tmp_path / "generated").exists()
    assert not list(tmp_path.glob(".stm32tk-creation-*"))
    assert not list(tmp_path.glob(".stm32tk-activation-*"))


def test_apply_rejects_destination_drift_after_staging_before_activation(tmp_path: Path):
    data, store, prepared = _authorization(tmp_path)
    destination = tmp_path / "generated"
    events: list[str] = []

    def build(root: Path, preset: str):
        events.append(preset)
        if preset == "arm-release":
            destination.mkdir()
            (destination / "user.txt").write_text("keep", encoding="utf-8")
        return OperationResult.success("build", {"preset": preset})

    result = apply_creation(
        CreationApplyRequest(tmp_path, data, prepared.authorization_digest, True),
        store=store,
        adapter=RecordingAdapter([]),
        validate_native=_validator([]),
        configure=lambda root: OperationResult.success("configure", {}),
        build=build,
    )

    assert result.ok is False
    assert result.code == "CREATION_DESTINATION_CHANGED"
    assert events == ["arm-debug", "arm-release"]
    assert (destination / "user.txt").read_text(encoding="utf-8") == "keep"
    assert not list(tmp_path.glob(".stm32tk-creation-*"))
    assert not list(tmp_path.glob(".stm32tk-activation-*"))
    assert not list(tmp_path.glob(".generated.backup-*"))
    record = store.authorization_root / f"{prepared.authorization_digest}.json"
    assert __import__("json").loads(record.read_text(encoding="utf-8"))["state"] == "consumed"


def test_populated_destination_is_rejected_without_consuming_generation_call(tmp_path: Path):
    (tmp_path / "generated").mkdir()
    (tmp_path / "generated" / "existing.txt").write_text("keep", encoding="utf-8")
    data, store, prepared = _authorization(tmp_path)
    adapter = RecordingAdapter([])
    result = apply_creation(
        CreationApplyRequest(tmp_path, data, prepared.authorization_digest, True),
        store=store,
        adapter=adapter,
        validate_native=_validator([]),
        configure=lambda root: OperationResult.success("configure", {}),
        build=lambda root, preset: OperationResult.success("build", {}),
    )
    assert result.ok is False
    assert result.code == "CREATION_DESTINATION_CHANGED"
    assert adapter.calls == 0
    assert (tmp_path / "generated" / "existing.txt").read_text(encoding="utf-8") == "keep"


def test_apply_requires_exact_boolean_true(tmp_path: Path):
    data, store, prepared = _authorization(tmp_path)
    with pytest.raises(CreationAuthorizationError) as error:
        apply_creation(CreationApplyRequest(tmp_path, data, prepared.authorization_digest, False), store=store)
    assert error.value.code == "CREATION_AUTHORIZATION_REQUIRED"


@pytest.mark.parametrize("drift_kind", ["root", "plan", "action"])
def test_apply_rejects_authorization_root_and_expected_digest_drift_before_provider(
    tmp_path: Path, drift_kind: str
):
    data, store, prepared = _authorization(tmp_path)
    alternate_root = tmp_path / "alternate-root"
    alternate_root.mkdir()
    adapter = RecordingAdapter([])
    project_root = alternate_root if drift_kind == "root" else tmp_path
    expected_plan_id = "d" * 64 if drift_kind == "plan" else None
    expected_action_digest = "e" * 64 if drift_kind == "action" else None

    result = apply_creation(
        CreationApplyRequest(
            project_root,
            data,
            prepared.authorization_digest,
            True,
            expected_plan_id=expected_plan_id,
            expected_action_digest=expected_action_digest,
        ),
        store=store,
        adapter=adapter,
    )

    assert result.ok is False
    assert result.code == "CREATION_PLAN_CHANGED"
    assert adapter.calls == 0
    assert not (tmp_path / "generated").exists()
    assert not list(tmp_path.glob(".stm32tk-creation-*"))
    assert not list(tmp_path.glob(".stm32tk-activation-*"))
    record = store.authorization_root / f"{prepared.authorization_digest}.json"
    assert __import__("json").loads(record.read_text(encoding="utf-8"))["state"] == "consumed"
    assert list(alternate_root.iterdir()) == []


def test_adapter_factory_failure_is_typed_without_dispatch_or_owned_roots(tmp_path: Path):
    data, store, prepared = _authorization(tmp_path)
    result = apply_creation(
        CreationApplyRequest(tmp_path, data, prepared.authorization_digest, True),
        store=store,
        environment=SimpleNamespace(digest="c" * 64),
        adapter_factory=lambda capability, environment: (_ for _ in ()).throw(
            RuntimeError("injected adapter setup failure")
        ),
    )

    assert result.ok is False
    assert result.code == "CUBEMX_EXECUTION_ENVIRONMENT_CHANGED"
    assert not (tmp_path / "generated").exists()
    assert not list(tmp_path.glob(".stm32tk-creation-*"))
    assert not list(tmp_path.glob(".stm32tk-activation-*"))


def test_environment_digest_drift_stops_before_cube_mx_dispatch(tmp_path: Path):
    data, store, prepared = _authorization(tmp_path)
    adapter = RecordingAdapter([])
    result = apply_creation(
        CreationApplyRequest(tmp_path, data, prepared.authorization_digest, True),
        store=store,
        environment=SimpleNamespace(digest="d" * 64),
        adapter=adapter,
        validate_native=_validator([]),
    )

    assert result.ok is False
    assert result.code == "CREATION_EXECUTION_ENVIRONMENT_CHANGED"
    assert adapter.calls == 0
    assert not (tmp_path / "generated").exists()
    assert not list(tmp_path.glob(".stm32tk-creation-*"))
    record = store.authorization_root / f"{prepared.authorization_digest}.json"
    assert __import__("json").loads(record.read_text(encoding="utf-8"))["state"] == "consumed"


def test_environment_factory_preserves_typed_discovery_failure_before_dispatch(tmp_path: Path):
    data, store, prepared = _authorization(tmp_path)
    adapter = RecordingAdapter([])

    def environment_factory(capability):
        raise CreationEnvironmentError("CUBEMX_PACKAGE_MISSING", "firmware package is unavailable")

    result = apply_creation(
        CreationApplyRequest(tmp_path, data, prepared.authorization_digest, True),
        store=store,
        environment_factory=environment_factory,
        adapter=adapter,
        validate_native=_validator([]),
    )

    assert result.ok is False
    assert result.code == "CUBEMX_PACKAGE_MISSING"
    assert adapter.calls == 0
    assert not (tmp_path / "generated").exists()
    assert not list(tmp_path.glob(".stm32tk-creation-*"))


@pytest.mark.parametrize("factory_kind", ["none", "typed-error"])
def test_adapter_factory_public_failures_are_typed_before_owned_roots(
    tmp_path: Path, factory_kind: str
):
    data, store, prepared = _authorization(tmp_path)

    def adapter_factory(capability, environment):
        if factory_kind == "none":
            return None
        raise CubeMXAdapterError("CUBEMX_PROTOCOL_INVALID", "adapter protocol is unavailable")

    result = apply_creation(
        CreationApplyRequest(tmp_path, data, prepared.authorization_digest, True),
        store=store,
        environment=SimpleNamespace(digest="c" * 64),
        adapter_factory=adapter_factory,
    )

    assert result.ok is False
    assert result.code == (
        "CUBEMX_EXECUTION_ENVIRONMENT_CHANGED"
        if factory_kind == "none"
        else "CUBEMX_PROTOCOL_INVALID"
    )
    assert not (tmp_path / "generated").exists()
    assert not list(tmp_path.glob(".stm32tk-creation-*"))
    assert not list(tmp_path.glob(".stm32tk-activation-*"))


def test_adapter_generation_failure_returns_typed_outcome_and_cleans_transaction(
    tmp_path: Path,
):
    data, store, prepared = _authorization(tmp_path)
    events: list[str] = []

    class FailingAdapter:
        def generate(self, capability, staging):
            events.append("cubeMx")
            raise CubeMXAdapterError("CUBEMX_PROCESS_FAILED", "CubeMX provider failed")

    result = apply_creation(
        CreationApplyRequest(tmp_path, data, prepared.authorization_digest, True),
        store=store,
        environment=SimpleNamespace(digest="c" * 64),
        adapter=FailingAdapter(),
        validate_native=_validator([]),
        attempt_id_factory=lambda: "provider-failure",
    )

    assert result.ok is False
    assert result.code == "CUBEMX_PROCESS_FAILED"
    assert events == ["cubeMx"]
    assert not (tmp_path / "generated").exists()
    assert not (tmp_path / ".stm32tk-creation-provider-failure").exists()
    assert not (tmp_path / ".stm32tk-activation-provider-failure").exists()
    attempt = data / "creation" / "attempts" / "provider-failure" / "failure.json"
    assert __import__("json").loads(attempt.read_text(encoding="utf-8"))["phase"] == "cubemx"


def test_empty_activation_backup_cleanup_failure_restores_exact_empty_state(tmp_path: Path, monkeypatch):
    staging = tmp_path / "staging"
    staging.mkdir()
    (staging / "native.txt").write_text("generated", encoding="utf-8")
    destination = tmp_path / "generated"
    destination.mkdir()
    backup = tmp_path / ".generated.backup-test"
    real_rmtree = creation_apply_module.shutil.rmtree

    def fail_cleanup(path, *args, **kwargs):
        if Path(path) == backup:
            raise OSError("injected backup cleanup failure")
        return real_rmtree(path, *args, **kwargs)

    monkeypatch.setattr(creation_apply_module.shutil, "rmtree", fail_cleanup)
    with pytest.raises(CreationApplyError) as error:
        creation_apply_module._activate_empty(staging, destination, backup)
    assert error.value.code == "CREATION_ACTIVATION_FAILED"
    assert destination.is_dir()
    assert list(destination.iterdir()) == []
    assert not backup.exists()


def test_remove_empty_container_retries_transient_rmdir_failure(tmp_path: Path, monkeypatch):
    staging = tmp_path / ".stm32tk-creation-transient"
    staging.mkdir()
    real_rmdir = Path.rmdir
    rmdir_calls: list[Path] = []
    sleeps: list[float] = []

    def transient_rmdir(path: Path):
        rmdir_calls.append(path)
        if len(rmdir_calls) < 4:
            raise OSError("transient sharing violation")
        return real_rmdir(path)

    monkeypatch.setattr(Path, "rmdir", transient_rmdir)
    monkeypatch.setattr(
        creation_apply_module,
        "time",
        SimpleNamespace(sleep=lambda delay: sleeps.append(delay)),
        raising=False,
    )

    creation_apply_module._remove_empty_container(staging)

    assert len(rmdir_calls) == 4
    assert sleeps == [0.05, 0.05, 0.05]
    assert not staging.exists()


def test_remove_empty_container_persistent_failure_is_bounded(tmp_path: Path, monkeypatch):
    staging = tmp_path / ".stm32tk-creation-persistent"
    staging.mkdir()
    rmdir_calls: list[Path] = []
    sleeps: list[float] = []

    def persistent_rmdir(path: Path):
        rmdir_calls.append(path)
        raise OSError("persistent sharing violation")

    monkeypatch.setattr(Path, "rmdir", persistent_rmdir)
    monkeypatch.setattr(
        creation_apply_module,
        "time",
        SimpleNamespace(sleep=lambda delay: sleeps.append(delay)),
        raising=False,
    )
    with pytest.raises(CreationApplyError) as error:
        creation_apply_module._remove_empty_container(staging)

    assert error.value.code == "CREATION_ACTIVATION_FAILED"
    assert len(rmdir_calls) == 20
    assert sleeps == [0.05] * 19
    assert staging.is_dir()


def test_remove_empty_container_fails_immediately_when_entry_appears_between_attempts(
    tmp_path: Path, monkeypatch
):
    staging = tmp_path / ".stm32tk-creation-entry"
    staging.mkdir()
    rmdir_calls: list[Path] = []

    def entry_after_first_failure(path: Path):
        rmdir_calls.append(path)
        (staging / "unexpected-entry").write_text("appeared", encoding="utf-8")
        raise OSError("transient sharing violation")

    monkeypatch.setattr(Path, "rmdir", entry_after_first_failure)
    monkeypatch.setattr(
        creation_apply_module,
        "time",
        SimpleNamespace(sleep=lambda _delay: pytest.fail("non-empty container was retried")),
        raising=False,
    )
    with pytest.raises(CreationApplyError) as error:
        creation_apply_module._remove_empty_container(staging)

    assert error.value.code == "CREATION_ACTIVATION_FAILED"
    assert len(rmdir_calls) == 1
    assert (staging / "unexpected-entry").is_file()


@pytest.mark.parametrize("initial_state", ["absent", "empty"])
def test_public_apply_persistent_container_cleanup_preserves_exact_destination_state(
    tmp_path: Path, monkeypatch, initial_state: str
):
    destination = tmp_path / "generated"
    if initial_state == "empty":
        destination.mkdir()
    data, store, prepared = _authorization(tmp_path)
    rmdir_calls: list[Path] = []
    real_rmdir = Path.rmdir

    def persistent_container_rmdir(path: Path):
        if path.name.startswith(".stm32tk-creation-"):
            rmdir_calls.append(path)
            raise OSError("persistent sharing violation")
        return real_rmdir(path)

    monkeypatch.setattr(Path, "rmdir", persistent_container_rmdir)
    result = apply_creation(
        CreationApplyRequest(tmp_path, data, prepared.authorization_digest, True),
        store=store,
        adapter=RecordingAdapter([]),
        validate_native=_validator([]),
        configure=lambda root: OperationResult.success("configure", {}),
        build=lambda root, preset: OperationResult.success("build", {"preset": preset}),
    )

    assert result.ok is False
    assert result.code == "CREATION_ACTIVATION_FAILED"
    assert len(rmdir_calls) == 20
    if initial_state == "absent":
        assert not destination.exists()
    else:
        assert destination.is_dir()
        assert list(destination.iterdir()) == []
    assert not list(tmp_path.glob(".stm32tk-creation-*"))
    assert not list(tmp_path.glob(".generated.backup-*"))


def test_empty_activation_first_rename_failure_keeps_empty_destination(tmp_path: Path, monkeypatch):
    staging = tmp_path / "staging"
    staging.mkdir()
    destination = tmp_path / "generated"
    destination.mkdir()
    backup = tmp_path / ".generated.backup-first"
    real_replace = creation_apply_module.os.replace

    def fail_first(source, target):
        if Path(source) == destination and Path(target) == backup:
            raise OSError("injected first rename failure")
        return real_replace(source, target)

    monkeypatch.setattr(creation_apply_module.os, "replace", fail_first)
    with pytest.raises(CreationApplyError) as error:
        creation_apply_module._activate_empty(staging, destination, backup)
    assert error.value.code == "CREATION_ACTIVATION_FAILED"
    assert destination.is_dir() and list(destination.iterdir()) == []
    assert staging.exists() and not backup.exists()


def test_empty_activation_second_rename_failure_restores_empty_destination(tmp_path: Path, monkeypatch):
    staging = tmp_path / "staging"
    staging.mkdir()
    destination = tmp_path / "generated"
    destination.mkdir()
    backup = tmp_path / ".generated.backup-second"
    real_replace = creation_apply_module.os.replace

    def fail_second(source, target):
        if Path(source) == staging and Path(target) == destination:
            raise OSError("injected second rename failure")
        return real_replace(source, target)

    monkeypatch.setattr(creation_apply_module.os, "replace", fail_second)
    with pytest.raises(CreationApplyError) as error:
        creation_apply_module._activate_empty(staging, destination, backup)
    assert error.value.code == "CREATION_ACTIVATION_FAILED"
    assert destination.is_dir() and list(destination.iterdir()) == []
    assert staging.exists() and not backup.exists()


def test_empty_activation_rollback_failure_is_bounded(tmp_path: Path, monkeypatch):
    staging = tmp_path / "staging"
    staging.mkdir()
    (staging / "native.txt").write_text("generated", encoding="utf-8")
    destination = tmp_path / "generated"
    destination.mkdir()
    backup = tmp_path / ".generated.backup-rollback"
    real_replace = creation_apply_module.os.replace
    real_rmtree = creation_apply_module.shutil.rmtree

    def fail_restore(source, target):
        if Path(source) == destination and Path(target) == staging:
            raise OSError("injected rollback rename failure")
        return real_replace(source, target)

    def fail_cleanup(path, *args, **kwargs):
        if Path(path) == backup:
            raise OSError("injected backup cleanup failure")
        return real_rmtree(path, *args, **kwargs)

    monkeypatch.setattr(creation_apply_module.os, "replace", fail_restore)
    monkeypatch.setattr(creation_apply_module.shutil, "rmtree", fail_cleanup)
    with pytest.raises(CreationApplyError) as error:
        creation_apply_module._activate_empty(staging, destination, backup)
    assert error.value.code == "CREATION_ACTIVATION_ROLLBACK_FAILED"


def test_apply_reports_staging_cleanup_failure_with_bounded_evidence(tmp_path: Path, monkeypatch):
    data, store, prepared = _authorization(tmp_path)
    original_cleanup = creation_apply_module._cleanup

    def fail_staging_cleanup(path):
        if path is not None and path.name.startswith((".stm32tk-creation-", ".stm32tk-activation-")):
            return False
        return original_cleanup(path)

    monkeypatch.setattr(creation_apply_module, "_cleanup", fail_staging_cleanup)
    result = apply_creation(
        CreationApplyRequest(tmp_path, data, prepared.authorization_digest, True),
        store=store,
        adapter=RecordingAdapter([]),
        validate_native=_validator([]),
        configure=lambda root: OperationResult.success("configure", {}),
        build=lambda root, preset: OperationResult.failure("build", "FAIL", "failed", {}) if preset == "arm-release" else OperationResult.success("build", {}),
    )
    assert result.ok is False
    assert result.code == "CREATION_ACTIVATION_ROLLBACK_FAILED"


def test_activation_lock_serializes_independent_processes(tmp_path: Path):
    data_root = tmp_path / "data"
    destination = tmp_path / "generated"
    markers = tmp_path / "markers"
    markers.mkdir()
    script = r'''
import os
import sys
import time
from pathlib import Path
from stm32_toolkit.creation_apply import _acquire_activation_lock

data_root = Path(sys.argv[1])
destination = Path(sys.argv[2])
markers = Path(sys.argv[3])
pid = os.getpid()
with _acquire_activation_lock(data_root, destination):
    (markers / f"ready-{pid}").write_text("ready", encoding="utf-8")
    while not (markers / "release").exists():
        time.sleep(0.005)
    (markers / f"done-{pid}").write_text("done", encoding="utf-8")
'''
    environment = os.environ.copy()
    source_root = str(Path(__file__).resolve().parents[1] / "src")
    environment["PYTHONPATH"] = source_root + os.pathsep + environment.get("PYTHONPATH", "")
    processes = []
    try:
        for _ in range(2):
            processes.append(
                subprocess.Popen(
                    [sys.executable, "-c", script, str(data_root), str(destination), str(markers)],
                    env=environment,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
            )
        deadline = time.monotonic() + 10
        while len(list(markers.glob("ready-*"))) < 1 and time.monotonic() < deadline:
            time.sleep(0.01)
        assert len(list(markers.glob("ready-*"))) == 1
        time.sleep(0.2)
        assert len(list(markers.glob("ready-*"))) == 1
        (markers / "release").write_text("release", encoding="utf-8")
        outputs = [process.communicate(timeout=10) for process in processes]
        assert all(process.returncode == 0 for process in processes), outputs
        assert len(list(markers.glob("done-*"))) == 2
    finally:
        (markers / "release").write_text("release", encoding="utf-8")
        for process in processes:
            if process.poll() is None:
                try:
                    process.communicate(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.communicate(timeout=10)


def test_plan_revalidation_rejects_drift_before_cube_mx_call(tmp_path: Path):
    data, store, prepared = _authorization(tmp_path)
    adapter = RecordingAdapter([])

    def reject_drift(*args):
        raise CreationApplyError("CREATION_PLAN_CHANGED", "creation plan changed")

    result = apply_creation(
        CreationApplyRequest(tmp_path, data, prepared.authorization_digest, True),
        store=store,
        adapter=adapter,
        revalidate_plan=reject_drift,
        validate_native=_validator([]),
        configure=lambda root: OperationResult.success("configure", {}),
        build=lambda root, preset: OperationResult.success("build", {}),
    )
    assert result.ok is False
    assert result.code == "CREATION_PLAN_CHANGED"
    assert adapter.calls == 0


def test_post_activation_inventory_excludes_control_artifacts_and_host_paths(tmp_path: Path):
    data, store, prepared = _authorization(tmp_path)
    adapter = ControlArtifactAdapter([])

    def validate(staging, **kwargs):
        relative_files = [path.relative_to(staging).as_posix() for path in staging.rglob("*") if path.is_file()]
        assert all(not item.startswith(".stm32-toolkit-home") for item in relative_files)
        assert all(not item.endswith(".script") for item in relative_files)
        return SimpleNamespace(ownership_manifest_path=".stm32-toolkit/cubemx-ownership.json", ownership_manifest_sha256="1" * 64)

    result = apply_creation(
        CreationApplyRequest(tmp_path, data, prepared.authorization_digest, True),
        store=store,
        adapter=adapter,
        validate_native=validate,
        configure=lambda root: OperationResult.success("configure", {}),
        build=lambda root, preset: OperationResult.success("build", {}),
    )
    assert result.ok is True
    destination = tmp_path / "generated"
    public_bytes = b"".join(path.read_bytes() for path in destination.rglob("*") if path.is_file())
    assert str(tmp_path).encode() not in public_bytes
    assert b".stm32-toolkit-home" not in public_bytes
    assert b"script" not in public_bytes
    assert not (destination / ".cube-control").exists()


def test_absolute_staging_path_in_native_output_is_rejected_before_activation(tmp_path: Path):
    data, store, prepared = _authorization(tmp_path)
    adapter = AbsolutePathAdapter([])
    result = apply_creation(
        CreationApplyRequest(tmp_path, data, prepared.authorization_digest, True),
        store=store,
        adapter=adapter,
        validate_native=_validator([]),
        configure=lambda root: OperationResult.success("configure", {}),
        build=lambda root, preset: OperationResult.success("build", {}),
    )
    assert result.ok is False
    assert result.code == "CUBEMX_NATIVE_OUTPUT_INVALID"
    assert adapter.calls == 1
    assert not (tmp_path / "generated").exists()


def test_apply_validates_and_activates_only_adapter_project_child_root(tmp_path: Path):
    data, store, prepared = _authorization(tmp_path)
    seen: list[Path] = []

    def validate(project_root, **kwargs):
        seen.append(project_root)
        assert project_root.name == "generated"
        assert (project_root / "native.txt").is_file()
        return SimpleNamespace(ownership_manifest_path="m", ownership_manifest_sha256="1" * 64)

    result = apply_creation(
        CreationApplyRequest(tmp_path, data, prepared.authorization_digest, True),
        store=store,
        adapter=ChildRootAdapter([]),
        validate_native=validate,
        configure=lambda root: (assert_path(root, seen) or OperationResult.success("configure", {})),
        build=lambda root, preset: (assert_path(root, seen) or OperationResult.success("build", {"preset": preset})),
    )
    assert result.ok is True
    assert seen and seen[0].name == "generated"
    assert (tmp_path / "generated" / "native.txt").read_text(encoding="utf-8") == "generated"
    assert not list(tmp_path.glob(".stm32tk-creation-*"))


@pytest.mark.parametrize(
    "provider_shape",
    ["missing-project-root", "unexpected-project-name", "unexpected-sibling"],
)
def test_apply_rejects_provider_output_outside_one_authorized_project_child(
    tmp_path: Path, provider_shape: str
):
    data, store, prepared = _authorization(tmp_path)
    events: list[str] = []
    adapter = InvalidChildRootAdapter(events, provider_shape)

    result = apply_creation(
        CreationApplyRequest(tmp_path, data, prepared.authorization_digest, True),
        store=store,
        adapter=adapter,
        validate_native=_validator(events),
        configure=lambda root: OperationResult.success("configure", {}),
        build=lambda root, preset: OperationResult.success("build", {"preset": preset}),
    )

    assert result.ok is False
    assert result.code == "CUBEMX_NATIVE_OUTPUT_INVALID"
    assert adapter.calls == 1
    assert events == ["cubeMx"]
    assert not (tmp_path / "generated").exists()
    assert not list(tmp_path.glob(".stm32tk-creation-*"))
    assert not list(tmp_path.glob(".stm32tk-activation-*"))
    record = store.authorization_root / f"{prepared.authorization_digest}.json"
    assert __import__("json").loads(record.read_text(encoding="utf-8"))["state"] == "consumed"


def assert_path(path: Path, seen: list[Path]) -> None:
    assert seen and path != seen[0]
    assert path.name.startswith(".stm32tk-activation-")
    assert (path / "native.txt").is_file()


def test_host_path_scan_consumes_bounded_native_inventory(tmp_path: Path, monkeypatch):
    project = tmp_path / "generated"
    project.mkdir()
    listed = project / "listed.c"
    unlisted = project / "unlisted.c"
    listed.write_text("portable", encoding="utf-8")
    unlisted.write_text(str(tmp_path), encoding="utf-8")
    real_read = Path.read_bytes

    def guarded_read(path: Path):
        if path.resolve() == unlisted.resolve():
            raise AssertionError("host path scan read outside bounded inventory")
        return real_read(path)

    monkeypatch.setattr(Path, "read_bytes", guarded_read)
    creation_apply_module._assert_public_paths_are_portable(
        project,
        tmp_path,
        inventory=(("listed.c", listed.stat().st_size, "0" * 64),),
    )


_CACHE_ARTIFACTS = {
    "STM32F429ZITx.elf": b"\x7fELF creation cache delivery\n",
    "STM32F429ZITx.map": b"Memory Configuration\n",
    "firmware-identity.json": b'{"schemaVersion":2}\n',
}


def _write_preset_artifacts(root: Path, preset: str) -> Path:
    build_dir = root / "build" / preset
    build_dir.mkdir(parents=True)
    for name, payload in _CACHE_ARTIFACTS.items():
        (build_dir / name).write_bytes(payload)
    return build_dir


# Project-level evidence that must survive cache invalidation byte-identically.
_OWNED_SENTINELS: dict[str, bytes] = {
    ".stm32-project.json": b'{"schemaVersion":2,"sentinel":"project-model"}\n',
    MANAGED_MANIFEST_PATH: b'{"schemaVersion":1,"sentinel":"managed-manifest"}\n',
    ".stm32-toolkit/cubemx-ownership.json": b'{"schemaVersion":1,"sentinel":"ownership"}\n',
    "artifacts/migration/build-result.json": b'{"schemaVersion":2,"status":"success"}\n',
}

# Image payloads carry non-UTF-8 bytes so preservation is checked byte-for-byte
# rather than as decoded text.
_FIRMWARE_PAYLOADS: dict[str, bytes] = {
    "STM32F429ZITx.bin": b"\x00\x01\x02\xff\xfe\x00firmware\x00",
    "STM32F429ZITx.hex": b":020000040800F2\n:00000001FF\n",
}


def _write_owned_sentinels(root: Path) -> None:
    for relative, payload in _OWNED_SENTINELS.items():
        path = root.joinpath(*relative.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)


def test_creation_apply_invalidates_staged_cmake_caches_and_keeps_build_artifacts(
    tmp_path: Path,
):
    data, store, prepared = _authorization(tmp_path)
    observed: list[tuple[str, Path, bool, bool]] = []
    activated: list[str] = []

    def build(root: Path, preset: str):
        _write_owned_sentinels(root)
        build_dir = _write_preset_artifacts(root, preset)
        for name, payload in _FIRMWARE_PAYLOADS.items():
            (build_dir / name).write_bytes(payload)
        cache = build_dir / "CMakeCache.txt"
        cache.write_text(
            f"CMAKE_CACHEFILE_DIR:INTERNAL={root.as_posix()}/build/{preset}\n",
            encoding="utf-8",
        )
        files = build_dir / "CMakeFiles"
        (files / "3.31.5").mkdir(parents=True)
        (files / "3.31.5" / "CMakeCCompiler.cmake").write_text(
            'set(CMAKE_C_COMPILER "gcc.exe")\n', encoding="utf-8"
        )
        observed.append((preset, root, cache.is_file(), files.is_dir()))
        return OperationResult.success("build", {"preset": preset})

    result = apply_creation(
        CreationApplyRequest(tmp_path, data, prepared.authorization_digest, True),
        store=store,
        adapter=RecordingAdapter([]),
        validate_native=_validator([]),
        configure=lambda root: OperationResult.success("configure", {}),
        build=build,
        on_activate=lambda: activated.append("activate"),
    )

    assert result.ok is True, result.to_dict()
    # Both caches existed inside the attempt-owned activation staging tree at
    # build time, and the destination was only activated afterwards.
    assert [preset for preset, *_ in observed] == ["arm-debug", "arm-release"]
    assert all(
        root.name.startswith(".stm32tk-activation-") for _, root, _, _ in observed
    )
    assert all(cache and files for _, _, cache, files in observed)
    assert activated == ["activate"]

    destination = tmp_path / "generated"
    for relative, payload in _OWNED_SENTINELS.items():
        path = destination.joinpath(*relative.split("/"))
        assert path.read_bytes() == payload, relative
    for preset in ("arm-debug", "arm-release"):
        build_dir = destination / "build" / preset
        for name, payload in {**_CACHE_ARTIFACTS, **_FIRMWARE_PAYLOADS}.items():
            assert (build_dir / name).read_bytes() == payload, name
        assert not (build_dir / "CMakeCache.txt").exists()
        assert not (build_dir / "CMakeFiles").exists()
    assert (destination / "native.txt").read_text(encoding="utf-8") == "generated"
    assert not list(tmp_path.glob(".stm32tk-creation-*"))
    assert not list(tmp_path.glob(".stm32tk-activation-*"))


@pytest.mark.parametrize("layout", ["no-build-directory", "artifacts-without-cache"])
def test_creation_apply_allows_absent_staged_cache_paths(tmp_path: Path, layout: str):
    data, store, prepared = _authorization(tmp_path)

    def build(root: Path, preset: str):
        if layout == "artifacts-without-cache" and preset == "arm-debug":
            _write_preset_artifacts(root, preset)
        return OperationResult.success("build", {"preset": preset})

    result = apply_creation(
        CreationApplyRequest(tmp_path, data, prepared.authorization_digest, True),
        store=store,
        adapter=RecordingAdapter([]),
        validate_native=_validator([]),
        configure=lambda root: OperationResult.success("configure", {}),
        build=build,
    )

    assert result.ok is True, result.to_dict()
    destination = tmp_path / "generated"
    if layout == "artifacts-without-cache":
        build_dir = destination / "build" / "arm-debug"
        for name, payload in _CACHE_ARTIFACTS.items():
            assert (build_dir / name).read_bytes() == payload
        assert not (build_dir / "CMakeCache.txt").exists()
        assert not (build_dir / "CMakeFiles").exists()
    else:
        assert not (destination / "build").exists()


@pytest.mark.parametrize("shape", ["build-file", "cache-directory", "files-file"])
@pytest.mark.parametrize("destination_state", ["absent", "empty"])
def test_creation_apply_refuses_wrong_cache_shapes_before_activation(
    tmp_path: Path, shape: str, destination_state: str
):
    # The empty destination pre-exists the prepared capability so the scenario
    # matches the established empty-destination setup.
    destination = tmp_path / "generated"
    if destination_state == "empty":
        destination.mkdir()
    data, store, prepared = _authorization(tmp_path)
    expected_preset = "build" if shape == "build-file" else "arm-debug"
    expected_path = {
        "build-file": "build",
        "cache-directory": "build/arm-debug/CMakeCache.txt",
        "files-file": "build/arm-debug/CMakeFiles",
    }[shape]

    def build(root: Path, preset: str):
        if shape == "build-file":
            (root / "build").write_text("not a build directory\n", encoding="utf-8")
            return OperationResult.success("build", {"preset": preset})
        build_dir = _write_preset_artifacts(root, preset)
        if preset == "arm-debug":
            if shape == "cache-directory":
                (build_dir / "CMakeCache.txt").mkdir()
            else:
                (build_dir / "CMakeFiles").write_text(
                    "not a cache directory\n", encoding="utf-8"
                )
        return OperationResult.success("build", {"preset": preset})

    activated: list[str] = []
    result = apply_creation(
        CreationApplyRequest(tmp_path, data, prepared.authorization_digest, True),
        store=store,
        adapter=RecordingAdapter([]),
        validate_native=_validator([]),
        configure=lambda root: OperationResult.success("configure", {}),
        build=build,
        on_activate=lambda: activated.append("activate"),
    )

    assert result.ok is False
    assert result.code == "CREATION_CACHE_PREPARATION_FAILED"
    assert result.details["rule"] == "shape"
    assert result.details["preset"] == expected_preset
    assert result.details["path"] == expected_path
    assert activated == []
    if destination_state == "absent":
        assert not destination.exists()
    else:
        assert destination.is_dir()
        assert list(destination.iterdir()) == []
    assert not list(tmp_path.glob(".stm32tk-creation-*"))
    assert not list(tmp_path.glob(".stm32tk-activation-*"))
    assert not list(tmp_path.glob(".generated.backup-*"))
    record = store.authorization_root / f"{prepared.authorization_digest}.json"
    assert __import__("json").loads(record.read_text(encoding="utf-8"))["state"] == "consumed"


def test_creation_apply_refuses_linked_cache_entry_before_activation(tmp_path: Path):
    data, store, prepared = _authorization(tmp_path)
    outside = tmp_path / "outside-cache"
    outside.mkdir()
    (outside / "sentinel.txt").write_text("keep", encoding="utf-8")

    def build(root: Path, preset: str):
        build_dir = _write_preset_artifacts(root, preset)
        if preset == "arm-debug":
            (build_dir / "CMakeCache.txt").write_text("cache\n", encoding="utf-8")
            nested = build_dir / "CMakeFiles" / "3.31.5"
            nested.mkdir(parents=True)
            (nested / "CMakeCCompiler.cmake").write_text(
                "compiler\n", encoding="utf-8"
            )
            try:
                (nested / "linked").symlink_to(outside, target_is_directory=True)
            except (OSError, NotImplementedError):
                pytest.skip("directory symlinks are unavailable on this host")
        return OperationResult.success("build", {"preset": preset})

    result = apply_creation(
        CreationApplyRequest(tmp_path, data, prepared.authorization_digest, True),
        store=store,
        adapter=RecordingAdapter([]),
        validate_native=_validator([]),
        configure=lambda root: OperationResult.success("configure", {}),
        build=build,
    )

    assert result.ok is False
    assert result.code == "CREATION_CACHE_PREPARATION_FAILED"
    assert result.details["rule"] == "link"
    assert result.details["preset"] == "arm-debug"
    assert result.details["path"] == "build/arm-debug/CMakeFiles/3.31.5/linked"
    assert not (tmp_path / "generated").exists()
    assert (outside / "sentinel.txt").read_text(encoding="utf-8") == "keep"
    assert not list(tmp_path.glob(".stm32tk-creation-*"))
    assert not list(tmp_path.glob(".stm32tk-activation-*"))


def test_creation_apply_refuses_reparse_cache_entry_deterministically(
    tmp_path: Path, monkeypatch
):
    data, store, prepared = _authorization(tmp_path)
    real_lstat = creation_apply_module._cache_lstat
    target = "CMakeCCompiler.cmake"

    def reparse_lstat(path: Path):
        info = real_lstat(path)
        if Path(path).name == target:
            return SimpleNamespace(st_mode=stat.S_IFREG, st_file_attributes=0x400)
        return info

    def build(root: Path, preset: str):
        build_dir = _write_preset_artifacts(root, preset)
        (build_dir / "CMakeCache.txt").write_text("cache\n", encoding="utf-8")
        nested = build_dir / "CMakeFiles" / "3.31.5"
        nested.mkdir(parents=True)
        (nested / target).write_text("compiler\n", encoding="utf-8")
        return OperationResult.success("build", {"preset": preset})

    monkeypatch.setattr(creation_apply_module, "_cache_lstat", reparse_lstat)
    result = apply_creation(
        CreationApplyRequest(tmp_path, data, prepared.authorization_digest, True),
        store=store,
        adapter=RecordingAdapter([]),
        validate_native=_validator([]),
        configure=lambda root: OperationResult.success("configure", {}),
        build=build,
    )

    assert result.ok is False
    assert result.code == "CREATION_CACHE_PREPARATION_FAILED"
    assert result.details["rule"] == "reparse"
    assert result.details["preset"] == "arm-debug"
    assert result.details["path"] == f"build/arm-debug/CMakeFiles/3.31.5/{target}"
    assert not (tmp_path / "generated").exists()
    assert not list(tmp_path.glob(".stm32tk-creation-*"))
    assert not list(tmp_path.glob(".stm32tk-activation-*"))


@pytest.mark.parametrize("destination_state", ["absent", "empty"])
def test_creation_apply_cache_io_failure_leaves_destination_unchanged(
    tmp_path: Path, monkeypatch, destination_state: str
):
    # The empty destination is created before the capability is prepared,
    # matching the established empty-destination setup.
    destination = tmp_path / "generated"
    if destination_state == "empty":
        destination.mkdir()
    data, store, prepared = _authorization(tmp_path)
    real_lstat = creation_apply_module._cache_lstat

    def failing_lstat(path: Path):
        if Path(path).name == "CMakeCache.txt":
            raise OSError("injected cache inspection failure")
        return real_lstat(path)

    def build(root: Path, preset: str):
        build_dir = _write_preset_artifacts(root, preset)
        (build_dir / "CMakeCache.txt").write_text("cache\n", encoding="utf-8")
        (build_dir / "CMakeFiles").mkdir()
        (build_dir / "CMakeFiles" / "build.ninja").write_text(
            "rules\n", encoding="utf-8"
        )
        return OperationResult.success("build", {"preset": preset})

    monkeypatch.setattr(creation_apply_module, "_cache_lstat", failing_lstat)
    result = apply_creation(
        CreationApplyRequest(tmp_path, data, prepared.authorization_digest, True),
        store=store,
        adapter=RecordingAdapter([]),
        validate_native=_validator([]),
        configure=lambda root: OperationResult.success("configure", {}),
        build=build,
    )

    assert result.ok is False
    assert result.code == "CREATION_CACHE_PREPARATION_FAILED"
    assert result.details["rule"] == "io"
    assert result.details["preset"] == "arm-debug"
    assert result.details["path"] == "build/arm-debug/CMakeCache.txt"
    if destination_state == "absent":
        assert not destination.exists()
    else:
        assert destination.is_dir()
        assert list(destination.iterdir()) == []
    assert not list(tmp_path.glob(".stm32tk-creation-*"))
    assert not list(tmp_path.glob(".stm32tk-activation-*"))
    assert not list(tmp_path.glob(".generated.backup-*"))
    record = store.authorization_root / f"{prepared.authorization_digest}.json"
    assert __import__("json").loads(record.read_text(encoding="utf-8"))["state"] == "consumed"


def test_cache_invalidation_validates_release_before_deleting_any_debug_cache(
    tmp_path: Path,
):
    """An invalid later candidate must not let earlier deletions start."""
    root = tmp_path / "project"
    root.mkdir()
    debug_dir = _write_preset_artifacts(root, "arm-debug")
    debug_cache = debug_dir / "CMakeCache.txt"
    debug_cache.write_bytes(b"cache: debug\n")
    debug_files = debug_dir / "CMakeFiles"
    (debug_files / "3.31.5").mkdir(parents=True)
    compiler_module = debug_files / "3.31.5" / "CMakeCCompiler.cmake"
    compiler_module.write_bytes(b'set(CMAKE_C_COMPILER "gcc.exe")\n')
    debug_before = {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in debug_dir.rglob("*")
        if path.is_file()
    }
    release_dir = _write_preset_artifacts(root, "arm-release")
    (release_dir / "CMakeCache.txt").mkdir()
    release_cache = release_dir / "CMakeCache.txt"

    with pytest.raises(CreationApplyError) as error:
        creation_apply_module._invalidate_creation_build_caches(root)

    assert error.value.code == "CREATION_CACHE_PREPARATION_FAILED"
    assert error.value.details == {
        "preset": "arm-release",
        "rule": "shape",
        "path": "build/arm-release/CMakeCache.txt",
    }
    # Validation stopped before the removal phase, so every debug cache byte
    # queued for deletion is still present unchanged.
    debug_after = {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in debug_dir.rglob("*")
        if path.is_file()
    }
    assert debug_after == debug_before
    assert debug_cache.is_file()
    assert compiler_module.is_file()
    assert release_cache.is_dir()


def test_cache_invalidation_deletion_io_failure_is_typed_and_stops(
    tmp_path: Path, monkeypatch
):
    """A deletion-phase I/O error is typed, not a blanket exception."""
    root = tmp_path / "project"
    root.mkdir()
    debug_dir = _write_preset_artifacts(root, "arm-debug")
    debug_cache = debug_dir / "CMakeCache.txt"
    debug_cache.write_bytes(b"cache: debug\n")
    debug_files = debug_dir / "CMakeFiles"
    debug_files.mkdir()
    (debug_files / "build.ninja").write_bytes(b"rules\n")
    release_dir = _write_preset_artifacts(root, "arm-release")
    release_cache = release_dir / "CMakeCache.txt"
    release_cache.write_bytes(b"cache: release\n")
    real_unlink = creation_apply_module.os.unlink

    def failing_unlink(path):
        if Path(path) == debug_cache:
            raise OSError("injected deletion failure")
        return real_unlink(path)

    monkeypatch.setattr(creation_apply_module.os, "unlink", failing_unlink)
    with pytest.raises(CreationApplyError) as error:
        creation_apply_module._invalidate_creation_build_caches(root)

    assert type(error.value) is CreationApplyError
    assert error.value.code == "CREATION_CACHE_PREPARATION_FAILED"
    assert error.value.details == {
        "preset": "arm-debug",
        "rule": "io",
        "path": "build/arm-debug/CMakeCache.txt",
    }
    assert debug_cache.read_bytes() == b"cache: debug\n"
    assert (debug_files / "build.ninja").read_bytes() == b"rules\n"
    assert release_cache.read_bytes() == b"cache: release\n"
