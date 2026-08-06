from __future__ import annotations

import platform
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from typing import BinaryIO

from stm32_toolkit.detection import detect_project, planned_action
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

#: The exact three recommended VS Code extensions (STM32TK-0304).
VSCODE_EXTENSIONS = (
    "ms-vscode.cpptools",
    "ms-vscode.cmake-tools",
    "marus25.cortex-debug",
)
_VERSION_TIMEOUT_SECONDS = 5
_REAP_TIMEOUT_SECONDS = 1
_READER_JOIN_TIMEOUT_SECONDS = 0.1
_VERSION_CAPTURE_LIMIT = 8 * 1024
_STREAM_READ_BYTES = 4 * 1024
_VERSION_LINE_LIMIT = 512


def run_doctor(project_root: Path) -> OperationResult[dict[str, object]]:
    """Collect offline, read-only evidence about the local toolkit environment."""
    return OperationResult.success(
        "doctor",
        {
            "platform": _platform_evidence(),
            "project": _project_evidence(project_root),
            "tools": {name: _tool_evidence(name) for name in TOOLS},
            "vscodeExtensions": _vscode_extension_evidence(),
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
            "recommended_action": planned_action("create-project").to_dict(),
        }


def _tool_evidence(name: str) -> dict[str, object]:
    try:
        executable = shutil.which(name)
    except OSError:
        executable = None

    if executable is None:
        return _tool_result(False, None, "missing", None, None)

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


def _extension_evidence(
    installed: bool, version: str | None, status: str
) -> dict[str, object]:
    return {"installed": installed, "version": version, "status": status}


def _vscode_extension_evidence() -> dict[str, dict[str, object]]:
    """Bounded, read-only evidence for the three recommended VS Code extensions.

    Invokes exactly ``[resolved_code, "--list-extensions", "--show-versions"]``
    through the existing bounded process machinery.  Missing ``code`` yields
    ``unavailable`` for all three; a failed probe never claims missing.
    """
    try:
        executable = shutil.which("code")
    except OSError:
        executable = None
    if executable is None:
        return {
            extension: _extension_evidence(False, None, "unavailable")
            for extension in VSCODE_EXTENSIONS
        }
    status, return_code, stdout, _stderr = _run_process(
        (executable, "--list-extensions", "--show-versions")
    )
    if status != "ok" or return_code != 0:
        failure = status if status != "ok" else "nonzero"
        return {
            extension: _extension_evidence(False, None, failure)
            for extension in VSCODE_EXTENSIONS
        }
    parsed = _parse_extension_lines(_decode_output(stdout))
    return {
        extension: (
            _extension_evidence(True, parsed[extension.casefold()], "ok")
            if extension.casefold() in parsed
            else _extension_evidence(False, None, "missing")
        )
        for extension in VSCODE_EXTENSIONS
    }


def _parse_extension_lines(output: str) -> dict[str, str]:
    """Parse ``publisher.extension@version`` lines case-insensitively.

    Malformed and unrelated lines are ignored; the retained output is already
    capped at 8 KiB by the bounded reader.
    """
    parsed: dict[str, str] = {}
    for line in output.splitlines():
        identifier, separator, version = line.strip().rpartition("@")
        if not separator or not identifier or not version:
            continue
        if "." not in identifier or any(ch.isspace() for ch in identifier):
            continue
        parsed[identifier.casefold()] = version
    return parsed


def _version_line(output: str | None) -> str | None:
    if not isinstance(output, str):
        return None
    for line in output.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped[:_VERSION_LINE_LIMIT]
    return None
