import json
import os
from pathlib import Path
from uuid import UUID

import pytest

from stm32_toolkit.context import build_project_context
from stm32_toolkit.identity import compute_workspace_id


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
                "elfFresh": True,
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
            "files": ["legacy.uvprojx"],
            "recommendedSkill": "/migrate-keil",
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
        "recommendedActions": ["/migrate-keil"],
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


def test_newer_source_makes_elf_stale_and_newer_elf_is_fresh(
    configured_project: Path, tmp_path: Path
):
    source = configured_project / "App" / "main.c"
    elf = configured_project / "build-fw" / "firmware.elf"
    os.utime(elf, ns=(1_000_000_000, 1_000_000_000))
    os.utime(source, ns=(2_000_000_000, 2_000_000_000))

    stale = build_project_context(configured_project, tmp_path.parent / "data", "session-a")

    os.utime(elf, ns=(3_000_000_000, 3_000_000_000))
    fresh = build_project_context(configured_project, tmp_path.parent / "data", "session-a")

    assert stale.data["build"]["elfFresh"] is False
    assert fresh.data["build"]["elfFresh"] is True


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
