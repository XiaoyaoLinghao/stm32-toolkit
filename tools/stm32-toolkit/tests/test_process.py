"""Bounded fixed-argv subprocess execution contracts.

POSIX-only ``killpg`` behavior runs only through injected callable seams or
in a POSIX environment; every liveness assertion goes through a
platform-adapted helper (never ``os.killpg`` or ``os.kill(pid, 0)``
directly).  The Windows ``_is_windows`` branch is exercised with real child
processes on any host through the same seams, and the fake ``taskkill``
seam deterministically terminates the whole test process tree so no test
leaves a direct child, interpreter descendant, or pipe-drain thread behind.
No test is skipped or xfailed.
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


def write_pid_child(pid_file: Path, code: str = "import time; time.sleep(60)") -> tuple[str, ...]:
    return (
        PYTHON,
        "-c",
        f"import os; open({str(pid_file)!r}, 'w').write(str(os.getpid())); {code}",
    )


def write_tree_child(pid_file: Path, grand_pid_file: Path) -> tuple[str, ...]:
    """Spawn a child that (on POSIX) becomes its own process-group leader,
    spawns a grandchild that inherits that group, then sleeps.  Both PIDs
    are written to files so a test can prove the whole tree was reaped.

    The Windows-branch tests strip ``start_new_session`` through the Popen
    proxy, so on POSIX the child must create the group itself
    (``os.setpgid(0, 0)``); the grandchild then shares the group and the
    tree-killing ``taskkill`` fake can terminate exactly this tree with
    ``killpg`` without touching the test runner's process group.
    """
    body = (
        "import os, subprocess, sys, time\n"
        "if os.name == 'posix':\n"
        "    os.setpgid(0, 0)\n"
        "grand = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
        f"open({str(grand_pid_file)!r}, 'w').write(str(grand.pid))\n"
        f"open({str(pid_file)!r}, 'w').write(str(os.getpid()))\n"
        "time.sleep(60)\n"
    )
    return (PYTHON, "-c", body)


def _posix_process_state(pid: int) -> str | None:
    """Return the ``/proc`` state character for ``pid`` or ``None``."""
    try:
        data = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
        return data.rsplit(")", 1)[1].split()[0]
    except (OSError, IndexError, ValueError):
        return None


def _windows_process_is_alive(pid: int) -> bool:
    """Windows liveness probe via OpenProcess/GetExitCodeProcess."""
    import ctypes

    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return False
    try:
        exit_code = ctypes.c_ulong()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
            return False
        return exit_code.value == 259  # STILL_ACTIVE
    finally:
        kernel32.CloseHandle(handle)


def _process_is_alive(pid: int) -> bool:
    """True when ``pid`` still identifies a live, non-zombie process."""
    if os.name == "nt":
        return _windows_process_is_alive(pid)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    state = _posix_process_state(pid)
    if state is None:
        return False
    return state != "Z"


def assert_process_reaped(pid: int, timeout_seconds: float = 10.0) -> None:
    """Assert ``pid`` no longer identifies a live process.

    Waits up to ``timeout_seconds`` with an explicit bounded poll (never a
    fixed sleep) so orphan reaping on any host completes deterministically.
    """
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if not _process_is_alive(pid):
            return
        time.sleep(0.02)
    raise AssertionError(f"process {pid} is still alive after {timeout_seconds:.1f}s")


def make_taskkill_fake(taskkilled: list[int]):
    """A deterministic whole-process-tree ``taskkill`` double.

    POSIX: the test child is its own group leader (``os.setpgid(0, 0)``),
    so ``killpg`` terminates exactly the child tree.  Windows: ``taskkill
    /T`` is the deterministic tree killer.  The fake always records the
    root pid so a test can prove the seam was hit.
    """
    def fake_taskkill(pid: int) -> bool:
        taskkilled.append(pid)
        if os.name == "posix":
            os.killpg(pid, signal.SIGKILL)
        else:
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10,
            )
        return True

    return fake_taskkill


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
    code = "import sys\nsys.stdout.write('a\\n' * 40000)\n"
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
    # Exact bytes through the binary buffer: text-mode stdout on Windows
    # would translate "\n" and produce "\r\r\n", so the fixture must
    # write raw bytes to prove the product normalization is exact.
    code = "import sys\nsys.stdout.buffer.write(b'a\\r\\nb\\rc\\n')\n"
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
    assert_process_reaped(pid)
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
    assert_process_reaped(pid)
    assert_process_reaped(grand_pid)


def test_timeout_uses_graceful_then_force_termination_seams(tmp_path: Path, monkeypatch):
    pid_file = tmp_path / "child.pid"
    argv = write_pid_child(pid_file)
    terminated: list[int] = []
    killed: list[int] = []

    def terminate(pid):
        terminated.append(pid)
        raise OSError("injected graceful termination failure")

    def force_kill(pid):
        killed.append(pid)
        if os.name == "posix":
            os.killpg(pid, signal.SIGKILL)
        else:
            os.kill(pid, signal.SIGKILL)  # TerminateProcess on Windows

    # Force the POSIX branch on any host so the graceful→force seam
    # contract is exercised deterministically (``start_new_session`` is a
    # no-op on Windows, so the real child still runs).
    monkeypatch.setattr(process_mod, "_is_windows", False)
    monkeypatch.setattr(process_mod, "_terminate_group", terminate)
    monkeypatch.setattr(process_mod, "_kill_group", force_kill)
    result = run_process(ProcessRequest(argv=argv, cwd=tmp_path, timeout_seconds=1))
    assert result.timed_out is True
    pid = int(pid_file.read_text(encoding="utf-8"))
    assert terminated == [pid]
    assert killed == [pid]
    assert_process_reaped(pid)


def test_timeout_success_path_never_calls_termination_seams(tmp_path: Path, monkeypatch):
    called: list[str] = []
    monkeypatch.setattr(process_mod, "_terminate_group", lambda pid: called.append("term"))
    monkeypatch.setattr(process_mod, "_kill_group", lambda pid: called.append("kill"))
    result = run_process(
        ProcessRequest(argv=(PYTHON, "-c", "pass"), cwd=tmp_path, timeout_seconds=30)
    )
    assert result.timed_out is False
    assert called == []


def install_windows_popen_proxy(
    monkeypatch: pytest.MonkeyPatch,
    captured: dict | None = None,
    instances: list | None = None,
):
    """Strip Windows-only Popen kwargs so the real child runs on any host.

    The Windows branch passes ``creationflags`` which real POSIX ``Popen``
    rejects; the proxy captures or strips it and delegates everything else.
    When ``instances`` is given every proxy instance is recorded so a test
    can spy on ``kill()`` (the taskkill-fallback contract).
    """
    real_popen = subprocess.Popen

    class WindowsPopenProxy:
        def __init__(self, *args, **kwargs):
            if captured is not None:
                captured["creationflags"] = kwargs.pop("creationflags", 0)
                captured["start_new_session"] = kwargs.pop("start_new_session", False)
            else:
                kwargs.pop("creationflags", None)
                kwargs.pop("start_new_session", None)
            self._kill_called = False
            self._popen = real_popen(*args, **kwargs)
            if instances is not None:
                instances.append(self)

        def kill(self):
            self._kill_called = True
            return self._popen.kill()

        def __getattr__(self, name):
            return getattr(self._popen, name)

    monkeypatch.setattr(subprocess, "Popen", WindowsPopenProxy)


def test_windows_branch_uses_taskkill_seam(tmp_path: Path, monkeypatch):
    pid_file = tmp_path / "child.pid"
    grand_pid_file = tmp_path / "grand.pid"
    argv = write_tree_child(pid_file, grand_pid_file)
    taskkilled: list[int] = []
    graceful: list[int] = []

    install_windows_popen_proxy(monkeypatch)
    monkeypatch.setattr(process_mod, "_is_windows", True)
    monkeypatch.setattr(process_mod, "_windows_graceful", lambda pid: graceful.append(pid))
    monkeypatch.setattr(process_mod, "_taskkill", make_taskkill_fake(taskkilled))
    result = run_process(ProcessRequest(argv=argv, cwd=tmp_path, timeout_seconds=1))
    assert result.timed_out is True
    pid = int(pid_file.read_text(encoding="utf-8"))
    grand_pid = int(grand_pid_file.read_text(encoding="utf-8"))
    assert graceful == [pid]
    assert taskkilled == [pid]
    assert_process_reaped(pid)
    assert_process_reaped(grand_pid)


def test_windows_branch_falls_back_to_kill_when_taskkill_fails(tmp_path: Path, monkeypatch):
    pid_file = tmp_path / "child.pid"
    argv = write_pid_child(pid_file)
    taskkilled: list[int] = []
    instances: list = []

    install_windows_popen_proxy(monkeypatch, instances=instances)
    monkeypatch.setattr(process_mod, "_is_windows", True)
    monkeypatch.setattr(process_mod, "_windows_graceful", lambda pid: None)
    monkeypatch.setattr(process_mod, "_taskkill", lambda pid: taskkilled.append(pid) or False)
    result = run_process(ProcessRequest(argv=argv, cwd=tmp_path, timeout_seconds=1))
    assert result.timed_out is True
    pid = int(pid_file.read_text(encoding="utf-8"))
    assert taskkilled == [pid]
    assert instances[0]._kill_called is True  # the kill() fallback was exercised
    assert_process_reaped(pid)


def test_windows_branch_uses_create_new_process_group_flag(tmp_path: Path, monkeypatch):
    captured: dict = {}
    install_windows_popen_proxy(monkeypatch, captured)
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


def test_timeout_escalates_to_sigkill_when_sigterm_is_ignored(tmp_path: Path):
    pid_file = tmp_path / "child.pid"
    code = (
        "import os, signal, time\n"
        "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        f"open({str(pid_file)!r}, 'w').write(str(os.getpid()))\n"
        "time.sleep(60)\n"
    )
    argv = (PYTHON, "-c", code)
    result = run_process(ProcessRequest(argv=argv, cwd=tmp_path, timeout_seconds=1))
    assert result.timed_out is True
    pid = int(pid_file.read_text(encoding="utf-8"))
    assert_process_reaped(pid)


def test_output_sink_edge_cases():
    from stm32_toolkit.process import _OutputSink

    sink = _OutputSink(8, 4)
    sink.append(b"")
    assert sink.text() == ""
    sink.append(b"ab\ncd\n")
    sink.append(b"ef\n")
    assert sink.text() == "ab\ncd\nef"
    # byte cap cuts mid-line deterministically
    sink = _OutputSink(4, 100)
    sink.append(b"abcdef")
    assert sink.truncated is True
    assert sink.text() == "abcd"
    # line cap cuts at the Nth newline
    sink = _OutputSink(1024, 2)
    sink.append(b"a\nb\nc\nd\n")
    assert sink.truncated is True
    assert sink.text() == "a\nb\n"
    # discarded overflow continues to be counted
    sink = _OutputSink(4, 100)
    sink.append(b"abcdef")
    sink.append(b"gh")
    assert sink.text() == "abcd"


def test_windows_branch_graceful_signal_is_seam_injected(tmp_path: Path, monkeypatch):
    pid_file = tmp_path / "child.pid"
    grand_pid_file = tmp_path / "grand.pid"
    argv = write_tree_child(pid_file, grand_pid_file)
    graceful: list[int] = []
    taskkilled: list[int] = []

    install_windows_popen_proxy(monkeypatch)
    monkeypatch.setattr(process_mod, "_is_windows", True)
    monkeypatch.setattr(process_mod, "_windows_graceful", lambda pid: graceful.append(pid))
    monkeypatch.setattr(process_mod, "_taskkill", make_taskkill_fake(taskkilled))
    result = run_process(ProcessRequest(argv=argv, cwd=tmp_path, timeout_seconds=1))
    assert result.timed_out is True
    pid = int(pid_file.read_text(encoding="utf-8"))
    grand_pid = int(grand_pid_file.read_text(encoding="utf-8"))
    assert graceful == [pid]
    assert taskkilled == [pid]
    assert_process_reaped(pid)
    assert_process_reaped(grand_pid)
