"""Bounded subprocess execution for the toolkit build pipeline (STM32TK-0305).

The process layer never uses a shell or command strings.  Every request runs
one exact argv list with concurrent bounded stdout/stderr draining (byte and
line caps per stream), a 1..3600 second timeout, and deterministic
termination: a new session/process group on POSIX and
``CREATE_NEW_PROCESS_GROUP`` plus ``taskkill /T`` child-tree termination on
Windows.  Captured text is decoded as UTF-8 with replacement and never with
the platform default encoding.
"""

from __future__ import annotations

import os
import signal
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

#: Simulated platform switch so the Windows branches are unit-testable on any
#: host; the real Windows process-group behavior remains a Codex gate.
_WINDOWS = os.name == "nt"

#: Accepted timeout range in seconds.
MIN_TIMEOUT_SECONDS = 1.0
MAX_TIMEOUT_SECONDS = 3600.0

#: Default per-stream capture bounds (1 MiB and 20,000 lines).
DEFAULT_MAX_BYTES = 1_048_576
DEFAULT_MAX_LINES = 20_000

_STREAM_READ_BYTES = 64 * 1024
_TERMINATE_GRACE_SECONDS = 2.0
_REAP_TIMEOUT_SECONDS = 5.0
_READER_JOIN_TIMEOUT_SECONDS = 1.0


class ProcessError(Exception):
    """A deterministic subprocess start failure (for example a missing executable)."""


@dataclass(frozen=True)
class ProcessRequest:
    """One bounded process invocation."""

    argv: tuple[str, ...]
    cwd: Path
    timeout_seconds: float
    max_bytes: int = DEFAULT_MAX_BYTES
    max_lines: int = DEFAULT_MAX_LINES


@dataclass(frozen=True)
class ProcessResult:
    """Captured evidence for one process invocation."""

    returncode: int | None
    stdout: str
    stderr: str
    timed_out: bool
    duration_seconds: float
    stdout_truncated: bool = False
    stderr_truncated: bool = False


def run_process(request: ProcessRequest) -> ProcessResult:
    """Run one bounded argv list and return its captured evidence.

    Raises :class:`ValueError` for invalid requests and :class:`ProcessError`
    when the executable cannot be started.  On timeout the whole child
    process tree is terminated; the returned result is marked ``timed_out``.
    """
    _validate_request(request)
    creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) if _WINDOWS else 0
    try:
        process = subprocess.Popen(
            request.argv,
            cwd=str(request.cwd),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            start_new_session=not _WINDOWS,
            creationflags=creationflags,
        )
    except OSError as error:
        raise ProcessError("Executable could not be started") from error

    captured, readers = _start_readers(process, request)
    started = time.monotonic()
    timed_out = False
    try:
        returncode = process.wait(timeout=request.timeout_seconds)
    except subprocess.TimeoutExpired:
        timed_out = True
        returncode = None
        _terminate_tree(process)
        try:
            process.wait(timeout=_REAP_TIMEOUT_SECONDS)
            returncode = process.returncode
        except subprocess.TimeoutExpired:
            pass
    _join_readers(readers)
    duration_seconds = time.monotonic() - started
    return ProcessResult(
        returncode=returncode,
        stdout=_decode(captured["stdout"]["data"]),
        stderr=_decode(captured["stderr"]["data"]),
        timed_out=timed_out,
        duration_seconds=duration_seconds,
        stdout_truncated=captured["stdout"]["truncated"],
        stderr_truncated=captured["stderr"]["truncated"],
    )


def _validate_request(request: ProcessRequest) -> None:
    if not isinstance(request, ProcessRequest):
        raise TypeError("request must be a ProcessRequest")
    if not isinstance(request.argv, tuple) or not request.argv or any(
        not isinstance(argument, str) or not argument for argument in request.argv
    ):
        raise ValueError("argv must be a non-empty tuple of non-empty strings")
    if not isinstance(request.timeout_seconds, (int, float)) or isinstance(
        request.timeout_seconds, bool
    ):
        raise ValueError("timeout_seconds must be a number")
    if not (MIN_TIMEOUT_SECONDS <= request.timeout_seconds <= MAX_TIMEOUT_SECONDS):
        raise ValueError("timeout_seconds must be between 1 and 3600 seconds")
    if not isinstance(request.max_bytes, int) or request.max_bytes < 1:
        raise ValueError("max_bytes must be a positive integer")
    if not isinstance(request.max_lines, int) or request.max_lines < 1:
        raise ValueError("max_lines must be a positive integer")
    if not isinstance(request.cwd, Path):
        raise ValueError("cwd must be a pathlib.Path")


def _start_readers(
    process: subprocess.Popen[bytes], request: ProcessRequest
) -> tuple[dict[str, dict[str, object]], tuple[threading.Thread, ...]]:
    captured = {
        "stdout": {"data": bytearray(), "truncated": False},
        "stderr": {"data": bytearray(), "truncated": False},
    }
    readers = tuple(
        threading.Thread(
            target=_read_stream,
            args=(stream, captured[name], request.max_bytes, request.max_lines),
            name=f"stm32-toolkit-process-{name}",
            daemon=True,
        )
        for name, stream in (("stdout", process.stdout), ("stderr", process.stderr))
        if stream is not None
    )
    for reader in readers:
        reader.start()
    return captured, readers


def _read_stream(
    stream: BinaryIO,
    state: dict[str, object],
    max_bytes: int,
    max_lines: int,
) -> None:
    try:
        data, truncated = _drain_stream(stream, max_bytes, max_lines)
        state["data"] = data
        state["truncated"] = truncated
    except (OSError, ValueError):
        state["data"] = bytearray()
        state["truncated"] = True
    finally:
        try:
            stream.close()
        except OSError:
            pass


def _drain_stream(stream: BinaryIO, max_bytes: int, max_lines: int) -> tuple[bytes, bool]:
    """Read one stream up to the byte/line caps, then keep draining to EOF.

    Retained bytes never exceed ``max_bytes`` and retained lines never exceed
    ``max_lines``; once a cap is hit the remaining pipe is still consumed so
    the child never blocks on a full pipe buffer.
    """
    retained = bytearray()
    truncated = False
    while True:
        chunk = stream.read(_STREAM_READ_BYTES)
        if not chunk:
            break
        remaining_bytes = max_bytes - len(retained)
        if remaining_bytes <= 0:
            truncated = True
            continue
        retained.extend(chunk[:remaining_bytes])
        if len(retained) >= max_bytes:
            truncated = True
            continue
        newline_count = retained.count(b"\n")
        if newline_count >= max_lines:
            index = -1
            for _ in range(max_lines):
                index = retained.find(b"\n", index + 1)
            del retained[index + 1:]
            truncated = True
    return bytes(retained), truncated


def _terminate_tree(process: subprocess.Popen[bytes]) -> None:
    if _WINDOWS:
        _terminate_windows(process)
    else:
        _terminate_posix(process)


def _terminate_posix(process: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(os.getpgid(process.pid), signal.SIGTERM)
    except OSError:
        try:
            process.terminate()
        except OSError:
            pass
    try:
        process.wait(timeout=_TERMINATE_GRACE_SECONDS)
        return
    except subprocess.TimeoutExpired:
        pass
    except OSError:
        return
    try:
        os.killpg(os.getpgid(process.pid), signal.SIGKILL)
    except OSError:
        try:
            process.kill()
        except OSError:
            pass
    try:
        process.wait(timeout=_REAP_TIMEOUT_SECONDS)
    except (OSError, subprocess.TimeoutExpired):
        pass


def _terminate_windows(process: subprocess.Popen[bytes]) -> None:
    try:
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=_REAP_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired):
        try:
            process.terminate()
        except OSError:
            pass
    try:
        process.wait(timeout=_TERMINATE_GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        try:
            process.kill()
        except OSError:
            pass
    except OSError:
        pass


def _join_readers(readers: tuple[threading.Thread, ...]) -> None:
    for reader in readers:
        reader.join(timeout=_READER_JOIN_TIMEOUT_SECONDS)


def _decode(data: object) -> str:
    return bytes(data).decode("utf-8", errors="replace")
