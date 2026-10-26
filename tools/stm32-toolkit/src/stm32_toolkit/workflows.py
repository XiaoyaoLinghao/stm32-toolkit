"""Shared stable workflow adapters (STM32TK-0306).

The adapter layer owns input validation, exception translation, fresh
replanning, and plan-ID comparison.  It imports the accepted core modules
(Keil inspection, migration, generation, build, project model) and never
lets them import back; all mutation goes through
``apply_keil_delivery`` / ``apply_project_configuration`` / ``run_build``.
Keil conversion is an independent delivery into an explicit new directory;
the legacy in-place ``plan_keil_conversion``/``apply_keil_conversion``
engines remain available for historical evidence but are not a public
fallback.

Every conversion/configuration call freshly recomputes the deterministic
plan from current disk state and compares the exact plan ID immediately
before apply.  ``authorized`` must be the JSON boolean ``True``; any other
value fails closed without calling an apply seam.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from stm32_toolkit.build import BuildRequest, run_build
from stm32_toolkit.extra_regions import (
    ExtraRegionError,
    normalize_extra_regions_option,
)
from stm32_toolkit.generation import (
    GenerationError,
    apply_project_configuration,
    plan_project_configuration,
)
from stm32_toolkit.keil import (
    KeilInspectionError,
    capture_keil_baseline,
    inspect_keil,
)
from stm32_toolkit.migration import (
    MigrationPlanError,
    apply_keil_delivery,
    plan_keil_delivery,
    preflight_keil_conversion,
)
from stm32_toolkit.memory_layout import (
    MemoryLayoutError,
    normalize_memory_layout_option,
)
from stm32_toolkit.migration.model import portable_path_error
from stm32_toolkit.migration.startup import normalize_startup_options
from stm32_toolkit.project_model import ProjectManifestError, load_project_model
from stm32_toolkit.result import OperationResult

#: Adapter-owned stable failure codes (work order section 6.5).
WORKFLOW_INPUT_INVALID = "WORKFLOW_INPUT_INVALID"
AUTHORIZATION_REQUIRED = "AUTHORIZATION_REQUIRED"
PLAN_CHANGED = "PLAN_CHANGED"
KEIL_INSPECTION_UNAVAILABLE = "KEIL_INSPECTION_UNAVAILABLE"
MIGRATION_PLAN_UNAVAILABLE = "MIGRATION_PLAN_UNAVAILABLE"
KEIL_PREFLIGHT_UNAVAILABLE = "KEIL_PREFLIGHT_UNAVAILABLE"
CONFIGURATION_PLAN_UNAVAILABLE = "CONFIGURATION_PLAN_UNAVAILABLE"
DELIVERY_DESTINATION_REQUIRED = "DELIVERY_DESTINATION_REQUIRED"

SUPPORTED_PRESETS = ("arm-debug", "arm-release")
_MIN_TIMEOUT_SECONDS = 1
_MAX_TIMEOUT_SECONDS = 3600
_PLAN_ID_CHARS = frozenset("0123456789abcdef")


class _InputInvalid(Exception):
    """Internal adapter-owned input failure translated to WORKFLOW_INPUT_INVALID."""

    def __init__(self, field: str, rule: str, **extra: object) -> None:
        super().__init__(f"{field}:{rule}")
        self.details: dict[str, object] = {"field": field, "rule": rule}
        self.details.update(extra)


def _failure(
    operation: str, code: str, message: str, details: dict[str, object]
) -> OperationResult[None]:
    return OperationResult.failure(operation, code, message, details)


def _bind_project_root(project_root: object) -> Path:
    """Canonicalize the caller-supplied project root or raise ``_InputInvalid``."""
    if not isinstance(project_root, Path):
        raise _InputInvalid("projectRoot", "type")
    try:
        canonical = project_root.expanduser().resolve(strict=True)
    except (OSError, RuntimeError, ValueError):
        raise _InputInvalid("projectRoot", "value") from None
    if not canonical.is_dir():
        raise _InputInvalid("projectRoot", "value")
    return canonical


def _optional_portable_path(value: object, field: str) -> Path | None:
    """Validate a caller-supplied optional portable project-relative path."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise _InputInvalid(field, "type")
    # Portable paths use ``/``; a backslash is ambiguous across hosts.
    if "\\" in value:
        raise _InputInvalid(field, "portablePath")
    if portable_path_error(value) is not None:
        raise _InputInvalid(field, "portablePath")
    return Path(value)


def _optional_name(value: object, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise _InputInvalid(field, "type")
    return value


def _delivery_destination(value: object) -> Path:
    """Return the explicit destination as a Path (absolute is checked later)."""
    if isinstance(value, Path):
        return value
    if isinstance(value, str):
        return Path(value)
    raise _InputInvalid("destination", "type")


def _destination_required(operation: str) -> OperationResult[None]:
    """Fail with the public requirement to choose an independent output root."""
    return _failure(
        operation,
        DELIVERY_DESTINATION_REQUIRED,
        "an absolute new output directory is required for Keil conversion",
        {
            "field": "destination",
            "rule": "required",
            "example": "C:/work/my-project-gcc",
            "rationale": (
                "The Keil source is read-only; the deliverable is a separate,"
                " independently buildable GCC/CMake project. Choose an absolute"
                " directory outside the source that is absent or empty."
            ),
        },
    )


def _require_plan_id(value: object) -> None:
    """Raise ``_InputInvalid`` unless ``value`` is exactly 64 lowercase hex."""
    if value is None:
        raise _InputInvalid("planId", "required")
    if not isinstance(value, str) or len(value) != 64 or not _PLAN_ID_CHARS.issuperset(value):
        raise _InputInvalid("planId", "format", allowed="64 lowercase hex characters")


def _apply_intent(plan_id: object, authorized: object) -> bool:
    """True when the caller's arguments indicate an apply request.

    Only the JSON boolean ``True`` authorizes apply; ``False`` is the
    read-only plan mode.  Every other value is an apply intent that fails
    closed with ``AUTHORIZATION_REQUIRED`` before any core call.
    """
    return plan_id is not None or authorized is not False


def _authorization_failure(
    operation: str, authorized: object
) -> OperationResult[None] | None:
    """Return the fail-closed authorization envelope for non-boolean values.

    Only ``authorized is False`` may enter read-only planning and only
    ``authorized is True`` may apply; strings, integers, null, and
    containers always fail closed here without inspect/plan/apply work.
    """
    if type(authorized) is bool:
        return None
    return _failure(
        operation,
        AUTHORIZATION_REQUIRED,
        "authorization must be the JSON boolean true",
        {"field": "authorized", "rule": "type"},
    )


# ---------------------------------------------------------------------------
# inspect
# ---------------------------------------------------------------------------


def inspect_keil_workflow(
    project_root: Path,
    *,
    uvprojx: str | None = None,
    target_name: str | None = None,
    include_baseline: bool = True,
) -> OperationResult[dict[str, object]]:
    """Read-only Keil inspection plus optional AXF/MAP baseline evidence."""
    try:
        root = _bind_project_root(project_root)
        uvprojx_path = _optional_portable_path(uvprojx, "uvprojx")
        target = _optional_name(target_name, "targetName")
        if type(include_baseline) is not bool:
            raise _InputInvalid("includeBaseline", "type")
    except _InputInvalid as error:
        return _failure(
            "keil-inspect",
            WORKFLOW_INPUT_INVALID,
            "Keil inspection workflow input is invalid",
            error.details,
        )

    try:
        inspection = inspect_keil(root, uvprojx_path, target)
        baseline = (
            capture_keil_baseline(root, inspection) if include_baseline else None
        )
    except KeilInspectionError as error:
        return _failure("keil-inspect", error.code, error.message, error.details)
    except (OSError, ValueError):
        return _failure(
            "keil-inspect",
            KEIL_INSPECTION_UNAVAILABLE,
            "Keil inspection is unavailable",
            {"field": "inspection", "rule": "unavailable"},
        )

    data: dict[str, object] = {"inspection": inspection.to_dict(), "baseline": None}
    if baseline is not None:
        data["baseline"] = baseline.to_dict()
    result = OperationResult.success("keil-inspect", data)
    if baseline is not None:
        return replace(
            result, details={"baselineSemantics": "parseable-historical-artifact-only"}
        )
    return result


# ---------------------------------------------------------------------------
# preflight
# ---------------------------------------------------------------------------


def preflight_keil_workflow(
    project_root: Path,
    *,
    uvprojx: str | None = None,
    target_name: str | None = None,
    startup_strategy: str | None = None,
    startup_source: str | None = None,
    memory_layout: object = None,
    extra_regions: object = None,
) -> OperationResult[dict[str, object]]:
    """Read-only migration preflight; analysis succeeds without Git.

    The result always means "analysis completed", never "apply authorized".
    Technical blockers and Git/apply prerequisites are reported separately.
    """
    operation = "keil-preflight"
    try:
        root = _bind_project_root(project_root)
        uvprojx_path = _optional_portable_path(uvprojx, "uvprojx")
        target = _optional_name(target_name, "targetName")
        strategy = _optional_name(startup_strategy, "startupStrategy")
        source = _optional_name(startup_source, "startupSource")
        startup_options = normalize_startup_options(strategy, source)
        layout = normalize_memory_layout_option(memory_layout)
        extras = normalize_extra_regions_option(extra_regions)
    except _InputInvalid as error:
        return _failure(
            operation,
            WORKFLOW_INPUT_INVALID,
            "Keil preflight workflow input is invalid",
            error.details,
        )
    except MigrationPlanError as error:
        return _failure(operation, error.code, error.message, error.details)
    except MemoryLayoutError as error:
        return _failure(operation, error.code, error.message, error.details)
    except ExtraRegionError as error:
        return _failure(operation, error.code, error.message, error.details)

    try:
        inspection = inspect_keil(root, uvprojx_path, target)
        data = preflight_keil_conversion(
            root,
            inspection,
            startup_options=startup_options,
            memory_layout=layout,
            extra_regions=extras,
        )
    except KeilInspectionError as error:
        return _failure(operation, error.code, error.message, error.details)
    except MigrationPlanError as error:
        return _failure(operation, error.code, error.message, error.details)
    except (OSError, ValueError):
        return _failure(
            operation,
            KEIL_PREFLIGHT_UNAVAILABLE,
            "Keil preflight is unavailable",
            {"field": "preflight", "rule": "unavailable"},
        )

    return replace(
        OperationResult.success(operation, data),
        details={
            "analysisOnly": True,
            "grantsApplyAuthorization": False,
            "hardwareDiscovery": "not-performed",
        },
    )


# ---------------------------------------------------------------------------
# conversion plan/apply
# ---------------------------------------------------------------------------


def convert_keil_workflow(
    project_root: Path,
    *,
    destination: object = None,
    uvprojx: str | None = None,
    target_name: str | None = None,
    plan_id: str | None = None,
    authorized: bool = False,
    startup_strategy: str | None = None,
    startup_source: str | None = None,
    memory_layout: object = None,
    extra_regions: object = None,
) -> OperationResult[dict[str, object]]:
    """Plan or apply one independent Keil-to-GCC delivery.

    The source project is read-only.  ``destination`` is an explicit absolute
    directory outside it that is absent or verified empty; there is no
    in-place fallback.  The returned PLAN is the complete delivery preview
    (``planId``/``sourceSnapshotSha256``/``outputs``/``sourcePatches``), and
    APPLY publishes one complete output directory without building or
    flashing it.  Git is optional and never a plan prerequisite.

    The destination, startup, memory-layout and extra-region options are part
    of the plan identity.  Apply re-runs the deterministic plan with the
    request options and refuses a stale plan ID, so a caller-edited
    destination/option request cannot be accepted after review.
    """
    operation = "keil-conversion-apply" if _apply_intent(plan_id, authorized) else "keil-conversion-plan"
    try:
        root = _bind_project_root(project_root)
        output_root = None if destination is None else _delivery_destination(destination)
        uvprojx_path = _optional_portable_path(uvprojx, "uvprojx")
        target = _optional_name(target_name, "targetName")
        strategy = _optional_name(startup_strategy, "startupStrategy")
        source = _optional_name(startup_source, "startupSource")
        startup_options = normalize_startup_options(strategy, source)
        layout = normalize_memory_layout_option(memory_layout)
        extras = normalize_extra_regions_option(extra_regions)
    except _InputInvalid as error:
        return _failure(
            operation,
            WORKFLOW_INPUT_INVALID,
            "Keil conversion workflow input is invalid",
            error.details,
        )
    except MigrationPlanError as error:
        return _failure(operation, error.code, error.message, error.details)
    except MemoryLayoutError as error:
        return _failure(operation, error.code, error.message, error.details)
    except ExtraRegionError as error:
        return _failure(operation, error.code, error.message, error.details)

    closed = _authorization_failure(operation, authorized)
    if closed is not None:
        return closed
    if authorized is False and plan_id is not None:
        return _failure(
            operation,
            AUTHORIZATION_REQUIRED,
            "authorization is required to apply the conversion plan",
            {"field": "authorized", "rule": "required"},
        )
    if output_root is None:
        return _destination_required(operation)

    try:
        inspection = inspect_keil(root, uvprojx_path, target)
        plan = plan_keil_delivery(
            root,
            output_root,
            inspection,
            startup_options=startup_options,
            memory_layout=layout,
            extra_regions=extras,
        )
    except KeilInspectionError as error:
        return _failure(operation, error.code, error.message, error.details)
    except MigrationPlanError as error:
        return _failure(operation, error.code, error.message, error.details)
    except (OSError, ValueError):
        return _failure(
            operation,
            MIGRATION_PLAN_UNAVAILABLE,
            "Keil conversion plan is unavailable",
            {"field": "plan", "rule": "unavailable"},
        )

    if authorized is False:
        return OperationResult.success("keil-conversion-plan", plan.to_dict())

    try:
        _require_plan_id(plan_id)
    except _InputInvalid as error:
        return _failure(
            operation,
            AUTHORIZATION_REQUIRED,
            "authorization requires the exact current plan ID",
            error.details,
        )
    if plan_id != plan.plan_id:
        return _failure(
            operation,
            PLAN_CHANGED,
            "the conversion plan changed since planning",
            {"field": "planId", "rule": "stale", "currentPlanId": plan.plan_id},
        )
    applied = apply_keil_delivery(plan, authorized=True, plan_id=plan_id)
    return replace(applied, operation=operation)


# ---------------------------------------------------------------------------
# configuration plan/apply
# ---------------------------------------------------------------------------


def configure_project_workflow(
    project_root: Path,
    *,
    plan_id: str | None = None,
    authorized: bool = False,
    debug_backend: object = None,
    debug_target: object = None,
    vscode_toolkit_path: object = None,
    vscode_gcc_path: object = None,
) -> OperationResult[dict[str, object]]:
    """Read-only configuration plan, or apply only with the exact plan ID.

    ``debug_backend``/``debug_target`` are passed through unchanged: supplying
    both selects the explicit manifest-edit route, supplying neither keeps the
    historical build-only route, and an incomplete or malformed pair is
    refused by the shared debug validator with complete field diagnostics.
    ``vscode_toolkit_path``/``vscode_gcc_path`` are likewise passed through:
    supplying both renders the validated absolute native paths, omitting both
    keeps the portable user-setting defaults.  Applying requires the same
    options, so a changed or omitted pair is a different plan and is refused
    before any write.
    """
    operation = (
        "project-configuration-apply"
        if _apply_intent(plan_id, authorized)
        else "project-configuration-plan"
    )
    try:
        root = _bind_project_root(project_root)
    except _InputInvalid as error:
        return _failure(
            operation,
            WORKFLOW_INPUT_INVALID,
            "Project configuration workflow input is invalid",
            error.details,
        )

    closed = _authorization_failure(operation, authorized)
    if closed is not None:
        return closed
    if authorized is False and plan_id is not None:
        return _failure(
            operation,
            AUTHORIZATION_REQUIRED,
            "authorization is required to apply the configuration plan",
            {"field": "authorized", "rule": "required"},
        )

    try:
        model = load_project_model(root)
        if (
            debug_backend is None
            and debug_target is None
            and vscode_toolkit_path is None
            and vscode_gcc_path is None
        ):
            # Historical configure route: call the accepted one-argument
            # planning shape exactly, preserving legacy doubles and shape.
            plan = plan_project_configuration(model)
        else:
            # Any supplied value (including only one of a pair) goes through
            # the shared validators unchanged so incomplete/invalid pairs still
            # fail with complete field diagnostics.
            plan = plan_project_configuration(
                model,
                debug_backend=debug_backend,
                debug_target=debug_target,
                vscode_toolkit_path=vscode_toolkit_path,
                vscode_gcc_path=vscode_gcc_path,
            )
    except ProjectManifestError as error:
        return _failure(operation, error.code, error.message, error.details)
    except GenerationError as error:
        return _failure(operation, error.code, error.message, error.details)
    except (OSError, ValueError):
        return _failure(
            operation,
            CONFIGURATION_PLAN_UNAVAILABLE,
            "Project configuration plan is unavailable",
            {"field": "plan", "rule": "unavailable"},
        )

    if authorized is False:
        return OperationResult.success("project-configuration-plan", plan.to_dict())

    try:
        _require_plan_id(plan_id)
    except _InputInvalid as error:
        return _failure(
            operation,
            AUTHORIZATION_REQUIRED,
            "authorization requires the exact current plan ID",
            error.details,
        )
    if plan_id != plan.plan_id:
        return _failure(
            operation,
            PLAN_CHANGED,
            "the configuration plan changed since planning",
            {"field": "planId", "rule": "stale", "currentPlanId": plan.plan_id},
        )
    return apply_project_configuration(plan)


# ---------------------------------------------------------------------------
# build
# ---------------------------------------------------------------------------


def build_firmware_workflow(
    project_root: Path,
    *,
    preset: str,
    clean: bool = False,
    timeout_seconds: int = 300,
    authorized: bool,
) -> OperationResult[object]:
    """Run the guarded build; the caller must pass JSON boolean true."""
    try:
        root = _bind_project_root(project_root)
    except _InputInvalid as error:
        return _failure(
            "build",
            WORKFLOW_INPUT_INVALID,
            "Build workflow input is invalid",
            error.details,
        )

    if type(authorized) is not bool or authorized is not True:
        return _failure(
            "build",
            AUTHORIZATION_REQUIRED,
            "authorization is required to start a build",
            {"field": "authorized", "rule": "required"},
        )
    if preset not in SUPPORTED_PRESETS:
        return _failure(
            "build",
            WORKFLOW_INPUT_INVALID,
            "Build workflow input is invalid",
            {"field": "preset", "rule": "value", "allowed": "arm-debug|arm-release"},
        )
    if type(clean) is not bool:
        return _failure(
            "build",
            WORKFLOW_INPUT_INVALID,
            "Build workflow input is invalid",
            {"field": "clean", "rule": "type"},
        )
    if (
        type(timeout_seconds) is not int
        or not (_MIN_TIMEOUT_SECONDS <= timeout_seconds <= _MAX_TIMEOUT_SECONDS)
    ):
        return _failure(
            "build",
            WORKFLOW_INPUT_INVALID,
            "Build workflow input is invalid",
            {
                "field": "timeoutSeconds",
                "rule": "value",
                "allowed": "integer 1..3600",
            },
        )

    return run_build(
        BuildRequest(
            project_root=root,
            preset=preset,
            clean=clean,
            timeout_seconds=timeout_seconds,
        )
    )
