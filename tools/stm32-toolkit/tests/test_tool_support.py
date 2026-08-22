from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from stm32_toolkit.tool_support import (
    SupportProfileRequest,
    ToolFact,
    ToolSupportIssue,
    ToolSupportProfile,
    discover_tool_support,
)


def _write_executable(path: Path, content: bytes = b"tool") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def test_support_profile_is_closed_deterministic_and_python_312_only(tmp_path: Path):
    root = tmp_path / "clt"
    gcc = _write_executable(root / "GNU-tools-for-STM32" / "bin" / "arm-none-eabi-gcc.exe")
    cmake = _write_executable(root / "CMake" / "bin" / "cmake.exe")
    ninja = _write_executable(root / "Ninja" / "bin" / "ninja.exe")
    vscode = _write_executable(tmp_path / "VSCode" / "bin" / "code.exe")
    cubemx = _write_executable(tmp_path / "CubeMX" / "STM32CubeMX.exe")
    profile_file = tmp_path / "profile.json"
    profile_file.write_text(
        json.dumps(
            {
                "cubeCltRoot": str(root),
                "cubeMx": {"path": str(cubemx), "version": "6.18.0"},
                "gcc": {"path": str(gcc), "version": "14.3.1"},
                "cmake": {"path": str(cmake), "version": "4.3.1"},
                "ninja": {"path": str(ninja), "version": "1.13.2"},
                "vsCode": {"path": str(vscode), "version": "1.133.0"},
                "vsCodeExtensions": {"ms-vscode.cpptools": "1.21.0"},
            }
        ),
        encoding="utf-8",
    )
    profile = discover_tool_support(
        SupportProfileRequest(profile_path=profile_file, data_root=tmp_path)
    )
    payload = profile.to_dict()
    assert payload["pythonVersion"].startswith("3.12.")
    assert payload["gcc"]["source"] == "explicit"
    assert tuple(payload) == (
        "pythonVersion", "cubeMx", "cubeCltRoot", "gcc", "cmake", "ninja",
        "vsCode", "vsCodeExtensions", "issues",
    )
    assert payload["gcc"]["executableSha256"] == hashlib.sha256(gcc.read_bytes()).hexdigest()
    json.dumps(payload)
    with pytest.raises((AttributeError, TypeError)):
        profile.vscode_extensions += (("bad", "1"),)


def test_tool_support_models_are_immutable_and_issue_sorting_is_stable(tmp_path: Path):
    fact = ToolFact("gcc", tmp_path / "gcc.exe", "14.3.1", "explicit", "a" * 64)
    issue = ToolSupportIssue("Z_CODE", "z", "install")
    profile = ToolSupportProfile("3.12.10", None, None, fact, None, None, None, (), (issue,))
    with pytest.raises((AttributeError, TypeError)):
        profile.gcc = None
    assert profile.to_dict()["issues"] == [{"code": "Z_CODE", "component": "z", "remediation": "install"}]


def test_cubeclt_metadata_discovers_build_tools_but_not_cubemx(tmp_path: Path, monkeypatch):
    root = tmp_path / "clt"
    gcc = _write_executable(root / "GNU-tools-for-STM32" / "bin" / "arm-none-eabi-gcc.exe")
    cmake = _write_executable(root / "CMake" / "bin" / "cmake.exe")
    ninja = _write_executable(root / "Ninja" / "bin" / "ninja.exe")
    vscode = _write_executable(tmp_path / "code.exe")
    profile_file = tmp_path / "profile.json"
    profile_file.write_text(json.dumps({"cubeCltRoot": str(root), "vsCode": {"path": str(vscode), "version": "1.133.0"}}), encoding="utf-8")
    monkeypatch.setattr("stm32_toolkit.tool_support._discover_cube_mx", lambda payload: None)
    profile = discover_tool_support(SupportProfileRequest(profile_file, tmp_path))
    assert profile.gcc is not None and profile.gcc.path == gcc
    assert profile.cmake is not None and profile.cmake.path == cmake
    assert profile.ninja is not None and profile.ninja.path == ninja
    assert profile.cubemx is None
    assert "CUBEMX_MISSING" in [issue.code for issue in profile.issues]


def test_missing_tools_are_reported_without_writing(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("stm32_toolkit.tool_support.shutil.which", lambda _: None)
    monkeypatch.setattr("stm32_toolkit.tool_support._discover_cube_mx", lambda payload: None)
    before = tuple(sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*")))
    profile = discover_tool_support(SupportProfileRequest(data_root=tmp_path))
    after = tuple(sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*")))
    assert profile.cubemx is None
    assert any(item.code == "CUBEMX_MISSING" for item in profile.issues)
    assert before == after


def test_support_profile_must_be_inside_trusted_data_root(tmp_path: Path):
    outside = tmp_path.parent / "outside-profile.json"
    outside.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError):
        discover_tool_support(SupportProfileRequest(outside, tmp_path))


def test_cubeclt_metadata_batch_seam_is_bounded_and_injected(tmp_path: Path, monkeypatch):
    root = tmp_path / "clt"
    root.mkdir()
    monkeypatch.setattr("stm32_toolkit.tool_support._run_cubeclt_metadata", lambda value: {"GNUToolsForSTM32": str(root / "gcc"), "CMake": str(root / "cmake"), "Ninja": str(root / "ninja")})
    assert "GNUToolsForSTM32" in __import__("stm32_toolkit.tool_support", fromlist=["_run_cubeclt_metadata"])._run_cubeclt_metadata(root)
