import json
import os
import shutil
from pathlib import Path
from uuid import UUID

import pytest

from stm32_toolkit.build.identity import (
    ElfEvidence,
    GitEvidence,
    build_identity,
    git_evidence,
    sha256_file,
    snapshot_inputs,
    write_json_atomic,
    write_text_atomic,
)
from stm32_toolkit.build.model import MemoryUsage
from stm32_toolkit.context import build_project_context
from stm32_toolkit.identity import compute_workspace_id
from stm32_toolkit.process import ProcessRequest, run_process
from stm32_toolkit.project_model import load_project_model

FIXTURE_MINIMAL_GCC = Path(__file__).parent / "fixtures" / "minimal-gcc"
_MAX_ARTIFACT_BYTES = 64 * 1024 * 1024


def _git(command: str, cwd: Path, *args: str) -> None:
    result = run_process(
        ProcessRequest(argv=("git", command, *args), cwd=cwd, timeout_seconds=15.0)
    )
    assert result.returncode == 0


def _git_commit(cwd: Path, message: str) -> None:
    result = run_process(
        ProcessRequest(
            argv=(
                "git",
                "-c",
                "user.name=test",
                "-c",
                "user.email=test@example.com",
                "commit",
                "-m",
                message,
            ),
            cwd=cwd,
            timeout_seconds=15.0,
        )
    )
    assert result.returncode == 0


@pytest.fixture
def evidence_project(tmp_path: Path) -> Path:
    """A Schema v2 minimal project in a real Git repository."""
    root = tmp_path / "project"
    shutil.copytree(FIXTURE_MINIMAL_GCC, root)
    _git("init", root, "-b", "main")
    _git("add", root, ".")
    _git_commit(root, "initial")
    return root


def _publish_evidence_chain(
    root: Path,
    *,
    preset: str = "arm-debug",
    built_at_utc: str = "2026-08-06T06:58:00Z",
) -> None:
    """Publish log -> identity -> result exactly like the build runner."""
    model = load_project_model(root)
    elf_relative = model.build.elf
    map_relative = str(Path(elf_relative).with_suffix(".map"))
    elf_absolute = root / elf_relative
    map_absolute = root / map_relative
    elf_absolute.parent.mkdir(parents=True, exist_ok=True)
    elf_absolute.write_bytes(b"\x7fELF fake artifact\n")
    map_absolute.write_text("fake map evidence\n", encoding="utf-8")
    elf_sha256, elf_size = sha256_file(elf_absolute, _MAX_ARTIFACT_BYTES, "elfSize")
    map_sha256, map_size = sha256_file(map_absolute, _MAX_ARTIFACT_BYTES, "mapSize")
    git = git_evidence(root)
    assert git.head is not None
    identity = build_identity(
        preset=preset,
        clean_first=False,
        git=GitEvidence(git.head, git.branch, git.target),
        snapshot=snapshot_inputs(root, model),
        elf_path=elf_relative,
        elf_sha256=elf_sha256,
        elf_size=elf_size,
        map_path=map_relative,
        map_sha256=map_sha256,
        map_size=map_size,
        elf_evidence=ElfEvidence(
            entry_point=0x08000401,
            isr_vector_present=True,
            reset_handler_present=True,
            reset_handler_address=0x08000401,
            entry_point_consistent=True,
            undefined_symbols=(),
        ),
        memory_usage=(MemoryUsage("FLASH", 0x08000000, 0x100000, 0x6D0, 0.17),),
        built_at_utc=built_at_utc,
    )
    output = root / ".stm32-toolkit" / "build" / preset
    write_text_atomic(output / "build.log", "=== configure stdout ===\nfake\n")
    write_json_atomic(output / "firmware-identity.json", identity.to_dict())
    write_json_atomic(
        output / "build-result.json",
        {
            "schemaVersion": 1,
            "status": "success",
            "preset": preset,
            "cleanFirst": False,
            "buildId": identity.build_id,
            "builtAtUtc": built_at_utc,
            "returncode": 0,
            "timedOut": False,
            "durationSeconds": 1.0,
            "elf": {"path": elf_relative, "sha256": elf_sha256, "size": elf_size},
            "map": {"path": map_relative, "sha256": map_sha256, "size": map_size},
            "logPath": f".stm32-toolkit/build/{preset}/build.log",
            "identityPath": f".stm32-toolkit/build/{preset}/firmware-identity.json",
            "resultPath": f".stm32-toolkit/build/{preset}/build-result.json",
        },
    )


def _context_build(root: Path, tmp_path: Path) -> dict:
    result = build_project_context(root, tmp_path.parent / "data", "session-a")
    assert result.ok is True
    return result.to_dict()["data"]["build"]


def test_configured_context_reports_only_the_six_contract_sections(
    configured_project: Path, tmp_path: Path
):
    result = build_project_context(configured_project, tmp_path.parent / "data", "session-a")

    assert result.to_dict() == {
        "protocol": "stm32-toolkit/1",
        "ok": True,
        "operation": "project.context",
        "code": "OK",
        "message": "",
        "data": {
            "project": {
                "kind": "configured",
                "root": str(configured_project),
                "logicalProjectId": "12345678-1234-5678-1234-567812345678",
                "target": "STM32F429ZGTx",
                "framework": "spl",
            },
            "workspace": {
                "workspaceId": compute_workspace_id(
                    UUID("12345678-1234-5678-1234-567812345678"), configured_project
                ),
                "sessionId": "session-a",
            },
            "build": {
                "cmakeListsPresent": True,
                "elfPath": str(configured_project / "build-fw" / "firmware.elf"),
                "elfExists": True,
                "existingSourcePaths": [str(configured_project / "App" / "main.c")],
                "missingSourcePaths": [],
                "elfFresh": False,
            },
            "hardware": {"probe": None, "state": "unavailable"},
            "capabilities": {
                "build": True,
                "flash": False,
                "hostTest": False,
                "targetTest": False,
                "monitor": False,
                "breakpointDebug": False,
            },
            "recommendedActions": [],
        },
        "details": {},
    }
    assert (tmp_path.parent / "data" / "projects" / result.data["workspace"]["workspaceId"] / "sessions" / "session-a").is_dir()


def test_keil_context_stays_read_only_without_a_logical_project_id(tmp_path: Path):
    (tmp_path / "legacy.uvprojx").write_text("<Project/>", encoding="utf-8")
    data_root = tmp_path / "data"

    result = build_project_context(tmp_path, data_root, "session-a")

    assert result.ok is True
    assert result.to_dict()["data"] == {
        "project": {
            "kind": "keil",
            "root": str(tmp_path),
            "files": ["legacy.uvprojx"],
            "recommendedAction": {
                "id": "migrate-keil",
                "available": False,
                "explanation": "Keil migration is planned but unavailable in this foundation release.",
            },
        },
        "workspace": None,
        "build": {
            "cmakeListsPresent": False,
            "elfPath": None,
            "elfExists": False,
            "existingSourcePaths": [],
            "missingSourcePaths": [],
            "elfFresh": False,
        },
        "hardware": {"probe": None, "state": "unavailable"},
        "capabilities": {
            "build": False,
            "flash": False,
            "hostTest": False,
            "targetTest": False,
            "monitor": False,
            "breakpointDebug": False,
        },
        "recommendedActions": [{
            "id": "migrate-keil",
            "available": False,
            "explanation": (
                "Keil migration is planned but unavailable in this foundation release."
            ),
        }],
    }
    assert not data_root.exists()


def test_missing_manifest_source_keeps_an_existing_elf_stale(
    configured_project: Path, tmp_path: Path
):
    manifest_path = configured_project / ".stm32-project.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["build"]["sources"].append("App/missing.c")
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    result = build_project_context(configured_project, tmp_path.parent / "data", "session-a")

    assert result.ok is True
    assert result.to_dict()["data"]["build"] == {
        "cmakeListsPresent": True,
        "elfPath": str(configured_project / "build-fw" / "firmware.elf"),
        "elfExists": True,
        "existingSourcePaths": [str(configured_project / "App" / "main.c")],
        "missingSourcePaths": [str(configured_project / "App" / "missing.c")],
        "elfFresh": False,
    }


def test_mtime_freshness_is_ignored_without_evidence_chain(
    configured_project: Path, tmp_path: Path
):
    """Exit-0/mtime freshness is not proof: without a published evidence
    chain the ELF stays stale even when the ELF mtime is newest."""
    elf = configured_project / "build-fw" / "firmware.elf"
    source = configured_project / "App" / "main.c"
    os.utime(source, ns=(1_000_000_000, 1_000_000_000))
    os.utime(elf, ns=(9_000_000_000, 9_000_000_000))

    result = build_project_context(configured_project, tmp_path.parent / "data", "session-a")

    assert result.data["build"]["elfFresh"] is False


def test_evidence_chain_makes_elf_fresh(evidence_project: Path, tmp_path: Path):
    _publish_evidence_chain(evidence_project)

    build = _context_build(evidence_project, tmp_path)

    assert build["elfFresh"] is True
    assert build["elfExists"] is True
    assert build["missingSourcePaths"] == []


def test_evidence_chain_ignores_mtimes(evidence_project: Path, tmp_path: Path):
    _publish_evidence_chain(evidence_project)
    source = evidence_project / "Src" / "main.c"
    elf = evidence_project / "build" / "arm-debug" / "firmware.elf"
    os.utime(source, ns=(9_000_000_000, 9_000_000_000))
    os.utime(elf, ns=(1_000_000_000, 1_000_000_000))

    build = _context_build(evidence_project, tmp_path)

    assert build["elfFresh"] is True


def test_changed_source_content_breaks_evidence_chain(
    evidence_project: Path, tmp_path: Path
):
    _publish_evidence_chain(evidence_project)
    (evidence_project / "Src" / "main.c").write_text(
        "int main(void) { return 2; }\n", encoding="utf-8"
    )

    build = _context_build(evidence_project, tmp_path)

    assert build["elfFresh"] is False


def test_changed_assembly_content_breaks_evidence_chain(
    evidence_project: Path, tmp_path: Path
):
    _publish_evidence_chain(evidence_project)
    (evidence_project / "Startup" / "startup.s").write_text(
        "; changed\n", encoding="utf-8"
    )

    build = _context_build(evidence_project, tmp_path)

    assert build["elfFresh"] is False


def test_new_git_commit_breaks_evidence_chain(evidence_project: Path, tmp_path: Path):
    _publish_evidence_chain(evidence_project)
    (evidence_project / "README.md").write_text("readme\n", encoding="utf-8")
    _git("add", evidence_project, "README.md")
    _git_commit(evidence_project, "readme")

    build = _context_build(evidence_project, tmp_path)

    assert build["elfFresh"] is False


def test_tampered_elf_breaks_evidence_chain(evidence_project: Path, tmp_path: Path):
    _publish_evidence_chain(evidence_project)
    (evidence_project / "build" / "arm-debug" / "firmware.elf").write_bytes(
        b"tampered bytes"
    )

    build = _context_build(evidence_project, tmp_path)

    assert build["elfFresh"] is False


def test_missing_elf_breaks_evidence_chain(evidence_project: Path, tmp_path: Path):
    _publish_evidence_chain(evidence_project)
    (evidence_project / "build" / "arm-debug" / "firmware.elf").unlink()

    build = _context_build(evidence_project, tmp_path)

    assert build["elfFresh"] is False
    assert build["elfExists"] is False


def test_missing_result_commit_point_breaks_evidence_chain(
    evidence_project: Path, tmp_path: Path
):
    _publish_evidence_chain(evidence_project)
    (
        evidence_project
        / ".stm32-toolkit"
        / "build"
        / "arm-debug"
        / "build-result.json"
    ).unlink()

    build = _context_build(evidence_project, tmp_path)

    assert build["elfFresh"] is False


def test_missing_identity_breaks_evidence_chain(evidence_project: Path, tmp_path: Path):
    _publish_evidence_chain(evidence_project)
    (
        evidence_project
        / ".stm32-toolkit"
        / "build"
        / "arm-debug"
        / "firmware-identity.json"
    ).unlink()

    build = _context_build(evidence_project, tmp_path)

    assert build["elfFresh"] is False


def test_tampered_identity_breaks_evidence_chain(evidence_project: Path, tmp_path: Path):
    _publish_evidence_chain(evidence_project)
    identity_path = (
        evidence_project
        / ".stm32-toolkit"
        / "build"
        / "arm-debug"
        / "firmware-identity.json"
    )
    identity = json.loads(identity_path.read_text(encoding="utf-8"))
    identity["gitHead"] = "0" * 40
    identity_path.write_text(json.dumps(identity), encoding="utf-8")

    build = _context_build(evidence_project, tmp_path)

    assert build["elfFresh"] is False


def test_no_evidence_chain_is_stale(evidence_project: Path, tmp_path: Path):
    build = _context_build(evidence_project, tmp_path)

    assert build["elfFresh"] is False


def test_invalid_configured_manifest_returns_its_stable_error_without_data_directories(
    tmp_path: Path, copy_fixture
):
    copy_fixture("invalid-project.json", tmp_path / ".stm32-project.json")
    data_root = tmp_path / "data"

    result = build_project_context(tmp_path, data_root, "session-a")

    assert result.to_dict() == {
        "protocol": "stm32-toolkit/1",
        "ok": False,
        "operation": "project.context",
        "code": "PROJECT_SCHEMA_INVALID",
        "message": "Project manifest does not satisfy schema version 1",
        "data": None,
        "details": {"field": "logicalProjectId", "rule": "required"},
    }
    assert not data_root.exists()


def test_cmakelists_directory_does_not_enable_build(configured_project: Path, tmp_path: Path):
    (configured_project / "CMakeLists.txt").unlink()
    (configured_project / "CMakeLists.txt").mkdir()

    result = build_project_context(configured_project, tmp_path.parent / "data", "session-a")

    assert result.ok is True
    assert result.data["build"]["cmakeListsPresent"] is False
    assert result.data["capabilities"]["build"] is False

@pytest.mark.parametrize("data_root_name", ["", "plugin-data"])
def test_data_root_at_or_inside_project_is_rejected_without_creating_project_entries(
    configured_project: Path, data_root_name: str
):
    data_root = configured_project / data_root_name
    before = {path.relative_to(configured_project) for path in configured_project.rglob("*")}

    result = build_project_context(configured_project, data_root, "session-a")

    assert result.to_dict() == {
        "protocol": "stm32-toolkit/1",
        "ok": False,
        "operation": "project.context",
        "code": "PROJECT_CONTEXT_INVALID",
        "message": "Project context parameters are invalid",
        "data": None,
        "details": {"field": "dataRoot", "path": str(data_root)},
    }
    assert {path.relative_to(configured_project) for path in configured_project.rglob("*")} == before


def test_invalid_project_root_returns_a_stable_context_failure(tmp_path: Path):
    project_root = Path(chr(0))
    data_root = tmp_path / "data"

    result = build_project_context(project_root, data_root, "session-a")

    assert result.to_dict() == {
        "protocol": "stm32-toolkit/1",
        "ok": False,
        "operation": "project.context",
        "code": "PROJECT_CONTEXT_INVALID",
        "message": "Project context parameters are invalid",
        "data": None,
        "details": {"field": "projectRoot", "path": "\x00"},
    }
    assert not data_root.exists()


def test_invalid_session_id_identifies_the_session_field(configured_project: Path, tmp_path: Path):
    result = build_project_context(configured_project, tmp_path.parent / "data", "Session-A")

    assert result.to_dict() == {
        "protocol": "stm32-toolkit/1",
        "ok": False,
        "operation": "project.context",
        "code": "PROJECT_CONTEXT_INVALID",
        "message": "Project context parameters are invalid",
        "data": None,
        "details": {"field": "sessionId"},
    }


def test_detection_os_error_maps_to_stable_unavailable_context(monkeypatch, tmp_path: Path):
    """Catches filesystem discovery failures escaping the result envelope."""
    project_root = tmp_path / "project"
    project_root.mkdir()
    data_root = tmp_path / "data"

    def unavailable(path: Path):
        raise OSError("directory unavailable")

    monkeypatch.setattr("stm32_toolkit.context.detect_project", unavailable)

    result = build_project_context(project_root, data_root, "session-a")

    assert result.code == "PROJECT_CONTEXT_UNAVAILABLE"
    assert result.details == {"field": "projectRoot", "path": str(project_root)}
    assert not data_root.exists()


def test_workspace_creation_error_maps_to_data_root_without_project_mutation(
    monkeypatch, configured_project: Path, tmp_path: Path
):
    """Catches plugin-state creation errors leaking or mutating project files."""
    data_root = tmp_path.parent / "unavailable-data"
    before = {
        path.relative_to(configured_project): path.stat().st_mtime_ns
        for path in configured_project.rglob("*")
    }

    def unavailable(workspace) -> None:
        raise OSError("cannot create workspace")

    monkeypatch.setattr("stm32_toolkit.context.WorkspacePaths.ensure", unavailable)

    result = build_project_context(configured_project, data_root, "session-a")

    after = {
        path.relative_to(configured_project): path.stat().st_mtime_ns
        for path in configured_project.rglob("*")
    }
    assert result.code == "PROJECT_CONTEXT_UNAVAILABLE"
    assert result.details == {"field": "dataRoot", "path": str(data_root)}
    assert before == after
    assert not data_root.exists()


def test_missing_assembly_source_keeps_existing_elf_stale(
    configured_project: Path, tmp_path: Path
):
    manifest_path = configured_project / ".stm32-project.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["build"]["assemblySources"] = ["Startup/missing.s"]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    result = build_project_context(
        configured_project, tmp_path.parent / "data", "session-a"
    )

    assert result.ok is True
    assert result.data["build"]["missingSourcePaths"] == (
        str(configured_project / "Startup" / "missing.s"),
    )
    assert result.data["build"]["elfFresh"] is False


def test_newer_assembly_source_breaks_evidence_chain(
    evidence_project: Path, tmp_path: Path
):
    """A changed assembly input invalidates the input snapshot digest."""
    _publish_evidence_chain(evidence_project)
    startup = evidence_project / "Startup" / "startup.s"
    os.utime(startup, ns=(9_000_000_000, 9_000_000_000))

    build = _context_build(evidence_project, tmp_path)

    assert str(startup) in build["existingSourcePaths"]
    assert build["elfFresh"] is True

    startup.write_text("Reset_Handler:\n  b .\n", encoding="utf-8")
    build = _context_build(evidence_project, tmp_path)
    assert build["elfFresh"] is False


def test_unreadable_source_breaks_evidence_chain(evidence_project: Path, tmp_path: Path):
    _publish_evidence_chain(evidence_project)
    os.chmod(evidence_project / "Src" / "main.c", 0o000)

    try:
        build = _context_build(evidence_project, tmp_path)
    finally:
        os.chmod(evidence_project / "Src" / "main.c", 0o644)

    assert build["elfFresh"] is False


def test_unreadable_elf_breaks_evidence_chain(evidence_project: Path, tmp_path: Path):
    _publish_evidence_chain(evidence_project)
    elf = evidence_project / "build" / "arm-debug" / "firmware.elf"
    os.chmod(elf, 0o000)

    try:
        build = _context_build(evidence_project, tmp_path)
    finally:
        os.chmod(elf, 0o644)

    assert build["elfFresh"] is False


def test_evidence_dir_as_file_breaks_evidence_chain(evidence_project: Path, tmp_path: Path):
    _publish_evidence_chain(evidence_project)
    build_root = evidence_project / ".stm32-toolkit" / "build"
    import shutil as _shutil

    _shutil.rmtree(build_root)
    build_root.write_text("file", encoding="utf-8")

    build = _context_build(evidence_project, tmp_path)

    assert build["elfFresh"] is False


def test_tampered_identity_schema_version_breaks_evidence_chain(
    evidence_project: Path, tmp_path: Path
):
    _publish_evidence_chain(evidence_project)
    identity_path = (
        evidence_project
        / ".stm32-toolkit"
        / "build"
        / "arm-debug"
        / "firmware-identity.json"
    )
    identity = json.loads(identity_path.read_text(encoding="utf-8"))
    identity["schemaVersion"] = 2
    identity_path.write_text(json.dumps(identity), encoding="utf-8")

    build = _context_build(evidence_project, tmp_path)

    assert build["elfFresh"] is False


def test_tampered_identity_elf_shape_breaks_evidence_chain(
    evidence_project: Path, tmp_path: Path
):
    _publish_evidence_chain(evidence_project)
    identity_path = (
        evidence_project
        / ".stm32-toolkit"
        / "build"
        / "arm-debug"
        / "firmware-identity.json"
    )
    identity = json.loads(identity_path.read_text(encoding="utf-8"))
    identity["elf"] = "not-a-dict"
    identity_path.write_text(json.dumps(identity), encoding="utf-8")

    build = _context_build(evidence_project, tmp_path)

    assert build["elfFresh"] is False


def test_tampered_identity_snapshot_shape_breaks_evidence_chain(
    evidence_project: Path, tmp_path: Path
):
    _publish_evidence_chain(evidence_project)
    identity_path = (
        evidence_project
        / ".stm32-toolkit"
        / "build"
        / "arm-debug"
        / "firmware-identity.json"
    )
    identity = json.loads(identity_path.read_text(encoding="utf-8"))
    identity["inputSnapshot"] = ["not", "a", "dict"]
    identity_path.write_text(json.dumps(identity), encoding="utf-8")

    build = _context_build(evidence_project, tmp_path)

    assert build["elfFresh"] is False


def test_tampered_identity_elf_path_breaks_evidence_chain(
    evidence_project: Path, tmp_path: Path
):
    _publish_evidence_chain(evidence_project)
    identity_path = (
        evidence_project
        / ".stm32-toolkit"
        / "build"
        / "arm-debug"
        / "firmware-identity.json"
    )
    identity = json.loads(identity_path.read_text(encoding="utf-8"))
    identity["elf"]["path"] = "other/firmware.elf"
    identity_path.write_text(json.dumps(identity), encoding="utf-8")

    build = _context_build(evidence_project, tmp_path)

    assert build["elfFresh"] is False


def test_tampered_identity_map_path_breaks_evidence_chain(
    evidence_project: Path, tmp_path: Path
):
    _publish_evidence_chain(evidence_project)
    identity_path = (
        evidence_project
        / ".stm32-toolkit"
        / "build"
        / "arm-debug"
        / "firmware-identity.json"
    )
    identity = json.loads(identity_path.read_text(encoding="utf-8"))
    identity["map"]["path"] = "other/firmware.map"
    identity_path.write_text(json.dumps(identity), encoding="utf-8")

    build = _context_build(evidence_project, tmp_path)

    assert build["elfFresh"] is False


def test_tampered_identity_elf_size_breaks_evidence_chain(
    evidence_project: Path, tmp_path: Path
):
    _publish_evidence_chain(evidence_project)
    identity_path = (
        evidence_project
        / ".stm32-toolkit"
        / "build"
        / "arm-debug"
        / "firmware-identity.json"
    )
    identity = json.loads(identity_path.read_text(encoding="utf-8"))
    identity["elf"]["size"] = identity["elf"]["size"] + 1
    identity_path.write_text(json.dumps(identity), encoding="utf-8")

    build = _context_build(evidence_project, tmp_path)

    assert build["elfFresh"] is False


def test_other_preset_result_does_not_masquerade_as_model_elf(
    evidence_project: Path, tmp_path: Path
):
    _publish_evidence_chain(evidence_project, preset="arm-release")
    _publish_evidence_chain(evidence_project)

    build = _context_build(evidence_project, tmp_path)

    assert build["elfFresh"] is True


def test_failed_result_status_breaks_evidence_chain(evidence_project: Path, tmp_path: Path):
    _publish_evidence_chain(evidence_project)
    result_path = (
        evidence_project
        / ".stm32-toolkit"
        / "build"
        / "arm-debug"
        / "build-result.json"
    )
    result = json.loads(result_path.read_text(encoding="utf-8"))
    result["status"] = "failed"
    result_path.write_text(json.dumps(result), encoding="utf-8")

    build = _context_build(evidence_project, tmp_path)

    assert build["elfFresh"] is False


def test_result_preset_mismatch_breaks_evidence_chain(evidence_project: Path, tmp_path: Path):
    _publish_evidence_chain(evidence_project)
    result_path = (
        evidence_project
        / ".stm32-toolkit"
        / "build"
        / "arm-debug"
        / "build-result.json"
    )
    result = json.loads(result_path.read_text(encoding="utf-8"))
    result["preset"] = "arm-other"
    result_path.write_text(json.dumps(result), encoding="utf-8")

    build = _context_build(evidence_project, tmp_path)

    assert build["elfFresh"] is False


def test_result_build_id_mismatch_breaks_evidence_chain(evidence_project: Path, tmp_path: Path):
    _publish_evidence_chain(evidence_project)
    result_path = (
        evidence_project
        / ".stm32-toolkit"
        / "build"
        / "arm-debug"
        / "build-result.json"
    )
    result = json.loads(result_path.read_text(encoding="utf-8"))
    result["buildId"] = "0" * 64
    result_path.write_text(json.dumps(result), encoding="utf-8")

    build = _context_build(evidence_project, tmp_path)

    assert build["elfFresh"] is False


def test_tampered_map_breaks_evidence_chain(evidence_project: Path, tmp_path: Path):
    _publish_evidence_chain(evidence_project)
    (evidence_project / "build" / "arm-debug" / "firmware.map").write_text(
        "tampered map\n", encoding="utf-8"
    )

    build = _context_build(evidence_project, tmp_path)

    assert build["elfFresh"] is False


def test_non_string_identity_elf_path_breaks_evidence_chain(
    evidence_project: Path, tmp_path: Path
):
    _publish_evidence_chain(evidence_project)
    identity_path = (
        evidence_project
        / ".stm32-toolkit"
        / "build"
        / "arm-debug"
        / "firmware-identity.json"
    )
    identity = json.loads(identity_path.read_text(encoding="utf-8"))
    identity["elf"]["path"] = 123
    identity_path.write_text(json.dumps(identity), encoding="utf-8")

    build = _context_build(evidence_project, tmp_path)

    assert build["elfFresh"] is False
