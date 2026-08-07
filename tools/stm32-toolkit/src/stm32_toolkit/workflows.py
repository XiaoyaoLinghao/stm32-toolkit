"""Shared stable workflow adapters (STM32TK-0306).

The adapter layer owns input validation, exception translation, fresh
replanning, and plan-ID comparison.  It imports the accepted core modules
(Keil inspection, migration, generation, build, project model) and never
lets them import back; all mutation goes through
``apply_keil_conversion`` / ``apply_project_configuration`` / ``run_build``.

Every conversion/configuration call freshly recomputes the deterministic
plan from current disk state and compares the exact plan ID immediately
before apply.  ``authorized`` must be the JSON boolean ``True``; any other
value fails closed without calling an apply seam.
"""

from __future__ import annotations

from pathlib import Path

from stm32_toolkit.build import BuildRequest, run_build
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
    apply_keil_conversion,
    plan_keil_conversion,
)
from stm32_toolkit.migration.model import portable_path_error
from stm32_toolkit.project_model import ProjectManifestError, load_project_model
from stm32_toolkit.result import OperationResult

#: Adapter-owned stable failure codes (work order section 6.5).
WORKFLOW_INPUT_INVALID = "WORKFLOW_INPUT_INVALID"
AUTHORIZATION_REQUIRED = "AUTHORIZATION_REQUIRED"
PLAN_CHANGED = "PLAN_CHANGED"
KEIL_INSPECTION_UNAVAILABLE = "KEIL_INSPECTION_UNAVAILABLE"
MIGRATION_PLAN_UNAVAILABLE = "MIGRATION_PLAN_UNAVAILABLE"
CONFIGURATION_PLAN_UNAVAILABLE = "CONFIGURATION_PLAN_UNAVAILABLE"

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


def _require_plan_id(value: object) -> None:
    """Raise ``_InputInvalid`` unless ``value`` is exactly 64 lowercase hex."""
    if value is None:
        raise _InputInvalid("planId", "required")
    if not isinstance(value, str) or len(value) != 64 or not _PLAN_ID_CHARS.issuperset(value):
        raise _InputInvalid("planId", "format", allowed="64 lowercase hex characters")


def _apply_intent(plan_id: object, authorized: object) -> bool:
    """True when the caller's arguments indicate an apply request."""
    return plan_id is not None or authorized is not False


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
    return OperationResult.success("keil-inspect", data)


# ---------------------------------------------------------------------------
# conversion plan/apply
# ---------------------------------------------------------------------------


def convert_keil_workflow(
    project_root: Path,
    *,
    uvprojx: str | None = None,
    target_name: str | None = None,
    plan_id: str | None = None,
    authorized: bool = False,
) -> OperationResult[dict[str, object]]:
    """Read-only conversion plan, or apply only with the exact plan ID."""
    operation = "keil-conversion-apply" if _apply_intent(plan_id, authorized) else "keil-conversion-plan"
    try:
        root = _bind_project_root(project_root)
        uvprojx_path = _optional_portable_path(uvprojx, "uvprojx")
        target = _optional_name(target_name, "targetName")
    except _InputInvalid as error:
        return _failure(
            operation,
            WORKFLOW_INPUT_INVALID,
            "Keil conversion workflow input is invalid",
            error.details,
        )

    try:
        inspection = inspect_keil(root, uvprojx_path, target)
        plan = plan_keil_conversion(root, inspection)
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

    if authorized is not True:
        if plan_id is not None:
            return _failure(
                operation,
                AUTHORIZATION_REQUIRED,
                "authorization is required to apply the conversion plan",
                {"field": "authorized", "rule": "required"},
            )
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
    return apply_keil_conversion(plan)


# ---------------------------------------------------------------------------
# configuration plan/apply
# ---------------------------------------------------------------------------


def configure_project_workflow(
    project_root: Path,
    *,
    plan_id: str | None = None,
    authorized: bool = False,
) -> OperationResult[dict[str, object]]:
    """Read-only configuration plan, or apply only with the exact plan ID."""
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

    try:
        model = load_project_model(root)
        plan = plan_project_configuration(model)
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

    if authorized is not True:
        if plan_id is not None:
            return _failure(
                operation,
                AUTHORIZATION_REQUIRED,
                "authorization is required to apply the configuration plan",
                {"field": "authorized", "rule": "required"},
            )
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

    if authorized is not True:
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
