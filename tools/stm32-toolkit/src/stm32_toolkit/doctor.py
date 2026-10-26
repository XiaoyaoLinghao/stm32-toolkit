from __future__ import annotations

import importlib.metadata
import os
import platform
import shutil
import stat
import subprocess
import sys
import threading
from dataclasses import replace
from pathlib import Path
from typing import BinaryIO

from stm32_toolkit.detection import detect_project, planned_action
from stm32_toolkit import __version__ as TOOLKIT_VERSION
from stm32_toolkit.doctor_readiness import (
    RECOMMENDED_EXTENSIONS as VSCODE_EXTENSIONS,
    collect_doctor_readiness,
)
from stm32_toolkit.keil.model import KeilInspectionError
from stm32_toolkit.result import OperationResult
from stm32_toolkit.tool_support import (
    SupportProfileRequest,
    ToolSupportProfile,
    _windows_file_version,
    discover_tool_support,
)
from stm32_toolkit.public_inventory import (
    MCP_TOOL_NAMES,
    REQUIRED_PYTHON,
    SKILL_NAMES,
    SUPPORTED_PYTHON,
)


TOOLS = (
    "arm-none-eabi-gcc",
    "arm-none-eabi-gdb",
    "cmake",
    "ninja",
    "pyocd",
    "STM32CubeMX",
    "code",
)

_GUI_TOOLS = frozenset({"STM32CubeMX", "code"})
_VERSION_TIMEOUT_SECONDS = 5
_REAP_TIMEOUT_SECONDS = 1
_READER_JOIN_TIMEOUT_SECONDS = 0.1
_VERSION_CAPTURE_LIMIT = 8 * 1024
_STREAM_READ_BYTES = 4 * 1024
_VERSION_LINE_LIMIT = 512

#: pyOCD evidence is deliberately split: ``data.tools.pyocd`` is PATH command
#: evidence, while ``probeCore.dependencies.pyocd`` is installed-distribution
#: metadata in this interpreter.  Neither is importability or hardware proof.
_PYOCD_RUNTIME_PRESENT = "runtime-package-present"
_PYOCD_RUNTIME_UNCONFIRMED = "runtime-package-unconfirmed"
_PYOCD_EVIDENCE_BASIS = "distribution-metadata"

_PYOCD_MESSAGE_PRESENT = (
    "pyOCD distribution metadata is present in this Toolkit interpreter's "
    "installed distributions. This evidence basis is distribution metadata "
    "only: importability, a working Probe backend, and hardware readiness were "
    "not checked, so it does not prove that pyOCD can be imported or that any "
    "target can be attached. The internal Probe backend imports pyOCD from its "
    "runtime, so a separate `pyocd` PATH command is not required for probe "
    "workflows."
)
_PYOCD_MESSAGE_PATH_MISSING = (
    "pyOCD distribution metadata is present in this Toolkit interpreter's "
    "installed distributions, but no `pyocd` command was found through PATH. "
    "This evidence basis is distribution metadata only: importability, a "
    "working Probe backend, and hardware readiness were not checked. The "
    "internal Probe backend imports pyOCD from its runtime, so a missing PATH "
    "command alone does not establish a missing runtime dependency."
)
_PYOCD_MESSAGE_UNCONFIRMED = (
    "pyOCD distribution metadata could not be confirmed from this Toolkit "
    "interpreter's installed distributions. This is unconfirmed evidence, not "
    "proof that the runtime package is uninstalled, and a separate `pyocd` PATH "
    "command would not confirm the runtime dependency either. Importability and "
    "hardware readiness were not checked."
)
_PYOCD_REMEDIATION_PRESENT = (
    "Distribution metadata alone does not verify importability, a working "
    "Probe backend, or hardware. Keep using the managed runtime and confirm it "
    "with the matching setup Check (`bin/setup-stm32-env.ps1 -Mode Check`). No "
    "PATH correction is needed solely because the PATH lookup is missing; do "
    "not add a global pip install or a PATH edit as the default remedy."
)
_PYOCD_REMEDIATION_UNCONFIRMED = (
    "Re-run the matching managed interpreter's setup Check "
    "(`bin/setup-stm32-env.ps1 -Mode Check`) and use the managed runtime whose "
    "`pyocd` distribution is installed; a separate PATH command does not "
    "substitute for that dependency, and this metadata check does not verify "
    "importability or hardware. Do not use a global pip install or a PATH edit "
    "as the default remedy."
)
_PYOCD_CLI_NOT_ON_PATH = "PYOCD_CLI_NOT_ON_PATH_RUNTIME_PRESENT"
_PYOCD_RUNTIME_UNCONFIRMED_CODE = "PYOCD_RUNTIME_PACKAGE_UNCONFIRMED"


def run_doctor(
    project_root: Path, *, data_root: Path | None = None,
    support_profile: ToolSupportProfile | None = None,
    probe_vscode_extensions: bool = True,
    vscode_path: Path | None = None,
    uv4_path: Path | None = None,
    armcc_path: Path | None = None,
) -> OperationResult[dict[str, object]]:
    """Collect offline, read-only evidence about the local toolkit environment.

    ``ok=true`` only means the report was collected.  Missing, invalid, or
    incomplete observations remain explicit evidence; they are not readiness
    failures fabricated into installed/missing facts.

    pyOCD is reported through two separate evidence forms: ``tools.pyocd`` is
    PATH command evidence and ``probeCore.dependencies.pyocd`` is installed
    distribution metadata in this interpreter.  ``probeCore.pyocdResolution``
    combines them for presentation only; it never imports pyOCD, starts a
    worker, enumerates probes, or claims importability or hardware readiness.
    """
    support = support_profile or discover_tool_support(SupportProfileRequest(data_root=data_root), probe_versions=True)
    readiness = collect_doctor_readiness(
        support_profile=support,
        probe_vscode_extensions=probe_vscode_extensions,
        vscode_path=vscode_path,
        uv4_path=uv4_path,
        armcc_path=armcc_path,
    )
    creation_support = support.to_dict()
    # The declared support-profile list remains compatible, with explicit
    # provenance.  Live observations stay only in vscodeExtensions above.
    creation_support["vsCodeExtensionsSource"] = "support-profile-declared"
    # Both pyOCD evidence forms are collected exactly once per doctor call:
    # PATH command evidence from ``tools`` and installed-distribution metadata
    # from ``probeCore.dependencies``.  No pyOCD import, worker, probe
    # enumeration, or extra process/network discovery happens here.
    tools = {name: _tool_evidence(name) for name in TOOLS}
    dependencies = {
        "aiohttp": _dependency_evidence("aiohttp"),
        "pyocd": _dependency_evidence("pyocd"),
    }
    pyocd_resolution = _pyocd_resolution(tools["pyocd"], dependencies["pyocd"])
    return replace(OperationResult.success(
        "doctor",
        {
            "platform": _platform_evidence(),
            "project": _project_evidence(project_root),
            "tools": tools,
            "vscodeExtensions": readiness["vscodeExtensions"],
            "vscodeExtensionObservation": readiness["vscodeExtensionObservation"],
            "keilTools": readiness["keilTools"],
            "readiness": readiness["readiness"],
            "diagnostics": [
                *readiness["diagnostics"],
                *_pyocd_diagnostics(pyocd_resolution),
            ],
            "probeCore": _probe_core_evidence(
                data_root, dependencies, pyocd_resolution
            ),
            "creationSupport": creation_support,
            "runtime": _runtime_evidence(),
            "publicInventory": _public_inventory(),
            "mutated": False,
        },
    ), details={"probeRegistrySemantics": "probe-lease-directory"})


def _monitor_version() -> str | None:
    try:
        return importlib.metadata.version("stm32-monitor")
    except (importlib.metadata.PackageNotFoundError, OSError, ValueError):
        return None


def _runtime_evidence() -> dict[str, object]:
    monitor_version = _monitor_version()
    python_version = ".".join(str(part) for part in sys.version_info[:3])
    return {
        "requiredPython": REQUIRED_PYTHON,
        "pythonVersion": python_version,
        "pythonSupported": sys.version_info[:2] == SUPPORTED_PYTHON,
        "toolkitVersion": TOOLKIT_VERSION,
        "monitorVersion": monitor_version,
        "versionsCompatible": monitor_version == TOOLKIT_VERSION,
    }


def _public_inventory() -> dict[str, object]:
    return {
        "mcpTools": list(MCP_TOOL_NAMES.values()),
        "skills": list(SKILL_NAMES),
    }


def _dependency_evidence(distribution: str) -> dict[str, object]:
    try:
        version = importlib.metadata.version(distribution)
    except importlib.metadata.PackageNotFoundError:
        return {"available": False, "version": None}
    except Exception:
        return {"available": False, "version": None}
    return {"available": True, "version": version}


def _probe_registry_evidence(data_root: Path | None) -> dict[str, object]:
    if data_root is None:
        return {"status": "unconfigured", "safe": True}
    lexical_data = data_root.expanduser().absolute()
    registry = lexical_data / "probe-registry"
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    for component in reversed((lexical_data, *lexical_data.parents)):
        try:
            component_metadata = os.lstat(component)
        except FileNotFoundError:
            continue
        except OSError:
            return {"status": "unavailable", "safe": False}
        if (
            component.is_symlink()
            or getattr(component_metadata, "st_file_attributes", 0) & reparse_flag
            or not stat.S_ISDIR(component_metadata.st_mode)
        ):
            return {"status": "redirect", "safe": False}
    try:
        data_metadata = os.lstat(lexical_data)
    except FileNotFoundError:
        return {"status": "missing", "safe": True}
    except OSError:
        return {"status": "unavailable", "safe": False}
    if (
        lexical_data.is_symlink()
        or getattr(data_metadata, "st_file_attributes", 0) & reparse_flag
        or not stat.S_ISDIR(data_metadata.st_mode)
    ):
        return {"status": "redirect", "safe": False}
    try:
        registry_metadata = os.lstat(registry)
    except FileNotFoundError:
        return {"status": "missing", "safe": True}
    except OSError:
        return {"status": "unavailable", "safe": False}
    if (
        registry.is_symlink()
        or getattr(registry_metadata, "st_file_attributes", 0) & reparse_flag
        or not stat.S_ISDIR(registry_metadata.st_mode)
    ):
        return {"status": "redirect", "safe": False}
    try:
        registry.resolve(strict=True).relative_to(lexical_data.resolve(strict=True))
    except (OSError, ValueError):
        return {"status": "redirect", "safe": False}
    return {"status": "ok", "safe": True}


def _probe_core_evidence(
    data_root: Path | None,
    dependencies: dict[str, object],
    pyocd_resolution: dict[str, object],
) -> dict[str, object]:
    return {
        "dependencies": dependencies,
        "registry": _probe_registry_evidence(data_root),
        "pyocdResolution": pyocd_resolution,
    }


def _pyocd_resolution(
    path_evidence: dict[str, object],
    runtime_metadata: dict[str, object],
) -> dict[str, object]:
    """Combine the two pyOCD evidence forms without cross-inference.

    ``path_evidence`` is ``data.tools.pyocd`` (PATH executable evidence);
    ``runtime_metadata`` is ``data.probeCore.dependencies.pyocd`` (installed
    distribution metadata).  A metadata lookup failure is reported as
    unconfirmed rather than as an uninstalled runtime, and a missing PATH
    command never overrides present metadata.
    """
    runtime_available = runtime_metadata.get("available") is True
    runtime_version = runtime_metadata.get("version") if runtime_available else None
    path_available = path_evidence.get("available") is True
    path_status = path_evidence.get("status")
    if not runtime_available:
        status = _PYOCD_RUNTIME_UNCONFIRMED
        message = _PYOCD_MESSAGE_UNCONFIRMED
        remediation = _PYOCD_REMEDIATION_UNCONFIRMED
    elif path_available:
        status = _PYOCD_RUNTIME_PRESENT
        message = _PYOCD_MESSAGE_PRESENT
        remediation = _PYOCD_REMEDIATION_PRESENT
    else:
        status = _PYOCD_RUNTIME_PRESENT
        message = _PYOCD_MESSAGE_PATH_MISSING
        remediation = _PYOCD_REMEDIATION_PRESENT
    return {
        "status": status,
        "runtimeAvailable": runtime_available,
        "runtimeVersion": (
            runtime_version if isinstance(runtime_version, str) else None
        ),
        "pathCommandAvailable": path_available,
        "pathCommandStatus": (
            path_status if isinstance(path_status, str) else "unknown"
        ),
        "evidenceBasis": _PYOCD_EVIDENCE_BASIS,
        "hardwareVerified": False,
        "message": message,
        "remediation": remediation,
    }


def _pyocd_diagnostics(
    resolution: dict[str, object],
) -> list[dict[str, object]]:
    """Additive diagnostics that preserve the CLI evidence as-is."""
    if resolution.get("runtimeAvailable") is not True:
        return [
            {
                "component": "pyocd",
                "code": _PYOCD_RUNTIME_UNCONFIRMED_CODE,
                "severity": "warning",
                "message": resolution["message"],
                "remediation": resolution["remediation"],
            }
        ]
    if resolution.get("pathCommandAvailable") is not True:
        return [
            {
                "component": "pyocd",
                "code": _PYOCD_CLI_NOT_ON_PATH,
                "severity": "info",
                "message": resolution["message"],
                "remediation": resolution["remediation"],
            }
        ]
    return []


def _platform_evidence() -> dict[str, str]:
    return {
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
    }


def _project_evidence(project_root: Path) -> dict[str, object]:
    try:
        return detect_project(project_root).to_dict()
    except KeilInspectionError as error:
        return {
            "kind": "unknown",
            "files": [],
            "recommended_action": planned_action("create-project").to_dict(),
            "discoveryError": {
                "code": error.code,
                "message": error.message,
                "details": error.details,
            },
        }
    except (OSError, ValueError):
        return {
            "kind": "unknown",
            "files": [],
            "recommended_action": planned_action("create-project").to_dict(),
        }


def _tool_evidence(name: str) -> dict[str, object]:
    try:
        executable = shutil.which(name)
    except OSError:
        executable = None

    if executable is None:
        return _tool_result(False, None, "missing", None, None)

    if name in _GUI_TOOLS:
        version = _windows_file_version(Path(executable))
        return _tool_result(True, executable, "ok" if version else "unknown", None, version)

    status, return_code, stdout, stderr = _run_process((executable, "--version"))
    if status in {"timeout", "error"}:
        return _tool_result(True, executable, status, return_code, None)

    version = _version_line(_decode_output(stdout))
    if version is None:
        version = _version_line(_decode_output(stderr))
    status = "ok" if return_code == 0 else "nonzero"
    return _tool_result(True, executable, status, return_code, version)


def _run_process(argv: tuple[str, ...]) -> tuple[str, int | None, bytes, bytes]:
    try:
        process = subprocess.Popen(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
        )
    except OSError:
        return "error", None, b"", b""

    captured, readers = _start_readers(process)
    try:
        return_code = process.wait(timeout=_VERSION_TIMEOUT_SECONDS)
        status = "ok"
    except subprocess.TimeoutExpired:
        _terminate_and_reap(process)
        return_code = None
        status = "timeout"
    except OSError:
        _terminate_and_reap(process)
        return_code = None
        status = "error"
    _join_readers(readers)
    _close_finished_streams(process, readers)
    return status, return_code, bytes(captured["stdout"]), bytes(captured["stderr"])

def _start_readers(process: subprocess.Popen[bytes]) -> tuple[dict[str, bytes], tuple[threading.Thread, ...]]:
    captured: dict[str, bytes] = {"stdout": b"", "stderr": b""}
    readers = tuple(
        threading.Thread(
            target=_read_stream,
            args=(stream, captured, name),
            name=f"stm32-toolkit-doctor-{name}",
            daemon=True,
        )
        for name, stream in (("stdout", process.stdout), ("stderr", process.stderr))
        if stream is not None
    )
    for reader in readers:
        reader.start()
    return captured, readers


def _read_stream(stream: BinaryIO, captured: dict[str, bytes], name: str) -> None:
    try:
        captured[name] = _drain_stream(stream)
    except (OSError, ValueError):
        captured[name] = b""
    finally:
        _close_stream(stream)


def _drain_stream(stream: BinaryIO) -> bytes:
    retained = bytearray()
    while True:
        chunk = stream.read(_STREAM_READ_BYTES)
        if not chunk:
            break
        available = _VERSION_CAPTURE_LIMIT - len(retained)
        if available > 0:
            retained.extend(chunk[:available])
    return bytes(retained)


def _terminate_and_reap(process: subprocess.Popen[bytes]) -> None:
    try:
        process.terminate()
    except OSError:
        pass
    try:
        process.wait(timeout=_REAP_TIMEOUT_SECONDS)
        return
    except subprocess.TimeoutExpired:
        pass
    except OSError:
        return

    try:
        process.kill()
    except OSError:
        pass
    try:
        process.wait(timeout=_REAP_TIMEOUT_SECONDS)
    except (OSError, subprocess.TimeoutExpired):
        pass


def _join_readers(readers: tuple[threading.Thread, ...]) -> None:
    for reader in readers:
        reader.join(timeout=_READER_JOIN_TIMEOUT_SECONDS)


def _close_finished_streams(
    process: subprocess.Popen[bytes], readers: tuple[threading.Thread, ...]
) -> None:
    for stream, reader in zip((process.stdout, process.stderr), readers):
        if not reader.is_alive():
            _close_stream(stream)


def _close_stream(stream: BinaryIO | None) -> None:
    if stream is None:
        return
    try:
        stream.close()
    except OSError:
        pass


def _decode_output(output: bytes) -> str:
    return output.decode("utf-8", errors="replace")


def _tool_result(
    available: bool,
    executable: str | None,
    status: str,
    return_code: int | None,
    version: str | None,
) -> dict[str, object]:
    return {
        "available": available,
        "path": executable,
        "status": status,
        "returnCode": return_code,
        "version": version,
    }


def _version_line(output: str | None) -> str | None:
    if not isinstance(output, str):
        return None
    for line in output.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped[:_VERSION_LINE_LIMIT]
    return None
