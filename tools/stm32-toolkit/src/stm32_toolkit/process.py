"""Bounded fixed-argv subprocess execution.

``run_process`` spawns an exact argv tuple without a shell, concurrently
drains stdout and stderr as bytes while the child runs, retains at most
``max_output_bytes`` and ``max_lines`` LF-delimited lines per stream
(discarding overflow while continuing to drain so a chatty child can never
deadlock the caller), decodes retained output as UTF-8 with replacement,
normalizes CRLF and bare CR to LF, and on timeout terminates only the
process group/tree created for this invocation and reaps it.

POSIX uses a new session/process group and ``killpg``; Windows uses
``CREATE_NEW_PROCESS_GROUP`` plus bounded ``taskkill /T`` child-tree
termination.  The platform switch and the termination callables are module
seams so the Windows branch is exercised with real child processes on any
host and no test ever touches ``os.killpg`` on Windows.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path

MIN_TIMEOUT_SECONDS = 1
MAX_TIMEOUT_SECONDS = 3600
MIN_OUTPUT_BYTES = 1024 * 1024
MAX_OUTPUT_BYTES = 8 * 1024 * 1024
DEFAULT_OUTPUT_BYTES = 1024 * 1024
DEFAULT_MAX_LINES = 20000
_GRACE_SECONDS = 2.0
_REAP_SECONDS = 2.0
_CREATE_NEW_PROCESS_GROUP = 0x00000200


class ProcessError(Exception):
    """A stable process launch failure carrying a bounded rule."""

    def __init__(self, rule: str, message: str) -> None:
        super().__init__(message)
        self.rule = rule
        self.message = message


def process_error(rule: str, message: str) -> ProcessError:
    return ProcessError(rule, message)


@dataclass(frozen=True)
class ProcessRequest:
    """A fixed-argv process invocation with hard output bounds."""

    argv: tuple[str, ...]
    cwd: Path
    timeout_seconds: int
    max_output_bytes: int = DEFAULT_OUTPUT_BYTES
    max_lines: int = DEFAULT_MAX_LINES

    def __post_init__(self) -> None:
        if not isinstance(self.argv, tuple) or not self.argv:
            raise ValueError("argv must be a non-empty tuple")
        if not all(isinstance(item, str) for item in self.argv):
            raise ValueError("argv entries must be strings")
        if type(self.cwd) is not Path and not isinstance(self.cwd, Path):
            raise ValueError("cwd must be an existing directory Path")
        if not self.cwd.is_dir():
            raise ValueError("cwd must be an existing directory Path")
        if type(self.timeout_seconds) is not int:
            raise ValueError("timeout_seconds must be an integer")
        if not MIN_TIMEOUT_SECONDS <= self.timeout_seconds <= MAX_TIMEOUT_SECONDS:
            raise ValueError("timeout_seconds must be in 1..3600")
        if (
            type(self.max_output_bytes) is not int
            or not MIN_OUTPUT_BYTES <= self.max_output_bytes <= MAX_OUTPUT_BYTES
        ):
            raise ValueError("max_output_bytes must be an integer in 1..8 MiB")
        if type(self.max_lines) is not int or self.max_lines < 1:
            raise ValueError("max_lines must be a positive integer")


@dataclass(frozen=True)
class ProcessResult:
    """A completed bounded process result with normalized LF text output."""

    returncode: int
    stdout: str
    stderr: str
    timed_out: bool
    duration_ms: int
    stdout_truncated: bool
    stderr_truncated: bool


# ---------------------------------------------------------------------------
# platform seams (tests inject these; Windows branch never touches killpg)
# ---------------------------------------------------------------------------

_is_windows: bool = sys.platform == "win32"


def _default_terminate_group(pid: int) -> None:
    os.killpg(pid, signal.SIGTERM)


def _default_kill_group(pid: int) -> None:
    os.killpg(pid, signal.SIGKILL)


def _default_windows_graceful(pid: int) -> None:
    os.kill(pid, signal.CTRL_BREAK_EVENT)


def _default_windows_taskkill(pid: int) -> bool:
    """Terminate the child tree on Windows; returns False when it fails."""
    try:
        completed = subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return completed.returncode == 0


_terminate_group = _default_terminate_group
_kill_group = _default_kill_group
_windows_graceful = _default_windows_graceful
_taskkill = _default_windows_taskkill


# ---------------------------------------------------------------------------
# bounded output sink
# ---------------------------------------------------------------------------


class _OutputSink:
    """Retain at most ``max_bytes`` and ``max_lines``; discard the overflow."""

    def __init__(self, max_bytes: int, max_lines: int) -> None:
        self._max_bytes = max_bytes
        self._max_lines = max_lines
        self._data = bytearray()
        self._newlines = 0
        self._truncated = False
        self._discarded = 0

    def append(self, chunk: bytes) -> None:
        if self._truncated:
            self._discarded += len(chunk)
            return
        if not chunk:
            return
        byte_room = self._max_bytes - len(self._data)
        line_room = self._max_lines - self._newlines
        if len(chunk) <= byte_room and chunk.count(b"\n") <= line_room:
            self._data += chunk
            self._newlines += chunk.count(b"\n")
            return
        keep = byte_room
        if keep > 0:
            prefix = chunk[:keep]
            newlines = prefix.count(b"\n")
            if newlines > line_room:
                index = -1
                for _ in range(line_room):
                    index = prefix.find(b"\n", index + 1)
                keep = index + 1
            self._data += chunk[:keep]
            self._newlines += chunk[:keep].count(b"\n")
        self._truncated = True
        self._discarded += len(chunk) - keep

    def text(self) -> str:
        return _normalize_newlines(self._data.decode("utf-8", errors="replace"))

    @property
    def truncated(self) -> bool:
        return self._truncated


def _normalize_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _drain(stream, sink: _OutputSink) -> None:
    try:
        while True:
            chunk = stream.read(65536)
            if not chunk:
                break
            sink.append(chunk)
    finally:
        try:
            stream.close()
        except OSError:
            pass


# ---------------------------------------------------------------------------
# execution
# ---------------------------------------------------------------------------


def run_process(request: ProcessRequest) -> ProcessResult:
    """Run the exact fixed argv with bounded, concurrently drained output."""
    if type(request) is not ProcessRequest:
        raise TypeError("request must be a ProcessRequest")
    started = time.monotonic()
    process = None
    stdout_sink = _OutputSink(request.max_output_bytes, request.max_lines)
    stderr_sink = _OutputSink(request.max_output_bytes, request.max_lines)
    threads: list[threading.Thread] = []
    timed_out = False
    try:
        kwargs: dict[str, object] = {
            "args": request.argv,
            "cwd": str(request.cwd),
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "shell": False,
        }
        if _is_windows:
            kwargs["creationflags"] = _CREATE_NEW_PROCESS_GROUP
        else:
            kwargs["start_new_session"] = True
        process = subprocess.Popen(**kwargs)
        threads.append(threading.Thread(target=_drain, args=(process.stdout, stdout_sink), daemon=True))
        threads.append(threading.Thread(target=_drain, args=(process.stderr, stderr_sink), daemon=True))
        for thread in threads:
            thread.start()
        try:
            process.wait(timeout=request.timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            _terminate_tree(process)
    except OSError as error:
        raise process_error(
            "launch", "process could not be launched"
        ) from error
    finally:
        for thread in threads:
            thread.join(timeout=2.0)
        if process is not None:
            try:
                process.stdout.close()
            except OSError:
                pass
            try:
                process.stderr.close()
            except OSError:
                pass
    returncode = process.returncode if process is not None else -1
    if returncode is None:
        try:
            returncode = process.wait(timeout=_REAP_SECONDS)
        except subprocess.TimeoutExpired:
            returncode = -1
    duration_ms = int((time.monotonic() - started) * 1000)
    return ProcessResult(
        returncode=returncode,
        stdout=stdout_sink.text(),
        stderr=stderr_sink.text(),
        timed_out=timed_out,
        duration_ms=duration_ms,
        stdout_truncated=stdout_sink.truncated,
        stderr_truncated=stderr_sink.truncated,
    )


def _terminate_tree(process: subprocess.Popen) -> None:
    """Terminate only this invocation's tree, wait, force-kill, and reap."""
    pid = process.pid
    if _is_windows:
        try:
            _windows_graceful(pid)
        except OSError:
            pass
        try:
            process.wait(timeout=_GRACE_SECONDS)
            return
        except subprocess.TimeoutExpired:
            pass
        if not _taskkill(pid):
            try:
                process.kill()
            except OSError:
                pass
    else:
        try:
            _terminate_group(pid)
        except OSError:
            pass
        try:
            process.wait(timeout=_GRACE_SECONDS)
            return
        except subprocess.TimeoutExpired:
            pass
        try:
            _kill_group(pid)
        except OSError:
            pass
    try:
        process.wait(timeout=_REAP_SECONDS)
    except subprocess.TimeoutExpired:
        pass
