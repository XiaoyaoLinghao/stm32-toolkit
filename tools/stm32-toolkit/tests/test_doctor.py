import json
import subprocess
from pathlib import Path

from stm32_toolkit.doctor import TOOLS, run_doctor


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

    def fake_which(name: str) -> str | None:
        return tool_path if name == "cmake" else None

    def fake_run(argv, **kwargs):
        calls.append((argv, kwargs))
        return subprocess.CompletedProcess(argv, 0, "cmake version 3.29.0\nextra", "")

    monkeypatch.setattr("stm32_toolkit.doctor.shutil.which", fake_which)
    monkeypatch.setattr("stm32_toolkit.doctor.subprocess.run", fake_run)

    result = run_doctor(tmp_path)

    assert result.data["tools"]["cmake"] == {
        "available": True,
        "path": tool_path,
        "status": "ok",
        "returnCode": 0,
        "version": "cmake version 3.29.0",
    }
    assert calls == [
        ((tool_path, "--version"), {"capture_output": True, "check": False, "shell": False, "text": True, "timeout": 5})
    ]


def test_doctor_keeps_nonzero_and_timeout_as_tool_evidence(monkeypatch, tmp_path: Path):
    def fake_which(name: str) -> str | None:
        return f"C:/tools/{name}.exe" if name in {"cmake", "ninja"} else None

    def fake_run(argv, **kwargs):
        if argv[0].endswith("cmake.exe"):
            return subprocess.CompletedProcess(argv, 7, "", "version unavailable")
        raise subprocess.TimeoutExpired(argv, kwargs["timeout"])

    monkeypatch.setattr("stm32_toolkit.doctor.shutil.which", fake_which)
    monkeypatch.setattr("stm32_toolkit.doctor.subprocess.run", fake_run)

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


def test_doctor_evidence_is_json_serializable(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("stm32_toolkit.doctor.shutil.which", lambda name: None)

    result = run_doctor(tmp_path)

    assert json.loads(json.dumps(result.to_dict()))["data"]["project"]["kind"] == "unknown"
