from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from stm32_toolkit import regeneration
from stm32_toolkit.creation_apply import _seed_native_managed_manifest
from stm32_toolkit.cubemx_project import parse_native_project, write_native_project_manifests
from stm32_toolkit.generation.creation import CreationRequest
from stm32_toolkit.generation.managed_files import model_sha256_for, sha256_hex
from stm32_toolkit.project_model import load_project_model
from stm32_toolkit.regeneration import (
    MAX_DIFF_BYTES,
    MAX_FILE_BYTES,
    MAX_RECORD_BYTES,
    MAX_PREVIEW_BYTES,
    MAX_TOTAL_BYTES,
    InventoryEntry,
    RegenerationError,
    RegenerationInputError,
    RegenerationWorkflowRequest,
    build_regeneration_preview,
    classify_regeneration_project,
    plan_regeneration,
)

FIXTURE = Path(__file__).parent / "fixtures" / "cubemx-6.18" / "native-f429"


def test_regeneration_request_requires_portable_non_root_destination(tmp_path: Path):
    with pytest.raises(RegenerationInputError):
        RegenerationWorkflowRequest(tmp_path, tmp_path / "data", "session", ".")


def test_regeneration_request_normalizes_absolute_roots(tmp_path: Path):
    request = RegenerationWorkflowRequest(
        tmp_path.resolve(), (tmp_path / "data").resolve(), "session", "generated"
    )
    assert request.destination == "generated"
    assert request.project_root == tmp_path / "generated"


@pytest.mark.parametrize(
    ("workspace_root", "data_root", "session_id", "destination", "field"),
    [
        pytest.param("valid", "valid", "session", "", "destination", id="S1-A"),
        pytest.param("relative", "valid", "session", "generated", "workspaceRoot", id="S1-C"),
        pytest.param("valid", "valid", "", "generated", "sessionId", id="S1-E"),
    ],
)
def test_regeneration_request_rejects_selected_public_inputs(
    tmp_path: Path,
    workspace_root: str,
    data_root: str,
    session_id: str,
    destination: str,
    field: str,
):
    workspace = tmp_path / "workspace"
    data = tmp_path / "data"
    requested_workspace = Path("relative-workspace") if workspace_root == "relative" else workspace
    requested_data = Path("relative-data") if data_root == "relative" else data

    with pytest.raises(RegenerationInputError) as caught:
        RegenerationWorkflowRequest(requested_workspace, requested_data, session_id, destination)

    assert caught.value.code == "REGENERATION_INPUT_INVALID"
    assert caught.value.field == field
    assert not workspace.exists()
    assert not data.exists()


def test_plan_regeneration_is_read_only_for_non_project(tmp_path: Path):
    request = RegenerationWorkflowRequest(
        tmp_path.resolve(), (tmp_path / "data").resolve(), "session", "generated"
    )
    result = plan_regeneration(request)
    assert result.code in {"REGENERATION_PROJECT_INVALID", "REGENERATION_NOT_CUBEMX_PROJECT"}
    assert not (tmp_path / "generated").exists()


def test_plan_regeneration_rejects_non_request_public_input(tmp_path: Path):
    result = plan_regeneration("not-a-RegenerationWorkflowRequest")

    assert result.ok is False
    assert result.operation == "project-regenerate-plan"
    assert result.code == "REGENERATION_INPUT_INVALID"
    assert result.message == "regeneration input is invalid"
    assert result.details["field"] == "request"
    assert not (tmp_path / "workspace").exists()
    assert not (tmp_path / "data").exists()


def test_regeneration_preview_omits_text_diff_over_record_bound_but_keeps_hashes():
    before_bytes = b"a" * (MAX_DIFF_BYTES + 1)
    after_bytes = b"b" * (MAX_DIFF_BYTES + 1)
    before = SimpleNamespace(
        inventory=(InventoryEntry("Core/main.c", "file", len(before_bytes), "a" * 64, "cubemx"),),
        file_bytes={"Core/main.c": before_bytes},
        ownership_manifest_digest="1" * 64,
        managed_manifest_digest="2" * 64,
    )
    after = SimpleNamespace(
        inventory=(InventoryEntry("Core/main.c", "file", len(after_bytes), "b" * 64, "cubemx"),),
        file_bytes={"Core/main.c": after_bytes},
        ownership_manifest_digest="3" * 64,
        managed_manifest_digest="4" * 64,
    )
    preview = build_regeneration_preview(before, after)
    assert preview.changes[0].unified_diff is None
    assert preview.changes[0].before_sha256 == "a" * 64


def test_regeneration_preview_fails_closed_when_aggregate_display_exceeds_bound():
    old = b"a\n" * 1_000
    new = b"b\n" * 1_000
    before_entries = tuple(
        InventoryEntry(f"Core/{index:02d}.c", "file", len(old), "a" * 64, "cubemx")
        for index in range(300)
    )
    after_entries = tuple(
        InventoryEntry(f"Core/{index:02d}.c", "file", len(new), "b" * 64, "cubemx")
        for index in range(300)
    )
    before = SimpleNamespace(
        inventory=before_entries,
        file_bytes={entry.path: old for entry in before_entries},
        ownership_manifest_digest="1" * 64,
        managed_manifest_digest="2" * 64,
    )
    after = SimpleNamespace(
        inventory=after_entries,
        file_bytes={entry.path: new for entry in after_entries},
        ownership_manifest_digest="3" * 64,
        managed_manifest_digest="4" * 64,
    )
    with pytest.raises(RegenerationError) as caught:
        build_regeneration_preview(before, after)
    assert caught.value.code == "REGENERATION_PREVIEW_TOO_LARGE"


@pytest.mark.parametrize("status", ("added", "deleted", "binary"))
def test_regeneration_preview_bounds_complete_change_record_metadata(status: str):
    count = 10_000
    before_data = b"\xff" if status == "binary" else b""
    after_data = b"\xfe" if status == "binary" else b""
    before_entries = ()
    after_entries = ()
    before_bytes = {}
    after_bytes = {}
    if status in {"deleted", "binary"}:
        before_entries = tuple(
            InventoryEntry(f"App/{index:05d}.bin", "file", len(before_data), f"{index:064x}", "user")
            for index in range(count)
        )
        before_bytes = {entry.path: before_data for entry in before_entries}
    if status in {"added", "binary"}:
        after_entries = tuple(
            InventoryEntry(f"App/{index:05d}.bin", "file", len(after_data), f"{index + 1:064x}", "user")
            for index in range(count)
        )
        after_bytes = {entry.path: after_data for entry in after_entries}
    before = SimpleNamespace(
        inventory=before_entries,
        file_bytes=before_bytes,
        ownership_manifest_digest="1" * 64,
        managed_manifest_digest="2" * 64,
    )
    after = SimpleNamespace(
        inventory=after_entries,
        file_bytes=after_bytes,
        ownership_manifest_digest="3" * 64,
        managed_manifest_digest="4" * 64,
    )
    with pytest.raises(RegenerationError) as caught:
        build_regeneration_preview(before, after)
    assert caught.value.code == "REGENERATION_PREVIEW_TOO_LARGE"


def test_regeneration_preview_public_payload_is_bounded_for_successful_preview():
    before = SimpleNamespace(
        inventory=(InventoryEntry("App/keep.txt", "file", 1, "a" * 64, "user"),),
        file_bytes={"App/keep.txt": b"a"},
        ownership_manifest_digest="1" * 64,
        managed_manifest_digest="2" * 64,
    )
    after = SimpleNamespace(
        inventory=(InventoryEntry("App/keep.txt", "file", 1, "b" * 64, "user"),),
        file_bytes={"App/keep.txt": b"b"},
        ownership_manifest_digest="3" * 64,
        managed_manifest_digest="4" * 64,
    )
    preview = build_regeneration_preview(before, after)
    encoded = json.dumps(preview.to_dict(), sort_keys=True, separators=(",", ":")).encode("utf-8")
    assert len(encoded) <= MAX_PREVIEW_BYTES


def test_regeneration_read_rejects_open_identity_change(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    victim = tmp_path / "victim.bin"
    replacement = tmp_path / "replacement.bin"
    victim.write_bytes(b"same-size")
    replacement.write_bytes(b"same-size")
    real_open = regeneration.os.open

    def open_replacement(path, flags, *args, **kwargs):
        if Path(path) == victim:
            return real_open(replacement, flags, *args, **kwargs)
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(regeneration.os, "open", open_replacement)
    with pytest.raises(RegenerationError) as caught:
        regeneration._read_file(victim)
    assert caught.value.code == "REGENERATION_STATE_CHANGED"


def test_destination_symlink_is_rejected_before_resolution(tmp_path: Path):
    target = tmp_path / "outside"
    target.mkdir()
    link = tmp_path / "generated"
    try:
        link.symlink_to(target, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation is unavailable")
    request = RegenerationWorkflowRequest(tmp_path, tmp_path / "data", "session", "generated")
    result = plan_regeneration(request)
    assert result.code == "REGENERATION_PATH_UNSAFE"


def _persisted_project(tmp_path: Path) -> tuple[Path, Path, SimpleNamespace]:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    destination = workspace / "generated"
    shutil.copytree(FIXTURE, destination)
    environment = SimpleNamespace(
        digest="a" * 64,
        cubemx_version="6.18.1-RC2",
        cubemx_sha256="b" * 64,
        package_name="STM32Cube_FW_F4",
        package_version="1.28.3",
        package_sha256="c" * 64,
    )
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
    _seed_native_managed_manifest(destination, model_sha256=model_sha256_for(loaded), inventory=model.files)
    (destination / "App").mkdir()
    (destination / "App" / "keep.txt").write_bytes(b"user bytes")
    subprocess.run(["git", "init", "-q"], cwd=workspace, check=True)
    subprocess.run(["git", "add", "-A"], cwd=workspace, check=True)
    subprocess.run(
        ["git", "-c", "user.name=regen", "-c", "user.email=regen@example.com", "commit", "-q", "-m", "fixture"],
        cwd=workspace,
        check=True,
    )
    return workspace, destination, environment


def _manifest_bytes(root: Path, relative: str) -> bytes:
    return (root / relative).read_bytes()


def _write_manifest_payload(root: Path, relative: str, payload: object) -> None:
    (root / relative).write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False),
        encoding="utf-8",
    )


def _mutate_s4_manifest(destination: Path, case_id: str) -> tuple[Path, bytes, str, str]:
    ownership_relative = ".stm32-toolkit/cubemx-ownership.json"
    managed_relative = ".stm32-toolkit/generated-files.json"
    ownership = destination / ownership_relative
    managed = destination / managed_relative
    if case_id == "S4-A":
        original = ownership.read_bytes().rstrip()
        mutated = original[:-1] + b',"schemaVersion":1}'
        ownership.write_bytes(mutated)
        return ownership, mutated, "REGENERATION_OWNERSHIP_INVALID", "ownership manifest is invalid"
    if case_id == "S4-B":
        ownership.write_text("[]", encoding="utf-8")
        return ownership, b"[]", "REGENERATION_OWNERSHIP_INVALID", "CubeMX ownership manifest is invalid"

    payload = json.loads(ownership.read_text(encoding="utf-8"))
    if case_id == "S4-C":
        payload.pop("tool")
        expected_message = "CubeMX ownership manifest is invalid"
    elif case_id == "S4-D":
        payload["generator"]["extra"] = "unexpected"
        expected_message = "CubeMX generator facts are invalid"
    elif case_id == "S4-E":
        payload["generator"]["tool"] = "wrong-tool"
        expected_message = "CubeMX generator facts are invalid"
    elif case_id == "S4-F":
        payload["source"]["packageName"] = 7
        expected_message = "CubeMX package facts are invalid"
    elif case_id == "S4-G":
        payload["source"]["packageSha256"] = "g" * 64
        expected_message = "CubeMX package facts are invalid"
    elif case_id == "S4-H":
        payload["planId"] = "bad"
        expected_message = "CubeMX ownership binding is invalid"
    elif case_id == "S4-I":
        payload["files"] = {}
        expected_message = "CubeMX ownership file list is invalid"
    elif case_id == "S4-J":
        payload["files"][0]["extra"] = True
        expected_message = "CubeMX ownership file list is invalid"
    elif case_id == "S4-K":
        payload["files"][0]["size"] = True
        expected_message = "CubeMX ownership file facts are invalid"
    elif case_id == "S4-L":
        payload = json.loads(managed.read_text(encoding="utf-8"))
        payload["projectManifestSha256"] = "d" * 64
        expected_message = "Toolkit managed model hash does not match the project"
        _write_manifest_payload(destination, managed_relative, payload)
        return managed, _manifest_bytes(destination, managed_relative), "REGENERATION_TOOLKIT_DRIFT", expected_message
    elif case_id == "S4-M":
        payload = json.loads(managed.read_text(encoding="utf-8"))
        rows = list(payload["files"])
        rows[0] = {**rows[0], "path": "App/generated.txt"}
        payload["files"] = sorted(rows, key=lambda row: row["path"])
        expected_message = "Toolkit managed path is outside the closed target set"
        _write_manifest_payload(destination, managed_relative, payload)
        return (
            managed,
            _manifest_bytes(destination, managed_relative),
            "REGENERATION_OWNERSHIP_INVALID",
            expected_message,
        )
    else:
        raise AssertionError(f"unknown S4 case: {case_id}")
    _write_manifest_payload(destination, ownership_relative, payload)
    return (
        ownership,
        _manifest_bytes(destination, ownership_relative),
        "REGENERATION_OWNERSHIP_INVALID",
        expected_message,
    )


def _tree_state(root: Path) -> tuple[bool, dict[str, bytes]]:
    if not root.exists():
        return False, {}
    return True, {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


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


def _streamed_file_facts(root: Path) -> dict[str, tuple[int, str]]:
    return {
        path.relative_to(root).as_posix(): (path.stat().st_size, _streamed_sha256(path))
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_plan_reports_invalid_supplied_environment_facts_without_write(tmp_path: Path):
    workspace, destination, environment = _persisted_project(tmp_path)
    environment.digest = "g" * 64
    request = RegenerationWorkflowRequest(workspace, tmp_path / "data", "session", "generated")
    before_project = _tree_state(destination)
    before_data = _tree_state(tmp_path / "data")

    result = plan_regeneration(request, environment=environment)

    assert result.ok is True
    assert result.code == "OK"
    assert any(
        item["code"] == "REGENERATION_GENERATOR_DRIFT"
        and item["message"] == "CubeMX execution facts are invalid"
        for item in result.data["blockers"]
    )
    assert _tree_state(destination) == before_project
    assert _tree_state(tmp_path / "data") == before_data


def test_plan_rejects_missing_declared_ioc_without_write(tmp_path: Path):
    workspace, destination, environment = _persisted_project(tmp_path)
    (destination / "STM32F429ZITx.ioc").unlink()
    request = RegenerationWorkflowRequest(workspace, tmp_path / "data", "session", "generated")
    before_project = _tree_state(destination)
    before_data = _tree_state(tmp_path / "data")

    result = plan_regeneration(request, environment=environment)

    assert result.code == "REGENERATION_PROJECT_INVALID"
    assert result.message == "CubeMX IOC is unavailable"
    assert _tree_state(destination) == before_project
    assert _tree_state(tmp_path / "data") == before_data


def test_plan_rejects_malformed_schema_v2_manifest_without_upgrade(tmp_path: Path):
    workspace, destination, environment = _persisted_project(tmp_path)
    manifest = destination / ".stm32-project.json"
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["schemaVersion"] = 2
    payload.pop("target")
    manifest.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    request = RegenerationWorkflowRequest(workspace, tmp_path / "data", "session", "generated")
    before_project = _tree_state(destination)
    before_data = _tree_state(tmp_path / "data")

    result = plan_regeneration(request, environment=environment)

    assert result.code == "REGENERATION_NOT_CUBEMX_PROJECT"
    assert result.message == "the destination is not a CubeMX project"
    assert _tree_state(destination) == before_project
    assert _tree_state(tmp_path / "data") == before_data


def test_plan_rejects_project_aggregate_size_limit_with_real_streamed_files(tmp_path: Path):
    workspace, destination, environment = _persisted_project(tmp_path)
    request = RegenerationWorkflowRequest(workspace, tmp_path / "data", "session", "generated")
    baseline_total = sum(
        path.stat().st_size for path in destination.rglob("*") if path.is_file()
    )
    baseline_files = sum(1 for path in destination.rglob("*") if path.is_file())
    payload_bytes = 8 * MAX_FILE_BYTES + 1
    assert baseline_total + payload_bytes <= 300 * 1024 * 1024
    assert baseline_files + 9 < 200_000
    aggregate_paths = [destination / "App" / f"aggregate-{index:02d}.bin" for index in range(8)]
    aggregate_paths.append(destination / "App" / "aggregate-overflow.bin")
    for path in aggregate_paths[:-1]:
        _write_streamed_bytes(path, MAX_FILE_BYTES)
    _write_streamed_bytes(aggregate_paths[-1], 1)
    before_files = {
        path.relative_to(destination).as_posix(): (path.stat().st_size, _streamed_sha256(path))
        for path in aggregate_paths
    }
    before_project = _streamed_file_facts(destination)
    before_data = _tree_state(tmp_path / "data")

    result = plan_regeneration(request, environment=environment)

    assert result.ok is False
    assert result.operation == "project-regenerate-plan"
    assert result.code == "REGENERATION_PATH_UNSAFE"
    assert result.message == "project aggregate size exceeds its bound"
    assert result.details == {}
    assert {
        path.relative_to(destination).as_posix(): (path.stat().st_size, _streamed_sha256(path))
        for path in aggregate_paths
    } == before_files
    assert _streamed_file_facts(destination) == before_project
    assert _tree_state(tmp_path / "data") == before_data


@pytest.mark.parametrize(
    ("case_id", "mutate", "expected_code", "expected_message"),
    [
        pytest.param(
            "S5-J",
            lambda payload: payload["project"].__setitem__("origin", "manual"),
            "REGENERATION_NOT_CUBEMX_PROJECT",
            "the destination is not a CubeMX project",
            id="S5-J",
        ),
        pytest.param(
            "S5-K",
            lambda payload: payload["generatedBy"].__setitem__("tool", "other"),
            "REGENERATION_PROJECT_INVALID",
            "the CubeMX project generation contract is invalid",
            id="S5-K",
        ),
    ],
)
def test_plan_rejects_closed_project_contract_variants(
    tmp_path: Path,
    case_id: str,
    mutate,
    expected_code: str,
    expected_message: str,
):
    del case_id
    workspace, destination, environment = _persisted_project(tmp_path)
    manifest = destination / ".stm32-project.json"
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    mutate(payload)
    manifest.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    request = RegenerationWorkflowRequest(workspace, tmp_path / "data", "session", "generated")
    before_project = _tree_state(destination)
    before_data = _tree_state(tmp_path / "data")

    result = plan_regeneration(request, environment=environment)

    assert result.ok is False
    assert result.operation == "project-regenerate-plan"
    assert result.code == expected_code
    assert result.message == expected_message
    assert result.details == {}
    assert _tree_state(destination) == before_project
    assert _tree_state(tmp_path / "data") == before_data


@pytest.mark.parametrize(
    "case_id",
    [
        pytest.param("S2-B", id="S2-B"),
        pytest.param("S2-C", id="S2-C"),
        pytest.param("S2-F", id="S2-F"),
    ],
)
def test_scan_limits(tmp_path: Path, case_id: str):
    workspace, destination, environment = _persisted_project(tmp_path)
    request = RegenerationWorkflowRequest(workspace, tmp_path / "data", "session", "generated")
    managed = destination / ".stm32-toolkit" / "generated-files.json"

    if case_id == "S2-B":
        managed.unlink()
        managed.mkdir()
        expected_code = "REGENERATION_OWNERSHIP_INVALID"
        expected_message = "Toolkit managed manifest is unavailable"
        expected_details = {}
    elif case_id == "S2-C":
        oversized = b"x" * (MAX_RECORD_BYTES + 1)
        managed.write_bytes(oversized)
        expected_code = "REGENERATION_OWNERSHIP_INVALID"
        expected_message = "Toolkit managed manifest is unavailable"
        expected_details = {}
    elif case_id == "S2-F":
        nested = destination / "App"
        for index in range(32):
            nested = nested / f"d{index:02d}"
            nested.mkdir()
        expected_code = "REGENERATION_PATH_UNSAFE"
        expected_message = "project path exceeds its bound"
        expected_details = {}
    else:
        raise AssertionError(f"unknown scan case: {case_id}")

    before_project = _tree_state(destination)
    before_data = _tree_state(tmp_path / "data")
    result = plan_regeneration(request, environment=environment)

    assert result.ok is False
    assert result.operation == "project-regenerate-plan"
    assert result.code == expected_code
    assert result.message == expected_message
    assert result.details == expected_details
    assert _tree_state(destination) == before_project
    assert _tree_state(tmp_path / "data") == before_data
    if case_id == "S2-B":
        assert managed.is_dir()
    elif case_id == "S2-C":
        assert managed.read_bytes() == oversized
    else:
        assert nested.is_dir()


@pytest.mark.parametrize(
    "case_id",
    [
        pytest.param("S3-A", id="S3-A"),
        pytest.param("S3-B", id="S3-B"),
        pytest.param("S3-C", id="S3-C"),
        pytest.param("S3-G", id="S3-G"),
    ],
)
def test_inventory_bounds(tmp_path: Path, case_id: str):
    workspace, destination, environment = _persisted_project(tmp_path)
    request = RegenerationWorkflowRequest(workspace, tmp_path / "data", "session", "generated")

    if case_id == "S3-A":
        artifact = destination / "build" / "artifacts.bin"
        artifact.parent.mkdir()
        artifact.write_bytes(b"derived bytes")
    elif case_id == "S3-B":
        unknown_file = destination / "README.local"
        unknown_file.write_bytes(b"unknown bytes")
    elif case_id == "S3-C":
        unknown_directory = destination / "unknown-dir"
        unknown_directory.mkdir()
    elif case_id == "S3-G":
        sharp_s = destination / "App" / "ß.txt"
        double_s = destination / "App" / "ss.txt"
        try:
            sharp_s.write_bytes(b"sharp s")
            double_s.write_bytes(b"double s")
        except OSError as error:
            pytest.skip(f"filesystem cannot create distinct Unicode names: {error}")
        names = {path.name for path in (destination / "App").iterdir()}
        if not {"ß.txt", "ss.txt"}.issubset(names):
            pytest.skip("filesystem did not retain two distinct Unicode directory entries")
    else:
        raise AssertionError(f"unknown inventory case: {case_id}")

    before_project = _tree_state(destination)
    before_data = _tree_state(tmp_path / "data")
    if case_id == "S3-A":
        snapshot = classify_regeneration_project(request)
        inventory = {entry.path: entry.ownership for entry in snapshot.inventory}
        assert inventory["build"] == "derived"
        assert inventory["build/artifacts.bin"] == "derived"
        result = plan_regeneration(request, environment=environment)
        assert result.ok is True
        assert result.operation == "project-regenerate-plan"
        assert result.code == "OK"
        assert result.message == ""
        assert result.data["blockers"] == ()
        assert artifact.read_bytes() == b"derived bytes"
    else:
        result = plan_regeneration(request, environment=environment)
        assert result.ok is False
        assert result.operation == "project-regenerate-plan"
        assert result.code == (
            "REGENERATION_PATH_UNSAFE" if case_id == "S3-G" else "REGENERATION_UNKNOWN_PATH"
        )
        assert result.message == (
            "project contains a case-fold path collision"
            if case_id == "S3-G"
            else "project contains an unknown path"
        )
        expected_path = "App/ß.txt" if case_id == "S3-G" else (
            "README.local" if case_id == "S3-B" else "unknown-dir"
        )
        assert result.details == {"path": expected_path}
        if case_id == "S3-C":
            assert unknown_directory.is_dir()

    assert _tree_state(destination) == before_project
    assert _tree_state(tmp_path / "data") == before_data


def test_public_preview_omits_oversized_unified_diff_with_real_file_hashes(tmp_path: Path):
    before_root = tmp_path / "before"
    after_root = tmp_path / "after"
    before_root.mkdir()
    after_root.mkdir()
    before_workspace, before_destination, _ = _persisted_project(before_root)
    after_workspace, after_destination, _ = _persisted_project(after_root)
    before_bytes = b"a\n" * 20_000
    after_bytes = b"b\n" * 20_000
    (before_destination / "App" / "diff.txt").write_bytes(before_bytes)
    (after_destination / "App" / "diff.txt").write_bytes(after_bytes)
    before_request = RegenerationWorkflowRequest(
        before_workspace, tmp_path / "before-data", "session", "generated"
    )
    after_request = RegenerationWorkflowRequest(
        after_workspace, tmp_path / "after-data", "session", "generated"
    )
    before_project = _tree_state(before_destination)
    after_project = _tree_state(after_destination)
    before_data = _tree_state(tmp_path / "before-data")
    after_data = _tree_state(tmp_path / "after-data")

    before_snapshot = classify_regeneration_project(before_request)
    after_snapshot = classify_regeneration_project(after_request)
    preview = build_regeneration_preview(before_snapshot, after_snapshot)

    change = next(item for item in preview.changes if item.path == "App/diff.txt")
    assert len(before_bytes) <= MAX_DIFF_BYTES
    assert len(after_bytes) <= MAX_DIFF_BYTES
    assert change.unified_diff is None
    assert change.before_size == len(before_bytes)
    assert change.after_size == len(after_bytes)
    assert change.before_sha256 == sha256_hex(before_bytes)
    assert change.after_sha256 == sha256_hex(after_bytes)
    assert _tree_state(before_destination) == before_project
    assert _tree_state(after_destination) == after_project
    assert _tree_state(tmp_path / "before-data") == before_data
    assert _tree_state(tmp_path / "after-data") == after_data


@pytest.mark.parametrize(
    "case_id",
    [
        pytest.param("S4-A", id="S4-A"),
        pytest.param("S4-B", id="S4-B"),
        pytest.param("S4-C", id="S4-C"),
        pytest.param("S4-D", id="S4-D"),
        pytest.param("S4-E", id="S4-E"),
        pytest.param("S4-F", id="S4-F"),
        pytest.param("S4-G", id="S4-G"),
        pytest.param("S4-H", id="S4-H"),
        pytest.param("S4-I", id="S4-I"),
        pytest.param("S4-J", id="S4-J"),
        pytest.param("S4-K", id="S4-K"),
        pytest.param("S4-L", id="S4-L"),
        pytest.param("S4-M", id="S4-M"),
    ],
)


def test_regeneration_plan_rejects_selected_persisted_manifest_mutations(tmp_path: Path, case_id: str):
    workspace, destination, environment = _persisted_project(tmp_path)
    request = RegenerationWorkflowRequest(workspace, tmp_path / "data", "session", "generated")
    baseline = plan_regeneration(request, environment=environment)
    assert baseline.ok is True
    assert baseline.data["blockers"] == ()
    before_data = _tree_state(tmp_path / "data")
    manifest_path, mutated_bytes, expected_code, expected_message = _mutate_s4_manifest(destination, case_id)
    assert manifest_path.read_bytes() == mutated_bytes
    after_mutation_project = _tree_state(destination)
    after_mutation_data = _tree_state(tmp_path / "data")

    result = plan_regeneration(request, environment=environment)

    assert result.code == expected_code
    assert result.message == expected_message
    assert manifest_path.read_bytes() == mutated_bytes
    assert _tree_state(destination) == after_mutation_project
    assert _tree_state(tmp_path / "data") == after_mutation_data == before_data
