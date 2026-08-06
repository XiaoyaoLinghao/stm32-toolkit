import io
import json
import subprocess
import sys
import time
from pathlib import Path

from stm32_toolkit.doctor import (
    TOOLS,
    _READER_JOIN_TIMEOUT_SECONDS,
    _STREAM_READ_BYTES,
    _VERSION_CAPTURE_LIMIT,
    _drain_stream,
    _join_readers,
    _read_stream,
    _run_process,
    _terminate_and_reap,
    run_doctor,
)


class _FakeProcess:
    def __init__(
        self,
        *,
        stdout: bytes = b"",
        stderr: bytes = b"",
        returncode: int = 0,
        timeout_once: bool = False,
    ):
        self.stdout = io.BytesIO(stdout)
        self.stderr = io.BytesIO(stderr)
        self.returncode = returncode
        self.timeout_once = timeout_once
        self.wait_timeouts: list[float] = []
        self.terminated = False
        self.killed = False

    def wait(self, timeout: float) -> int:
        self.wait_timeouts.append(timeout)
        if self.timeout_once and len(self.wait_timeouts) == 1:
            raise subprocess.TimeoutExpired(("tool", "--version"), timeout)
        return self.returncode

    def terminate(self) -> None:
        self.terminated = True

    def kill(self) -> None:
        self.killed = True


def test_doctor_reports_missing_planned_tools_without_mutating(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("stm32_toolkit.doctor.shutil.which", lambda name: None)

    result = run_doctor(tmp_path)

    assert result.ok is True
    assert tuple(result.data["tools"]) == TOOLS
    assert result.data["tools"]["arm-none-eabi-gcc"] == {
        "available": False,
        "path": None,
        "status": "missing",
        "returnCode": None,
        "version": None,
    }
    assert result.data["mutated"] is False
    assert not any(tmp_path.iterdir())


def test_doctor_records_a_found_tool_version_with_fixed_read_only_command(monkeypatch, tmp_path: Path):
    tool_path = r"C:\Program Files\CMake\bin\cmake.exe"
    calls: list[tuple[object, dict[str, object]]] = []
    process = _FakeProcess(stdout=b"cmake version 3.29.0\nextra")

    def fake_which(name: str) -> str | None:
        return tool_path if name == "cmake" else None

    def fake_popen(argv, **kwargs):
        calls.append((argv, kwargs))
        return process

    monkeypatch.setattr("stm32_toolkit.doctor.shutil.which", fake_which)
    monkeypatch.setattr("stm32_toolkit.doctor.subprocess.Popen", fake_popen)

    result = run_doctor(tmp_path)

    assert result.data["tools"]["cmake"] == {
        "available": True,
        "path": tool_path,
        "status": "ok",
        "returnCode": 0,
        "version": "cmake version 3.29.0",
    }
    assert calls == [
        ((tool_path, "--version"), {
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "shell": False,
        })
    ]
    assert process.wait_timeouts == [5]


def test_doctor_keeps_nonzero_and_timeout_as_tool_evidence(monkeypatch, tmp_path: Path):
    cmake_process = _FakeProcess(stderr=b"version unavailable", returncode=7)
    ninja_process = _FakeProcess(timeout_once=True)

    def fake_which(name: str) -> str | None:
        return f"C:/tools/{name}.exe" if name in {"cmake", "ninja"} else None

    def fake_popen(argv, **kwargs):
        if argv[0].endswith("cmake.exe"):
            return cmake_process
        return ninja_process

    monkeypatch.setattr("stm32_toolkit.doctor.shutil.which", fake_which)
    monkeypatch.setattr("stm32_toolkit.doctor.subprocess.Popen", fake_popen)

    result = run_doctor(tmp_path)

    assert result.ok is True
    assert result.data["tools"]["cmake"] == {
        "available": True,
        "path": "C:/tools/cmake.exe",
        "status": "nonzero",
        "returnCode": 7,
        "version": "version unavailable",
    }
    assert result.data["tools"]["ninja"] == {
        "available": True,
        "path": "C:/tools/ninja.exe",
        "status": "timeout",
        "returnCode": None,
        "version": None,
    }
    assert ninja_process.terminated is True
    assert ninja_process.wait_timeouts == [5, 1]
    assert ninja_process.stdout.closed is True
    assert ninja_process.stderr.closed is True


def test_drain_stream_retains_a_fixed_byte_limit_for_oversized_output():
    class ReadBoundedStream(io.BytesIO):
        def __init__(self, value: bytes):
            super().__init__(value)
            self.request_sizes: list[int] = []

        def read(self, size: int = -1) -> bytes:
            self.request_sizes.append(size)
            assert 0 < size <= _STREAM_READ_BYTES
            return super().read(size)

    stream = ReadBoundedStream(b"x" * (_VERSION_CAPTURE_LIMIT * 3))

    retained = _drain_stream(stream)

    assert len(retained) == _VERSION_CAPTURE_LIMIT
    assert len(stream.request_sizes) > 1
    assert max(stream.request_sizes) == _STREAM_READ_BYTES


def test_doctor_decodes_invalid_version_bytes_as_evidence(monkeypatch, tmp_path: Path):
    process = _FakeProcess(stdout=b"\xffcmake version\n")
    monkeypatch.setattr(
        "stm32_toolkit.doctor.shutil.which",
        lambda name: "C:/tools/cmake.exe" if name == "cmake" else None,
    )
    monkeypatch.setattr("stm32_toolkit.doctor.subprocess.Popen", lambda argv, **kwargs: process)

    result = run_doctor(tmp_path)

    assert result.ok is True
    assert result.data["tools"]["cmake"]["status"] == "ok"
    assert result.data["tools"]["cmake"]["version"] == "\ufffdcmake version"



def test_reader_cleanup_uses_a_bounded_join_for_each_pipe():
    """Catches one blocked pipe preventing cleanup of the other reader."""
    class BlockingReader:
        def __init__(self):
            self.timeouts: list[float] = []

        def join(self, timeout: float) -> None:
            self.timeouts.append(timeout)

    stdout_reader = BlockingReader()
    stderr_reader = BlockingReader()

    _join_readers((stdout_reader, stderr_reader))

    assert stdout_reader.timeouts == [_READER_JOIN_TIMEOUT_SECONDS]
    assert stderr_reader.timeouts == [_READER_JOIN_TIMEOUT_SECONDS]


def test_runner_returns_before_a_descendant_releases_inherited_pipes(tmp_path: Path):
    """Catches waiting for inherited pipe handles without scheduler timing assumptions."""
    marker = tmp_path / "descendant-finished"
    release = tmp_path / "release-descendant"
    descendant = (
        "import pathlib, time; "
        f"release=pathlib.Path({str(release)!r}); marker=pathlib.Path({str(marker)!r}); "
        "\nwhile not release.exists(): time.sleep(0.01)\n"
        "marker.write_text('done')"
    )
    parent = (
        "import subprocess, sys; "
        f"subprocess.Popen([sys.executable, '-c', {descendant!r}])"
    )

    try:
        status, return_code, _, _ = _run_process((sys.executable, "-c", parent))
        assert status == "ok"
        assert return_code == 0
        assert not marker.exists()
    finally:
        release.write_text("release", encoding="utf-8")

    deadline = time.monotonic() + 3
    while not marker.exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    assert marker.read_text(encoding="utf-8") == "done"


def test_doctor_treats_executable_discovery_errors_as_missing(monkeypatch, tmp_path: Path):
    """Catches an OS lookup error aborting the complete doctor report."""
    def unavailable(name: str) -> str | None:
        raise OSError("lookup unavailable")

    monkeypatch.setattr("stm32_toolkit.doctor.shutil.which", unavailable)

    result = run_doctor(tmp_path)

    assert result.ok is True
    assert all(tool["status"] == "missing" for tool in result.data["tools"].values())


def test_doctor_treats_process_start_errors_as_tool_evidence(monkeypatch, tmp_path: Path):
    """Catches a stale executable path crashing doctor instead of reporting it."""
    monkeypatch.setattr(
        "stm32_toolkit.doctor.shutil.which",
        lambda name: "C:/tools/cmake.exe" if name == "cmake" else None,
    )

    def unavailable(argv, **kwargs):
        raise OSError("cannot start")

    monkeypatch.setattr("stm32_toolkit.doctor.subprocess.Popen", unavailable)

    result = run_doctor(tmp_path)

    assert result.data["tools"]["cmake"] == {
        "available": True,
        "path": "C:/tools/cmake.exe",
        "status": "error",
        "returnCode": None,
        "version": None,
    }


def test_runner_kills_a_process_that_does_not_terminate(monkeypatch):
    """Catches a timed-out version process surviving terminate and cleanup."""
    process = _FakeProcess()
    waits = iter([
        subprocess.TimeoutExpired(("tool", "--version"), 5),
        subprocess.TimeoutExpired(("tool", "--version"), 1),
        9,
    ])

    def wait(timeout: float) -> int:
        process.wait_timeouts.append(timeout)
        outcome = next(waits)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    process.wait = wait
    monkeypatch.setattr(
        "stm32_toolkit.doctor.subprocess.Popen",
        lambda argv, **kwargs: process,
    )

    status, return_code, _, _ = _run_process(("tool", "--version"))

    assert status == "timeout"
    assert return_code is None
    assert process.terminated is True
    assert process.killed is True
    assert process.wait_timeouts == [5, 1, 1]


def test_reaper_swallows_wait_errors_after_termination():
    """Catches cleanup exceptions escaping from an already failed tool check."""
    process = _FakeProcess()

    def wait(timeout: float) -> int:
        raise OSError("wait unavailable")

    process.wait = wait

    _terminate_and_reap(process)

    assert process.terminated is True
    assert process.killed is False


def test_runner_translates_wait_os_error_and_reaps_process(monkeypatch):
    """Catches process wait failures escaping doctor or skipping termination."""
    process = _FakeProcess()
    waits = iter([OSError("wait unavailable"), 0])

    def wait(timeout: float) -> int:
        process.wait_timeouts.append(timeout)
        outcome = next(waits)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    process.wait = wait
    monkeypatch.setattr(
        "stm32_toolkit.doctor.subprocess.Popen",
        lambda argv, **kwargs: process,
    )

    status, return_code, stdout, stderr = _run_process(("tool", "--version"))

    assert (status, return_code, stdout, stderr) == ("error", None, b"", b"")
    assert process.terminated is True
    assert process.wait_timeouts == [5, 1]


def test_reader_discards_stream_errors_and_attempts_close():
    """Catches malformed pipe reads crashing doctor or bypassing stream cleanup."""
    class BrokenStream:
        def __init__(self):
            self.close_attempted = False

        def read(self, size: int) -> bytes:
            raise ValueError("stream closed")

        def close(self) -> None:
            self.close_attempted = True
            raise OSError("close unavailable")

    stream = BrokenStream()
    captured = {"stdout": b"stale"}

    _read_stream(stream, captured, "stdout")

    assert captured == {"stdout": b""}
    assert stream.close_attempted is True

def test_doctor_evidence_is_json_serializable(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("stm32_toolkit.doctor.shutil.which", lambda name: None)

    result = run_doctor(tmp_path)

    assert json.loads(json.dumps(result.to_dict()))["data"]["project"]["kind"] == "unknown"


# ---------------------------------------------------------------------------
# VS Code extension evidence (STM32TK-0304)
# ---------------------------------------------------------------------------


from stm32_toolkit.doctor import (
    VSCODE_EXTENSIONS,
    _parse_extension_lines,
    _vscode_extension_evidence,
)


def _code_extension_processes(stdout: bytes):
    def fake_popen(argv, **kwargs):
        if argv[1:] == ("--list-extensions", "--show-versions"):
            return _FakeProcess(stdout=stdout)
        return _FakeProcess(stdout=b"code version 1.90.0\n")

    return fake_popen


def test_doctor_vscode_extensions_unavailable_without_code(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("stm32_toolkit.doctor.shutil.which", lambda name: None)

    result = run_doctor(tmp_path)

    extensions = result.data["vscodeExtensions"]
    assert tuple(extensions) == VSCODE_EXTENSIONS
    assert all(
        value == {"installed": False, "version": None, "status": "unavailable"}
        for value in extensions.values()
    )
    assert result.data["mutated"] is False


def test_doctor_vscode_extensions_parsed_with_fixed_argv(monkeypatch, tmp_path: Path):
    code_path = r"C:\Program Files\Microsoft VS Code\bin\code.exe"
    calls: list[tuple[object, dict[str, object]]] = []

    def fake_which(name: str) -> str | None:
        return code_path if name == "code" else None

    def fake_popen(argv, **kwargs):
        calls.append((argv, kwargs))
        if argv[1:] == ("--list-extensions", "--show-versions"):
            return _FakeProcess(
                stdout=(
                    b"ms-vscode.cpptools@1.21.0\n"
                    b"ms-vscode.cmake-tools@1.18.42\n"
                    b"unrelated.extension@9.9.9\n"
                )
            )
        return _FakeProcess(stdout=b"code version 1.90.0\n")

    monkeypatch.setattr("stm32_toolkit.doctor.shutil.which", fake_which)
    monkeypatch.setattr("stm32_toolkit.doctor.subprocess.Popen", fake_popen)

    result = run_doctor(tmp_path)

    extensions = result.data["vscodeExtensions"]
    assert extensions["ms-vscode.cpptools"] == {
        "installed": True,
        "version": "1.21.0",
        "status": "ok",
    }
    assert extensions["ms-vscode.cmake-tools"] == {
        "installed": True,
        "version": "1.18.42",
        "status": "ok",
    }
    assert extensions["marus25.cortex-debug"] == {
        "installed": False,
        "version": None,
        "status": "missing",
    }
    extension_call = next(
        call for call in calls if call[0][1:] == ("--list-extensions", "--show-versions")
    )
    assert extension_call[0] == (code_path, "--list-extensions", "--show-versions")
    assert extension_call[1]["shell"] is False
    assert extension_call[1]["stdin"] == subprocess.DEVNULL
    assert not any(tmp_path.iterdir())


def test_doctor_vscode_extensions_case_insensitive_parse(monkeypatch, tmp_path: Path):
    code_path = "C:/tools/code.exe"
    monkeypatch.setattr(
        "stm32_toolkit.doctor.shutil.which",
        lambda name: code_path if name == "code" else None,
    )
    monkeypatch.setattr(
        "stm32_toolkit.doctor.subprocess.Popen",
        _code_extension_processes(b"MS-VSCODE.CPPTOOLS@1.2.3\nMARUS25.Cortex-Debug@1.8.0\n"),
    )

    result = run_doctor(tmp_path)

    extensions = result.data["vscodeExtensions"]
    assert extensions["ms-vscode.cpptools"]["status"] == "ok"
    assert extensions["ms-vscode.cpptools"]["version"] == "1.2.3"
    assert extensions["marus25.cortex-debug"]["installed"] is True


def test_parse_extension_lines_ignores_malformed_and_unrelated():
    output = (
        "ms-vscode.cpptools@1.21.0\n"
        "garbage line\n"
        "no-version-line\n"
        "publisher.extension\n"
        "ext@1.0\n"
        "has space.id@1.0\n"
        "other.ext@2.0\n"
    )
    parsed = _parse_extension_lines(output)
    assert parsed == {
        "ms-vscode.cpptools": "1.21.0",
        "other.ext": "2.0",
    }


def test_doctor_vscode_extensions_nonzero_probe(monkeypatch, tmp_path: Path):
    code_path = "C:/tools/code.exe"
    monkeypatch.setattr(
        "stm32_toolkit.doctor.shutil.which",
        lambda name: code_path if name == "code" else None,
    )
    monkeypatch.setattr(
        "stm32_toolkit.doctor.subprocess.Popen",
        lambda argv, **kwargs: _FakeProcess(stdout=b"", returncode=7),
    )

    result = run_doctor(tmp_path)

    assert all(
        value == {"installed": False, "version": None, "status": "nonzero"}
        for value in result.data["vscodeExtensions"].values()
    )


def test_doctor_vscode_extensions_timeout_probe(monkeypatch, tmp_path: Path):
    code_path = "C:/tools/code.exe"
    monkeypatch.setattr(
        "stm32_toolkit.doctor.shutil.which",
        lambda name: code_path if name == "code" else None,
    )
    processes = []

    def fake_popen(argv, **kwargs):
        process = _FakeProcess(timeout_once=True)
        processes.append(process)
        return process

    monkeypatch.setattr("stm32_toolkit.doctor.subprocess.Popen", fake_popen)

    result = run_doctor(tmp_path)

    assert all(
        value == {"installed": False, "version": None, "status": "timeout"}
        for value in result.data["vscodeExtensions"].values()
    )
    assert all(process.terminated for process in processes)


def test_doctor_vscode_extensions_error_probe(monkeypatch, tmp_path: Path):
    code_path = "C:/tools/code.exe"
    monkeypatch.setattr(
        "stm32_toolkit.doctor.shutil.which",
        lambda name: code_path if name == "code" else None,
    )

    def unavailable(argv, **kwargs):
        raise OSError("cannot start")

    monkeypatch.setattr("stm32_toolkit.doctor.subprocess.Popen", unavailable)

    result = run_doctor(tmp_path)

    assert all(
        value == {"installed": False, "version": None, "status": "error"}
        for value in result.data["vscodeExtensions"].values()
    )


def test_doctor_vscode_extensions_capped_output_still_parses(monkeypatch, tmp_path: Path):
    code_path = "C:/tools/code.exe"
    monkeypatch.setattr(
        "stm32_toolkit.doctor.shutil.which",
        lambda name: code_path if name == "code" else None,
    )
    monkeypatch.setattr(
        "stm32_toolkit.doctor.subprocess.Popen",
        _code_extension_processes(
            b"ms-vscode.cpptools@1.21.0\n" + b"x" * (_VERSION_CAPTURE_LIMIT * 3)
        ),
    )

    result = run_doctor(tmp_path)

    assert result.data["vscodeExtensions"]["ms-vscode.cpptools"]["status"] == "ok"
    assert result.data["vscodeExtensions"]["ms-vscode.cpptools"]["installed"] is True


def test_doctor_vscode_extension_evidence_never_mutates(monkeypatch, tmp_path: Path):
    code_path = "C:/tools/code.exe"
    monkeypatch.setattr(
        "stm32_toolkit.doctor.shutil.which",
        lambda name: code_path if name == "code" else None,
    )
    monkeypatch.setattr(
        "stm32_toolkit.doctor.subprocess.Popen",
        _code_extension_processes(b"ms-vscode.cpptools@1.21.0\n"),
    )

    evidence = _vscode_extension_evidence()

    assert evidence["ms-vscode.cpptools"]["status"] == "ok"
    assert not any(tmp_path.iterdir())


def test_doctor_extension_discovery_error_is_unavailable(monkeypatch, tmp_path: Path):
    def unavailable(name: str) -> str | None:
        raise OSError("lookup unavailable")

    monkeypatch.setattr("stm32_toolkit.doctor.shutil.which", unavailable)

    result = run_doctor(tmp_path)

    assert all(
        value["status"] == "unavailable"
        for value in result.data["vscodeExtensions"].values()
    )
