from __future__ import annotations

from pathlib import Path

from stm32_toolkit.detection import ProjectDetection, detect_project
from stm32_toolkit.paths import WorkspacePaths
from stm32_toolkit.project import ProjectManifest, ProjectManifestError
from stm32_toolkit.result import OperationResult


_OPERATION = "project.context"


def build_project_context(
    project_root: Path,
    data_root: Path,
    session_id: str | None = None,
) -> OperationResult[dict[str, object]]:
    """Return a deterministic project evidence snapshot without hardware access."""
    detection = detect_project(project_root)
    if detection.kind != "configured":
        return OperationResult.success(_OPERATION, _unconfigured_context(detection))

    try:
        manifest = ProjectManifest.load(project_root)
        workspace = WorkspacePaths.from_roots(
            data_root,
            manifest.project_root,
            manifest.logical_project_id,
            session_id,
        )
        workspace.ensure()
    except ProjectManifestError as error:
        return OperationResult.failure(
            _OPERATION,
            error.code,
            error.message,
            error.details,
        )
    except ValueError:
        return OperationResult.failure(
            _OPERATION,
            "PROJECT_CONTEXT_INVALID",
            "Project context parameters are invalid",
            {"field": "sessionId"},
        )
    except OSError:
        return OperationResult.failure(
            _OPERATION,
            "PROJECT_CONTEXT_UNAVAILABLE",
            "Project context data is not available",
            {"path": str(data_root)},
        )

    build = _build_evidence(manifest)
    return OperationResult.success(
        _OPERATION,
        {
            "project": {
                "kind": "configured",
                "logicalProjectId": str(manifest.logical_project_id),
                "target": manifest.target_device,
                "framework": manifest.framework_type,
            },
            "workspace": {
                "workspaceId": workspace.workspace_id,
                "sessionId": workspace.session_id,
            },
            "build": build,
            "hardware": _hardware_evidence(),
            "capabilities": _capabilities(
                build_available=bool(build["cmakeListsPresent"])
            ),
            "recommendedActions": [],
        },
    )


def _unconfigured_context(detection: ProjectDetection) -> dict[str, object]:
    return {
        "project": {
            "kind": detection.kind,
            "files": list(detection.files),
            "recommendedSkill": detection.recommended_skill,
        },
        "workspace": None,
        "build": _empty_build_evidence(),
        "hardware": _hardware_evidence(),
        "capabilities": _capabilities(build_available=False),
        "recommendedActions": [detection.recommended_skill],
    }


def _build_evidence(manifest: ProjectManifest) -> dict[str, object]:
    cmake_lists = manifest.project_root / "CMakeLists.txt"
    elf_path = manifest.elf_path
    elf_exists = elf_path is not None and elf_path.is_file()
    existing_sources = tuple(path for path in manifest.source_paths if path.is_file())
    missing_sources = tuple(path for path in manifest.source_paths if not path.is_file())
    elf_fresh = (
        elf_exists
        and not missing_sources
        and elf_path is not None
        and all(elf_path.stat().st_mtime_ns >= source.stat().st_mtime_ns for source in existing_sources)
    )

    return {
        "cmakeListsPresent": cmake_lists.is_file(),
        "elfPath": str(elf_path) if elf_path is not None else None,
        "elfExists": elf_exists,
        "existingSourcePaths": [str(path) for path in existing_sources],
        "missingSourcePaths": [str(path) for path in missing_sources],
        "elfFresh": elf_fresh,
    }


def _empty_build_evidence() -> dict[str, object]:
    return {
        "cmakeListsPresent": False,
        "elfPath": None,
        "elfExists": False,
        "existingSourcePaths": [],
        "missingSourcePaths": [],
        "elfFresh": False,
    }


def _hardware_evidence() -> dict[str, object]:
    return {"probe": None, "state": "unavailable"}


def _capabilities(*, build_available: bool) -> dict[str, bool]:
    return {
        "build": build_available,
        "flash": False,
        "hostTest": False,
        "targetTest": False,
        "monitor": False,
        "breakpointDebug": False,
    }
