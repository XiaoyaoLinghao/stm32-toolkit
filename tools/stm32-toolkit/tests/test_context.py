"""Evidence-backed project context freshness (STM32TK-0305).

``elfFresh`` is true only when the complete evidence chain is consistent:
a published success build-result, a schema-valid identity with an
independently recomputed build ID, current Git HEAD, target, preset, input
snapshot, and ELF/MAP digests.  Missing, malformed, failure, unreadable,
mismatched, or oversized evidence fails closed to ``False``; mtimes are
never consulted.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from uuid import UUID

import pytest

from stm32_toolkit.build import BuildRequest, run_build
from stm32_toolkit.build import identity as identity_mod
from stm32_toolkit.context import build_project_context
from stm32_toolkit.identity import compute_workspace_id

from test_build_runner import install_fake_cmake, prepare_project


def raise_on_open(path: Path, monkeypatch: pytest.MonkeyPatch, error: OSError) -> None:
    """Make ``Path.open`` raise ``error`` for ``path`` (platform-independent)."""
    real_open = Path.open

    def patched(self, mode: str = "r", *args, **kwargs):
        if mode == "rb" and self == path:
            raise error
        return real_open(self, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", patched)


def build_successfully(root: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    install_fake_cmake(monkeypatch, tmp_path)
    result = run_build(BuildRequest(project_root=root, preset="arm-debug"))
    assert result.ok is True
    return result


EMPTY_FRESHNESS = {
    "buildId": None,
    "elfSha256": None,
    "preset": None,
    "gitHead": None,
    "identityPath": None,
    "buildResultPath": None,
    "buildLogPath": None,
}


def test_configured_context_reports_evidence_sections_without_build(
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
                **EMPTY_FRESHNESS,
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
            **EMPTY_FRESHNESS,
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


def test_missing_manifest_source_keeps_evidence_stale(
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
        **EMPTY_FRESHNESS,
    }


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


def test_newer_assembly_source_without_evidence_is_stale(
    configured_project: Path, tmp_path: Path
):
    startup = configured_project / "Startup" / "startup.s"
    startup.parent.mkdir()
    startup.write_text("Reset_Handler:\n", encoding="utf-8")
    manifest_path = configured_project / ".stm32-project.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["build"]["assemblySources"] = ["Startup/startup.s"]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    elf = configured_project / "build-fw" / "firmware.elf"
    os.utime(elf, ns=(1_000_000_000, 1_000_000_000))
    os.utime(startup, ns=(2_000_000_000, 2_000_000_000))

    result = build_project_context(
        configured_project, tmp_path.parent / "data", "session-a"
    )

    assert result.ok is True
    assert str(startup) in result.data["build"]["existingSourcePaths"]
    assert result.data["build"]["elfFresh"] is False


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
    assert result.data["build"]["elfFresh"] is False
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


# ---------------------------------------------------------------------------
# evidence-backed freshness
# ---------------------------------------------------------------------------


def test_context_fresh_after_successful_build(tmp_path: Path, monkeypatch):
    root = prepare_project(tmp_path)
    build = build_successfully(root, monkeypatch, tmp_path)

    result = build_project_context(root, tmp_path.parent / "data", "session-a")

    assert result.ok is True
    evidence = result.data["build"]
    assert evidence["elfFresh"] is True
    assert evidence["preset"] == "arm-debug"
    assert evidence["buildId"] == build.data.identity.build_id
    assert evidence["elfSha256"] == build.data.identity.elf_sha256
    assert evidence["gitHead"] == build.data.identity.git_head
    assert evidence["identityPath"] == "build/arm-debug/firmware-identity.json"
    assert evidence["buildResultPath"] == "artifacts/migration/build-result.json"
    assert evidence["buildLogPath"] == "artifacts/migration/build.log"
    assert evidence["elfExists"] is True
    assert evidence["missingSourcePaths"] == ()


def test_context_stale_after_source_change(tmp_path: Path, monkeypatch):
    root = prepare_project(tmp_path)
    build_successfully(root, monkeypatch, tmp_path)
    (root / "Src" / "main.c").write_text("int main(void) { return 7; }\n", encoding="utf-8")

    result = build_project_context(root, tmp_path.parent / "data", "session-a")

    assert result.data["build"]["elfFresh"] is False


def test_context_stale_after_elf_replaced(tmp_path: Path, monkeypatch):
    root = prepare_project(tmp_path)
    build_successfully(root, monkeypatch, tmp_path)
    elf_path = root / "build" / "arm-debug" / "firmware.elf"
    elf_path.write_bytes(b"tampered ELF bytes")

    result = build_project_context(root, tmp_path.parent / "data", "session-a")

    assert result.data["build"]["elfFresh"] is False


def test_context_stale_after_git_head_changes(tmp_path: Path, monkeypatch):
    from test_build_runner import git

    root = prepare_project(tmp_path)
    build_successfully(root, monkeypatch, tmp_path)
    git("commit", "-q", "--allow-empty", "-m", "move head", cwd=root)

    result = build_project_context(root, tmp_path.parent / "data", "session-a")

    assert result.data["build"]["elfFresh"] is False


def test_context_stale_after_identity_tampered(tmp_path: Path, monkeypatch):
    root = prepare_project(tmp_path)
    build_successfully(root, monkeypatch, tmp_path)
    identity_path = root / "build" / "arm-debug" / "firmware-identity.json"
    document = json.loads(identity_path.read_text(encoding="utf-8"))
    document["buildId"] = "0" * 64
    identity_path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")

    result = build_project_context(root, tmp_path.parent / "data", "session-a")

    assert result.data["build"]["elfFresh"] is False


def test_context_stale_after_record_tampered(tmp_path: Path, monkeypatch):
    root = prepare_project(tmp_path)
    build_successfully(root, monkeypatch, tmp_path)
    record_path = root / "artifacts" / "migration" / "build-result.json"
    record = json.loads(record_path.read_text(encoding="utf-8"))
    record["status"] = "failure"
    record_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")

    result = build_project_context(root, tmp_path.parent / "data", "session-a")

    assert result.data["build"]["elfFresh"] is False


def test_context_stale_after_failed_build_supersedes_old_success(
    tmp_path: Path, monkeypatch
):
    root = prepare_project(tmp_path)
    build_successfully(root, monkeypatch, tmp_path)
    monkeypatch.setenv("FAKE_CMAKE_EXIT", "5")
    failed = run_build(BuildRequest(project_root=root, preset="arm-debug"))
    assert failed.ok is False

    result = build_project_context(root, tmp_path.parent / "data", "session-a")

    assert result.data["build"]["elfFresh"] is False
    assert result.data["build"]["buildId"] is None


def test_context_stale_on_malformed_record(tmp_path: Path, monkeypatch):
    root = prepare_project(tmp_path)
    build_successfully(root, monkeypatch, tmp_path)
    record_path = root / "artifacts" / "migration" / "build-result.json"
    record_path.write_bytes(b"{broken")

    result = build_project_context(root, tmp_path.parent / "data", "session-a")

    assert result.data["build"]["elfFresh"] is False


def test_context_stale_on_unreadable_record(tmp_path: Path, monkeypatch):
    root = prepare_project(tmp_path)
    build_successfully(root, monkeypatch, tmp_path)
    record_path = root / "artifacts" / "migration" / "build-result.json"
    raise_on_open(record_path, monkeypatch, PermissionError("injected"))

    result = build_project_context(root, tmp_path.parent / "data", "session-a")

    assert result.data["build"]["elfFresh"] is False


def test_context_ignores_release_evidence_for_debug_freshness(
    tmp_path: Path, monkeypatch
):
    root = prepare_project(tmp_path)
    install_fake_cmake(monkeypatch, tmp_path)
    release = run_build(BuildRequest(project_root=root, preset="arm-release"))
    assert release.ok is True

    result = build_project_context(root, tmp_path.parent / "data", "session-a")

    assert result.data["build"]["elfFresh"] is False
    assert result.data["build"]["preset"] is None


def test_context_unreadable_evidence_fails_closed_without_error(tmp_path: Path, monkeypatch):
    root = prepare_project(tmp_path)
    build_successfully(root, monkeypatch, tmp_path)
    real_read = identity_mod._read_limited

    def selective(path, limit):
        if Path(path).name == "firmware-identity.json":
            raise PermissionError("injected permission failure")
        return real_read(path, limit)

    monkeypatch.setattr(identity_mod, "_read_limited", selective)
    result = build_project_context(root, tmp_path.parent / "data", "session-a")
    assert result.ok is True
    assert result.data["build"]["elfFresh"] is False


def test_context_stale_when_model_elf_is_not_standard(tmp_path: Path, monkeypatch):
    root = prepare_project(tmp_path)
    build_successfully(root, monkeypatch, tmp_path)
    from test_build_runner import git

    payload = json.loads((root / ".stm32-project.json").read_text(encoding="utf-8"))
    payload["build"]["elf"] = "build-fw/firmware.elf"
    (root / ".stm32-project.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    git("add", "-A", cwd=root)
    git("commit", "-q", "-m", "non-standard elf", cwd=root)

    result = build_project_context(root, tmp_path.parent / "data", "session-a")

    assert result.data["build"]["elfFresh"] is False


def test_context_stale_when_model_elf_basename_invalid(tmp_path: Path, monkeypatch):
    root = prepare_project(tmp_path)
    build_successfully(root, monkeypatch, tmp_path)
    from test_build_runner import git

    payload = json.loads((root / ".stm32-project.json").read_text(encoding="utf-8"))
    payload["build"]["elf"] = "build/arm-debug/weird"
    (root / ".stm32-project.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    git("add", "-A", cwd=root)
    git("commit", "-q", "-m", "invalid elf basename", cwd=root)

    result = build_project_context(root, tmp_path.parent / "data", "session-a")

    assert result.data["build"]["elfFresh"] is False


def test_context_stale_when_record_preset_mismatched(tmp_path: Path, monkeypatch):
    root = prepare_project(tmp_path)
    build_successfully(root, monkeypatch, tmp_path)
    record_path = root / "artifacts" / "migration" / "build-result.json"
    record = json.loads(record_path.read_text(encoding="utf-8"))
    record["preset"] = "arm-release"
    record_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")

    result = build_project_context(root, tmp_path.parent / "data", "session-a")

    assert result.data["build"]["elfFresh"] is False


def test_context_stale_when_record_target_mismatched(tmp_path: Path, monkeypatch):
    root = prepare_project(tmp_path)
    build_successfully(root, monkeypatch, tmp_path)
    record_path = root / "artifacts" / "migration" / "build-result.json"
    record = json.loads(record_path.read_text(encoding="utf-8"))
    record["targetDevice"] = "STM32F429ZGTx"
    record_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")

    result = build_project_context(root, tmp_path.parent / "data", "session-a")

    assert result.data["build"]["elfFresh"] is False


def test_context_stale_when_record_and_identity_disagree(tmp_path: Path, monkeypatch):
    root = prepare_project(tmp_path)
    build_successfully(root, monkeypatch, tmp_path)
    identity_path = root / "build" / "arm-debug" / "firmware-identity.json"
    document = json.loads(identity_path.read_text(encoding="utf-8"))
    document["gitHead"] = "0" * 40
    document["buildId"] = identity_mod.compute_build_id(document)
    identity_path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")

    result = build_project_context(root, tmp_path.parent / "data", "session-a")

    assert result.data["build"]["elfFresh"] is False


def test_context_stale_when_identity_preset_mismatched(tmp_path: Path, monkeypatch):
    root = prepare_project(tmp_path)
    build_successfully(root, monkeypatch, tmp_path)
    identity_path = root / "build" / "arm-debug" / "firmware-identity.json"
    document = json.loads(identity_path.read_text(encoding="utf-8"))
    document["preset"] = "arm-release"
    document["buildId"] = identity_mod.compute_build_id(document)
    identity_path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")

    result = build_project_context(root, tmp_path.parent / "data", "session-a")

    assert result.data["build"]["elfFresh"] is False


def test_context_stale_when_identity_paths_mismatched(tmp_path: Path, monkeypatch):
    root = prepare_project(tmp_path)
    build_successfully(root, monkeypatch, tmp_path)
    identity_path = root / "build" / "arm-debug" / "firmware-identity.json"
    document = json.loads(identity_path.read_text(encoding="utf-8"))
    document["elfPath"] = "build/arm-debug/other.elf"
    document["buildId"] = identity_mod.compute_build_id(document)
    identity_path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")

    result = build_project_context(root, tmp_path.parent / "data", "session-a")

    assert result.data["build"]["elfFresh"] is False


def test_context_stale_when_elf_unreadable(tmp_path: Path, monkeypatch):
    root = prepare_project(tmp_path)
    build_successfully(root, monkeypatch, tmp_path)
    raise_on_open(root / "build" / "arm-debug" / "firmware.elf", monkeypatch, PermissionError("injected"))

    result = build_project_context(root, tmp_path.parent / "data", "session-a")

    assert result.data["build"]["elfFresh"] is False


def test_context_stale_on_oversized_evidence(tmp_path: Path, monkeypatch):
    root = prepare_project(tmp_path)
    build_successfully(root, monkeypatch, tmp_path)
    import stm32_toolkit.context as context_mod

    monkeypatch.setattr(context_mod, "_ELF_LIMIT_BYTES", 4)

    result = build_project_context(root, tmp_path.parent / "data", "session-a")

    assert result.data["build"]["elfFresh"] is False


def test_context_stale_when_map_tampered(tmp_path: Path, monkeypatch):
    root = prepare_project(tmp_path)
    build_successfully(root, monkeypatch, tmp_path)
    (root / "build" / "arm-debug" / "firmware.map").write_text("tampered\n", encoding="utf-8")

    result = build_project_context(root, tmp_path.parent / "data", "session-a")

    assert result.data["build"]["elfFresh"] is False


def test_regular_contained_fails_closed_on_escape(tmp_path: Path, monkeypatch):
    import stm32_toolkit.context as context_mod

    root = prepare_project(tmp_path)
    assert context_mod._regular_contained(root, "Src/main.c", "elf") is True
    assert context_mod._regular_contained(root, "../escape.c", "elf") is False
    assert context_mod._regular_contained(root, "missing.c", "elf") is False
    assert context_mod._regular_contained(root, "Src", "elf") is False


def test_data_root_with_nul_returns_stable_invalid(configured_project: Path, tmp_path: Path):
    result = build_project_context(configured_project, Path("bad\x00root"), "session-a")

    assert result.code == "PROJECT_CONTEXT_INVALID"
    assert result.details == {"field": "dataRoot", "path": "bad\x00root"}


def test_data_root_resolve_os_error_maps_to_unavailable(
    monkeypatch, configured_project: Path, tmp_path: Path
):
    real_resolve = Path.resolve

    def selective(self, strict: bool = False):
        if "unavailable-data" in str(self):
            raise OSError("injected")
        return real_resolve(self, strict=strict)

    monkeypatch.setattr(Path, "resolve", selective)
    data_root = tmp_path.parent / "unavailable-data"
    result = build_project_context(configured_project, data_root, "session-a")

    assert result.code == "PROJECT_CONTEXT_UNAVAILABLE"
    assert result.details == {"field": "dataRoot", "path": str(data_root)}
