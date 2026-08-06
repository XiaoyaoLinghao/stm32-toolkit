from __future__ import annotations

from pathlib import Path

from stm32_toolkit.build.identity import (
    BuildError as _EvidenceError,
    git_evidence,
    read_json_bounded,
    sha256_file,
    snapshot_sha256,
)
from stm32_toolkit.detection import ProjectDetection, detect_project
from stm32_toolkit.paths import WorkspacePaths
from stm32_toolkit.project import ProjectManifest, ProjectManifestError
from stm32_toolkit.result import OperationResult


_OPERATION = "project.context"

#: Relative evidence directory and file names published by the build runner.
_BUILD_EVIDENCE_DIR = ".stm32-toolkit/build"
_RESULT_NAME = "build-result.json"
_MAX_EVIDENCE_JSON_BYTES = 8 * 1024 * 1024
_MAX_ARTIFACT_BYTES = 64 * 1024 * 1024


def build_project_context(
    project_root: Path,
    data_root: Path,
    session_id: str | None = None,
) -> OperationResult[dict[str, object]]:
    """Return a deterministic project evidence snapshot without hardware access."""
    try:
        canonical_root = project_root.expanduser().resolve(strict=False)
        detection = detect_project(canonical_root)
    except ValueError:
        return _context_invalid("projectRoot", str(project_root))
    except OSError:
        return _context_unavailable("projectRoot", str(project_root))

    if detection.kind != "configured":
        return OperationResult.success(
            _OPERATION, _unconfigured_context(detection, canonical_root)
        )

    try:
        manifest = ProjectManifest.load(canonical_root)
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
                "root": str(manifest.project_root),
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

def _unconfigured_context(
    detection: ProjectDetection, project_root: Path
) -> dict[str, object]:
    return {
        "project": {
            "kind": detection.kind,
            "root": str(project_root),
            "files": list(detection.files),
            "recommendedAction": detection.recommended_action.to_dict(),
        },
        "workspace": None,
        "build": _empty_build_evidence(),
        "hardware": _hardware_evidence(),
        "capabilities": _capabilities(build_available=False),
        "recommendedActions": [detection.recommended_action.to_dict()],
    }


def _build_evidence(manifest: ProjectManifest) -> dict[str, object]:
    cmake_lists = manifest.project_root / "CMakeLists.txt"
    elf_path = manifest.elf_path
    elf_exists = elf_path is not None and elf_path.is_file()
    sources = (*manifest.source_paths, *manifest.assembly_source_paths)
    existing_sources = tuple(path for path in sources if path.is_file())
    missing_sources = tuple(path for path in sources if not path.is_file())
    elf_fresh = (
        elf_exists
        and not missing_sources
        and elf_path is not None
        and _evidence_chain_fresh(manifest, elf_path)
    )

    return {
        "cmakeListsPresent": cmake_lists.is_file(),
        "elfPath": str(elf_path) if elf_path is not None else None,
        "elfExists": elf_exists,
        "existingSourcePaths": [str(path) for path in existing_sources],
        "missingSourcePaths": [str(path) for path in missing_sources],
        "elfFresh": elf_fresh,
    }


def _evidence_chain_fresh(manifest: ProjectManifest, elf_path: Path) -> bool:
    """Evidence-backed ELF freshness; never trusts mtimes.

    ``elfFresh`` is true only when a published build result with status
    ``success`` exists and the complete evidence chain is consistent: Git
    HEAD, result-to-identity build id link, input snapshot, and the current
    ELF/MAP bytes matching the identity digests.
    """
    root = manifest.project_root
    evidence = git_evidence(root)
    current_head = evidence.head
    if current_head is None:
        return False
    try:
        snapshot = snapshot_sha256(root, _snapshot_paths(manifest))
    except _EvidenceError:
        return False
    elf_relative = _portable_relative(elf_path, root)
    map_relative = _portable_relative(elf_path.with_suffix(".map"), root)
    if elf_relative is None or map_relative is None:
        return False
    build_root = root / _BUILD_EVIDENCE_DIR
    try:
        preset_dirs = sorted(path for path in build_root.iterdir() if path.is_dir())
    except OSError:
        return False
    for preset_dir in preset_dirs:
        if _result_chain_fresh(
            preset_dir, root, elf_relative, map_relative, current_head, snapshot
        ):
            return True
    return False


def _snapshot_paths(manifest: ProjectManifest) -> tuple[str, ...]:
    root = manifest.project_root
    relative: list[str] = [".stm32-project.json"]
    for path in (*manifest.source_paths, *manifest.assembly_source_paths):
        try:
            relative.append(path.relative_to(root).as_posix())
        except ValueError:
            continue
    return tuple(relative)


def _result_chain_fresh(
    preset_dir: Path,
    root: Path,
    elf_relative: str,
    map_relative: str,
    current_head: str,
    snapshot: str,
) -> bool:
    try:
        result = read_json_bounded(preset_dir / _RESULT_NAME, _MAX_EVIDENCE_JSON_BYTES)
    except _EvidenceError:
        return False
    if result.get("status") != "success" or result.get("preset") != preset_dir.name:
        return False
    identity_path = preset_dir / Path(str(result.get("identityPath", ""))).name
    try:
        identity = read_json_bounded(identity_path, _MAX_EVIDENCE_JSON_BYTES)
    except _EvidenceError:
        return False
    if identity.get("schemaVersion") != 1 or identity.get("gitHead") != current_head:
        return False
    if result.get("buildId") != identity.get("buildId"):
        return False
    elf = identity.get("elf")
    map_artifact = identity.get("map")
    snapshot_artifact = identity.get("inputSnapshot")
    if not isinstance(elf, dict) or not isinstance(map_artifact, dict):
        return False
    if not isinstance(snapshot_artifact, dict):
        return False
    if _as_posix(elf.get("path")) != elf_relative:
        return False
    if _as_posix(map_artifact.get("path")) != map_relative:
        return False
    if snapshot_artifact.get("sha256") != snapshot:
        return False
    if not _artifact_matches(root / elf_relative, elf):
        return False
    if not _artifact_matches(root / map_relative, map_artifact):
        return False
    return True


def _artifact_matches(path: Path, artifact: dict) -> bool:
    if not path.is_file():
        return False
    try:
        digest, size = sha256_file(path, _MAX_ARTIFACT_BYTES, "size")
    except _EvidenceError:
        return False
    return artifact.get("sha256") == digest and artifact.get("size") == size


def _portable_relative(path: Path, root: Path) -> str | None:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return None


def _as_posix(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return Path(value).as_posix()


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
