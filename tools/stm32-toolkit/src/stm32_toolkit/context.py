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
    try:
        detection = detect_project(project_root)
    except ValueError:
        return _context_invalid("projectRoot", str(project_root))
    except OSError:
        return _context_unavailable("projectRoot", str(project_root))

    if detection.kind != "configured":
        return OperationResult.success(_OPERATION, _unconfigured_context(detection))

    try:
        manifest = ProjectManifest.load(project_root)
    except ProjectManifestError as error:
        return OperationResult.failure(
            _OPERATION,
            error.code,
            error.message,
            error.details,
        )

    try:
        canonical_data_root = data_root.expanduser().resolve(strict=False)
    except ValueError:
        return _context_invalid("dataRoot", str(data_root))
    except OSError:
        return _context_unavailable("dataRoot", str(data_root))

    if _is_project_path(canonical_data_root, manifest.project_root):
        return _context_invalid("dataRoot", str(canonical_data_root))

    try:
        workspace = WorkspacePaths.from_roots(
            canonical_data_root,
            manifest.project_root,
            manifest.logical_project_id,
            session_id,
        )
    except ValueError:
        return _context_invalid("sessionId")
    except OSError:
        return _context_unavailable("dataRoot", str(canonical_data_root))

    try:
        workspace.ensure()
    except ValueError:
        return _context_invalid("dataRoot", str(canonical_data_root))
    except OSError:
        return _context_unavailable("dataRoot", str(canonical_data_root))
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


def _context_invalid(field: str, path: str | None = None) -> OperationResult[None]:
    details: dict[str, object] = {"field": field}
    if path is not None:
        details["path"] = path
    return OperationResult.failure(
        _OPERATION,
        "PROJECT_CONTEXT_INVALID",
        "Project context parameters are invalid",
        details,
    )


def _context_unavailable(field: str, path: str) -> OperationResult[None]:
    return OperationResult.failure(
        _OPERATION,
        "PROJECT_CONTEXT_UNAVAILABLE",
        "Project context data is not available",
        {"field": field, "path": path},
    )


def _is_project_path(path: Path, project_root: Path) -> bool:
    try:
        path.relative_to(project_root)
    except ValueError:
        return False
    return True

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
