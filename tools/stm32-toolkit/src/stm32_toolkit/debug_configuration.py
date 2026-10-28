"""Pure debug-configuration validation and diagnostics.

This module is deliberately inert: it never imports PyOCD, connects a probe,
queries a target catalog, downloads a package or maps a Keil device.  Target
syntax validation is therefore only a shape check and says nothing about
whether a target is installed, supported or matches a physical device.

The same helpers serve the project-configure edit route (an explicit
``debug_backend``/``debug_target`` pair) and read-only context/preflight
reporting, so both describe a missing or invalid pair identically.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: The only supported debug backend.  Selecting it records metadata only.
DEBUG_BACKEND_PYOCD = "pyocd"

#: Stable diagnostic/error codes.  They never vary with host formatting.
DEBUG_CONFIGURATION_INVALID = "DEBUG_CONFIGURATION_INVALID"
DEBUG_BACKEND_MISSING = "DEBUG_BACKEND_MISSING"
DEBUG_TARGET_MISSING = "DEBUG_TARGET_MISSING"
DEBUG_BACKEND_UNSUPPORTED = "DEBUG_BACKEND_UNSUPPORTED"
DEBUG_TARGET_MALFORMED = "DEBUG_TARGET_MALFORMED"

#: The existing hardware identifier grammar.  Matching is exact: values are
#: never trimmed, case-folded or coerced.
DEBUG_TARGET_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"
_DEBUG_TARGET_RE = re.compile(DEBUG_TARGET_PATTERN)

CONFIGURED = "configured"
NEEDS_USER_INPUT = "needs-user-input"
TARGET_SUPPORT_NOT_CHECKED = "not-checked"

#: Every diagnostic names the real project-configure entry point plus the
#: explicit paired parameters.  These strings are part of the public protocol,
#: so they must never invent a bare ``configure`` command or tool name.
_CONFIGURE_REMEDIATION = (
    "Rerun the project configure entry with both explicit parameters: "
    "`stm32-toolkit project configure --project <project> --debug-backend "
    "pyocd --debug-target <pyocd-target> --dry-run --json` (MCP: "
    "`stm32_project_configure` with `debugBackend` and `debugTarget`). "
    "Review the PLAN, then apply with "
    "`stm32-toolkit project configure --project <project> --debug-backend "
    "pyocd --debug-target <pyocd-target> --apply --json "
    "--plan-id <data.plan_id> --authorized` (MCP: the same pair with "
    "`planId=<data.plan_id>` and `authorized=true`)."
)
_BACKEND_REMEDIATION = (
    "Use the project configure entry to set the pair: "
    "`stm32-toolkit project configure --project <project> --debug-backend "
    "pyocd --debug-target <pyocd-target> --dry-run --json` (MCP: "
    "`stm32_project_configure` with `debugBackend` and `debugTarget`); "
    "`pyocd` is the only supported debug backend."
)
_TARGET_REMEDIATION = (
    "Use the project configure entry to set the pair: "
    "`stm32-toolkit project configure --project <project> --debug-backend "
    "pyocd --debug-target <pyocd-target> --dry-run --json` (MCP: "
    "`stm32_project_configure` with `debugBackend` and `debugTarget`). "
    "A target starts with an ASCII letter or digit, is at most 128 characters "
    "and contains only letters, digits, '.', '_', ':' or '-'."
)
_NEEDS_INPUT_NEXT_STEPS = (
    _CONFIGURE_REMEDIATION,
    (
        "Configuration presence does not install, discover or verify a PyOCD "
        "target; confirm target support separately before a debug session."
    ),
)
_CONFIGURED_NEXT_STEPS = (
    (
        "A configured debug pair only records metadata; a live debug session "
        "still requires an authorized debug handoff."
    ),
    (
        "If build or firmware identities predate this manifest edit, rebuild "
        "with --clean before flashing or debugging."
    ),
)


@dataclass(frozen=True)
class DebugDiagnostic:
    """One actionable, stable diagnostic for a debug configuration field."""

    code: str
    field: str
    rule: str
    message: str
    remediation: str

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "field": self.field,
            "rule": self.rule,
            "message": self.message,
            "remediation": self.remediation,
        }


@dataclass(frozen=True)
class DebugConfiguration:
    """A validated, explicitly requested debug backend/target pair."""

    backend: str
    target: str

    def to_dict(self) -> dict[str, object]:
        return {"backend": self.backend, "target": self.target}


@dataclass(frozen=True)
class DebugConfigurationStatus:
    """Read-only description of the manifest's current debug pair.

    ``backend``/``target`` echo the configured strings (null when absent or
    not a string).  A ``configured`` status means the pair is present and
    well-formed only; ``target_support`` stays ``not-checked`` and
    ``hardware_verified`` stays false.
    """

    backend: str | None
    target: str | None
    status: str
    missing_fields: tuple[str, ...]
    diagnostics: tuple[DebugDiagnostic, ...]
    target_support: str
    hardware_verified: bool
    next_steps: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "backend": self.backend,
            "target": self.target,
            "status": self.status,
            "missingFields": list(self.missing_fields),
            "diagnostics": [entry.to_dict() for entry in self.diagnostics],
            "targetSupport": self.target_support,
            "hardwareVerified": self.hardware_verified,
            "nextSteps": list(self.next_steps),
        }


class DebugConfigurationError(Exception):
    """Structured refusal for an incomplete or invalid requested pair.

    ``details`` is safe for protocol responses: it carries only stable codes,
    field/rule names and remediation text, never host paths or raw input
    beyond the echoed field name.
    """

    code = DEBUG_CONFIGURATION_INVALID

    def __init__(
        self,
        diagnostics: tuple[DebugDiagnostic, ...],
        missing_fields: tuple[str, ...],
    ) -> None:
        self.diagnostics = tuple(diagnostics)
        self.missing_fields = tuple(missing_fields)
        first = self.diagnostics[0]
        self.message = first.message
        super().__init__(self.message)
        self.details: dict[str, object] = {
            "field": first.field,
            "rule": first.rule,
            "diagnostics": [entry.to_dict() for entry in self.diagnostics],
            "missingFields": list(self.missing_fields),
        }


def _backend_diagnostic(value: object) -> DebugDiagnostic | None:
    if value is None:
        return DebugDiagnostic(
            DEBUG_BACKEND_MISSING,
            "debug.backend",
            "missing",
            "debug.backend is not configured",
            _BACKEND_REMEDIATION,
        )
    if type(value) is not str:
        return DebugDiagnostic(
            DEBUG_BACKEND_UNSUPPORTED,
            "debug.backend",
            "type",
            "debug.backend must be a string",
            _BACKEND_REMEDIATION,
        )
    if value == "":
        return DebugDiagnostic(
            DEBUG_BACKEND_UNSUPPORTED,
            "debug.backend",
            "empty",
            "debug.backend is empty",
            _BACKEND_REMEDIATION,
        )
    if value != DEBUG_BACKEND_PYOCD:
        return DebugDiagnostic(
            DEBUG_BACKEND_UNSUPPORTED,
            "debug.backend",
            "unsupported",
            "debug.backend is not supported",
            _BACKEND_REMEDIATION,
        )
    return None


def _target_diagnostic(value: object) -> DebugDiagnostic | None:
    if value is None:
        return DebugDiagnostic(
            DEBUG_TARGET_MISSING,
            "debug.target",
            "missing",
            "debug.target is not configured",
            _TARGET_REMEDIATION,
        )
    if type(value) is not str:
        return DebugDiagnostic(
            DEBUG_TARGET_MALFORMED,
            "debug.target",
            "type",
            "debug.target must be a string",
            _TARGET_REMEDIATION,
        )
    if value == "":
        return DebugDiagnostic(
            DEBUG_TARGET_MALFORMED,
            "debug.target",
            "empty",
            "debug.target is empty",
            _TARGET_REMEDIATION,
        )
    if _DEBUG_TARGET_RE.fullmatch(value) is None:
        return DebugDiagnostic(
            DEBUG_TARGET_MALFORMED,
            "debug.target",
            "pattern",
            "debug.target is malformed",
            _TARGET_REMEDIATION,
        )
    return None


def _diagnostics(
    backend: object, target: object
) -> tuple[tuple[DebugDiagnostic, ...], tuple[str, ...]]:
    diagnostics: list[DebugDiagnostic] = []
    missing: list[str] = []
    backend_diagnostic = _backend_diagnostic(backend)
    if backend_diagnostic is not None:
        diagnostics.append(backend_diagnostic)
    if backend is None:
        missing.append("debug.backend")
    target_diagnostic = _target_diagnostic(target)
    if target_diagnostic is not None:
        diagnostics.append(target_diagnostic)
    if target is None:
        missing.append("debug.target")
    return tuple(diagnostics), tuple(missing)


def normalize_debug_configuration(
    backend: object, target: object
) -> DebugConfiguration | None:
    """Return the validated pair, ``None`` when both are omitted, or raise.

    Both values omitted is the legacy configure request.  Providing only one
    value, a non-string value, an empty/whitespace value or any backend other
    than ``pyocd`` refuses with every applicable field diagnostic at once.
    """
    if backend is None and target is None:
        return None
    diagnostics, missing = _diagnostics(backend, target)
    if diagnostics:
        raise DebugConfigurationError(diagnostics, missing)
    assert isinstance(backend, str) and isinstance(target, str)
    return DebugConfiguration(backend=backend, target=target)


def describe_debug_configuration(backend: object, target: object) -> DebugConfigurationStatus:
    """Describe the current manifest pair without rewriting or verifying it."""
    diagnostics, missing = _diagnostics(backend, target)
    configured = not diagnostics
    return DebugConfigurationStatus(
        backend=backend if isinstance(backend, str) else None,
        target=target if isinstance(target, str) else None,
        status=CONFIGURED if configured else NEEDS_USER_INPUT,
        missing_fields=missing,
        diagnostics=diagnostics,
        target_support=TARGET_SUPPORT_NOT_CHECKED,
        hardware_verified=False,
        next_steps=(
            _CONFIGURED_NEXT_STEPS if configured else _NEEDS_INPUT_NEXT_STEPS
        ),
    )


_POST_MIGRATION_NEXT_STEPS = (
    (
        "Post-migration step only, never a conversion blocker or "
        "planReadiness prerequisite: after an authorized conversion writes "
        "`debug: {}` into .stm32-project.json, bind that conversion's "
        "destination root (`data.outputRoot` from the successful APPLY) as "
        "the project root for later CLI `--project-root` calls and for the "
        "bound MCP server. The read-only Keil source root is not the new "
        "project."
    ),
    (
        "Then record the pair through the existing project configure entry "
        "with both explicit parameters: "
        "`stm32-toolkit project configure --project <project> "
        "--debug-backend pyocd --debug-target <pyocd-target> --dry-run "
        "--json` (MCP: `stm32_project_configure` with `debugBackend` and "
        "`debugTarget`). Review that PLAN, then apply exactly that plan with "
        "`--apply --json --plan-id <data.plan_id> --authorized` (MCP: the "
        "same pair plus `planId=<data.plan_id>` and `authorized=true`). Both "
        "values are explicit user choices; no backend or target is inferred "
        "from the Keil project or the device name."
    ),
    (
        "Do this before establishing build or flash identities: the manifest "
        "edit naturally invalidates earlier build/firmware identity, so "
        "record the pair first and only then build and flash. Read the actual "
        "`data.build.buildId` and `data.build.elfSha256` from that fresh "
        "arm-debug build, and keep any flash as its own authorized step."
    ),
    (
        "A recorded pair is metadata only; target support and physical "
        "hardware remain unverified until a separate authorized debug "
        "handoff."
    ),
    (
        "The generated `.vscode/launch.json` stays empty by design: a live "
        "Cortex-Debug configuration exists only after an authorized "
        "handoff-begin, whose `data.cortexDebugLaunch.configuration` belongs "
        "to an independent external IDE workspace. Use it in that external "
        "workspace instead of writing a static launch configuration or "
        "rewriting the managed launch.json; detach the real IDE session, then "
        "run handoff-end with the original ticket. This guidance performs no "
        "hardware action and grants no authorization."
    ),
)


def post_migration_debug_configuration() -> dict[str, object]:
    """Describe the planned post-migration build-only model.

    An ordinary conversion emits ``debug: {}``.  That is valid for
    build-only use and is never a migration technical blocker or a
    planReadiness prerequisite.  The returned mapping keeps the shared
    status shape and adds explicit non-blocking markers.

    This is the single source of post-migration debug guidance: the read-only
    Keil preflight, the delivery PLAN and a successful delivery APPLY all
    expose it unchanged, and the delivery ``followUp`` string is derived from
    the same ``nextSteps``.  It is presentation only, so it never enters a
    plan/content identity, an output snapshot or an authorization decision.
    """
    payload = describe_debug_configuration(None, None).to_dict()
    payload["blocking"] = False
    payload["phase"] = "post-migration"
    payload["nextSteps"] = list(_POST_MIGRATION_NEXT_STEPS)
    return payload
