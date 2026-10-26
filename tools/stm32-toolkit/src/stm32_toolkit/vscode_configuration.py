"""Validated optional VS Code executable bindings (VSCODE-TASKS).

The generator defaults to explicit user-scope VS Code settings
(``stm32-toolkit.executablePath`` and ``stm32-toolkit.compilerPath``) instead
of discovering host programs or falling back to bare PATH names.  A caller may
instead supply both absolute native executable paths; both are then rendered
verbatim and bound into the immutable generation plan.

This module is deliberately inert beyond static filesystem inspection: it
never launches, probes, hashes or version-attests either executable.  Validation
says only that each value is an absolute, existing, non-redirected regular
native executable path.

:func:`build_vscode_guidance` derives the advisory PLAN/APPLY guidance from
those validated facts and existing preserved-file statuses.  It never reads
VS Code user settings or any user-owned editor file.
"""

from __future__ import annotations

import os
import re
import stat
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

VSCODE_CONFIGURATION_INVALID = "VSCODE_CONFIGURATION_INVALID"

#: The two portable user-scope settings the default generation route renders.
VSCODE_USER_SETTING_EXECUTABLE = "stm32-toolkit.executablePath"
VSCODE_USER_SETTING_COMPILER = "stm32-toolkit.compilerPath"

#: Fixed editor target whose preserved-unowned status needs explicit guidance.
_VSCODE_TASKS_PATH = ".vscode/tasks.json"

_FIELD_TOOLKIT = "vscode.toolkitPath"
_FIELD_GCC = "vscode.gccPath"

_VARIABLE_RE = re.compile(r"\$\{|\$\(|%[A-Za-z_][A-Za-z0-9_]*%")
_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
#: Narrow indirection so tests can simulate reparse components portably without
#: patching the global ``os`` module.
_LSTAT = os.lstat

_CONFIGURE_REMEDIATION = (
    "Rerun the project configure entry with both absolute native executable "
    "paths: `stm32-toolkit project configure --project <project> "
    "--vscode-toolkit-path <absolute stm32-toolkit executable> "
    "--vscode-gcc-path <absolute arm-none-eabi-gcc executable> --dry-run "
    "--json` (MCP: `stm32_project_configure` with `vscodeToolkitPath` and "
    "`vscodeGccPath`). Review the PLAN, then apply with the same two options, "
    "that exact data.plan_id and `--authorized`/`authorized=true`. Omit both "
    "options to keep the portable `${config:stm32-toolkit.executablePath}` "
    "and `${config:stm32-toolkit.compilerPath}` user-setting defaults."
)
_PAIR_REMEDIATION = (
    "Supply both `--vscode-toolkit-path` and `--vscode-gcc-path` (MCP: "
    "`vscodeToolkitPath` and `vscodeGccPath`), or omit both to keep the "
    "portable user-setting defaults. A single supplied path never authorizes "
    "a guess for the other."
)
_NATIVE_REMEDIATION = (
    "Pass the exact absolute native executable path. On Windows that is a "
    "regular `.exe` file, never a `.cmd`/`.bat` shell script, a directory, a "
    "symlink/reparse point, or a path containing `${...}`/`$(...)`/`%VAR%` "
    "variables. Spaces and Unicode are allowed. Confirm the binary identity "
    "with `stm32_doctor` separately; this static check is not a version or "
    "binary trust attestation."
)


@dataclass(frozen=True)
class VSCodeConfigurationDiagnostic:
    """One actionable, stable diagnostic for a VS Code executable binding."""

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
class VSCodeConfiguration:
    """A validated, explicitly requested pair of absolute native paths.

    Values are stored exactly as supplied so rendering, plan identity and
    replay compare the same strings; they are never normalized, trimmed or
    resolved.  ``toolkit_path`` configures generated process tasks and
    ``gcc_path`` configures IntelliSense only; neither selects the CMake
    build toolchain.
    """

    toolkit_path: str
    gcc_path: str

    def to_dict(self) -> dict[str, object]:
        return {
            "toolkitPath": self.toolkit_path,
            "gccPath": self.gcc_path,
        }


class VSCodeConfigurationError(Exception):
    """Structured refusal for an incomplete or unsafe VS Code binding pair."""

    code = VSCODE_CONFIGURATION_INVALID

    def __init__(
        self,
        diagnostics: tuple[VSCodeConfigurationDiagnostic, ...],
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


def _diagnostic(field: str, rule: str, message: str, remediation: str) -> VSCodeConfigurationDiagnostic:
    return VSCodeConfigurationDiagnostic(
        VSCODE_CONFIGURATION_INVALID, field, rule, message, remediation
    )


def _has_control_characters(value: str) -> bool:
    return any(ord(character) < 0x20 or 0x7F <= ord(character) <= 0x9F for character in value)


def _component_diagnostic(
    field: str, component: Path, *, terminal: bool
) -> VSCodeConfigurationDiagnostic | None:
    """Inspect one lexical path component without resolving redirects."""
    try:
        metadata = _LSTAT(component)
    except FileNotFoundError:
        return _diagnostic(
            field,
            "notFound",
            f"{field} does not exist",
            _NATIVE_REMEDIATION,
        )
    except NotADirectoryError:
        return _diagnostic(
            field,
            "parent",
            f"{field} has a parent that is not a directory",
            _NATIVE_REMEDIATION,
        )
    except OSError:
        return _diagnostic(
            field,
            "unavailable",
            f"{field} cannot be inspected",
            _NATIVE_REMEDIATION,
        )
    if stat.S_ISLNK(metadata.st_mode) or bool(
        getattr(metadata, "st_file_attributes", 0) & _REPARSE_POINT
    ):
        return _diagnostic(
            field,
            "redirect",
            f"{field} must not be a redirect",
            _NATIVE_REMEDIATION,
        )
    if not terminal:
        if not stat.S_ISDIR(metadata.st_mode):
            return _diagnostic(
                field,
                "parent",
                f"{field} has a parent that is not a directory",
                _NATIVE_REMEDIATION,
            )
        return None
    if stat.S_ISDIR(metadata.st_mode):
        return _diagnostic(
            field,
            "directory",
            f"{field} must be a file, not a directory",
            _NATIVE_REMEDIATION,
        )
    if not stat.S_ISREG(metadata.st_mode):
        return _diagnostic(
            field,
            "regularFile",
            f"{field} must be a regular file",
            _NATIVE_REMEDIATION,
        )
    return None


def _path_diagnostic(field: str, value: object) -> VSCodeConfigurationDiagnostic | None:
    """Return the first stable refusal for one supplied path value.

    Every lexical ancestor component is inspected as itself (never resolved),
    so a file reached through a symlink, junction or other reparse parent is
    refused even when the leaf is a regular file.
    """
    if type(value) is not str:
        return _diagnostic(field, "type", f"{field} must be a string", _NATIVE_REMEDIATION)
    if value.strip() == "":
        return _diagnostic(field, "empty", f"{field} is empty", _NATIVE_REMEDIATION)
    if _has_control_characters(value):
        return _diagnostic(
            field,
            "control",
            f"{field} contains a control character",
            _NATIVE_REMEDIATION,
        )
    if _VARIABLE_RE.search(value) is not None:
        return _diagnostic(
            field,
            "variable",
            f"{field} contains an unresolved variable",
            _NATIVE_REMEDIATION,
        )
    path = Path(value)
    if not path.is_absolute():
        return _diagnostic(
            field,
            "relative",
            f"{field} must be an absolute path",
            _NATIVE_REMEDIATION,
        )
    if os.name == "nt" and path.suffix.lower() != ".exe":
        return _diagnostic(
            field,
            "extension",
            f"{field} must be a native .exe file on Windows",
            _NATIVE_REMEDIATION,
        )
    parts = path.parts
    if len(parts) > 2:
        current = Path(parts[0])
        for part in parts[1:-1]:
            current = current / part
            diagnostic = _component_diagnostic(field, current, terminal=False)
            if diagnostic is not None:
                return diagnostic
    return _component_diagnostic(field, path, terminal=True)


def normalize_vscode_configuration(
    toolkit_path: object, gcc_path: object
) -> VSCodeConfiguration | None:
    """Return the validated pair, ``None`` when both are omitted, or raise.

    Both omitted is the portable user-setting default route.  Supplying only
    one, a non-string value, an empty/whitespace value, a control/variable
    containing value, a relative path or an unsafe target refuses with every
    applicable diagnostic before any plan is built.  No host discovery,
    execution or version attestation happens here.
    """
    if toolkit_path is None and gcc_path is None:
        return None
    diagnostics: list[VSCodeConfigurationDiagnostic] = []
    missing: list[str] = []
    for field, value in ((_FIELD_TOOLKIT, toolkit_path), (_FIELD_GCC, gcc_path)):
        if value is None:
            missing.append(field)
            diagnostics.append(
                _diagnostic(
                    field,
                    "missing",
                    f"{field} is not configured",
                    _PAIR_REMEDIATION,
                )
            )
            continue
        diagnostic = _path_diagnostic(field, value)
        if diagnostic is not None:
            diagnostics.append(diagnostic)
    if diagnostics:
        raise VSCodeConfigurationError(tuple(diagnostics), tuple(missing))
    assert isinstance(toolkit_path, str) and isinstance(gcc_path, str)
    return VSCodeConfiguration(toolkit_path=toolkit_path, gcc_path=gcc_path)


# ---------------------------------------------------------------------------
# derived PLAN/APPLY guidance (offline, advisory only)
# ---------------------------------------------------------------------------

_SETTINGS_REQUIRED_MESSAGE = (
    "The default generation route renders the VS Code task command "
    "`${config:stm32-toolkit.executablePath}` and the IntelliSense "
    "`compilerPath` `${config:stm32-toolkit.compilerPath}`. Those variables "
    "resolve from VS Code configuration, and this generator's supported "
    "default guidance is to supply both reviewed absolute native executable "
    "paths in User Settings; workspace configuration may also define them. "
    "This offline PLAN/APPLY does not evaluate your effective VS Code settings, "
    "so it makes no claim that the settings are absent, unbound, or incomplete."
)
_SETTINGS_REQUIRED_REMEDIATION = (
    "Put `stm32-toolkit.executablePath` and `stm32-toolkit.compilerPath` in "
    "VS Code **User Settings** with reviewed absolute native executable paths, "
    "or re-run PLAN and APPLY with the same explicitly paired "
    "`--vscode-toolkit-path`/`--vscode-gcc-path` options (MCP "
    "`vscodeToolkitPath`/`vscodeGccPath`) so the generated files carry the "
    "exact paths instead. PATH installation of the toolkit is not required and "
    "is not implied by this diagnostic."
)
_TASKS_PRESERVED_MESSAGE = (
    "The existing user-owned `.vscode/tasks.json` was retained unchanged: the "
    "requested executable bindings and the new STM32 Toolkit tasks were not "
    "applied to that file, and its contents were not inspected. Old bare "
    "commands may remain in it, so review it before running those tasks."
)
_TASKS_PRESERVED_REMEDIATION = (
    "Open `.vscode/tasks.json` manually and align each STM32 Toolkit task with "
    "the absolute managed runtime executable (for example "
    "`<DataRoot>/runtime/<version>/Scripts/stm32-toolkit.exe`) or with the "
    "documented User Settings `stm32-toolkit.executablePath` and "
    "`stm32-toolkit.compilerPath`. Inspect `data.vscodeGuidance` (this object) "
    "on PLAN or APPLY, `data.files[].status` and `unified_diff` for "
    "`.vscode/tasks.json` on PLAN, and `data.preservedPaths` on APPLY. This "
    "guidance does not claim that a bare command was found."
)


def build_vscode_guidance(
    configuration: VSCodeConfiguration | None,
    preserved_paths: Iterable[str] = (),
) -> dict[str, object]:
    """Derive advisory VS Code binding guidance from validated plan facts.

    ``configuration`` is the already-validated explicit pair or ``None`` for
    the portable user-setting default route. ``preserved_paths`` is exactly
    the plan's ``preserved-unowned`` editor paths; their contents are never
    read here. The result is presentation metadata only: it never authorizes
    a mutation, never asserts the VS Code user settings are unbound, and never
    claims that a preserved file contains a specific command.
    """
    binding_mode = "user-settings" if configuration is None else "explicit-paths"
    required_settings = (
        [VSCODE_USER_SETTING_EXECUTABLE, VSCODE_USER_SETTING_COMPILER]
        if configuration is None
        else []
    )
    paths = sorted(
        {str(path) for path in preserved_paths}, key=lambda value: value.encode("utf-8")
    )
    diagnostics: list[dict[str, object]] = []
    if configuration is None:
        diagnostics.append(
            {
                "code": "VSCODE_EXECUTABLE_SETTINGS_REQUIRED",
                "severity": "info",
                "message": _SETTINGS_REQUIRED_MESSAGE,
                "remediation": _SETTINGS_REQUIRED_REMEDIATION,
            }
        )
    if _VSCODE_TASKS_PATH in paths:
        diagnostics.append(
            {
                "code": "VSCODE_TASKS_PRESERVED",
                "severity": "warning",
                "path": _VSCODE_TASKS_PATH,
                "message": _TASKS_PRESERVED_MESSAGE,
                "remediation": _TASKS_PRESERVED_REMEDIATION,
            }
        )
    return {
        "bindingMode": binding_mode,
        "requiredUserSettings": required_settings,
        "userSettingsChecked": False,
        "preservedPaths": paths,
        "diagnostics": diagnostics,
    }


__all__ = [
    "VSCODE_CONFIGURATION_INVALID",
    "VSCODE_USER_SETTING_COMPILER",
    "VSCODE_USER_SETTING_EXECUTABLE",
    "VSCodeConfiguration",
    "VSCodeConfigurationDiagnostic",
    "VSCodeConfigurationError",
    "build_vscode_guidance",
    "normalize_vscode_configuration",
]
