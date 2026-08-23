"""Fail-closed, read-only discovery of the VS07-A creation environment.

Discovery is intentionally split into candidate collection, one common
resolver, and evidence builders. Static executables (CubeMX and VS Code)
never enter the process runner; only CubeCLT metadata and the three native
build-tool version commands use the bounded runner seam.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import hashlib
import json
import os
import re
import shutil  # compatibility import for existing doctor/test callers
import stat
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal

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
_BUILD_STANDARD_PATHS: dict[str, tuple[Path, ...]] = {
    "gcc": (
        Path(r"C:\ST\STM32CubeCLT_1.22.0\GNU-tools-for-STM32\bin\arm-none-eabi-gcc.exe"),
        Path(r"C:\Program Files\STMicroelectronics\STM32CubeCLT_1.22.0\GNU-tools-for-STM32\bin\arm-none-eabi-gcc.exe"),
    ),
    "cmake": (
        Path(r"C:\ST\STM32CubeCLT_1.22.0\CMake\bin\cmake.exe"),
        Path(r"C:\Program Files\STMicroelectronics\STM32CubeCLT_1.22.0\CMake\bin\cmake.exe"),
    ),
    "ninja": (
        Path(r"C:\ST\STM32CubeCLT_1.22.0\Ninja\bin\ninja.exe"),
        Path(r"C:\Program Files\STMicroelectronics\STM32CubeCLT_1.22.0\Ninja\bin\ninja.exe"),
    ),
}
_EXTENSIONS = (
    "ms-vscode.cpptools",
    "ms-vscode.cmake-tools",
    "marus25.cortex-debug",
)
_MAX_METADATA_BYTES = 64 * 1024
_MAX_VERSION_BYTES = 8 * 1024
_REPARSE = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
_REAL_POPEN = subprocess.Popen
_VERSION_PATTERN = re.compile(r"(?<!\d)(\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?)(?!\d)")
_EXPECTED_VERSIONS = {"gcc": "14.3.1", "cmake": "4.3.1", "ninja": "1.13.2"}
_EXECUTABLES = {
    "gcc": ("arm-none-eabi-gcc.exe",),
    "cmake": ("cmake.exe",),
    "ninja": ("ninja.exe",),
    "cubeMx": ("STM32CubeMX.exe",),
    "vsCode": ("Code.exe", "code.exe"),
}
_REGISTRY_KEYS = {
    "gcc": ("arm-none-eabi-gcc.exe",),
    "cmake": ("cmake.exe",),
    "ninja": ("ninja.exe",),
    "cubeMx": ("STM32CubeMX.exe",),
    "vsCode": ("Code.exe", "code.exe"),
}


class SupportProfileError(ValueError):
    """Raised when a trusted profile is absent, malformed, or unsafe."""


@dataclass(frozen=True, slots=True)
class ProcessObservation:
    returncode: int | None
    stdout: bytes
    stderr: bytes
    timed_out: bool = False
    truncated: bool = False


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
            "vsCodeExtensions": [{"id": extension, "version": version} for extension, version in self.vscode_extensions],
            "issues": [issue.to_dict() for issue in self.issues],
        }


@dataclass(frozen=True, slots=True)
class DiscoveryCandidate:
    path: Path
    source: str
    version_hint: str | None = None


@dataclass(frozen=True, slots=True)
class CandidateTier:
    source: str
    candidates: tuple[DiscoveryCandidate, ...]
    invalid: bool = False


@dataclass(frozen=True, slots=True)
class CandidateResolution:
    fact: ToolFact | None
    issue: ToolSupportIssue | None


def _component_label(component: str) -> str:
    return {"cubeMx": "CUBEMX", "vsCode": "VSCODE", "cubeClt": "CUBECLT"}.get(component, component.upper())


def _issue(component: str, suffix: str, remediation: str) -> ToolSupportIssue:
    return ToolSupportIssue(f"{_component_label(component)}_{suffix}", component, remediation)


def _is_reparse(info: object) -> bool:
    return bool(getattr(info, "st_file_attributes", 0) & _REPARSE)


def _lexists(path: Path) -> bool:
    try:
        os.lstat(path)
        return True
    except OSError:
        return False


def _safe_regular_file(path: Path) -> bool:
    try:
        info = os.lstat(path)
    except OSError:
        return False
    return stat.S_ISREG(info.st_mode) and not path.is_symlink() and not _is_reparse(info)


def _safe_directory(path: Path) -> bool:
    try:
        info = os.lstat(path)
    except OSError:
        return False
    return stat.S_ISDIR(info.st_mode) and not path.is_symlink() and not _is_reparse(info)


def _safe_chain(path: Path, *, regular: bool = False, directory: bool = False) -> Path | None:
    try:
        lexical = path.absolute()
        resolved = lexical.resolve(strict=True)
        current = lexical
        while True:
            info = os.lstat(current)
            if current.is_symlink() or _is_reparse(info):
                return None
            if current == current.parent:
                break
            current = current.parent
        target_info = os.lstat(resolved)
        if _is_reparse(target_info) or resolved.is_symlink():
            return None
        if regular and not stat.S_ISREG(target_info.st_mode):
            return None
        if directory and not stat.S_ISDIR(target_info.st_mode):
            return None
        return resolved
    except (OSError, RuntimeError, ValueError):
        return None


def _canonical_regular_file(path: Path) -> Path | None:
    return _safe_chain(path, regular=True)


def _canonical_directory(path: Path) -> Path | None:
    return _safe_chain(path, directory=True)


def _under_safe_root(path: Path, root: Path) -> bool:
    candidate = _safe_chain(path)
    base = _canonical_directory(root)
    if candidate is None or base is None:
        return False
    try:
        candidate.relative_to(base)
        return True
    except ValueError:
        return False


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _run_bounded(argv: tuple[str, ...], timeout_seconds: float = 5.0, capture_limit: int = _MAX_VERSION_BYTES) -> ProcessObservation:
    process = None
    try:
        process = _REAL_POPEN(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False)
        try:
            stdout, stderr = process.communicate(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            try:
                process.terminate()
            except OSError:
                pass
            try:
                process.wait(timeout=1)
            except (OSError, subprocess.TimeoutExpired):
                try:
                    process.kill()
                except OSError:
                    pass
                try:
                    process.wait(timeout=1)
                except (OSError, subprocess.TimeoutExpired):
                    pass
            try:
                process.communicate(timeout=1)
            except (OSError, subprocess.SubprocessError):
                pass
            return ProcessObservation(None, b"", b"", timed_out=True)
        out, err = stdout or b"", stderr or b""
        return ProcessObservation(process.returncode, out[:capture_limit], err[:capture_limit], truncated=len(out) + len(err) > capture_limit)
    except (OSError, ValueError, subprocess.SubprocessError):
        return ProcessObservation(None, b"", b"")


_VERSION_PATTERN = re.compile(r"(?<!\d)(\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?)(?!\d)")
_EXPECTED_VERSIONS = {"gcc": "14.3.1", "cmake": "4.3.1", "ninja": "1.13.2"}


def _extract_version(text: str) -> str | None:
    match = _VERSION_PATTERN.search(text or "")
    return match.group(1) if match else None


def _version_probe(path: Path) -> str | None:
    try:
        observation = _run_bounded((str(path), "--version"))
        if not isinstance(observation, ProcessObservation) or observation.returncode != 0 or observation.timed_out or observation.truncated:
            return None
        raw = observation.stdout or observation.stderr
        text = raw.decode("utf-8", errors="strict").strip()
        return text.splitlines()[0][:512] if text else None
    except (OSError, UnicodeError, subprocess.SubprocessError, AttributeError):
        return None


def _windows_file_version(path: Path) -> str | None:
    """Read PE version resources without starting the executable."""
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
        if not version.VerQueryValueW(buffer, r"\VarFileInfo\Translation", ctypes.byref(pointer), ctypes.byref(length)):
            return None
        language = ctypes.cast(pointer, ctypes.POINTER(ctypes.c_ushort * 2)).contents
        sub_block = rf"\StringFileInfo\{language[0]:04x}{language[1]:04x}\ProductVersion"
        if not version.VerQueryValueW(buffer, sub_block, ctypes.byref(pointer), ctypes.byref(length)):
            return None
        return ctypes.wstring_at(pointer, max(0, int(length.value) - 1)) or None
    except (AttributeError, OSError, TypeError, ValueError):
        return None


def _fact(name: str, path: Path, source: ToolSource, version: str | None = None, *, probe_versions: bool = True, allow_process_probe: bool = True) -> ToolFact | None:
    canonical = _canonical_regular_file(path)
    if canonical is None:
        return None
    try:
        digest = _digest(canonical)
    except OSError:
        return None
    selected = version
    if selected is None or selected == "unknown":
        if probe_versions:
            if name in ("cubeMx", "vsCode"):
                selected = _windows_file_version(canonical)
            elif allow_process_probe:
                selected = _extract_version(_version_probe(canonical) or "")
    return ToolFact(name, canonical, selected or "unknown", source, digest)


def _build_fact(candidate: DiscoveryCandidate, component: str, *, probe_versions: bool) -> ToolFact | None:
    version = candidate.version_hint
    if version is None and probe_versions:
        version = _extract_version(_version_probe(candidate.path) or "")
        if version is None:
            return None
    return _fact(component, candidate.path, candidate.source, version or "unknown", probe_versions=False, allow_process_probe=False)  # type: ignore[arg-type]


def _static_fact_for(component: str, candidate: DiscoveryCandidate, *, probe_versions: bool) -> ToolFact | None:
    version = candidate.version_hint
    if version is None and probe_versions:
        version = _windows_file_version(candidate.path)
        if version is None:
            return None
    return _fact(component, candidate.path, candidate.source, version or "unknown", probe_versions=False, allow_process_probe=False)  # type: ignore[arg-type]


def _resolve_component(component: str, tiers: tuple[CandidateTier, ...], evidence_builder: Callable[[DiscoveryCandidate], ToolFact | None]) -> CandidateResolution:
    """Apply the frozen tier transition table for one component."""
    for tier in tiers:
        if tier.invalid:
            return CandidateResolution(None, _issue(component, "INVALID", "Provide a safe supported executable."))
        canonical: dict[str, DiscoveryCandidate] = {}
        for candidate in tier.candidates:
            resolved = _canonical_regular_file(candidate.path)
            if resolved is None:
                return CandidateResolution(None, _issue(component, "INVALID", "Provide a safe supported executable."))
            key = os.path.normcase(str(resolved))
            canonical.setdefault(key, DiscoveryCandidate(resolved, candidate.source, candidate.version_hint))
        if not canonical:
            continue
        if len(canonical) > 1:
            return CandidateResolution(None, _issue(component, "AMBIGUOUS", "Provide exactly one supported executable."))
        fact = evidence_builder(next(iter(canonical.values())))
        if fact is None:
            return CandidateResolution(None, _issue(component, "PROBE_FAILED", "Provide readable supported version evidence."))
        return CandidateResolution(fact, None)
    return CandidateResolution(None, _issue(component, "MISSING", "Install or configure the supported tool."))


def _read_profile(path: Path | None) -> dict[str, object]:
    if path is None:
        return {}
    if not _safe_regular_file(path):
        raise SupportProfileError("support profile is unavailable")
    try:
        if path.stat().st_size > _MAX_METADATA_BYTES:
            raise SupportProfileError("support profile is oversized")
        payload = json.loads(path.read_bytes().decode("utf-8", errors="strict"))
    except SupportProfileError:
        raise
    except (OSError, UnicodeError, ValueError):
        raise SupportProfileError("support profile content is invalid") from None
    if not isinstance(payload, dict):
        raise SupportProfileError("support profile schema is invalid")
    return payload


def _profile_allowed(path: Path, data_root: Path | None) -> bool:
    if data_root is None:
        return False
    root = _canonical_directory(data_root)
    profile = _canonical_regular_file(path)
    if root is None or profile is None:
        return False
    try:
        profile.relative_to(root)
        return True
    except ValueError:
        return False


def _entry(payload: dict[str, object], name: str) -> dict[str, object] | None:
    value = payload.get(name)
    if isinstance(value, dict):
        return value
    tools = payload.get("tools")
    if isinstance(tools, dict) and isinstance(tools.get(name), dict):
        return tools[name]  # type: ignore[return-value]
    return None


def _validate_profile_payload(payload: dict[str, object], data_root: Path | None) -> None:
    if data_root is None or _canonical_directory(data_root) is None:
        raise SupportProfileError("support profile data root is unavailable")
    for key in ("cubeCltRoot", "cubeclt_root"):
        if key in payload:
            raw_root = payload[key]
            if not isinstance(raw_root, str) or _canonical_directory(Path(raw_root)) is None:
                raise SupportProfileError("support profile cubeclt root is invalid")
    for name in ("cubeMx", "vsCode", "gcc", "cmake", "ninja"):
        entry = _entry(payload, name)
        if entry is None:
            continue
        if set(entry) - {"path", "version"}:
            raise SupportProfileError("support profile schema is invalid")
        raw_path = entry.get("path")
        version = entry.get("version")
        if not isinstance(raw_path, str) or (version is not None and not isinstance(version, str)):
            raise SupportProfileError("support profile schema is invalid")
        if _canonical_regular_file(Path(raw_path)) is None:
            raise SupportProfileError("support profile candidate is invalid")


def _explicit_tier(payload: dict[str, object], component: str) -> CandidateTier | None:
    value = _entry(payload, component)
    if value is None:
        return None
    raw_path = value.get("path")
    version = value.get("version")
    if not isinstance(raw_path, str) or (version is not None and not isinstance(version, str)):
        return CandidateTier("explicit", (), invalid=True)
    return CandidateTier("explicit", (DiscoveryCandidate(Path(raw_path), "explicit", version),))


@dataclass(frozen=True, slots=True)
class _MetadataRead:
    values: dict[str, object]
    present: bool
    invalid: bool


def _read_metadata(root: Path) -> _MetadataRead:
    script = root / "STM32CubeCLT_metadata.bat"
    if not _lexists(script):
        return _MetadataRead({}, False, False)
    if not _safe_regular_file(script) or not _under_safe_root(script, root):
        return _MetadataRead({}, True, True)
    try:
        observation = _run_bounded((str(script), "-j"), capture_limit=_MAX_METADATA_BYTES)
        if not isinstance(observation, ProcessObservation) or observation.returncode != 0 or observation.timed_out or observation.truncated:
            return _MetadataRead({}, True, True)
        payload = json.loads(observation.stdout.decode("utf-8", errors="strict"))
        if not isinstance(payload, dict):
            return _MetadataRead({}, True, True)
        if any(not isinstance(key, str) for key in payload) or any(key in {"GNUToolsForSTM32", "CMake", "Ninja", "gcc", "cmake", "ninja"} and not isinstance(value, str) for key, value in payload.items()):
            return _MetadataRead({}, True, True)
        return _MetadataRead(dict(payload), True, False)
    except (OSError, UnicodeError, ValueError, AttributeError, subprocess.SubprocessError):
        return _MetadataRead({}, True, True)


def _run_cubeclt_metadata(root: Path) -> dict[str, str]:
    result = _read_metadata(root)
    return {key: value for key, value in result.values.items() if isinstance(value, str)}


def _metadata_candidates(root: Path) -> dict[str, str]:
    return _run_cubeclt_metadata(root)


def _metadata_value(metadata: _MetadataRead, component: str) -> object | None:
    names = {"gcc": ("gcc", "GNUToolsForSTM32"), "cmake": ("cmake", "CMake"), "ninja": ("ninja", "Ninja")}[component]
    for name in names:
        if name in metadata.values:
            return metadata.values[name]
    return None


def _known_layout(root: Path, component: str) -> Path:
    return root / {"gcc": "GNU-tools-for-STM32/bin/arm-none-eabi-gcc.exe", "cmake": "CMake/bin/cmake.exe", "ninja": "Ninja/bin/ninja.exe"}[component]


def _metadata_tier(root: Path | None, metadata: _MetadataRead, component: str) -> CandidateTier | None:
    if root is None:
        return None
    if metadata.invalid:
        return CandidateTier("cubeclt-metadata", (), invalid=True)
    if metadata.present:
        value = _metadata_value(metadata, component)
        if value is None:
            return CandidateTier("cubeclt-metadata", ())
        if not isinstance(value, str):
            return CandidateTier("cubeclt-metadata", (), invalid=True)
        path = Path(value)
        if not path.is_absolute():
            path = root / path
        expected_leaf = {"gcc": "arm-none-eabi-gcc.exe", "cmake": "cmake.exe", "ninja": "ninja.exe"}[component]
        if path.name.casefold() != expected_leaf.casefold() or not _under_safe_root(path, root):
            return CandidateTier("cubeclt-metadata", (), invalid=True)
        return CandidateTier("cubeclt-metadata", (DiscoveryCandidate(path, "cubeclt-metadata"),))
    known = _known_layout(root, component)
    return CandidateTier("cubeclt-metadata", (DiscoveryCandidate(known, "cubeclt-metadata"),)) if _lexists(known) else CandidateTier("cubeclt-metadata", ())


def _registry_candidates(component: str) -> tuple[DiscoveryCandidate, ...]:
    if os.name != "nt":
        return ()
    try:
        import winreg
    except ImportError:
        return ()
    result: list[DiscoveryCandidate] = []
    base = r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"
    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        for executable in _REGISTRY_KEYS[component]:
            try:
                opened = winreg.OpenKey(hive, f"{base}\\{executable}")
                if hasattr(opened, "__enter__"):
                    with opened as key:
                        value, _ = winreg.QueryValueEx(key, None)
                else:
                    value, _ = winreg.QueryValueEx(opened, None)
                    close = getattr(opened, "Close", None)
                    if close is not None:
                        close()
            except (OSError, AttributeError, TypeError):
                continue
            if isinstance(value, str) and value.strip():
                result.append(DiscoveryCandidate(Path(value.strip().strip('"')), "standard"))
    return tuple(result)


def _standard_tier(component: str) -> CandidateTier:
    if component in _BUILD_STANDARD_PATHS:
        paths = _BUILD_STANDARD_PATHS[component]
    elif component == "cubeMx":
        paths = _CUBEMX_PATHS
    else:
        paths = _VS_CODE_PATHS
    candidates = [DiscoveryCandidate(path, "standard") for path in paths]
    candidates.extend(_registry_candidates(component))
    return CandidateTier("standard", tuple(candidates))


def _path_tier(component: str) -> CandidateTier:
    names = _EXECUTABLES[component]
    suffixes = [""]
    for raw in os.environ.get("PATHEXT", ".COM;.EXE;.BAT;.CMD").split(";"):
        suffix = raw.strip().lower()
        if suffix and suffix not in suffixes:
            suffixes.append(suffix)
    if ".exe" not in suffixes:
        suffixes.append(".exe")
    directories: dict[str, Path] = {}
    for raw_dir in os.environ.get("PATH", "").split(os.pathsep):
        if raw_dir:
            directory = Path(raw_dir)
            directories.setdefault(os.path.normcase(str(directory.absolute())), directory)
    candidates: list[DiscoveryCandidate] = []
    for directory in directories.values():
        if not _safe_directory(directory):
            continue
        for base in names:
            stem = base[:-4] if base.casefold().endswith(".exe") else base
            possible = [base]
            if os.name != "nt":
                possible.append(stem)
            possible.extend(stem + suffix for suffix in suffixes if suffix)
            seen: set[str] = set()
            for name in possible:
                if name.casefold() in seen:
                    continue
                seen.add(name.casefold())
                path = directory / name
                if _lexists(path):
                    candidates.append(DiscoveryCandidate(path, "path"))
    return CandidateTier("path", tuple(candidates))


def _discover_cubeclt(payload: dict[str, object]) -> tuple[Path | None, _MetadataRead]:
    raw_root = payload.get("cubeCltRoot", payload.get("cubeclt_root"))
    if raw_root is not None:
        if not isinstance(raw_root, str):
            raise SupportProfileError("support profile cubeclt root is invalid")
        root = _canonical_directory(Path(raw_root))
        if root is None:
            raise SupportProfileError("support profile cubeclt root is invalid")
        return root, _read_metadata(root)
    for candidate in _CUBECLT_ROOTS:
        root = _canonical_directory(candidate)
        if root is not None:
            return root, _read_metadata(root)
    return None, _MetadataRead({}, False, False)


def _metadata_fact(root: Path, name: str, metadata: dict[str, str], *, probe_versions: bool = True) -> ToolFact | None:
    value = _metadata_value(_MetadataRead(metadata, True, False), name)
    if not isinstance(value, str):
        return None
    path = Path(value)
    if not path.is_absolute():
        path = root / path
    if not _under_safe_root(path, root):
        return None
    return _build_fact(DiscoveryCandidate(path, "cubeclt-metadata"), name, probe_versions=probe_versions)


def _resolve_static(payload: dict[str, object], component: str, *, probe_versions: bool) -> CandidateResolution:
    tiers: list[CandidateTier] = []
    explicit = _explicit_tier(payload, component)
    if explicit is not None:
        tiers.append(explicit)
    tiers.extend((_standard_tier(component), _path_tier(component)))
    return _resolve_component(component, tuple(tiers), lambda candidate: _static_fact_for(component, candidate, probe_versions=probe_versions))


_LAST_DISCOVERY_ISSUES: dict[str, ToolSupportIssue] = {}


def _discover_cube_mx(payload: dict[str, object], *, probe_versions: bool = True) -> ToolFact | None:
    result = _resolve_static(payload, "cubeMx", probe_versions=probe_versions)
    if result.issue is not None:
        _LAST_DISCOVERY_ISSUES["cubeMx"] = result.issue
    return result.fact


def _discover_vscode(payload: dict[str, object], *, probe_versions: bool = True) -> ToolFact | None:
    result = _resolve_static(payload, "vsCode", probe_versions=probe_versions)
    if result.issue is not None:
        _LAST_DISCOVERY_ISSUES["vsCode"] = result.issue
    return result.fact


_DEFAULT_DISCOVER_CUBE_MX = _discover_cube_mx
_DEFAULT_DISCOVER_VSCODE = _discover_vscode


def _discover_cubeclt_fact(root: Path | None, name: str, metadata: dict[str, str], *, probe_versions: bool = True) -> ToolFact | None:
    return _metadata_fact(root, name, metadata, probe_versions=probe_versions) if root else None


def _find_path_fact(name: str, *, probe_versions: bool = True) -> ToolFact | None:
    return _resolve_component(name, (_path_tier(name),), lambda candidate: _build_fact(candidate, name, probe_versions=probe_versions)).fact


def _extensions(payload: dict[str, object]) -> tuple[tuple[str, str], ...]:
    raw = payload.get("vsCodeExtensions")
    found = {key: value for key, value in raw.items() if isinstance(key, str) and isinstance(value, str)} if isinstance(raw, dict) else {}
    return tuple((name, found[name]) for name in _EXTENSIONS if name in found)


def _append_issue(issues: list[ToolSupportIssue], issue: ToolSupportIssue | None) -> None:
    if issue is not None and not any(item.code == issue.code and item.component == issue.component for item in issues):
        issues.append(issue)


def discover_tool_support(request: SupportProfileRequest | None = None, *, probe_versions: bool = True) -> ToolSupportProfile:
    request = request or SupportProfileRequest()
    if request.profile_path is not None and not _profile_allowed(request.profile_path, request.data_root):
        raise SupportProfileError("support profile is outside trusted data root")
    payload = _read_profile(request.profile_path)
    if request.profile_path is not None:
        _validate_profile_payload(payload, request.data_root)
    _LAST_DISCOVERY_ISSUES.clear()
    cubeclt_root, metadata = _discover_cubeclt(payload)
    facts: dict[str, ToolFact | None] = {}
    issues: list[ToolSupportIssue] = []
    for component in ("gcc", "cmake", "ninja"):
        tiers: list[CandidateTier] = []
        explicit = _explicit_tier(payload, component)
        if explicit is not None:
            tiers.append(explicit)
        metadata_tier = _metadata_tier(cubeclt_root, metadata, component)
        if metadata_tier is not None:
            tiers.append(metadata_tier)
        tiers.extend((_standard_tier(component), _path_tier(component)))
        result = _resolve_component(component, tuple(tiers), lambda candidate, component=component: _build_fact(candidate, component, probe_versions=probe_versions))
        facts[component] = result.fact
        _append_issue(issues, result.issue)
        if result.fact is not None and result.fact.version != _EXPECTED_VERSIONS[component]:
            _append_issue(issues, _issue(component, "UNSUPPORTED", f"Use the supported {_EXPECTED_VERSIONS[component]} version."))
    # Keep the historical helper seam callable by simple monkeypatches used by
    # doctor-facing tests while preserving the probe_versions test seam.
    if _discover_cube_mx is _DEFAULT_DISCOVER_CUBE_MX:
        cubemx = _discover_cube_mx(payload, probe_versions=probe_versions)
    else:
        cubemx = _discover_cube_mx(payload)
    _append_issue(issues, _LAST_DISCOVERY_ISSUES.get("cubeMx"))
    if cubemx is not None and not cubemx.version.startswith("6.18"):
        _append_issue(issues, _issue("cubeMx", "UNSUPPORTED", "Use STM32CubeMX 6.18.x."))
    if cubemx is None and "cubeMx" not in _LAST_DISCOVERY_ISSUES:
        _append_issue(issues, _issue("cubeMx", "MISSING", "Install STM32CubeMX 6.18 and rerun discovery."))
    if _discover_vscode is _DEFAULT_DISCOVER_VSCODE:
        vscode = _discover_vscode(payload, probe_versions=probe_versions)
    else:
        vscode = _discover_vscode(payload)
    _append_issue(issues, _LAST_DISCOVERY_ISSUES.get("vsCode"))
    if vscode is None and "vsCode" not in _LAST_DISCOVERY_ISSUES:
        _append_issue(issues, _issue("vsCode", "MISSING", "Install VS Code or provide its supported executable."))
    if sys.version_info[:2] != (3, 12):
        _append_issue(issues, ToolSupportIssue("PYTHON_UNSUPPORTED", "python", "Use CPython >=3.12,<3.13."))
    if cubeclt_root is None:
        _append_issue(issues, _issue("cubeClt", "MISSING", "Install STM32CubeCLT 1.22.0 or provide a trusted profile."))
    issues.sort(key=lambda issue: (issue.code, issue.component, issue.remediation))
    return ToolSupportProfile(f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}", cubemx, cubeclt_root, facts["gcc"], facts["cmake"], facts["ninja"], vscode, _extensions(payload), tuple(issues))
