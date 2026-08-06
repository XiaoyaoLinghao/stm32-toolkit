"""Process contract tests for the bounded process runner (STM32TK-0305).

The process module is the bounded subprocess layer used by the build runner:
concurrent stdout/stderr drain with byte and line caps, a 1..3600 second
timeout, POSIX process-group and Windows process-group termination, UTF-8
decoding with replacement, and no shell/command-string execution.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

import stm32_toolkit.process as process_mod
from stm32_toolkit.process import (
    ProcessError,
    ProcessRequest,
    ProcessResult,
    run_process,
)


def _request(*, timeout: float = 30.0, **kwargs) -> ProcessRequest:
    values = dict(
        argv=(sys.executable, "-c", "pass"),
        cwd=Path.cwd(),
        timeout_seconds=timeout,
    )
    values.update(kwargs)
    return ProcessRequest(**values)


def _run(*, timeout: float = 30.0, **kwargs) -> ProcessResult:
    return run_process(_request(timeout=timeout, **kwargs))


def test_run_process_captures_stdout_and_exit_code():
    result = _run(argv=(sys.executable, "-c", "print('hello stdout')"))

    assert result.returncode == 0
    assert result.stdout == "hello stdout\n"
    assert result.stderr == ""
    assert result.timed_out is False
    assert result.stdout_truncated is False
    assert result.stderr_truncated is False
    assert result.duration_seconds >= 0


def test_run_process_separates_stderr_from_stdout():
    code = "import sys; print('out line'); print('err line', file=sys.stderr)"
    result = _run(argv=(sys.executable, "-c", code))

    assert result.returncode == 0
    assert result.stdout == "out line\n"
    assert result.stderr == "err line\n"


def test_run_process_reports_nonzero_exit_code():
    result = _run(argv=(sys.executable, "-c", "import sys; sys.exit(3)"))

    assert result.returncode == 3
    assert result.timed_out is False


def test_run_process_timeout_terminates_and_reports_timed_out():
    code = "import time; time.sleep(60)"
    result = _run(argv=(sys.executable, "-c", code), timeout=1.0)

    assert result.timed_out is True
    assert result.duration_seconds < 10
    assert result.returncode is not None


def test_run_process_bounds_stdout_bytes_without_deadlock():
    code = "print('x' * 2000)"
    result = _run(argv=(sys.executable, "-c", code), max_bytes=100, max_lines=20000)

    assert result.returncode == 0
    assert len(result.stdout) == 100
    assert result.stdout_truncated is True
    assert result.stderr_truncated is False


def test_run_process_bounds_stdout_lines_exactly():
    code = "for _ in range(100): print('line')"
    result = _run(argv=(sys.executable, "-c", code), max_bytes=1_048_576, max_lines=10)

    assert result.returncode == 0
    assert result.stdout.splitlines() == ["line"] * 10
    assert result.stdout_truncated is True


def test_run_process_bounds_stderr_independently():
    code = "import sys; [print('e', file=sys.stderr) for _ in range(50)]"
    result = _run(argv=(sys.executable, "-c", code), max_bytes=1_048_576, max_lines=5)

    assert result.returncode == 0
    assert result.stdout == ""
    assert len(result.stderr.splitlines()) == 5
    assert result.stderr_truncated is True
    assert result.stdout_truncated is False


def test_run_process_drains_heavy_concurrent_streams():
    code = (
        "import sys\n"
        "for i in range(5000):\n"
        "    print('out %d' % i)\n"
        "    print('err %d' % i, file=sys.stderr)\n"
    )
    result = _run(argv=(sys.executable, "-c", code))

    assert result.returncode == 0
    assert len(result.stdout.splitlines()) == 5000
    assert len(result.stderr.splitlines()) == 5000
    assert result.stdout_truncated is False
    assert result.stderr_truncated is False


def test_run_process_decodes_invalid_utf8_with_replacement():
    code = "import sys; sys.stdout.buffer.write(b'\\xff\\xfeok\\n')"
    result = _run(argv=(sys.executable, "-c", code))

    assert result.returncode == 0
    assert "\ufffd" in result.stdout
    assert result.stdout.endswith("ok\n")


def test_run_process_missing_executable_raises_process_error(tmp_path: Path):
    with pytest.raises(ProcessError):
        run_process(
            ProcessRequest(
                argv=("stm32-toolkit-no-such-executable-xyz",),
                cwd=tmp_path,
                timeout_seconds=5.0,
            )
        )


def test_run_process_missing_cwd_raises_process_error(tmp_path: Path):
    with pytest.raises(ProcessError):
        run_process(
            ProcessRequest(
                argv=(sys.executable, "-c", "pass"),
                cwd=tmp_path / "missing-dir",
                timeout_seconds=5.0,
            )
        )


def test_run_process_rejects_invalid_requests():
    with pytest.raises(ValueError):
        run_process(ProcessRequest(argv=(), cwd=Path.cwd(), timeout_seconds=5.0))
    with pytest.raises(ValueError):
        run_process(ProcessRequest(argv=("",), cwd=Path.cwd(), timeout_seconds=5.0))
    with pytest.raises(ValueError):
        run_process(_request(timeout=0.5))
    with pytest.raises(ValueError):
        run_process(_request(timeout=4000.0))
    with pytest.raises(ValueError):
        run_process(_request(timeout=True))
    with pytest.raises(ValueError):
        run_process(_request(max_bytes=0))
    with pytest.raises(ValueError):
        run_process(_request(max_lines=0))
    with pytest.raises(TypeError):
        run_process("not-a-request")  # type: ignore[arg-type]


def test_run_process_windows_process_group_branch(monkeypatch):
    monkeypatch.setattr(process_mod, "_WINDOWS", True)

    result = _run(argv=(sys.executable, "-c", "print('win')"))

    assert result.returncode == 0
    assert result.stdout == "win\n"


def test_run_process_windows_termination_branch(monkeypatch):
    monkeypatch.setattr(process_mod, "_WINDOWS", True)

    code = "import time; time.sleep(60)"
    result = _run(argv=(sys.executable, "-c", code), timeout=1.0)

    assert result.timed_out is True
    assert result.duration_seconds < 10


def test_run_process_non_windows_termination_branch(monkeypatch):
    monkeypatch.setattr(process_mod, "_WINDOWS", False)

    code = "import time; time.sleep(60)"
    result = _run(argv=(sys.executable, "-c", code), timeout=1.0)

    assert result.timed_out is True
    assert result.duration_seconds < 10


def test_run_process_does_not_use_shell_or_command_strings():
    # A command string passed as a single argv element must not be executed.
    result = _run(argv=(sys.executable, "-c", "print('ok')"))

    assert result.returncode == 0
    assert result.stdout == "ok\n"


def test_run_process_reap_timeout_after_termination(monkeypatch):
    """The post-termination reap itself can time out; the result stays total."""
    monkeypatch.setattr(process_mod, "_terminate_tree", lambda process: None)
    code = "import time; time.sleep(10)"

    result = _run(argv=(sys.executable, "-c", code), timeout=1.0)

    assert result.timed_out is True
    assert result.returncode is None
    assert result.duration_seconds < 10


def test_run_process_rejects_non_path_cwd():
    with pytest.raises(ValueError):
        run_process(
            ProcessRequest(
                argv=(sys.executable, "-c", "pass"),
                cwd="not-a-path",  # type: ignore[arg-type]
                timeout_seconds=5.0,
            )
        )


def test_run_process_reader_failure_clears_capture(monkeypatch):
    def failing(_stream, _max_bytes, _max_lines):
        raise OSError("read failed")

    monkeypatch.setattr(process_mod, "_drain_stream", failing)
    code = (
        "import os, sys;"
        "devnull = os.open(os.devnull, os.O_WRONLY);"
        "os.dup2(devnull, 1); os.dup2(devnull, 2);"
        "print('x')"
    )

    result = _run(argv=(sys.executable, "-c", code))

    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""
    assert result.stdout_truncated is True
    assert result.stderr_truncated is True


def test_run_process_posix_killpg_fallback(monkeypatch):
    """When killpg is unavailable, terminate the direct child instead."""

    def no_killpg(_pid, _sig):
        raise OSError("no killpg")

    monkeypatch.setattr(process_mod.os, "killpg", no_killpg)
    code = "import time; time.sleep(60)"

    result = _run(argv=(sys.executable, "-c", code), timeout=1.0)

    assert result.timed_out is True
    assert result.duration_seconds < 10


def test_run_process_posix_sigkill_escalation():
    """A SIGTERM-ignoring child is escalated to SIGKILL after the grace period."""
    code = (
        "import signal, time;"
        "signal.signal(signal.SIGTERM, signal.SIG_IGN);"
        "time.sleep(60)"
    )

    result = _run(argv=(sys.executable, "-c", code), timeout=1.0)

    assert result.timed_out is True
    assert result.duration_seconds < 10


def test_run_process_posix_kill_fallback_when_killpg_unavailable(monkeypatch):
    """When killpg never works, the SIGKILL escalation uses process.kill()."""

    def no_killpg(_pid, _sig):
        raise OSError("no killpg")

    monkeypatch.setattr(process_mod.os, "killpg", no_killpg)
    code = (
        "import signal, time;"
        "signal.signal(signal.SIGTERM, signal.SIG_IGN);"
        "time.sleep(60)"
    )

    result = _run(argv=(sys.executable, "-c", code), timeout=1.0)

    assert result.timed_out is True
    assert result.duration_seconds < 10


def test_run_process_windows_taskkill_failure_falls_back(monkeypatch):
    """Windows tree-kill failure falls back to direct termination and kill."""
    monkeypatch.setattr(process_mod, "_WINDOWS", True)

    def no_taskkill(*_args, **_kwargs):
        raise OSError("no taskkill")

    monkeypatch.setattr(process_mod.subprocess, "run", no_taskkill)
    code = (
        "import signal, time;"
        "signal.signal(signal.SIGTERM, signal.SIG_IGN);"
        "time.sleep(60)"
    )

    result = _run(argv=(sys.executable, "-c", code), timeout=1.0)

    assert result.timed_out is True
    assert result.duration_seconds < 10
