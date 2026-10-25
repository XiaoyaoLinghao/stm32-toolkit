"""Bounded, read-only observation of optional editor and Keil readiness evidence.

Nothing in this module installs, updates, launches an editor window, activates
a license, builds a project, or touches hardware.  A process that succeeds
while producing partial, truncated, ambiguous, or malformed output never
manufactures an ``installed`` or ``missing`` fact.
"""

from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from stm32_toolkit.tool_support import (
    ProcessObservation,
    ToolSupportProfile,
    _canonical_directory,
    _canonical_regular_file,
    _lexists,
    _run_bounded,
    _windows_file_version,
)

#: The exact three recommended VS Code extensions.
RECOMMENDED_EXTENSIONS = (
    "ms-vscode.cpptools",
    "ms-vscode.cmake-tools",
    "marus25.cortex-debug",
)
#: Declared by the debug-handoff companion profile; observed versions are only
#: compared with this value, never treated as physical validation.
CORTEX_DEBUG_PROFILE_VERSION = "1.12.1"

_IS_WINDOWS = os.name == "nt"

EXTENSION_LIST_TIMEOUT_SECONDS = 10.0
EXTENSION_LIST_CAPTURE_LIMIT = 64 * 1024
ARMCC_TIMEOUT_SECONDS = 5.0
ARMCC_CAPTURE_LIMIT = 8 * 1024
_LAUNCHER_CAPTURE_LIMIT = 16 * 1024
_ARMCC_VERSION_LIMIT = 200

_EXTENSION_VERSION = (
    r"\d{1,16}(?:\.\d{1,16}){1,3}"
    r"(?:-[0-9A-Za-z][0-9A-Za-z.-]{0,63})?"
    r"(?:\+[0-9A-Za-z][0-9A-Za-z.-]{0,63})?"
)
_EXTENSION_LINE = re.compile(
    rf"^([A-Za-z0-9][A-Za-z0-9._-]{{0,127}})@({_EXTENSION_VERSION})$"
)
_LAUNCHER_LINE = re.compile(
    r'^"%~dp0\.\.\\Code\.exe" '
    r'"%~dp0\.\.\\(?:([A-Za-z0-9][A-Za-z0-9._-]{0,63})\\)?'
    r'resources\\app\\out\\cli\.js" %\*$'
)
_ARMCC_RECORD = re.compile(
    r"^(?:(?:Product|Component):\s*)?ARM Compiler (5\.\d{2})"
    r"(?: update (\d{1,5}))?(?: \(build (\d{1,6})\))?$"
)
_UV4_STANDARD_PATHS = (
    Path("C:/Keil_v5/UV4/UV4.exe"),
    Path("C:/Keil/UV4/UV4.exe"),
)
_ARMCC_STANDARD_PATHS = (
    Path("C:/Keil_v5/ARM/ARMCC/bin/armcc.exe"),
    Path("C:/Keil/ARM/ARMCC/bin/armcc.exe"),
)
_KEIL_ROUTES = ("keil-migration", "external-firmware")
_KEIL_NATIVE_BUILD_REASON = (
    "No native Keil/ARMCC build backend is implemented; discovered UV4 or "
    "ARMCC installations do not unlock one."
)

_VSCODE_SCOPE = "local-default-profile"
_VSCODE_PROBE = "vscode-cli-list-extensions"
_VSCODE_PATH_REMEDIATION = (
    "Pass an absolute, existing, non-redirected VS Code Code.exe or its "
    "installed bin/code.cmd with --vscode-path (MCP vscodePath), or use "
    "--skip-vscode-extensions (MCP probeVscodeExtensions=false)."
)
_VSCODE_SELECTION_REASONS = {
    "missing": "no VS Code installation was selected",
    "invalid": "the selected VS Code path is not a safe supported executable",
    "ambiguous": "more than one VS Code installation matched the bounded search",
    "unsupported-layout": (
        "the selected VS Code installation does not expose a supported CLI layout"
    ),
    "unsupported-platform": (
        "VS Code extension probing needs an explicit CLI entry on this platform"
    ),
}
_VSCODE_SELECTION_CODES = {
    "missing": "VSCODE_CLI_NOT_FOUND",
    "invalid": "VSCODE_PATH_INVALID",
    "ambiguous": "VSCODE_INSTALL_AMBIGUOUS",
    "unsupported-layout": "VSCODE_LAYOUT_UNSUPPORTED",
    "unsupported-platform": "VSCODE_PROBE_UNSUPPORTED",
}
_VSCODE_MISSING_REMEDIATION = (
    "Install VS Code, or pass its absolute Code.exe or installed bin/code.cmd "
    "with --vscode-path (MCP vscodePath); doctor never installs software."
)
_VSCODE_AMBIGUOUS_REMEDIATION = (
    "Pass exactly one Code.exe or installed bin/code.cmd with --vscode-path "
    "(MCP vscodePath)."
)
_VSCODE_LAYOUT_REMEDIATION = (
    "Pass a supported VS Code Code.exe or its installed bin/code.cmd; doctor "
    "parses that launcher and never executes batch content."
)
_VSCODE_PLATFORM_REMEDIATION = (
    "Pass an absolute VS Code CLI entry with --vscode-path (MCP vscodePath) on "
    "this platform, or use --skip-vscode-extensions."
)
_EXTENSION_MISSING_REMEDIATION = (
    "Install {extension} in the selected local VS Code default profile; "
    "doctor never installs or activates extensions."
)
_EXTENSION_UNKNOWN_REMEDIATION = (
    "Retry after confirming the selected VS Code CLI, or use "
    "--skip-vscode-extensions (MCP probeVscodeExtensions=false); partial or "
    "invalid output is not treated as extension evidence."
)

_UV4_MISSING_REMEDIATION = (
    "Install Keil uVision or pass its absolute UV4.exe with --uv4-path "
    "(MCP uv4Path); doctor never installs software or changes PATH."
)
_UV4_PATH_REMEDIATION = (
    "Pass an absolute, existing, non-redirected UV4.exe with --uv4-path "
    "(MCP uv4Path)."
)
_UV4_AMBIGUOUS_REMEDIATION = "Pass exactly one UV4.exe with --uv4-path (MCP uv4Path)."
_UV4_VERSION_REMEDIATION = (
    "Pass --uv4-path (MCP uv4Path) to the intended UV4.exe; static file-version "
    "metadata is unavailable."
)
_UV4_PLATFORM_REMEDIATION = (
    "Keil UV4 static version evidence is only available on Windows."
)

_ARMCC_MISSING_REMEDIATION = (
    "Install ARM Compiler 5 under the selected Keil installation or on PATH, "
    "or pass its absolute armcc.exe with --armcc-path (MCP armccPath); doctor "
    "never installs software or changes PATH."
)
_ARMCC_PATH_REMEDIATION = (
    "Pass an absolute, existing, non-redirected armcc.exe with --armcc-path "
    "(MCP armccPath)."
)
_ARMCC_AMBIGUOUS_REMEDIATION = (
    "Pass exactly one armcc.exe with --armcc-path (MCP armccPath)."
)
_ARMCC_PROBE_REMEDIATION = (
    "Confirm the selected armcc.exe runs locally; doctor only executes the "
    "fixed --vsn query and never builds or activates a license."
)
_ARMCC_PLATFORM_REMEDIATION = "ARMCC --vsn evidence is only available on Windows."

_RELEVANT_EXTENSIONS = frozenset(extension.casefold() for extension in RECOMMENDED_EXTENSIONS)


@dataclass(frozen=True, slots=True)
class _VscodeSelection:
    status: str
    source: str | None = None
    executable: Path | None = None
    script: Path | None = None
    locator: Path | None = None
    code: str | None = None
    remediation: str | None = None


@dataclass(frozen=True, slots=True)
class _ToolSelection:
    status: str
    source: str | None = None
    path: Path | None = None
    installation: Path | None = None
    code: str | None = None
    remediation: str | None = None


@dataclass(frozen=True, slots=True)
class _Listing:
    status: str
    code: str | None
    remediation: str | None
    reason: str | None
    return_code: int | None = None
    records: dict[str, str] | None = None

    @property
    def complete(self) -> bool:
        return self.records is not None


def _display(path: Path | None) -> str | None:
    return path.as_posix() if path is not None else None


def _vscode_selection(
    status: str,
    *,
    source: str | None = None,
    executable: Path | None = None,
    script: Path | None = None,
    locator: Path | None = None,
    remediation: str | None = None,
) -> _VscodeSelection:
    # A successful selection has no diagnostic code; only failure statuses
    # carry the fixed failure codes.
    code = None if status == "ok" else _VSCODE_SELECTION_CODES[status]
    return _VscodeSelection(
        status,
        source,
        executable,
        script,
        locator,
        code,
        remediation,
    )


def _path_locator() -> Path | None:
    try:
        found = shutil.which("code")
    except OSError:
        return None
    return Path(found) if found else None


def _vscode_standard_candidates() -> tuple[Path, ...]:
    candidates: list[Path] = []
    layouts = (
        ("LOCALAPPDATA", Path("Programs") / "Microsoft VS Code"),
        ("PROGRAMFILES", Path("Microsoft VS Code")),
        ("PROGRAMFILES(X86)", Path("Microsoft VS Code")),
    )
    for variable, relative in layouts:
        base = os.environ.get(variable)
        if not base:
            continue
        root = Path(base) / relative
        candidates.extend((root / "Code.exe", root / "bin" / "code.cmd"))
    return tuple(candidates)


def _launcher_script(launcher: Path) -> tuple[Path | None, bool]:
    """Return ``(script, recognized)`` for an installed ``bin/code.cmd``.

    Only the known launcher literal is inspected.  The batch file is never
    executed and its other content is never interpreted.
    """
    canonical = _canonical_regular_file(launcher)
    if canonical is None:
        return None, False
    try:
        with canonical.open("rb") as stream:
            payload = stream.read(_LAUNCHER_CAPTURE_LIMIT + 1)
    except OSError:
        return None, False
    if len(payload) > _LAUNCHER_CAPTURE_LIMIT:
        return None, False
    try:
        text = payload.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        return None, False
    matches = [
        match
        for line in text.splitlines()
        if (match := _LAUNCHER_LINE.match(line.strip())) is not None
    ]
    if len(matches) != 1:
        return None, False
    hash_component = matches[0].group(1)
    root = canonical.parent.parent
    if hash_component is None:
        script = root / "resources" / "app" / "out" / "cli.js"
    else:
        script = root / hash_component / "resources" / "app" / "out" / "cli.js"
    canonical_script = _canonical_regular_file(script)
    if canonical_script is None:
        return None, True
    return canonical_script, True


def _resolve_vscode_entry(
    entry: Path, source: str, *, explicit: bool
) -> _VscodeSelection:
    if explicit and not entry.is_absolute():
        return _vscode_selection("invalid", source=source, remediation=_VSCODE_PATH_REMEDIATION)
    canonical = _canonical_regular_file(entry)
    if canonical is None:
        return _vscode_selection("invalid", source=source, remediation=_VSCODE_PATH_REMEDIATION)
    name = canonical.name.casefold()
    if name not in {"code.exe", "code.cmd"}:
        return _vscode_selection("invalid", source=source, remediation=_VSCODE_PATH_REMEDIATION)
    if name == "code.exe":
        root = canonical.parent
        launcher = root / "bin" / "code.cmd"
        if _lexists(launcher):
            # The installed launcher is authoritative for the current layout;
            # a stale root/resources/app/out/cli.js must never win over it.
            canonical_launcher = _canonical_regular_file(launcher)
            if canonical_launcher is None:
                return _vscode_selection(
                    "invalid", source=source, remediation=_VSCODE_PATH_REMEDIATION
                )
            script, recognized = _launcher_script(canonical_launcher)
            if not recognized or script is None:
                return _vscode_selection(
                    "unsupported-layout",
                    source=source,
                    remediation=_VSCODE_LAYOUT_REMEDIATION,
                )
            return _vscode_selection(
                "ok",
                source=source,
                executable=canonical,
                script=script,
                locator=canonical_launcher,
            )
        # Fixed layout is accepted only when no installed launcher exists.
        script = _canonical_regular_file(root / "resources" / "app" / "out" / "cli.js")
        if script is None:
            return _vscode_selection(
                "unsupported-layout", source=source, remediation=_VSCODE_LAYOUT_REMEDIATION
            )
        return _vscode_selection(
            "ok", source=source, executable=canonical, script=script
        )
    root = canonical.parent.parent
    executable = _canonical_regular_file(root / "Code.exe")
    script, recognized = _launcher_script(canonical)
    if executable is None or not recognized or script is None:
        return _vscode_selection(
            "unsupported-layout", source=source, remediation=_VSCODE_LAYOUT_REMEDIATION
        )
    return _vscode_selection(
        "ok", source=source, executable=executable, script=script, locator=canonical
    )


def _resolve_direct_cli(entry: Path) -> _VscodeSelection:
    if not entry.is_absolute():
        return _vscode_selection("invalid", source="explicit", remediation=_VSCODE_PATH_REMEDIATION)
    canonical = _canonical_regular_file(entry)
    if canonical is None or not os.access(canonical, os.X_OK):
        return _vscode_selection("invalid", source="explicit", remediation=_VSCODE_PATH_REMEDIATION)
    return _vscode_selection("ok", source="explicit", executable=canonical)


def _resolve_vscode_tier(entries: tuple[Path, ...], source: str) -> _VscodeSelection:
    selections: list[_VscodeSelection] = []
    for entry in entries:
        selection = _resolve_vscode_entry(entry, source, explicit=False)
        if selection.status != "ok":
            return selection
        selections.append(selection)
    unique: dict[tuple[str, str], _VscodeSelection] = {}
    for selection in selections:
        key = (
            os.path.normcase(str(selection.executable)),
            os.path.normcase(str(selection.script)),
        )
        unique.setdefault(key, selection)
    if not unique:
        return _vscode_selection(
            "missing", source=source, remediation=_VSCODE_MISSING_REMEDIATION
        )
    if len(unique) > 1:
        return _vscode_selection(
            "ambiguous", source=source, remediation=_VSCODE_AMBIGUOUS_REMEDIATION
        )
    return next(iter(unique.values()))


def _resolve_vscode(
    support_profile: ToolSupportProfile | None, explicit: Path | None
) -> _VscodeSelection:
    if not _IS_WINDOWS:
        if explicit is not None:
            return _resolve_direct_cli(explicit)
        return _vscode_selection(
            "unsupported-platform", remediation=_VSCODE_PLATFORM_REMEDIATION
        )
    if explicit is not None:
        return _resolve_vscode_entry(explicit, "explicit", explicit=True)
    fact = getattr(support_profile, "vscode", None)
    fact_path = getattr(fact, "path", None)
    if isinstance(fact_path, Path):
        return _resolve_vscode_entry(fact_path, "support-profile", explicit=False)
    locator = _path_locator()
    if locator is not None:
        return _resolve_vscode_entry(locator, "path", explicit=False)
    existing = tuple(
        candidate for candidate in _vscode_standard_candidates() if _lexists(candidate)
    )
    if not existing:
        return _vscode_selection("missing", remediation=_VSCODE_MISSING_REMEDIATION)
    return _resolve_vscode_tier(existing, "standard")


def _vscode_child_env() -> dict[str, str]:
    environment = dict(os.environ)
    environment["ELECTRON_RUN_AS_NODE"] = "1"
    environment["VSCODE_DEV"] = ""
    return environment


def _run_extension_listing(selection: _VscodeSelection) -> _Listing:
    executable = selection.executable
    if executable is None:
        return _Listing(
            "start-error",
            "VSCODE_EXTENSIONS_START_FAILED",
            _EXTENSION_UNKNOWN_REMEDIATION,
            "no VS Code executable was selected",
        )
    if selection.script is None:
        argv = (str(executable), "--list-extensions", "--show-versions")
        environment = None
    else:
        argv = (
            str(executable),
            str(selection.script),
            "--list-extensions",
            "--show-versions",
        )
        environment = _vscode_child_env()
    observation = _run_bounded(
        argv,
        timeout_seconds=EXTENSION_LIST_TIMEOUT_SECONDS,
        capture_limit=EXTENSION_LIST_CAPTURE_LIMIT,
        env=environment,
    )
    return _classify_listing(observation)


def _classify_listing(observation: ProcessObservation) -> _Listing:
    if observation.timed_out:
        return _Listing(
            "timeout",
            "VSCODE_EXTENSIONS_TIMEOUT",
            _EXTENSION_UNKNOWN_REMEDIATION,
            "the selected VS Code CLI did not finish within 10 seconds",
        )
    if observation.returncode is None:
        return _Listing(
            "start-error",
            "VSCODE_EXTENSIONS_START_FAILED",
            _EXTENSION_UNKNOWN_REMEDIATION,
            "the selected VS Code CLI could not be started",
        )
    if observation.returncode != 0:
        return _Listing(
            "nonzero",
            "VSCODE_EXTENSIONS_NONZERO",
            _EXTENSION_UNKNOWN_REMEDIATION,
            "the selected VS Code CLI returned a nonzero status",
            observation.returncode,
        )
    if observation.truncated:
        return _Listing(
            "truncated",
            "VSCODE_EXTENSIONS_TRUNCATED",
            _EXTENSION_UNKNOWN_REMEDIATION,
            "the extension listing exceeded the 64 KiB capture limit",
            observation.returncode,
        )
    if observation.incomplete:
        return _Listing(
            "incomplete",
            "VSCODE_EXTENSIONS_INCOMPLETE",
            _EXTENSION_UNKNOWN_REMEDIATION,
            "the extension listing reader did not complete",
            observation.returncode,
        )
    try:
        text = observation.stdout.decode("utf-8", errors="strict")
        diagnostic_text = observation.stderr.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        return _Listing(
            "invalid-output",
            "VSCODE_EXTENSIONS_INVALID_OUTPUT",
            _EXTENSION_UNKNOWN_REMEDIATION,
            "the extension listing was not valid UTF-8",
            observation.returncode,
        )
    if diagnostic_text.strip():
        return _Listing(
            "diagnostic-output",
            "VSCODE_EXTENSIONS_STDERR",
            _EXTENSION_UNKNOWN_REMEDIATION,
            "the selected VS Code CLI wrote unexpected diagnostic output",
            observation.returncode,
        )
    records, malformed, conflict = _parse_listing(text)
    if malformed:
        return _Listing(
            "malformed-output",
            "VSCODE_EXTENSIONS_MALFORMED",
            _EXTENSION_UNKNOWN_REMEDIATION,
            "the extension listing contained a malformed extension record",
            observation.returncode,
        )
    if conflict:
        return _Listing(
            "conflicting-versions",
            "VSCODE_EXTENSIONS_CONFLICT",
            _EXTENSION_UNKNOWN_REMEDIATION,
            "the extension listing reported conflicting versions for a recommended extension",
            observation.returncode,
        )
    return _Listing("observed", None, None, None, observation.returncode, records)


def _parse_listing(text: str) -> tuple[dict[str, str], bool, bool]:
    records: dict[str, str] = {}
    malformed = False
    conflict = False
    for raw_line in text.splitlines():
        line = raw_line.rstrip("\r")
        if not line:
            continue
        if line != line.strip():
            malformed = True
            continue
        match = _EXTENSION_LINE.match(line)
        if match is None:
            malformed = True
            continue
        identifier, version = match.group(1), match.group(2)
        parts = identifier.split(".")
        if len(parts) < 2 or any(not part for part in parts):
            malformed = True
            continue
        key = identifier.casefold()
        previous = records.get(key)
        if previous is None:
            records[key] = version
        elif previous != version and key in _RELEVANT_EXTENSIONS:
            conflict = True
    return records, malformed, conflict


def _extension_entry(
    extension: str,
    *,
    installed: bool | None,
    version: str | None,
    status: str,
    code: str | None,
    remediation: str | None,
) -> dict[str, object]:
    entry: dict[str, object] = {
        "installed": installed,
        "version": version,
        "status": status,
        "code": code,
        "remediation": remediation,
    }
    if extension.casefold() == "marus25.cortex-debug":
        entry["profileVersion"] = CORTEX_DEBUG_PROFILE_VERSION
        entry["profileMatchBasis"] = "observed-extension-version-vs-declared-handoff-profile"
        if installed and version is not None:
            entry["profileMatch"] = (
                "match" if version == CORTEX_DEBUG_PROFILE_VERSION else "mismatch"
            )
        else:
            entry["profileMatch"] = "unverified"
    return entry


def _unknown_extensions(
    status: str, code: str | None, remediation: str | None
) -> dict[str, dict[str, object]]:
    return {
        extension: _extension_entry(
            extension,
            installed=None,
            version=None,
            status=status,
            code=code,
            remediation=remediation,
        )
        for extension in RECOMMENDED_EXTENSIONS
    }


def _complete_extensions(records: dict[str, str]) -> dict[str, dict[str, object]]:
    entries: dict[str, dict[str, object]] = {}
    for extension in RECOMMENDED_EXTENSIONS:
        version = records.get(extension.casefold())
        if version is None:
            entries[extension] = _extension_entry(
                extension,
                installed=False,
                version=None,
                status="absent",
                code="VSCODE_EXTENSION_MISSING",
                remediation=_EXTENSION_MISSING_REMEDIATION.format(extension=extension),
            )
        else:
            entries[extension] = _extension_entry(
                extension,
                installed=True,
                version=version,
                status="installed",
                code=None,
                remediation=None,
            )
    return entries


def _observation(
    status: str,
    *,
    complete: bool,
    selection: _VscodeSelection | None = None,
    return_code: int | None = None,
    code: str | None = None,
    remediation: str | None = None,
    reason: str | None = None,
) -> dict[str, object]:
    return {
        "scope": _VSCODE_SCOPE,
        "probe": _VSCODE_PROBE,
        "status": status,
        "completeInventory": complete,
        "source": selection.source if selection is not None else None,
        "executable": _display(selection.executable) if selection is not None else None,
        "cliScript": _display(selection.script) if selection is not None else None,
        "locator": _display(selection.locator) if selection is not None else None,
        "returnCode": return_code,
        "code": code,
        "remediation": remediation,
        "reason": reason,
    }


def _observe_vscode_extensions(
    support_profile: ToolSupportProfile | None,
    enabled: bool,
    explicit: Path | None,
) -> tuple[dict[str, dict[str, object]], dict[str, object]]:
    if not enabled:
        return (
            _unknown_extensions("skipped", None, None),
            _observation(
                "skipped",
                complete=False,
                reason="extension probing was disabled by the caller",
            ),
        )
    selection = _resolve_vscode(support_profile, explicit)
    if selection.status != "ok":
        return (
            _unknown_extensions(selection.status, selection.code, selection.remediation),
            _observation(
                selection.status,
                complete=False,
                selection=selection,
                code=selection.code,
                remediation=selection.remediation,
                reason=_VSCODE_SELECTION_REASONS[selection.status],
            ),
        )
    listing = _run_extension_listing(selection)
    if listing.complete:
        return (
            _complete_extensions(listing.records or {}),
            _observation(
                "observed",
                complete=True,
                selection=selection,
                return_code=listing.return_code,
            ),
        )
    return (
        _unknown_extensions(listing.status, listing.code, listing.remediation),
        _observation(
            listing.status,
            complete=False,
            selection=selection,
            return_code=listing.return_code,
            code=listing.code,
            remediation=listing.remediation,
            reason=listing.reason,
        ),
    )


def _tool_selection(
    status: str,
    *,
    source: str | None,
    path: Path | None,
    installation: Path | None,
    code: str | None,
    remediation: str | None,
) -> _ToolSelection:
    return _ToolSelection(status, source, path, installation, code, remediation)


def _explicit_tool(path: Path, leaf: str) -> _ToolSelection:
    if not path.is_absolute():
        return _tool_selection(
            "invalid",
            source="explicit",
            path=None,
            installation=None,
            code=None,
            remediation=None,
        )
    canonical = _canonical_regular_file(path)
    if canonical is None or canonical.name.casefold() != leaf:
        return _tool_selection(
            "invalid",
            source="explicit",
            path=None,
            installation=None,
            code=None,
            remediation=None,
        )
    return _tool_selection(
        "ok",
        source="explicit",
        path=canonical,
        installation=canonical.parent,
        code=None,
        remediation=None,
    )


def _resolve_named_tier(
    entries: tuple[Path, ...], leaf: str, source: str
) -> _ToolSelection:
    selected: dict[str, Path] = {}
    for entry in entries:
        canonical = _canonical_regular_file(entry)
        if canonical is None or canonical.name.casefold() != leaf:
            return _tool_selection(
                "invalid",
                source=source,
                path=None,
                installation=None,
                code=None,
                remediation=None,
            )
        selected.setdefault(os.path.normcase(str(canonical)), canonical)
    if not selected:
        return _tool_selection(
            "missing",
            source=source,
            path=None,
            installation=None,
            code=None,
            remediation=None,
        )
    if len(selected) > 1:
        return _tool_selection(
            "ambiguous",
            source=source,
            path=None,
            installation=None,
            code=None,
            remediation=None,
        )
    path = next(iter(selected.values()))
    return _tool_selection(
        "ok",
        source=source,
        path=path,
        installation=path.parent.parent,
        code=None,
        remediation=None,
    )


def _path_binary(name: str) -> Path | None:
    try:
        found = shutil.which(name)
    except OSError:
        return None
    return Path(found) if found else None


def _observe_uv4(explicit: Path | None) -> tuple[dict[str, object], dict[str, object] | None]:
    if not _IS_WINDOWS:
        record = _tool_record(
            available=None,
            source=None,
            path=None,
            status="unsupported-platform",
            version=None,
            return_code=None,
            code="UV4_PLATFORM_UNSUPPORTED",
            remediation=_UV4_PLATFORM_REMEDIATION,
        )
        return record, _diagnostic(
            "uv4", "UV4_PLATFORM_UNSUPPORTED", "unsupported-platform",
            _UV4_PLATFORM_REMEDIATION, "uv4Path", "--uv4-path",
        )
    if explicit is not None:
        selection = _explicit_tool(explicit, "uv4.exe")
        if selection.status == "invalid":
            selection = _tool_selection(
                "invalid", source="explicit", path=None, installation=None,
                code="UV4_PATH_INVALID", remediation=_UV4_PATH_REMEDIATION,
            )
    else:
        locator = _path_binary("UV4")
        if locator is not None:
            selection = _resolve_named_tier((locator,), "uv4.exe", "path")
        else:
            existing = tuple(
                candidate for candidate in _UV4_STANDARD_PATHS if _lexists(candidate)
            )
            selection = _resolve_named_tier(existing, "uv4.exe", "standard")
        if selection.status == "missing":
            selection = _tool_selection(
                "missing", source=None, path=None, installation=None,
                code="UV4_NOT_FOUND", remediation=_UV4_MISSING_REMEDIATION,
            )
        elif selection.status == "invalid":
            selection = _tool_selection(
                "invalid", source=selection.source, path=None, installation=None,
                code="UV4_PATH_INVALID", remediation=_UV4_PATH_REMEDIATION,
            )
        elif selection.status == "ambiguous":
            selection = _tool_selection(
                "ambiguous", source=selection.source, path=None, installation=None,
                code="UV4_AMBIGUOUS", remediation=_UV4_AMBIGUOUS_REMEDIATION,
            )
    record = _static_tool_record(selection, "UV4")
    diagnostic = None
    if record["code"] is not None:
        diagnostic = _diagnostic(
            "uv4",
            str(record["code"]),
            str(record["status"]),
            str(record["remediation"] or ""),
            "uv4Path",
            "--uv4-path",
        )
    return record, diagnostic


def _static_tool_record(selection: _ToolSelection, component: str) -> dict[str, object]:
    if selection.status != "ok":
        return _tool_record(
            available=False if selection.status == "missing" else None,
            source=selection.source,
            path=None,
            status=selection.status,
            version=None,
            return_code=None,
            code=selection.code,
            remediation=selection.remediation,
        )
    version = _windows_file_version(selection.path) if selection.path is not None else None
    status = "ok" if version else "version-unknown"
    code = None if version else f"{component}_VERSION_UNKNOWN"
    remediation = None if version else (
        _UV4_VERSION_REMEDIATION if component == "UV4" else _ARMCC_PROBE_REMEDIATION
    )
    return _tool_record(
        available=True,
        source=selection.source,
        path=selection.path,
        status=status,
        version=version,
        return_code=None,
        code=code,
        remediation=remediation,
    )


def _tool_diagnostic(
    component: str, selection: _ToolSelection, field: str, cli_option: str
) -> dict[str, object] | None:
    if selection.code is None:
        return None
    return _diagnostic(
        component, selection.code, selection.status, selection.remediation or "",
        field, cli_option,
    )


def _tool_record(
    *,
    available: bool | None,
    source: str | None,
    path: Path | None,
    status: str,
    version: str | None,
    return_code: int | None,
    code: str | None,
    remediation: str | None,
) -> dict[str, object]:
    return {
        "available": available,
        "path": _display(path),
        "source": source,
        "status": status,
        "version": version,
        "returnCode": return_code,
        "code": code,
        "remediation": remediation,
    }


def _observe_armcc(
    explicit: Path | None, uv4: dict[str, object]
) -> tuple[dict[str, object], dict[str, object] | None]:
    if not _IS_WINDOWS:
        record = _tool_record(
            available=None,
            source=None,
            path=None,
            status="unsupported-platform",
            version=None,
            return_code=None,
            code="ARMCC_PLATFORM_UNSUPPORTED",
            remediation=_ARMCC_PLATFORM_REMEDIATION,
        )
        return record, _diagnostic(
            "armcc", "ARMCC_PLATFORM_UNSUPPORTED", "unsupported-platform",
            _ARMCC_PLATFORM_REMEDIATION, "armccPath", "--armcc-path",
        )
    if explicit is not None:
        selection = _explicit_tool(explicit, "armcc.exe")
        if selection.status == "invalid":
            selection = _tool_selection(
                "invalid", source="explicit", path=None, installation=None,
                code="ARMCC_PATH_INVALID", remediation=_ARMCC_PATH_REMEDIATION,
            )
    else:
        locator = _path_binary("armcc")
        if locator is not None:
            selection = _resolve_named_tier((locator,), "armcc.exe", "path")
        else:
            selection = _uv4_armcc_tier(uv4)
            if selection.status == "missing":
                existing = tuple(
                    candidate
                    for candidate in _ARMCC_STANDARD_PATHS
                    if _lexists(candidate)
                )
                selection = _resolve_named_tier(existing, "armcc.exe", "standard")
        if selection.status == "missing":
            selection = _tool_selection(
                "missing", source=None, path=None, installation=None,
                code="ARMCC_NOT_FOUND", remediation=_ARMCC_MISSING_REMEDIATION,
            )
        elif selection.status == "invalid":
            selection = _tool_selection(
                "invalid", source=selection.source, path=None, installation=None,
                code="ARMCC_PATH_INVALID", remediation=_ARMCC_PATH_REMEDIATION,
            )
        elif selection.status == "ambiguous":
            selection = _tool_selection(
                "ambiguous", source=selection.source, path=None, installation=None,
                code="ARMCC_AMBIGUOUS", remediation=_ARMCC_AMBIGUOUS_REMEDIATION,
            )
    if selection.status != "ok" or selection.path is None:
        record = _tool_record(
            available=False if selection.status == "missing" else None,
            source=selection.source,
            path=None,
            status=selection.status,
            version=None,
            return_code=None,
            code=selection.code,
            remediation=selection.remediation,
        )
        return record, _tool_diagnostic(
            "armcc", selection, "armccPath", "--armcc-path"
        )
    return _probe_armcc(selection)


def _uv4_armcc_tier(uv4: dict[str, object]) -> _ToolSelection:
    if uv4.get("status") not in {"ok", "version-unknown"}:
        return _tool_selection(
            "missing", source="uv4-installation", path=None, installation=None,
            code=None, remediation=None,
        )
    raw_path = uv4.get("path")
    if not isinstance(raw_path, str):
        return _tool_selection(
            "missing", source="uv4-installation", path=None, installation=None,
            code=None, remediation=None,
        )
    uv4_path = Path(raw_path)
    root = uv4_path.parent.parent
    if _canonical_directory(root) is None:
        return _tool_selection(
            "invalid", source="uv4-installation", path=None, installation=None,
            code="ARMCC_PATH_INVALID", remediation=_ARMCC_PATH_REMEDIATION,
        )
    candidate = root / "ARM" / "ARMCC" / "bin" / "armcc.exe"
    if not _lexists(candidate):
        return _tool_selection(
            "missing", source="uv4-installation", path=None, installation=None,
            code=None, remediation=None,
        )
    return _resolve_named_tier((candidate,), "armcc.exe", "uv4-installation")


def _probe_armcc(
    selection: _ToolSelection,
) -> tuple[dict[str, object], dict[str, object] | None]:
    assert selection.path is not None
    observation = _run_bounded(
        (str(selection.path), "--vsn"),
        timeout_seconds=ARMCC_TIMEOUT_SECONDS,
        capture_limit=ARMCC_CAPTURE_LIMIT,
    )
    status, version, code, remediation, reason = _classify_armcc(observation)
    record = _tool_record(
        available=True,
        source=selection.source,
        path=selection.path,
        status=status,
        version=version,
        return_code=observation.returncode,
        code=code,
        remediation=remediation,
    )
    if code is None:
        return record, None
    record["reason"] = reason
    return record, _diagnostic(
        "armcc", code, status, remediation or "", "armccPath", "--armcc-path"
    )


def _classify_armcc(
    observation: ProcessObservation,
) -> tuple[str, str | None, str | None, str | None, str | None]:
    if observation.timed_out:
        return (
            "timeout", None, "ARMCC_PROBE_TIMEOUT", _ARMCC_PROBE_REMEDIATION,
            "the selected armcc did not answer --vsn within 5 seconds",
        )
    if observation.returncode is None:
        return (
            "start-error", None, "ARMCC_PROBE_ERROR", _ARMCC_PROBE_REMEDIATION,
            "the selected armcc could not be started",
        )
    if observation.returncode != 0:
        return (
            "nonzero", None, "ARMCC_PROBE_NONZERO", _ARMCC_PROBE_REMEDIATION,
            "the selected armcc returned a nonzero status for --vsn",
        )
    if observation.truncated:
        return (
            "truncated", None, "ARMCC_PROBE_TRUNCATED", _ARMCC_PROBE_REMEDIATION,
            "the armcc --vsn output exceeded the 8 KiB capture limit",
        )
    if observation.incomplete:
        return (
            "incomplete", None, "ARMCC_PROBE_INCOMPLETE", _ARMCC_PROBE_REMEDIATION,
            "the armcc --vsn reader did not complete",
        )
    try:
        stdout_text = observation.stdout.decode("utf-8", errors="strict")
        stderr_text = observation.stderr.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        return (
            "invalid-output", None, "ARMCC_OUTPUT_INVALID", _ARMCC_PROBE_REMEDIATION,
            "the armcc --vsn output was not valid UTF-8",
        )
    version, conflict = _armcc_versions(stdout_text, stderr_text)
    if conflict:
        return (
            "version-conflict", None, "ARMCC_VERSION_CONFLICT",
            _ARMCC_PROBE_REMEDIATION,
            "the armcc --vsn output reported conflicting compiler versions",
        )
    if version is None:
        return (
            "version-unknown", None, "ARMCC_VERSION_UNKNOWN", _ARMCC_PROBE_REMEDIATION,
            "the armcc --vsn output contained no recognized ARM Compiler version",
        )
    return "ok", version, None, None, None


def _armcc_versions(stdout_text: str, stderr_text: str) -> tuple[str | None, bool]:
    """Return ``(safe_version, conflict)`` from recognized ARM Compiler records.

    Only exact Product/Component/bare ``ARM Compiler 5.xx`` records are
    accepted.  Unrelated text, serial numbers, license messages, and error
    output never become a version.
    """
    records: list[tuple[str, str | None, str | None]] = []
    for text in (stdout_text, stderr_text):
        for raw_line in text.splitlines():
            match = _ARMCC_RECORD.match(raw_line.strip())
            if match is not None:
                records.append((match.group(1), match.group(2), match.group(3)))
    if not records:
        return None, False
    bases = {base for base, _update, _build in records}
    if len(bases) > 1:
        return None, True
    updates = {update for _base, update, _build in records if update is not None}
    if len(updates) > 1:
        return None, True
    builds = {build for _base, _update, build in records if build is not None}
    if len(builds) > 1:
        return None, True
    update = next(iter(updates)) if updates else None
    build = next(iter(builds)) if builds else None
    version = next(iter(bases))
    if update is not None:
        version += f" update {update}"
    if build is not None:
        version += f" (build {build})"
    return version[:_ARMCC_VERSION_LIMIT], False


def _diagnostic(
    component: str,
    code: str | None,
    status: str,
    remediation: str,
    field: str | None,
    cli_option: str | None,
    *,
    extension_id: str | None = None,
) -> dict[str, object]:
    return {
        "component": component,
        "code": code,
        "status": status,
        "remediation": remediation,
        "field": field,
        "cliOption": cli_option,
        "extensionId": extension_id,
    }


def collect_doctor_readiness(
    *,
    support_profile: ToolSupportProfile | None = None,
    probe_vscode_extensions: bool = True,
    vscode_path: Path | None = None,
    uv4_path: Path | None = None,
    armcc_path: Path | None = None,
) -> dict[str, object]:
    """Collect bounded readiness evidence without changing any tool state."""
    extensions, observation = _observe_vscode_extensions(
        support_profile, probe_vscode_extensions, vscode_path
    )
    uv4, uv4_diagnostic = _observe_uv4(uv4_path)
    armcc, armcc_diagnostic = _observe_armcc(armcc_path, uv4)

    diagnostics: list[dict[str, object]] = []
    if observation["code"] is not None:
        diagnostics.append(
            _diagnostic(
                "vsCode",
                observation["code"] if isinstance(observation["code"], str) else None,
                str(observation["status"]),
                str(observation["remediation"] or ""),
                "vscodePath",
                "--vscode-path",
            )
        )
    for extension in RECOMMENDED_EXTENSIONS:
        entry = extensions[extension]
        if entry["status"] == "absent":
            diagnostics.append(
                _diagnostic(
                    "vsCodeExtension",
                    str(entry["code"]),
                    "absent",
                    str(entry["remediation"]),
                    None,
                    None,
                    extension_id=extension,
                )
            )
    if uv4_diagnostic is not None:
        diagnostics.append(uv4_diagnostic)
    if armcc_diagnostic is not None:
        diagnostics.append(armcc_diagnostic)

    return {
        "vscodeExtensions": extensions,
        "vscodeExtensionObservation": observation,
        "keilTools": {
            "toolkitNativeBuildSupported": False,
            "nativeBuildReason": _KEIL_NATIVE_BUILD_REASON,
            "routes": list(_KEIL_ROUTES),
            "uv4": uv4,
            "armcc": armcc,
        },
        "readiness": {
            "reportCollected": True,
            "vscodeExtensionInventory": observation["status"],
            "vscodeExtensionsComplete": observation["completeInventory"],
            "uv4": uv4["status"],
            "armcc": armcc["status"],
            "toolkitNativeBuildSupported": False,
        },
        "diagnostics": diagnostics,
    }
