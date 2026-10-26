from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from stm32_toolkit import __version__
from stm32_toolkit.build.identity import (
    BuildError,
    compute_build_id,
    git_evidence,
    identity_discovery_policy,
    read_bounded,
    read_evidence_json,
    snapshot_project_inputs,
    validate_identity_document,
    validate_snapshot_build_result,
)
from stm32_toolkit.build.model import (
    SNAPSHOT_IDENTITY_SCHEMA_VERSION,
    SOURCE_BASELINE_INPUT_SNAPSHOT,
)
from stm32_toolkit.debug_configuration import (
    CONFIGURED as DEBUG_CONFIGURED,
    DebugConfigurationStatus,
    describe_debug_configuration,
)
from stm32_toolkit.detection import ProjectDetection, detect_project
from stm32_toolkit.generation.managed_files import (
    MANAGED_MANIFEST_PATH,
    GenerationError,
    model_sha256_for,
    parse_managed_manifest,
    sha256_hex,
)
from stm32_toolkit.keil.model import KeilInspectionError
from stm32_toolkit.paths import WorkspacePaths
from stm32_toolkit.project import ProjectManifest, ProjectManifestError
from stm32_toolkit.project_model import load_project_model
from stm32_toolkit.result import OperationResult


_OPERATION = "project.context"

#: Evidence JSON bound (identity/result documents are small; oversize is stale).
_EVIDENCE_LIMIT_BYTES = 8 * 1024 * 1024
_ELF_LIMIT_BYTES = 64 * 1024 * 1024
_MAP_LIMIT_BYTES = 32 * 1024 * 1024
_CONTEXT_DETAILS = {
    "capabilitySemantics": "current-readiness",
    "hardwareDiscovery": "not-performed",
}


def _context_success(data: dict[str, object]) -> OperationResult[dict[str, object]]:
    return replace(OperationResult.success(_OPERATION, data), details=_CONTEXT_DETAILS)


def build_project_context(
    project_root: Path,
    data_root: Path,
    session_id: str | None = None,
) -> OperationResult[dict[str, object]]:
    """Return a deterministic project evidence snapshot without hardware access."""
    try:
        canonical_root = project_root.expanduser().resolve(strict=False)
        detection = detect_project(canonical_root)
    except KeilInspectionError as error:
        return OperationResult.failure(_OPERATION, error.code, error.message, error.details)
    except ValueError:
        return _context_invalid("projectRoot", str(project_root))
    except OSError:
        return _context_unavailable("projectRoot", str(project_root))

    if detection.kind != "configured":
        return _context_success(_unconfigured_context(detection, canonical_root))

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
    build_ready = _build_ready(build)
    configure_available = _valid_supported_schema(canonical_root)
    debug_status = _debug_configuration_status(canonical_root)
    capability_details = _configured_capability_details(
        build=build,
        build_ready=build_ready,
        configure_available=configure_available,
        snapshot_fresh=(
            build.get("elfFresh") is True
            and build.get("sourceBaseline") == SOURCE_BASELINE_INPUT_SNAPSHOT
        ),
        debug_status=debug_status,
    )
    flash_details = capability_details["flash"]
    assert isinstance(flash_details, dict)
    data: dict[str, object] = {
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
            build_available=build_ready,
            configure_available=configure_available,
        ),
        "capabilityDetails": capability_details,
        "firmwareRoutes": _firmware_routes(flash_details),
        "recommendedActions": [],
    }
    if debug_status is not None:
        # Additive read-only description of the manifest pair.  A valid pair
        # means only that configuration is present; it never claims probe,
        # target or firmware verification.
        data["debugConfiguration"] = debug_status.to_dict()
    return _context_success(data)


def _valid_supported_schema(project_root: Path) -> bool:
    """True when a valid supported project model loads from the root."""
    try:
        model = load_project_model(project_root)
    except (ProjectManifestError, OSError, ValueError, TypeError):
        return False
    return model.schema_version in (2, 3)


def _debug_configuration_status(
    project_root: Path,
) -> DebugConfigurationStatus | None:
    """Describe the model's debug pair, or ``None`` when no model loads.

    A model-load failure keeps the existing broader context contract: this
    helper adds no new failure mode, never connects a backend and never
    verifies a target.
    """
    try:
        model = load_project_model(project_root)
    except (ProjectManifestError, OSError, ValueError, TypeError):
        return None
    if model.schema_version not in (2, 3):
        return None
    return describe_debug_configuration(model.debug.backend, model.debug.target)


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

_PREFLIGHT_ACTION = {
    "id": "keil-preflight",
    "available": True,
    "explanation": (
        "Run stm32_keil_preflight with the selected project-relative uvprojx "
        "and exact targetName. It is read-only, requires no Git, may return "
        "blockers, and does not authorize conversion; the PLAN also needs a "
        "separate absolute new output directory."
    ),
}

_HARDWARE_NOT_EVALUATED_REASON = (
    "Project context does not enumerate probes or inspect target state, so "
    "this hardware capability is not evaluated here; the tool still exists."
)
_HARDWARE_NEXT_STEPS = (
    "Call stm32_probe_list to enumerate connected probes. It requires no "
    "build, debug backend, target, or SVD and does not modify the board."
)
_FLASH_NOT_EVALUATED_REASON = (
    _HARDWARE_NOT_EVALUATED_REASON
    + " This managed flash entry covers only stm32_flash and requires"
    " Git-shaped managed firmware provenance: a build from a non-Git input"
    " snapshot is build-only and firmware admission refuses it with"
    " FIRMWARE_PROVENANCE_UNSUPPORTED before any probe, lease, or attach"
    " effect. It does not describe a separately selected imported image."
)
_FLASH_NEXT_STEPS = (
    _HARDWARE_NEXT_STEPS,
    "For this managed route, build and inspect snapshot firmware without Git;"
    " to flash the managed build identity, restore a Git repository with a"
    " committed HEAD and rebuild. Never fabricate a commit or dirty state.",
    "A separately selected external/snapshot import is a different route"
    " (stm32_firmware_import -> stm32_firmware_admit -> stm32_flash_imported)"
    " with its own inputs and authorizations; it is not an available or"
    " admitted image in context and never substitutes automatically for this"
    " managed identity.",
)
_SNAPSHOT_HARDWARE_REASON = (
    "This managed capability depends on the current managed build's firmware"
    " admission. The build has sourceBaseline input-snapshot-v1 because Git"
    " provenance was unavailable, so admission refuses it with"
    " FIRMWARE_PROVENANCE_UNSUPPORTED before any probe, lease, or attach"
    " effect; no hardware state was evaluated."
)
_SNAPSHOT_HARDWARE_NEXT_STEPS = (
    "For the managed route, restore a Git repository with a committed HEAD,"
    " rebuild, and re-run stm32_project_context; never fabricate a commit or"
    " dirty state.",
    "Probe discovery remains independent: stm32_probe_list requires no"
    " firmware identity and does not modify the board.",
)
_SNAPSHOT_FLASH_NEXT_STEPS = _SNAPSHOT_HARDWARE_NEXT_STEPS + (
    "This managed flash stop does not select another route: a separately"
    " selected imported image (stm32_firmware_import -> stm32_firmware_admit"
    " -> stm32_flash_imported) has its own inputs and authorizations, and its"
    " receipt is never a managed build identity.",
)


def _unconfigured_context(
    detection: ProjectDetection, project_root: Path
) -> dict[str, object]:
    keil_detected = detection.kind == "keil"
    recommended = [detection.recommended_action.to_dict()]
    if keil_detected:
        recommended.append(dict(_PREFLIGHT_ACTION))
    capability_details = _unconfigured_capability_details(detection.kind)
    flash_details = capability_details["flash"]
    assert isinstance(flash_details, dict)
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
            keil_preflight=keil_detected,
            keil_convert=keil_detected,
        ),
        "capabilityDetails": capability_details,
        "firmwareRoutes": _firmware_routes(flash_details),
        "recommendedActions": recommended,
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
        "gitDirty": None,
        "sourceBaseline": None,
        "gitEvidence": None,
        "identityPath": None,
        "buildResultPath": None,
        "buildLogPath": None,
    }
    evidence.update(_managed_configuration_evidence(root))
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
        **{
            "managedManifestPresent": False,
            "managedManifestValid": False,
            "managedFilesMissing": [],
            "managedFilesDrifted": [],
        },
        "buildId": None,
        "elfSha256": None,
        "preset": None,
        "gitHead": None,
        "gitDirty": None,
        "sourceBaseline": None,
        "gitEvidence": None,
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
    keil_preflight: bool = False,
    keil_convert: bool = False,
    configure_available: bool = False,
) -> dict[str, bool]:
    return {
        "build": build_available,
        "keilInspect": keil_inspect,
        "keilPreflight": keil_preflight,
        "keilConvert": keil_convert,
        "configure": configure_available,
        "flash": False,
        "hostTest": False,
        "targetTest": False,
        "monitor": False,
        "breakpointDebug": False,
    }


def _capability(
    status: str, reason: str, next_steps: tuple[str, ...]
) -> dict[str, object]:
    return {"status": status, "reason": reason, "nextSteps": list(next_steps)}


_IMPORTED_ROUTE_REASON = (
    "Project context does not read or evaluate any external firmware, target,"
    " migration plan, MAP, admission, or probe, so this route is not"
    " evaluated. Tool availability is not image readiness. A managed blocker"
    " or failure never selects this route automatically."
)
_IMPORTED_ROUTE_NEXT_STEPS = (
    "For an explicitly selected external/snapshot import, collect the original"
    " project-relative firmware path, its SHA-256, format, supported target,"
    " and reviewed internal Flash regions (plus a BIN base address), then call"
    " stm32_firmware_import without planId for a read-only PLAN. Keep the"
    " plan source SHA-256 distinct from the normalized image SHA-256.",
    "After separate authorization for the immutable offline copy, apply that"
    " exact planId and call stm32_firmware_admit offline. Only a new explicit"
    " authorization for one exact probe may call stm32_flash_imported.",
    "An imported receipt covers only that snapshot's programming and readback."
    " It does not unlock debug, Monitor, Target tests, legacy flash evidence,"
    " reset/recovery, or a managed build identity.",
)


def _firmware_routes(flash: dict[str, object]) -> dict[str, object]:
    """Describe the two explicit firmware routes without evaluating either.

    The managed entry mirrors the current ``capabilityDetails.flash`` evidence
    exactly. The imported entry is always ``not-evaluated``: context has not
    read any external firmware, target, plan, admission, or probe, and no
    route may switch automatically after a managed failure.
    """
    status = flash.get("status")
    reason = flash.get("reason")
    next_steps = flash.get("nextSteps")
    assert isinstance(status, str)
    assert isinstance(reason, str)
    assert isinstance(next_steps, list)
    return {
        "managed": {
            "status": status,
            "reason": reason,
            "nextSteps": list(next_steps),
            "tools": ["stm32_probe_list", "stm32_flash"],
            "identity": ["buildId", "elfSha256"],
            "requiresGit": True,
            "requiresManagedModel": True,
        },
        "imported": {
            "status": "not-evaluated",
            "reason": _IMPORTED_ROUTE_REASON,
            "nextSteps": list(_IMPORTED_ROUTE_NEXT_STEPS),
            "tools": [
                "stm32_firmware_import",
                "stm32_firmware_admit",
                "stm32_flash_imported",
            ],
            "requiresGit": False,
            "requiresManagedModel": False,
            "selection": "explicit",
        },
    }


def _debug_capability_block(
    status: DebugConfigurationStatus,
) -> tuple[str, tuple[str, ...]]:
    """Render every missing/invalid field as one concrete blocked reason."""
    reasons = "; ".join(
        f"{entry.field} ({entry.rule}): {entry.message}"
        for entry in status.diagnostics
    )
    return (
        "Debug configuration is incomplete or invalid, so this managed "
        "hardware capability is blocked: " + reasons + ".",
        tuple(status.next_steps),
    )


def _merge_reason(*parts: str | None) -> str:
    return " ".join(part for part in parts if part)


def _merge_next_steps(
    *groups: tuple[str, ...] | None,
) -> tuple[str, ...]:
    merged: list[str] = []
    for group in groups:
        if group is None:
            continue
        for step in group:
            if step not in merged:
                merged.append(step)
    return tuple(merged)


def _hardware_capability_details(
    *,
    snapshot_fresh: bool = False,
    debug_status: DebugConfigurationStatus | None = None,
) -> dict[str, dict[str, object]]:
    debug_block: tuple[str, tuple[str, ...]] | None = None
    if debug_status is not None and debug_status.status != DEBUG_CONFIGURED:
        debug_block = _debug_capability_block(debug_status)
    if snapshot_fresh:
        # The current build is known to be refused by firmware admission, so
        # the affected capabilities are a concrete blocker, not "not
        # evaluated".  Probe discovery is deliberately not affected.  Every
        # existing snapshot/Git reason is preserved and any debug blocker is
        # appended, never substituted.
        reason = _merge_reason(
            _SNAPSHOT_HARDWARE_REASON, debug_block[0] if debug_block else None
        )
        next_steps = _merge_next_steps(
            _SNAPSHOT_HARDWARE_NEXT_STEPS, debug_block[1] if debug_block else None
        )
        blocked = _capability("blocked", reason, next_steps)
        # Only managed flash may describe the separate imported route; debug,
        # Monitor, and Target-test guidance never offers an import as a remedy.
        return {
            "flash": _capability(
                "blocked",
                reason,
                _merge_next_steps(
                    _SNAPSHOT_FLASH_NEXT_STEPS,
                    debug_block[1] if debug_block else None,
                ),
            ),
            "targetTest": dict(blocked),
            "monitor": dict(blocked),
            "breakpointDebug": dict(blocked),
        }
    if debug_block is not None:
        reason, next_steps = debug_block
        blocked = _capability("blocked", reason, next_steps)
        return {
            "flash": dict(blocked),
            "targetTest": dict(blocked),
            "monitor": dict(blocked),
            "breakpointDebug": dict(blocked),
        }
    hardware = _capability(
        "not-evaluated", _HARDWARE_NOT_EVALUATED_REASON, (_HARDWARE_NEXT_STEPS,)
    )
    return {
        "flash": _capability(
            "not-evaluated", _FLASH_NOT_EVALUATED_REASON, _FLASH_NEXT_STEPS
        ),
        "targetTest": dict(hardware),
        "monitor": dict(hardware),
        "breakpointDebug": dict(hardware),
    }


def _configured_capability_details(
    *,
    build: dict[str, object],
    build_ready: bool,
    configure_available: bool,
    snapshot_fresh: bool = False,
    debug_status: DebugConfigurationStatus | None = None,
) -> dict[str, dict[str, object]]:
    if build_ready:
        build_reason = "Managed configuration evidence is complete."
        build_next = (
            "Call stm32_build with the desired preset and authorized=true after "
            "explicit user authorization.",
        )
    else:
        if not build["cmakeListsPresent"]:
            build_reason = "No CMakeLists.txt is present."
        elif not build["managedManifestPresent"]:
            build_reason = "The managed configuration manifest is missing."
        elif not build["managedManifestValid"]:
            build_reason = (
                "The managed configuration manifest is invalid or does not "
                "match the project model."
            )
        elif build["managedFilesMissing"]:
            build_reason = "Managed configuration files are missing."
        else:
            build_reason = "Managed configuration files have drifted."
        build_next = (
            "Run stm32_project_configure to review and apply managed "
            "configuration with explicit authorization; do not hand-edit "
            "generated files.",
        )
    no_keil_reason = (
        "This project root is bound to .stm32-project.json; no Keil project "
        "is selected for migration."
    )
    no_keil_next = (
        "If this tree also contains a Keil project, start a Toolkit session "
        "bound to that project root and select its uvprojx.",
    )
    details: dict[str, dict[str, object]] = {
        "build": _capability(
            "available" if build_ready else "blocked", build_reason, build_next
        ),
        "keilInspect": _capability("blocked", no_keil_reason, no_keil_next),
        "keilPreflight": _capability("blocked", no_keil_reason, no_keil_next),
        "keilConvert": _capability("blocked", no_keil_reason, no_keil_next),
        "configure": _capability(
            "available" if configure_available else "blocked",
            (
                "A valid supported Schema v2/v3 project model is available."
                if configure_available
                else "No valid supported Schema v2/v3 project model was loaded."
            ),
            (
                "Call stm32_project_configure to review the read-only plan "
                "before any authorized apply.",
            ),
        ),
        "hostTest": _capability(
            "not-evaluated",
            "Project context does not discover or evaluate host tests.",
            (
                "Call stm32_test_host_discover to evaluate host-test readiness "
                "for this configured project.",
            ),
        ),
    }
    details.update(
        _hardware_capability_details(
            snapshot_fresh=snapshot_fresh, debug_status=debug_status
        )
    )
    return details


def _unconfigured_capability_details(kind: str) -> dict[str, dict[str, object]]:
    keil_detected = kind == "keil"
    if keil_detected:
        keil_details = {
            "keilInspect": _capability(
                "available",
                "A Keil .uvprojx entry point exists, but entry availability "
                "does not establish migration readiness.",
                (
                    "Call stm32_keil_inspect with the project-relative uvprojx "
                    "and exact targetName.",
                    "Call stm32_keil_preflight with the same selection to "
                    "receive typed blockers and the required delivery "
                    "destination input.",
                ),
            ),
            "keilPreflight": _capability(
                "available",
                "Read-only preflight is available without Git and may still "
                "return blockers.",
                (
                    "Call stm32_keil_preflight with the selected uvprojx and "
                    "exact targetName, then resolve every reported blocker.",
                    "Choose an absolute new output directory outside the Keil "
                    "source; preflight does not create or evaluate it.",
                ),
            ),
            "keilConvert": _capability(
                "available",
                "The conversion entry point exists; an independent destination, "
                "a reviewed plan and explicit authorization are still required.",
                (
                    "After preflight is complete and blockers are resolved, "
                    "call stm32_keil_convert with destination set to the chosen "
                    "absolute new output directory and no planId for a "
                    "read-only PLAN response.",
                    "Review data.planId, data.outputs[] and data.sourcePatches[]; "
                    "pass that exact data.planId as the apply request's planId "
                    "with the same destination and options only after explicit "
                    "user authorization.",
                    "After apply, bind the result's outputRoot as the VS Code "
                    "workspace and MCP project root, then run context, "
                    "configure and build there. Git is optional.",
                ),
            ),
        }
    else:
        blocked = _capability(
            "blocked",
            "No .uvprojx project was detected in this project root.",
            ("Select or create a Keil project before using Keil workflows.",),
        )
        keil_details = {
            "keilInspect": dict(blocked),
            "keilPreflight": dict(blocked),
            "keilConvert": dict(blocked),
        }
    details: dict[str, dict[str, object]] = {
        "build": _capability(
            "blocked",
            "No valid supported .stm32-project.json is configured.",
            (
                "Create, migrate, or configure a valid project before building.",
            ),
        ),
        **keil_details,
        "configure": _capability(
            "blocked",
            "Configuration requires a valid supported .stm32-project.json.",
            (
                "Create a project model or complete Keil migration first; "
                "configuration has its own read-only plan and authorization.",
            ),
        ),
        "hostTest": _capability(
            "blocked",
            "Host tests require a configured project with test metadata.",
            (
                "Configure the project first, then call "
                "stm32_test_host_discover.",
            ),
        ),
    }
    details.update(_hardware_capability_details())
    return details


def _build_ready(evidence: dict[str, object]) -> bool:
    """Build capability requires complete managed configuration evidence.

    A bare CMakeLists.txt is not enough: the managed manifest must be
    present and valid (parse, versions, and model digest) and every managed
    file it records must exist un-drifted on disk.  This check is strictly
    read-only; it never repairs or refreshes any file.
    """
    return (
        bool(evidence["cmakeListsPresent"])
        and bool(evidence["managedManifestPresent"])
        and bool(evidence["managedManifestValid"])
        and not evidence["managedFilesMissing"]
        and not evidence["managedFilesDrifted"]
    )


# ---------------------------------------------------------------------------
# managed-configuration evidence (STM32TK-0306 revision 1)
# ---------------------------------------------------------------------------


def _managed_configuration_evidence(root: Path) -> dict[str, object]:
    """Read-only evidence about the managed configuration state.

    Returns ``managedManifestPresent``, ``managedManifestValid`` (parse,
    version, template version, and model digest agreement), and the lists of
    managed files that are missing or drifted on disk.  Any invalid,
    unreadable, oversized, escaping, or non-regular state fails closed to
    ``valid=False`` without ever writing to the project.
    """
    manifest_abs = root.joinpath(*MANAGED_MANIFEST_PATH.split("/"))
    if not _regular_contained(root, MANAGED_MANIFEST_PATH, "manifest"):
        return {
            "managedManifestPresent": False,
            "managedManifestValid": False,
            "managedFilesMissing": [],
            "managedFilesDrifted": [],
        }
    try:
        data = read_bounded(manifest_abs, _EVIDENCE_LIMIT_BYTES)
        if len(data) > _EVIDENCE_LIMIT_BYTES:
            raise ValueError("oversize")
        payload = json.loads(data.decode("utf-8"))
        records = parse_managed_manifest(data)
    except (BuildError, GenerationError, OSError, ValueError, TypeError, UnicodeDecodeError, KeyError):
        return {
            "managedManifestPresent": True,
            "managedManifestValid": False,
            "managedFilesMissing": [],
            "managedFilesDrifted": [],
        }

    digest_ok = True
    try:
        model = load_project_model(root)
        if model.schema_version in (2, 3):
            digest_ok = (
                model_sha256_for(model) == payload.get("projectManifestSha256")
            )
    except (ProjectManifestError, OSError, ValueError, TypeError):
        digest_ok = False

    missing: list[str] = []
    drifted: list[str] = []
    for record in records:
        if not _regular_contained(root, record.path, "managed"):
            missing.append(record.path)
            continue
        path = root.joinpath(*record.path.split("/"))
        try:
            file_data = read_bounded(path, _EVIDENCE_LIMIT_BYTES)
        except OSError:
            missing.append(record.path)
            continue
        if sha256_hex(file_data) != record.sha256:
            drifted.append(record.path)
    return {
        "managedManifestPresent": True,
        "managedManifestValid": digest_ok,
        "managedFilesMissing": missing,
        "managedFilesDrifted": drifted,
    }


# ---------------------------------------------------------------------------
# evidence-backed freshness
# ---------------------------------------------------------------------------


def _evidence_fresh(manifest: ProjectManifest, root: Path) -> dict[str, object] | None:
    """Return fresh evidence fields or ``None`` when any link fails closed.

    ``elfFresh`` requires: build-result status success; a schema-valid
    identity whose build ID recomputes; record and identity agreement on the
    shared fields; target, preset, complete input snapshot, ELF digest, and
    MAP digest all agreeing; every path contained and regular.  Schema 1
    additionally requires the current Git HEAD.  Schema 2 is the explicit
    non-Git input-snapshot baseline: it must carry null Git fields and
    bounded unavailability evidence, and freshness never spawns Git.  Only
    the model-selected debug evidence is consulted; another preset's
    evidence is never accepted.
    """
    try:
        model = load_project_model(root)
        if model.schema_version not in (2, 3):
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
        identity_schema = identity_doc.get("schemaVersion")
        if type(identity_schema) is not int:
            return None
        if type(record.get("schemaVersion")) is not int:
            return None
        if record.get("schemaVersion") != identity_schema:
            return None
        if compute_build_id(identity_doc) != identity_doc.get("buildId"):
            return None
        if identity_schema == SNAPSHOT_IDENTITY_SCHEMA_VERSION:
            expected_artifacts = frozenset(
                {log_rel, result_rel, identity_rel, elf_rel, map_rel}
            )
            if not validate_snapshot_build_result(
                record, preset="arm-debug", expected_artifact_paths=expected_artifacts
            ):
                return None
            if identity_doc.get("logicalProjectId") != str(model.logical_project_id):
                return None
            if identity_doc.get("toolkitVersion") != __version__:
                return None
        if identity_schema == 1:
            shared_fields = (
                "buildId",
                "gitHead",
                "gitDirty",
                "inputSnapshotSha256",
                "targetDevice",
                "preset",
            )
        elif identity_schema == SNAPSHOT_IDENTITY_SCHEMA_VERSION:
            shared_fields = (
                "buildId",
                "sourceBaseline",
                "gitHead",
                "gitDirty",
                "gitEvidence",
                "inputSnapshotSha256",
                "targetDevice",
                "preset",
            )
        else:
            return None
        for field in shared_fields:
            if record.get(field) != identity_doc.get(field):
                return None
        if identity_doc.get("elfPath") != elf_rel or identity_doc.get("mapPath") != map_rel:
            return None

        snapshot = snapshot_project_inputs(model, policy=identity_discovery_policy(identity_doc))
        if snapshot.sha256 != identity_doc.get("inputSnapshotSha256"):
            return None
        if identity_schema == 1:
            git = git_evidence(root)
            if git.head != identity_doc.get("gitHead"):
                return None
            source_baseline = "git"
        else:
            # Snapshot freshness is decided from the exact input snapshot
            # and artifacts; Git unavailability is evidence, never "clean".
            if identity_doc.get("sourceBaseline") != SOURCE_BASELINE_INPUT_SNAPSHOT:
                return None
            if identity_doc.get("gitHead") is not None:
                return None
            if identity_doc.get("gitDirty") is not None:
                return None
            evidence = identity_doc.get("gitEvidence")
            if (
                not isinstance(evidence, dict)
                or evidence.get("status") != "unavailable"
                or not isinstance(evidence.get("code"), str)
                or not isinstance(evidence.get("rule"), str)
            ):
                return None
            source_baseline = SOURCE_BASELINE_INPUT_SNAPSHOT
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
            "inputDiscoveryPolicy": identity_discovery_policy(identity_doc),
            "elfSha256": identity_doc["elfSha256"],
            "preset": "arm-debug",
            "gitHead": identity_doc["gitHead"],
            "gitDirty": identity_doc["gitDirty"],
            "sourceBaseline": source_baseline,
            "gitEvidence": (
                dict(identity_doc["gitEvidence"]) if identity_schema != 1 else None
            ),
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
