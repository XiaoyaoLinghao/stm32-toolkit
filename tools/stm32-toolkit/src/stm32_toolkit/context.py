from __future__ import annotations

from pathlib import Path

from stm32_toolkit.build.identity import (
    BuildError,
    compute_build_id,
    git_evidence,
    read_bounded,
    read_evidence_json,
    snapshot_project_inputs,
    validate_identity_document,
)
from stm32_toolkit.detection import ProjectDetection, detect_project
from stm32_toolkit.generation.managed_files import sha256_hex
from stm32_toolkit.paths import WorkspacePaths
from stm32_toolkit.project import ProjectManifest, ProjectManifestError
from stm32_toolkit.project_model import load_project_model
from stm32_toolkit.result import OperationResult


_OPERATION = "project.context"

#: Evidence JSON bound (identity/result documents are small; oversize is stale).
_EVIDENCE_LIMIT_BYTES = 8 * 1024 * 1024
_ELF_LIMIT_BYTES = 64 * 1024 * 1024
_MAP_LIMIT_BYTES = 32 * 1024 * 1024


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
                build_available=bool(build["cmakeListsPresent"]),
                configure_available=_valid_schema_v2(canonical_root),
            ),
            "recommendedActions": [],
        },
    )


def _valid_schema_v2(project_root: Path) -> bool:
    """True only when a valid Schema v2 project model loads from the root."""
    try:
        model = load_project_model(project_root)
    except (ProjectManifestError, OSError, ValueError, TypeError):
        return False
    return model.schema_version == 2


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
    keil_detected = detection.kind == "keil"
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
        "capabilities": _capabilities(
            build_available=False,
            keil_inspect=keil_detected,
            keil_convert=keil_detected,
        ),
        "recommendedActions": [detection.recommended_action.to_dict()],
    }


def _build_evidence(manifest: ProjectManifest) -> dict[str, object]:
    root = manifest.project_root
    cmake_lists = root / "CMakeLists.txt"
    elf_path = manifest.elf_path
    elf_exists = elf_path is not None and elf_path.is_file()
    sources = (*manifest.source_paths, *manifest.assembly_source_paths)
    existing_sources = tuple(path for path in sources if path.is_file())
    missing_sources = tuple(path for path in sources if not path.is_file())
    fresh = _evidence_fresh(manifest, root)
    evidence: dict[str, object] = {
        "cmakeListsPresent": cmake_lists.is_file(),
        "elfPath": str(elf_path) if elf_path is not None else None,
        "elfExists": elf_exists,
        "existingSourcePaths": [str(path) for path in existing_sources],
        "missingSourcePaths": [str(path) for path in missing_sources],
        "elfFresh": fresh is not None,
        "buildId": None,
        "elfSha256": None,
        "preset": None,
        "gitHead": None,
        "identityPath": None,
        "buildResultPath": None,
        "buildLogPath": None,
    }
    if fresh is not None:
        evidence.update(fresh)
    return evidence


def _empty_build_evidence() -> dict[str, object]:
    return {
        "cmakeListsPresent": False,
        "elfPath": None,
        "elfExists": False,
        "existingSourcePaths": [],
        "missingSourcePaths": [],
        "elfFresh": False,
        "buildId": None,
        "elfSha256": None,
        "preset": None,
        "gitHead": None,
        "identityPath": None,
        "buildResultPath": None,
        "buildLogPath": None,
    }


def _hardware_evidence() -> dict[str, object]:
    return {"probe": None, "state": "unavailable"}


def _capabilities(
    *,
    build_available: bool,
    keil_inspect: bool = False,
    keil_convert: bool = False,
    configure_available: bool = False,
) -> dict[str, bool]:
    return {
        "build": build_available,
        "keilInspect": keil_inspect,
        "keilConvert": keil_convert,
        "configure": configure_available,
        "flash": False,
        "hostTest": False,
        "targetTest": False,
        "monitor": False,
        "breakpointDebug": False,
    }


# ---------------------------------------------------------------------------
# evidence-backed freshness
# ---------------------------------------------------------------------------


def _evidence_fresh(manifest: ProjectManifest, root: Path) -> dict[str, object] | None:
    """Return fresh evidence fields or ``None`` when any link fails closed.

    ``elfFresh`` requires: build-result status success; a schema-valid
    identity whose build ID recomputes; record and identity agreement on the
    shared fields; current Git HEAD, target, preset, complete input snapshot,
    ELF digest, and MAP digest all agreeing; every path contained and
    regular.  Only the model-selected debug evidence is consulted; another
    preset's evidence is never accepted.
    """
    try:
        model = load_project_model(root)
        if model.schema_version != 2:
            return None
        elf_rel = model.build.elf
        if elf_rel is None or not elf_rel.startswith("build/arm-debug/"):
            return None
        base = elf_rel[len("build/arm-debug/") :]
        if not base.endswith(".elf") or "/" in base or "\\" in base:
            return None
        map_rel = "build/arm-debug/" + base[: -len(".elf")] + ".map"
        identity_rel = "build/arm-debug/firmware-identity.json"
        result_rel = "artifacts/migration/build-result.json"
        log_rel = "artifacts/migration/build.log"

        record = read_evidence_json(
            root.joinpath(*result_rel.split("/")), result_rel, _EVIDENCE_LIMIT_BYTES
        )
        if record is None or record.get("status") != "success":
            return None
        if record.get("preset") != "arm-debug":
            return None
        if record.get("targetDevice") != model.target.device:
            return None

        identity_doc = read_evidence_json(
            root.joinpath(*identity_rel.split("/")), identity_rel, _EVIDENCE_LIMIT_BYTES
        )
        if identity_doc is None:
            return None
        validate_identity_document(identity_doc)
        if compute_build_id(identity_doc) != identity_doc.get("buildId"):
            return None
        for field in ("buildId", "gitHead", "gitDirty", "inputSnapshotSha256", "targetDevice", "preset"):
            if record.get(field) != identity_doc.get(field):
                return None
        if identity_doc.get("preset") != "arm-debug":
            return None
        if identity_doc.get("elfPath") != elf_rel or identity_doc.get("mapPath") != map_rel:
            return None

        snapshot = snapshot_project_inputs(model)
        if snapshot.sha256 != identity_doc.get("inputSnapshotSha256"):
            return None
        git = git_evidence(root)
        if git.head != identity_doc.get("gitHead"):
            return None
        if not _regular_contained(root, elf_rel, "elf"):
            return None
        if not _regular_contained(root, map_rel, "map"):
            return None
        elf_data = read_bounded(root.joinpath(*elf_rel.split("/")), _ELF_LIMIT_BYTES)
        map_data = read_bounded(root.joinpath(*map_rel.split("/")), _MAP_LIMIT_BYTES)
        if len(elf_data) > _ELF_LIMIT_BYTES or len(map_data) > _MAP_LIMIT_BYTES:
            return None
        if sha256_hex(elf_data) != identity_doc.get("elfSha256"):
            return None
        if sha256_hex(map_data) != identity_doc.get("mapSha256"):
            return None
        return {
            "buildId": identity_doc["buildId"],
            "elfSha256": identity_doc["elfSha256"],
            "preset": "arm-debug",
            "gitHead": identity_doc["gitHead"],
            "identityPath": identity_rel,
            "buildResultPath": result_rel,
            "buildLogPath": log_rel,
        }
    except (BuildError, OSError, ValueError, TypeError, KeyError):
        return None


def _regular_contained(root: Path, rel: str, kind: str) -> bool:
    """Fail closed unless ``rel`` resolves inside ``root`` to a regular file."""
    import os
    import stat

    path = root.joinpath(*rel.split("/"))
    try:
        resolved = path.resolve(strict=False)
        resolved.relative_to(root)
    except (OSError, RuntimeError, ValueError):
        return False
    try:
        lst = os.lstat(path)
    except OSError:
        return False
    if not stat.S_ISREG(lst.st_mode):
        return False
    return True
