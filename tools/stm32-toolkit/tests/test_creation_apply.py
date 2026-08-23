from __future__ import annotations

import os
import hashlib
import shutil
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
from stm32_toolkit.generation.creation import CreationRequest
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
        if path is not None and path.name.startswith(".stm32tk-creation-"):
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


def assert_path(path: Path, seen: list[Path]) -> None:
    assert seen and path == seen[0]


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
