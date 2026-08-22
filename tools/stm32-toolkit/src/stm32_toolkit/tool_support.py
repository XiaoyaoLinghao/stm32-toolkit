"""Read-only discovery of the supported STM32 creation environment.

This module deliberately has no creation or mutation capabilities.  A support
profile is a closed snapshot of local facts; callers can bind a creation plan
to its digest without exposing executable commands to MCP clients.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
import ctypes
import ctypes.wintypes
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

ToolSource = Literal["explicit", "cubeclt-metadata", "standard", "path"]

_CUBECLT_ROOTS = (
    Path(r"C:\ST\STM32CubeCLT_1.22.0"),
    Path(r"C:\ST\STM32CubeCLT_1.22.0\bin"),
)
_CUBEMX_PATHS = (
    Path(r"C:\Program Files\STMicroelectronics\STM32CubeMX\STM32CubeMX.exe"),
    Path(r"C:\Program Files\STMicroelectronics\Software\STM32CubeMX\STM32CubeMX.exe"),
    Path(r"C:\ST\STM32CubeMX\STM32CubeMX.exe"),
)
_VS_CODE_PATHS = (
    Path(r"C:\Program Files\Microsoft VS Code\bin\code.exe"),
    Path(r"C:\Program Files\Microsoft VS Code\Code.exe"),
    Path(r"C:\Program Files (x86)\Microsoft VS Code\bin\code.exe"),
)
_EXTENSIONS = (
    "ms-vscode.cpptools",
    "ms-vscode.cmake-tools",
    "marus25.cortex-debug",
)
_MAX_METADATA_BYTES = 64 * 1024
_MAX_VERSION_BYTES = 8 * 1024
_REPARSE = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
_REAL_POPEN = subprocess.Popen


class SupportProfileError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ProcessObservation:
    returncode: int | None
    stdout: bytes
    stderr: bytes
    timed_out: bool = False
    truncated: bool = False


def _run_bounded(argv: tuple[str, ...], timeout_seconds: float = 5.0, capture_limit: int = _MAX_VERSION_BYTES) -> ProcessObservation:
    process = None
    try:
        process = _REAL_POPEN(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False)
        try:
            stdout, stderr = process.communicate(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            try: process.terminate()
            except OSError: pass
            try: process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                try: process.kill()
                except OSError: pass
                try: process.wait(timeout=1)
                except (OSError, subprocess.TimeoutExpired): pass
            return ProcessObservation(None, b"", b"", timed_out=True)
        combined = (stdout or b"") + (stderr or b"")
        return ProcessObservation(process.returncode, (stdout or b"")[:capture_limit], (stderr or b"")[:capture_limit], truncated=len(combined) > capture_limit)
    except OSError:
        return ProcessObservation(None, b"", b"")


@dataclass(frozen=True, slots=True)
class SupportProfileRequest:
    profile_path: Path | None = None
    data_root: Path | None = None


@dataclass(frozen=True, slots=True)
class ToolSupportIssue:
    code: str
    component: str
    remediation: str

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "component": self.component, "remediation": self.remediation}


@dataclass(frozen=True, slots=True)
class ToolFact:
    name: str
    path: Path
    version: str
    source: ToolSource
    executable_sha256: str

    def to_dict(self) -> dict[str, str]:
        return {
            "name": self.name,
            "path": self.path.as_posix(),
            "version": self.version,
            "source": self.source,
            "executableSha256": self.executable_sha256,
        }


@dataclass(frozen=True, slots=True)
class ToolSupportProfile:
    python_version: str
    cubemx: ToolFact | None
    cubeclt_root: Path | None
    gcc: ToolFact | None
    cmake: ToolFact | None
    ninja: ToolFact | None
    vscode: ToolFact | None
    vscode_extensions: tuple[tuple[str, str], ...]
    issues: tuple[ToolSupportIssue, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "pythonVersion": self.python_version,
            "cubeMx": self.cubemx.to_dict() if self.cubemx else None,
            "cubeCltRoot": self.cubeclt_root.as_posix() if self.cubeclt_root else None,
            "gcc": self.gcc.to_dict() if self.gcc else None,
            "cmake": self.cmake.to_dict() if self.cmake else None,
            "ninja": self.ninja.to_dict() if self.ninja else None,
            "vsCode": self.vscode.to_dict() if self.vscode else None,
            "vsCodeExtensions": [
                {"id": extension, "version": version}
                for extension, version in self.vscode_extensions
            ],
            "issues": [issue.to_dict() for issue in self.issues],
        }


def _safe_regular_file(path: Path) -> bool:
    try:
        info = os.lstat(path)
    except OSError:
        return False
    return stat.S_ISREG(info.st_mode) and not path.is_symlink() and not bool(
        getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    )


def _safe_directory(path: Path) -> bool:
    try:
        info = os.lstat(path)
    except OSError:
        return False
    return stat.S_ISDIR(info.st_mode) and not path.is_symlink() and not bool(
        getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    )


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _version_probe(path: Path) -> str | None:
    """Probe only a discovered executable with a fixed bounded argv."""
    try:
        observation = _run_bounded((str(path), "--version"))
        if observation.returncode != 0 or observation.timed_out or observation.truncated:
            return None
        raw = (observation.stdout or observation.stderr)[:_MAX_VERSION_BYTES]
        line = raw.decode("utf-8", errors="strict").splitlines()[0] if raw else ""
        return line[:512] or None
    except (OSError, subprocess.SubprocessError, UnicodeError):
        return None


def _run_cubeclt_metadata(root: Path) -> dict[str, str]:
    script = root / "STM32CubeCLT_metadata.bat"
    if not _safe_regular_file(script):
        return {}
    try:
        observation = _run_bounded((str(script), "-j"), capture_limit=_MAX_METADATA_BYTES)
        if observation.returncode != 0 or observation.timed_out or observation.truncated:
            return {}
        payload = json.loads(observation.stdout.decode("utf-8", errors="strict"))
        return {str(k): str(v) for k, v in payload.items()} if isinstance(payload, dict) else {}
    except (OSError, UnicodeError, ValueError, subprocess.SubprocessError):
        return {}


def _windows_file_version(path: Path) -> str | None:
    """Read the PE version resource without starting the executable."""
    if os.name != "nt":
        return None
    try:
        version = ctypes.windll.version
        size = version.GetFileVersionInfoSizeW(str(path), None)
        if not size:
            return None
        buffer = ctypes.create_string_buffer(size)
        if not version.GetFileVersionInfoW(str(path), 0, size, buffer):
            return None
        pointer = ctypes.c_void_p()
        length = ctypes.wintypes.UINT()
        if not version.VerQueryValueW(buffer, "\\VarFileInfo\\Translation", ctypes.byref(pointer), ctypes.byref(length)):
            return None
        language = ctypes.cast(pointer, ctypes.POINTER(ctypes.c_ushort * 2)).contents
        sub_block = f"\\StringFileInfo\\{language[0]:04x}{language[1]:04x}\\ProductVersion"
        if not version.VerQueryValueW(buffer, sub_block, ctypes.byref(pointer), ctypes.byref(length)):
            return None
        return ctypes.wstring_at(pointer, max(0, int(length.value) - 1)) or None
    except (AttributeError, OSError, TypeError, ValueError):
        return None


def _fact(
    name: str,
    path: Path,
    source: ToolSource,
    version: str | None = None,
    *,
    probe_versions: bool = True,
    allow_process_probe: bool = True,
) -> ToolFact | None:
    if not _safe_regular_file(path):
        return None
    try:
        current = path.absolute()
        anchor = Path(current.anchor)
        while current != anchor:
            info = os.lstat(current)
            if current.is_symlink() or bool(getattr(info, "st_file_attributes", 0) & _REPARSE):
                return None
            current = current.parent
    except OSError:
        return None
    try:
        digest = _digest(path)
    except OSError:
        return None
    probed = _windows_file_version(path) if probe_versions else None
    probed = probed or (_version_probe(path) if probe_versions and allow_process_probe else None)
    selected = version or probed or "unknown"
    if name in ("gcc", "cmake", "ninja"):
        match = re.search(r"\b(14\.3\.1|4\.3\.1|1\.13\.2)\b", selected)
        selected = match.group(1) if match else selected
    return ToolFact(name, path.absolute(), selected, source, digest)


def _read_profile(path: Path | None) -> dict[str, object]:
    if path is None:
        return {}
    if not _safe_regular_file(path):
        raise SupportProfileError("support profile is unavailable")
    try:
        if path.stat().st_size > _MAX_METADATA_BYTES:
            raise SupportProfileError("support profile is oversized")
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise SupportProfileError("support profile schema is invalid")
        return payload
    except SupportProfileError:
        raise
    except (OSError, UnicodeError, ValueError):
        raise SupportProfileError("support profile content is invalid") from None


def _profile_allowed(path: Path, data_root: Path | None) -> bool:
    if data_root is None:
            return False
    try:
        root = data_root.resolve(strict=True)
        candidate = path.absolute()
        candidate.relative_to(root)
        current = candidate
        while current != root:
            info = os.lstat(current)
            if current.is_symlink() or bool(getattr(info, "st_file_attributes", 0) & _REPARSE):
                return False
            current = current.parent
        return _safe_regular_file(candidate)
    except (OSError, ValueError):
        return False


def _under_safe_root(path: Path, root: Path) -> bool:
    try:
        candidate = path.absolute()
        base = root.resolve(strict=True)
        candidate.relative_to(base)
        current = candidate
        while current != base:
            info = os.lstat(current)
            if current.is_symlink() or bool(getattr(info, "st_file_attributes", 0) & _REPARSE):
                return False
            current = current.parent
        return True
    except (OSError, ValueError):
        return False


def _entry(payload: dict[str, object], name: str) -> dict[str, object] | None:
    value = payload.get(name)
    if isinstance(value, dict):
        return value
    tools = payload.get("tools")
    if isinstance(tools, dict) and isinstance(tools.get(name), dict):
        return tools[name]  # type: ignore[return-value]
    return None


def _explicit_fact(payload: dict[str, object], name: str) -> ToolFact | None:
    entry = _entry(payload, name)
    if entry is None:
        return None
    raw_path = entry.get("path")
    if not isinstance(raw_path, str):
        return None
    return _fact(
        name,
        Path(raw_path),
        "explicit",
        str(entry.get("version") or "unknown"),
        allow_process_probe=name not in ("cubeMx", "vsCode"),
    )


def _metadata_candidates(root: Path) -> dict[str, str]:
    """Read only the bounded native CubeCLT metadata seam."""
    return _run_cubeclt_metadata(root)


def _metadata_fact(root: Path, name: str, metadata: dict[str, str], *, probe_versions: bool = True) -> ToolFact | None:
    metadata_key = {"gcc": "GNUToolsForSTM32", "cmake": "CMake", "ninja": "Ninja"}.get(name, name)
    relative = metadata.get(name) or metadata.get(name.lower()) or metadata.get(metadata_key)
    if relative:
        path = Path(relative)
        if not path.is_absolute():
            path = root / path
        if path.is_dir():
            leaf = {"gcc": "arm-none-eabi-gcc.exe", "cmake": "cmake.exe", "ninja": "ninja.exe"}[name]
            path = path / leaf
        if not _under_safe_root(path, root):
            return None
        return _fact(name, path, "cubeclt-metadata", probe_versions=probe_versions)
    layouts = {
        "gcc": ("GNU-tools-for-STM32/bin/arm-none-eabi-gcc.exe", "bin/arm-none-eabi-gcc.exe"),
        "cmake": ("CMake/bin/cmake.exe", "bin/cmake.exe"),
        "ninja": ("Ninja/bin/ninja.exe", "bin/ninja.exe"),
    }
    for relative_path in layouts.get(name, ()):
        fact = _fact(name, root / relative_path, "cubeclt-metadata", probe_versions=probe_versions)
        if fact:
            return fact
    return None


def _find_path_fact(name: str, *, probe_versions: bool = True) -> ToolFact | None:
    try:
        located = shutil.which({"gcc": "arm-none-eabi-gcc", "cmake": "cmake", "ninja": "ninja"}[name])
    except (KeyError, OSError):
        located = None
    return _fact(name, Path(located), "path", probe_versions=probe_versions) if located else None


def _discover_cubeclt(payload: dict[str, object]) -> tuple[Path | None, dict[str, str]]:
    raw_root = payload.get("cubeCltRoot") or payload.get("cubeclt_root")
    if isinstance(raw_root, str):
        root = Path(raw_root)
        if _safe_directory(root):
            return root.absolute(), _metadata_candidates(root)
    for root in _CUBECLT_ROOTS:
        if _safe_directory(root):
            return root.absolute(), _metadata_candidates(root)
    return None, {}


def _discover_cubeclt_fact(root: Path | None, name: str, metadata: dict[str, str], *, probe_versions: bool = True) -> ToolFact | None:
    return _metadata_fact(root, name, metadata, probe_versions=probe_versions) if root else None


def _discover_vscode(payload: dict[str, object]) -> ToolFact | None:
    explicit = _explicit_fact(payload, "vsCode")
    if explicit:
        return explicit
    found = [_fact("vsCode", candidate, "standard", probe_versions=True, allow_process_probe=False) for candidate in _VS_CODE_PATHS]
    found = [fact for fact in found if fact]
    if os.name == "nt":
        try:
            import winreg
            for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
                with winreg.OpenKey(hive, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\Code.exe") as key:
                    registered, _ = winreg.QueryValueEx(key, None)
                if isinstance(registered, str):
                    fact = _fact("vsCode", Path(registered), "standard", probe_versions=True, allow_process_probe=False)
                    if fact:
                        found.append(fact)
        except (OSError, ImportError):
            pass
    if len(found) > 1:
        raise SupportProfileError("ambiguous vscode candidates")
    if found:
        return found[0]
    try:
        located = shutil.which("code")
    except OSError:
        located = None
    if located:
        return _fact("vsCode", Path(located), "path", probe_versions=True, allow_process_probe=False)
    return None


def _discover_cube_mx(payload: dict[str, object]) -> ToolFact | None:
    explicit = _explicit_fact(payload, "cubeMx")
    if explicit:
        return explicit
    registered_facts: list[ToolFact] = []
    if os.name == "nt":
        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\STM32CubeMX.exe") as key:
                registered, _ = winreg.QueryValueEx(key, None)
            if isinstance(registered, str):
                fact = _fact("cubeMx", Path(registered), "standard", probe_versions=True, allow_process_probe=False)
                if fact:
                    registered_facts.append(fact)
        except (OSError, ImportError):
            pass
    found = [_fact("cubeMx", candidate, "standard", probe_versions=True, allow_process_probe=False) for candidate in _CUBEMX_PATHS]
    found = registered_facts + [fact for fact in found if fact]
    if len(found) > 1:
        raise SupportProfileError("ambiguous cubeMx candidates")
    if found:
        return found[0]
    try:
        located = shutil.which("STM32CubeMX")
    except OSError:
        located = None
    if located:
        return _fact("cubeMx", Path(located), "path", probe_versions=True, allow_process_probe=False)
    return None


def _extensions(payload: dict[str, object]) -> tuple[tuple[str, str], ...]:
    raw = payload.get("vsCodeExtensions")
    found: dict[str, str] = {}
    if isinstance(raw, dict):
        found = {str(k): str(v) for k, v in raw.items() if isinstance(k, str)}
    return tuple((name, found[name]) for name in _EXTENSIONS if name in found)


def discover_tool_support(request: SupportProfileRequest | None = None, *, probe_versions: bool = True) -> ToolSupportProfile:
    request = request or SupportProfileRequest()
    python_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    if request.profile_path is not None and not _profile_allowed(request.profile_path, request.data_root):
        raise SupportProfileError("support profile is outside trusted data root")
    payload = _read_profile(request.profile_path)
    if request.profile_path is not None:
        for key in ("cubeCltRoot", "cubeclt_root"):
            if key in payload and not isinstance(payload[key], str):
                raise SupportProfileError("support profile schema is invalid")
        for key in ("cubeMx", "gcc", "cmake", "ninja", "vsCode"):
            value = payload.get(key)
            if value is not None and (not isinstance(value, dict) or not isinstance(value.get("path"), str)):
                raise SupportProfileError("support profile schema is invalid")
    cubeclt_root, metadata = _discover_cubeclt(payload)
    explicit = {name: _explicit_fact(payload, name) for name in ("gcc", "cmake", "ninja")}
    facts: dict[str, ToolFact | None] = {}
    for name in ("gcc", "cmake", "ninja"):
        facts[name] = explicit[name] or _discover_cubeclt_fact(cubeclt_root, name, metadata, probe_versions=probe_versions) or _find_path_fact(name, probe_versions=probe_versions)
    cubemx = _discover_cube_mx(payload)
    vscode = _discover_vscode(payload)
    issues: list[ToolSupportIssue] = []
    if not (sys.version_info.major == 3 and sys.version_info.minor == 12):
        issues.append(ToolSupportIssue("PYTHON_UNSUPPORTED", "python", "Use CPython >=3.12,<3.13."))
    if cubemx is None:
        issues.append(ToolSupportIssue("CUBEMX_MISSING", "cubeMx", "Install STM32CubeMX 6.18 and rerun discovery."))
    elif not cubemx.version.startswith("6.18"):
        issues.append(ToolSupportIssue("CUBEMX_UNSUPPORTED", "cubeMx", "Use STM32CubeMX 6.18.x."))
    if cubeclt_root is None:
        issues.append(ToolSupportIssue("CUBECLT_MISSING", "cubeClt", "Install STM32CubeCLT 1.22.0 or provide a trusted profile."))
    for name, code in (("gcc", "GCC_MISSING"), ("cmake", "CMAKE_MISSING"), ("ninja", "NINJA_MISSING")):
        if facts[name] is None:
            issues.append(ToolSupportIssue(code, name, "Provide the supported STM32CubeCLT 1.22.0 tool."))
        else:
            expected = {"gcc": "14.3.1", "cmake": "4.3.1", "ninja": "1.13.2"}[name]
            if facts[name].version != expected:
                issues.append(ToolSupportIssue(code.replace("_MISSING", "_UNSUPPORTED"), name, f"Use the supported {expected} version."))
    if vscode is None:
        issues.append(ToolSupportIssue("VSCODE_MISSING", "vsCode", "Install VS Code or provide its supported executable."))
    issues.sort(key=lambda issue: (issue.code, issue.component))
    return ToolSupportProfile(
        python_version,
        cubemx,
        cubeclt_root,
        facts["gcc"],
        facts["cmake"],
        facts["ninja"],
        vscode,
        _extensions(payload),
        tuple(issues),
    )
