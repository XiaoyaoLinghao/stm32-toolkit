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
    _run_process,
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



def test_runner_returns_when_a_descendant_keeps_its_pipes_open():
    descendant = "import time; time.sleep(0.5)"
    parent = (
        "import subprocess, sys; "
        f"subprocess.Popen([sys.executable, '-c', {descendant!r}])"
    )
    started = time.monotonic()

    status, return_code, _, _ = _run_process((sys.executable, "-c", parent))

    elapsed = time.monotonic() - started
    assert status == "ok"
    assert return_code == 0
    assert elapsed < _READER_JOIN_TIMEOUT_SECONDS * 3
    time.sleep(0.6)

def test_doctor_evidence_is_json_serializable(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("stm32_toolkit.doctor.shutil.which", lambda name: None)

    result = run_doctor(tmp_path)

    assert json.loads(json.dumps(result.to_dict()))["data"]["project"]["kind"] == "unknown"
