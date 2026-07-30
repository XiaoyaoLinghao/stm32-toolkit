from __future__ import annotations

import platform
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from typing import BinaryIO

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
_REAP_TIMEOUT_SECONDS = 1
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
        process = subprocess.Popen(
            (executable, "--version"),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
        )
    except OSError:
        return _tool_result(True, executable, "error", None, None)

    captured, readers = _start_readers(process)
    try:
        return_code = process.wait(timeout=_VERSION_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        _terminate_and_reap(process)
        _close_streams(process)
        _join_readers(readers)
        return _tool_result(True, executable, "timeout", None, None)
    except OSError:
        _terminate_and_reap(process)
        _close_streams(process)
        _join_readers(readers)
        return _tool_result(True, executable, "error", None, None)

    _join_readers(readers)
    _close_streams(process)
    version = _version_line(_decode_output(captured["stdout"]))
    if version is None:
        version = _version_line(_decode_output(captured["stderr"]))
    status = "ok" if return_code == 0 else "nonzero"
    return _tool_result(True, executable, status, return_code, version)


def _start_readers(process: subprocess.Popen[bytes]) -> tuple[dict[str, bytes], tuple[threading.Thread, ...]]:
    captured: dict[str, bytes] = {"stdout": b"", "stderr": b""}
    readers = tuple(
        threading.Thread(
            target=_read_stream,
            args=(stream, captured, name),
            name=f"stm32-toolkit-doctor-{name}",
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
        process.wait()
    except OSError:
        pass


def _join_readers(readers: tuple[threading.Thread, ...]) -> None:
    for reader in readers:
        reader.join()


def _close_streams(process: subprocess.Popen[bytes]) -> None:
    _close_stream(process.stdout)
    _close_stream(process.stderr)


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
