"""Bounded fixed-argv subprocess execution contracts.

POSIX-only ``killpg``/``fcntl`` behavior is exercised through injected
callable seams; the Windows ``_is_windows`` branch is exercised with real
child processes on any host through the same seams, so no test touches
``os.killpg`` on Windows and no test is skipped or xfailed.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

import stm32_toolkit.process as process_mod
from stm32_toolkit.process import ProcessError, ProcessRequest, ProcessResult, run_process

PYTHON = sys.executable


def write_pid_child(pid_file: Path, code: str = "import time; time.sleep(60)") -> list[str]:
    return [
        PYTHON,
        "-c",
        f"import os; open({str(pid_file)!r}, 'w').write(str(os.getpid())); {code}",
    ]


# ---------------------------------------------------------------------------
# request validation
# ---------------------------------------------------------------------------


def test_run_process_rejects_non_request():
    with pytest.raises(TypeError):
        run_process("nope")  # type: ignore[arg-type]


def test_request_rejects_empty_or_invalid_argv(tmp_path: Path):
    with pytest.raises(ValueError):
        ProcessRequest(argv=(), cwd=tmp_path, timeout_seconds=30)
    with pytest.raises(ValueError):
        ProcessRequest(argv=("echo", 3), cwd=tmp_path, timeout_seconds=30)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        ProcessRequest(argv=("echo",), cwd=tmp_path, timeout_seconds=0)
    with pytest.raises(ValueError):
        ProcessRequest(argv=("echo",), cwd=tmp_path, timeout_seconds=3601)
    with pytest.raises(ValueError):
        ProcessRequest(argv=("echo",), cwd=tmp_path, timeout_seconds=30, max_output_bytes=0)
    with pytest.raises(ValueError):
        ProcessRequest(argv=("echo",), cwd=tmp_path, timeout_seconds=30, max_output_bytes=9 * 1024 * 1024)
    with pytest.raises(ValueError):
        ProcessRequest(argv=("echo",), cwd=tmp_path, timeout_seconds=30, max_lines=0)


def test_request_rejects_bool_timeout_and_non_path_cwd(tmp_path: Path):
    with pytest.raises(ValueError):
        ProcessRequest(argv=("echo",), cwd=tmp_path, timeout_seconds=True)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        ProcessRequest(argv=("echo",), cwd="not-a-path", timeout_seconds=30)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        ProcessRequest(argv=("echo",), cwd=tmp_path / "missing", timeout_seconds=30)


def test_request_is_frozen():
    request = ProcessRequest(argv=("echo",), cwd=Path("."), timeout_seconds=30)
    with pytest.raises(FrozenInstanceError):
        request.argv = ()  # type: ignore[misc]


# ---------------------------------------------------------------------------
# basic execution
# ---------------------------------------------------------------------------


def test_run_process_echo(tmp_path: Path):
    result = run_process(
        ProcessRequest(argv=(PYTHON, "-c", "print('hello')"), cwd=tmp_path, timeout_seconds=30)
    )
    assert result.returncode == 0
    assert result.stdout == "hello\n"
    assert result.stderr == ""
    assert result.timed_out is False
    assert result.stdout_truncated is False
    assert result.stderr_truncated is False
    assert isinstance(result.duration_ms, int)
    assert result.duration_ms >= 0


def test_run_process_stderr_and_nonzero_exit(tmp_path: Path):
    result = run_process(
        ProcessRequest(argv=(PYTHON, "-c", "import sys; sys.stderr.write('bad'); sys.exit(3)"), cwd=tmp_path, timeout_seconds=30)
    )
    assert result.returncode == 3
    assert result.stdout == ""
    assert result.stderr == "bad"


def test_run_process_stdin_is_disconnected(tmp_path: Path):
    result = run_process(
        ProcessRequest(
            argv=(PYTHON, "-c", "import sys; print(repr(sys.stdin.read()))"),
            cwd=tmp_path,
            timeout_seconds=30,
        )
    )
    assert result.stdout == "''\n"


def test_run_process_uses_fixed_argv_without_a_shell(tmp_path: Path):
    argv = (PYTHON, "-c", "import sys; print(repr(sys.argv[1:]))", "a;b", "$HOME", "`x`")
    result = run_process(ProcessRequest(argv=argv, cwd=tmp_path, timeout_seconds=30))
    assert result.returncode == 0
    assert result.stdout == "['a;b', '$HOME', '`x`']\n"


def test_run_process_launch_failure(tmp_path: Path):
    with pytest.raises(ProcessError) as error:
        run_process(
            ProcessRequest(argv=("stm32tk-no-such-binary-xyz",), cwd=tmp_path, timeout_seconds=30)
        )
    assert error.value.rule == "launch"


def test_process_result_is_frozen(tmp_path: Path):
    result = run_process(
        ProcessRequest(argv=(PYTHON, "-c", "pass"), cwd=tmp_path, timeout_seconds=30)
    )
    with pytest.raises(FrozenInstanceError):
        result.stdout = "x"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# bounded concurrent draining and normalization
# ---------------------------------------------------------------------------


def test_concurrent_flood_of_both_streams_is_bounded_without_deadlock(tmp_path: Path):
    code = (
        "import sys, threading\n"
        "def pump(stream):\n"
        "    for _ in range(40000):\n"
        "        stream.write('x' * 80 + '\\n')\n"
        "    stream.flush()\n"
        "a = threading.Thread(target=pump, args=(sys.stdout,))\n"
        "b = threading.Thread(target=pump, args=(sys.stderr,))\n"
        "a.start(); b.start(); a.join(); b.join()\n"
    )
    result = run_process(
        ProcessRequest(argv=(PYTHON, "-c", code), cwd=tmp_path, timeout_seconds=60)
    )
    assert result.returncode == 0
    assert result.stdout_truncated is True
    assert result.stderr_truncated is True
    assert len(result.stdout.encode("utf-8")) <= 1024 * 1024
    assert len(result.stderr.encode("utf-8")) <= 1024 * 1024
    assert result.stdout.count("\n") <= 20000
    assert result.stderr.count("\n") <= 20000


def test_line_cap_cuts_at_the_nth_newline(tmp_path: Path):
    code = "import sys\n" + "sys.stdout.write('a\\n')" * 40000 + "\n"
    result = run_process(
        ProcessRequest(argv=(PYTHON, "-c", code), cwd=tmp_path, timeout_seconds=60)
    )
    assert result.stdout_truncated is True
    assert result.stdout.count("\n") == 20000
    assert result.stdout == "a\n" * 20000


def test_byte_cap_truncates_deterministically(tmp_path: Path):
    code = "import sys\nsys.stdout.write('x' * (2 * 1024 * 1024))\n"
    result = run_process(
        ProcessRequest(argv=(PYTHON, "-c", code), cwd=tmp_path, timeout_seconds=60)
    )
    assert result.stdout_truncated is True
    assert len(result.stdout.encode("utf-8")) == 1024 * 1024


def test_invalid_utf8_is_decoded_with_replacement(tmp_path: Path):
    code = "import sys\nsys.stdout.buffer.write(b'\\xff\\xfeok')\n"
    result = run_process(
        ProcessRequest(argv=(PYTHON, "-c", code), cwd=tmp_path, timeout_seconds=30)
    )
    assert result.stdout == "\ufffd\ufffdok"


def test_crlf_and_bare_cr_are_normalized_to_lf(tmp_path: Path):
    code = "import sys\nsys.stdout.write('a\\r\\nb\\rc\\n')\n"
    result = run_process(
        ProcessRequest(argv=(PYTHON, "-c", code), cwd=tmp_path, timeout_seconds=30)
    )
    assert result.stdout == "a\nb\nc\n"
    assert "\r" not in result.stdout


# ---------------------------------------------------------------------------
# timeout, process-group termination, reaping
# ---------------------------------------------------------------------------


def test_timeout_terminates_and_reaps_the_child(tmp_path: Path):
    pid_file = tmp_path / "child.pid"
    argv = write_pid_child(pid_file)
    result = run_process(ProcessRequest(argv=argv, cwd=tmp_path, timeout_seconds=1))
    assert result.timed_out is True
    pid = int(pid_file.read_text(encoding="utf-8"))
    with pytest.raises(ProcessLookupError):
        os.killpg(pid, 0)
    assert result.returncode is not None


def test_timeout_kills_the_whole_process_tree(tmp_path: Path):
    pid_file = tmp_path / "child.pid"
    grand_pid_file = tmp_path / "grand.pid"
    code = (
        "import os, subprocess, sys, time\n"
        f"p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
        f"open({str(grand_pid_file)!r}, 'w').write(str(p.pid))\n"
        f"open({str(pid_file)!r}, 'w').write(str(os.getpid()))\n"
        "time.sleep(60)\n"
    )
    result = run_process(
        ProcessRequest(argv=(PYTHON, "-c", code), cwd=tmp_path, timeout_seconds=1)
    )
    assert result.timed_out is True
    pid = int(pid_file.read_text(encoding="utf-8"))
    grand_pid = int(grand_pid_file.read_text(encoding="utf-8"))
    with pytest.raises(ProcessLookupError):
        os.killpg(pid, 0)
    with pytest.raises(ProcessLookupError):
        os.kill(grand_pid, 0)


def test_timeout_uses_graceful_then_force_termination_seams(tmp_path: Path, monkeypatch):
    pid_file = tmp_path / "child.pid"
    argv = write_pid_child(pid_file)
    terminated: list[int] = []
    killed: list[int] = []
    monkeypatch.setattr(process_mod, "_terminate_group", lambda pid: terminated.append(pid))
    monkeypatch.setattr(process_mod, "_kill_group", lambda pid: killed.append(pid))
    result = run_process(ProcessRequest(argv=argv, cwd=tmp_path, timeout_seconds=1))
    assert result.timed_out is True
    pid = int(pid_file.read_text(encoding="utf-8"))
    assert terminated == [pid]
    assert killed == [pid]
    with pytest.raises(ProcessLookupError):
        os.killpg(pid, 0)


def test_timeout_success_path_never_calls_termination_seams(tmp_path: Path, monkeypatch):
    called: list[str] = []
    monkeypatch.setattr(process_mod, "_terminate_group", lambda pid: called.append("term"))
    monkeypatch.setattr(process_mod, "_kill_group", lambda pid: called.append("kill"))
    result = run_process(
        ProcessRequest(argv=(PYTHON, "-c", "pass"), cwd=tmp_path, timeout_seconds=30)
    )
    assert result.timed_out is False
    assert called == []


def test_windows_branch_uses_taskkill_seam(tmp_path: Path, monkeypatch):
    pid_file = tmp_path / "child.pid"
    argv = write_pid_child(pid_file)
    taskkilled: list[int] = []
    monkeypatch.setattr(process_mod, "_is_windows", True)
    monkeypatch.setattr(process_mod, "_windows_graceful", lambda pid: None)
    monkeypatch.setattr(process_mod, "_taskkill", lambda pid: taskkilled.append(pid) or True)
    result = run_process(ProcessRequest(argv=argv, cwd=tmp_path, timeout_seconds=1))
    assert result.timed_out is True
    pid = int(pid_file.read_text(encoding="utf-8"))
    assert taskkilled == [pid]
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


def test_windows_branch_falls_back_to_kill_when_taskkill_fails(tmp_path: Path, monkeypatch):
    pid_file = tmp_path / "child.pid"
    argv = write_pid_child(pid_file)
    monkeypatch.setattr(process_mod, "_is_windows", True)
    monkeypatch.setattr(process_mod, "_windows_graceful", lambda pid: None)
    monkeypatch.setattr(process_mod, "_taskkill", lambda pid: False)
    result = run_process(ProcessRequest(argv=argv, cwd=tmp_path, timeout_seconds=1))
    assert result.timed_out is True
    pid = int(pid_file.read_text(encoding="utf-8"))
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


def test_windows_branch_uses_create_new_process_group_flag(tmp_path: Path, monkeypatch):
    captured: dict = {}
    real_popen = subprocess.Popen

    class SpyingPopen(real_popen):
        def __init__(self, *args, **kwargs):
            captured["creationflags"] = kwargs.get("creationflags", 0)
            captured["start_new_session"] = kwargs.get("start_new_session", False)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(process_mod, "subprocess", subprocess)
    monkeypatch.setattr(subprocess, "Popen", SpyingPopen)
    monkeypatch.setattr(process_mod, "_is_windows", True)
    result = run_process(
        ProcessRequest(argv=(PYTHON, "-c", "pass"), cwd=tmp_path, timeout_seconds=30)
    )
    assert result.returncode == 0
    assert captured["creationflags"] == 0x200  # CREATE_NEW_PROCESS_GROUP


def test_posix_branch_creates_a_new_session(tmp_path: Path, monkeypatch):
    captured: dict = {}
    real_popen = subprocess.Popen

    class SpyingPopen(real_popen):
        def __init__(self, *args, **kwargs):
            captured["start_new_session"] = kwargs.get("start_new_session", False)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(subprocess, "Popen", SpyingPopen)
    monkeypatch.setattr(process_mod, "_is_windows", False)
    result = run_process(
        ProcessRequest(argv=(PYTHON, "-c", "pass"), cwd=tmp_path, timeout_seconds=30)
    )
    assert result.returncode == 0
    assert captured["start_new_session"] is True


def test_windows_branch_graceful_signal_is_seam_injected(tmp_path: Path, monkeypatch):
    pid_file = tmp_path / "child.pid"
    argv = write_pid_child(pid_file)
    graceful: list[int] = []
    monkeypatch.setattr(process_mod, "_is_windows", True)
    monkeypatch.setattr(process_mod, "_windows_graceful", lambda pid: graceful.append(pid))
    monkeypatch.setattr(process_mod, "_taskkill", lambda pid: True)
    result = run_process(ProcessRequest(argv=argv, cwd=tmp_path, timeout_seconds=1))
    assert result.timed_out is True
    pid = int(pid_file.read_text(encoding="utf-8"))
    assert graceful == [pid]
