from __future__ import annotations

import platform
import shutil
import subprocess
import sys
from pathlib import Path

from stm32_toolkit.detection import detect_project
from stm32_toolkit.result import OperationResult


TOOLS = (
    "arm-none-eabi-gcc",
    "arm-none-eabi-gdb",
    "cmake",
    "ninja",
    "pyocd",
    "STM32CubeMX",
    "code",
)
_VERSION_TIMEOUT_SECONDS = 5
_VERSION_LINE_LIMIT = 512


def run_doctor(project_root: Path) -> OperationResult[dict[str, object]]:
    """Collect offline, read-only evidence about the local toolkit environment."""
    return OperationResult.success(
        "doctor",
        {
            "platform": _platform_evidence(),
            "project": _project_evidence(project_root),
            "tools": {name: _tool_evidence(name) for name in TOOLS},
            "mutated": False,
        },
    )


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
    except (OSError, ValueError):
        return {
            "kind": "unknown",
            "files": [],
            "recommended_skill": "/create-stm32-project",
        }


def _tool_evidence(name: str) -> dict[str, object]:
    try:
        executable = shutil.which(name)
    except OSError:
        executable = None

    if executable is None:
        return _tool_result(False, None, "missing", None, None)

    try:
        completed = subprocess.run(
            (executable, "--version"),
            capture_output=True,
            check=False,
            shell=False,
            text=True,
            timeout=_VERSION_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return _tool_result(True, executable, "timeout", None, None)
    except OSError:
        return _tool_result(True, executable, "error", None, None)

    version = _version_line(completed.stdout) or _version_line(completed.stderr)
    status = "ok" if completed.returncode == 0 else "nonzero"
    return _tool_result(True, executable, status, completed.returncode, version)


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
