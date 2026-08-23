from __future__ import annotations

import hashlib
import json
import os
import sys
from types import SimpleNamespace
from pathlib import Path

import pytest

from stm32_toolkit.tool_support import (
    ProcessObservation,
    SupportProfileError,
    SupportProfileRequest,
    ToolFact,
    ToolSupportIssue,
    ToolSupportProfile,
    discover_tool_support,
)

import stm32_toolkit.tool_support as support


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
    monkeypatch.setattr(
        support,
        "_run_bounded",
        lambda argv, **kwargs: ProcessObservation(0, b"14.3.1\n", b""),
    )
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
    gcc = _write_executable(root / "GNU-tools-for-STM32" / "bin" / "arm-none-eabi-gcc.exe")
    cmake = _write_executable(root / "CMake" / "bin" / "cmake.exe")
    ninja = _write_executable(root / "Ninja" / "bin" / "ninja.exe")
    script = _write_executable(root / "STM32CubeCLT_metadata.bat")
    def fake_runner(argv, **kwargs):
        if argv[0] == str(script):
            return ProcessObservation(0, json.dumps({"GNUToolsForSTM32": str(gcc), "CMake": str(cmake), "Ninja": str(ninja)}).encode(), b"")
        return ProcessObservation(0, b"GNU Arm Embedded Toolchain 14.3.1\n", b"")
    monkeypatch.setattr("stm32_toolkit.tool_support._run_bounded", fake_runner)
    import stm32_toolkit.tool_support as support
    metadata = support._read_metadata(root)
    assert metadata.values["GNUToolsForSTM32"] == str(gcc)
    tier = support._metadata_tier(root, metadata, "gcc")
    assert tier is not None and tier.candidates[0].path == gcc
    result = support._resolve_component(
        "gcc",
        (tier,),
        lambda candidate: support._build_fact(candidate, "gcc", probe_versions=True),
    )
    assert result.fact is not None and result.fact.version == "14.3.1"


def test_native_cubeclt_windows_metadata_directories_are_normalized(tmp_path: Path, monkeypatch):
    root, gcc, cmake, ninja = _metadata_root(tmp_path)
    # CubeCLT 1.22.0 emits these Windows paths with single backslashes and
    # points at component bin directories rather than executable leaves.
    raw = (
        '{"GNUToolsForSTM32":"' + str(gcc.parent) + '",'
        '"CMake":"' + str(cmake.parent) + '",'
        '"Ninja":"' + str(ninja.parent) + '"}'
    ).encode()
    metadata_path = root / "STM32CubeCLT_metadata.bat"
    monkeypatch.setattr(support, "_CUBECLT_ROOTS", ())
    monkeypatch.setattr(
        support,
        "_run_bounded",
        lambda argv, **kwargs: ProcessObservation(0, raw, b"")
        if Path(argv[0]) == metadata_path
        else ProcessObservation(0, b"", b""),
    )

    profile = discover_tool_support(
        _write_profile(tmp_path, {"cubeCltRoot": str(root)}), probe_versions=False
    )

    assert profile.gcc is not None and profile.gcc.path == gcc
    assert profile.cmake is not None and profile.cmake.path == cmake
    assert profile.ninja is not None and profile.ninja.path == ninja


def _write_profile(tmp_path: Path, payload: dict[str, object]) -> SupportProfileRequest:
    profile = tmp_path / "profile.json"
    profile.write_text(json.dumps(payload), encoding="utf-8")
    return SupportProfileRequest(profile_path=profile, data_root=tmp_path)


def _metadata_root(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    root = tmp_path / "cubeclt"
    gcc = _write_executable(root / "GNU-tools-for-STM32" / "bin" / "arm-none-eabi-gcc.exe")
    cmake = _write_executable(root / "CMake" / "bin" / "cmake.exe")
    ninja = _write_executable(root / "Ninja" / "bin" / "ninja.exe")
    script = _write_executable(root / "STM32CubeCLT_metadata.bat")
    return root, gcc, cmake, ninja


def test_invalid_explicit_candidate_is_fail_closed(tmp_path: Path, monkeypatch):
    candidate = _write_executable(tmp_path / "trusted-profile-tool.exe")
    path_dir = tmp_path / "path"
    path_candidate = _write_executable(path_dir / "arm-none-eabi-gcc.exe")
    monkeypatch.setenv("PATH", str(path_dir))
    monkeypatch.setattr(support, "_CUBECLT_ROOTS", ())
    monkeypatch.setattr(support, "_CUBEMX_PATHS", ())
    monkeypatch.setattr(support, "_VS_CODE_PATHS", ())
    monkeypatch.setattr(support, "_registry_candidates", lambda component: ())
    used = []
    monkeypatch.setattr(support, "_run_bounded", lambda argv, **kwargs: used.append(argv))

    with pytest.raises(SupportProfileError):
        discover_tool_support(
            _write_profile(
                tmp_path,
                {
                    "gcc": {"path": str(candidate), "version": 14.3},
                },
            ),
            probe_versions=False,
        )

    assert used == []
    assert path_candidate.exists()


def test_invalid_metadata_candidate_does_not_fall_back_to_path(tmp_path: Path, monkeypatch):
    root, gcc, cmake, ninja = _metadata_root(tmp_path)
    outside = _write_executable(tmp_path.parent / "outside-gcc.exe")
    path_dir = tmp_path / "path"
    path_gcc = _write_executable(path_dir / "arm-none-eabi-gcc.exe")
    monkeypatch.setenv("PATH", str(path_dir))
    metadata = json.dumps(
        {
            "GNUToolsForSTM32": str(outside),
            "CMake": str(cmake),
            "Ninja": str(ninja),
        }
    ).encode()

    def runner(argv, **kwargs):
        if Path(argv[0]).name == "STM32CubeCLT_metadata.bat":
            return ProcessObservation(0, metadata, b"")
        raise AssertionError("invalid metadata must not probe or select PATH")

    monkeypatch.setattr(support, "_run_bounded", runner)
    profile = discover_tool_support(
        _write_profile(tmp_path, {"cubeCltRoot": str(root)}),
        probe_versions=False,
    )
    issue = next(item for item in profile.issues if item.component == "gcc")
    assert issue.code == "GCC_INVALID"
    assert profile.gcc is None
    assert str(path_gcc) not in issue.remediation


@pytest.mark.parametrize("selected", ["explicit", "cubeclt-metadata", "standard", "path"])
def test_candidate_tier_priority(tmp_path: Path, selected: str):
    paths = {
        source: _write_executable(tmp_path / source / "tool.exe")
        for source in ("explicit", "cubeclt-metadata", "standard", "path")
    }
    tiers = tuple(
        support.CandidateTier(
            source,
            (support.DiscoveryCandidate(paths[source], source),)
            if source == selected or (source == "explicit" and selected == "explicit")
            else (),
        )
        for source in ("explicit", "cubeclt-metadata", "standard", "path")
    )
    result = support._resolve_component(
        "gcc",
        tiers,
        lambda candidate: ToolFact(
            "gcc", candidate.path, "14.3.1", candidate.source, "a" * 64
        ),
    )
    assert result.issue is None
    assert result.fact is not None
    assert result.fact.source == selected


def test_path_tier_rejects_two_distinct_candidates(tmp_path: Path, monkeypatch):
    first = _write_executable(tmp_path / "first" / "STM32CubeMX.exe")
    second = _write_executable(tmp_path / "second" / "STM32CubeMX.exe")
    monkeypatch.setenv("PATH", os.pathsep.join((str(first.parent), str(second.parent))))
    monkeypatch.setattr(support, "_CUBEMX_PATHS", ())
    monkeypatch.setattr(support, "_VS_CODE_PATHS", ())
    monkeypatch.setattr(support, "_CUBECLT_ROOTS", ())
    monkeypatch.setattr(support, "_registry_candidates", lambda component: ())
    monkeypatch.setattr(support, "_windows_file_version", lambda path: "6.18.1")

    profile = discover_tool_support(SupportProfileRequest(data_root=tmp_path))
    assert profile.cubemx is None
    assert any(item.code == "CUBEMX_AMBIGUOUS" for item in profile.issues)


def test_candidate_aliases_to_same_file_are_deduplicated(tmp_path: Path, monkeypatch):
    canonical = _write_executable(tmp_path / "code.exe")
    alias = canonical.parent / "." / canonical.name
    monkeypatch.setattr(support, "_VS_CODE_PATHS", (canonical, alias))
    monkeypatch.setattr(support, "_CUBEMX_PATHS", ())
    monkeypatch.setattr(support, "_CUBECLT_ROOTS", ())
    monkeypatch.setattr(support, "_registry_candidates", lambda component: ())
    monkeypatch.setattr(support, "_windows_file_version", lambda path: "1.133.0")
    monkeypatch.setenv("PATH", "")

    profile = discover_tool_support(SupportProfileRequest(data_root=tmp_path))
    assert profile.vscode is not None
    assert profile.vscode.path == canonical.absolute()
    assert not any(item.code == "VSCODE_AMBIGUOUS" for item in profile.issues)


def test_vscode_hkcu_registration_survives_missing_hklm(tmp_path: Path, monkeypatch):
    vscode = _write_executable(tmp_path / "Code.exe")

    class FakeWinreg:
        HKEY_LOCAL_MACHINE = "HKLM"
        HKEY_CURRENT_USER = "HKCU"

        @staticmethod
        def OpenKey(hive, _subkey):
            if hive == FakeWinreg.HKEY_LOCAL_MACHINE:
                raise OSError("missing HKLM")
            return object()

        @staticmethod
        def QueryValueEx(_key, _name):
            return str(vscode), 1

    monkeypatch.setattr(support.os, "name", "nt")
    monkeypatch.setitem(sys.modules, "winreg", FakeWinreg)
    monkeypatch.setattr(support, "_VS_CODE_PATHS", ())
    monkeypatch.setattr(support, "_CUBEMX_PATHS", ())
    monkeypatch.setattr(support, "_CUBECLT_ROOTS", ())
    monkeypatch.setenv("PATH", "")
    monkeypatch.setattr(support, "_windows_file_version", lambda path: "1.133.0")

    profile = discover_tool_support(SupportProfileRequest(data_root=tmp_path))
    assert profile.vscode is not None
    assert profile.vscode.path == vscode.absolute()
    assert profile.vscode.source == "standard"


@pytest.mark.parametrize(
    ("pe_version", "expected_fact", "expected_issue"),
    [("6.18.1", True, None), (None, False, "CUBEMX_PROBE_FAILED"), ("7.0.0", True, "CUBEMX_UNSUPPORTED")],
)
def test_static_tools_never_execute_cube_mx_or_vscode(
    tmp_path: Path, monkeypatch, pe_version: str | None, expected_fact: bool, expected_issue: str | None
):
    cubemx = _write_executable(tmp_path / "STM32CubeMX.exe")
    vscode = _write_executable(tmp_path / "Code.exe")
    profile_request = _write_profile(
        tmp_path,
        {"cubeMx": {"path": str(cubemx)}, "vsCode": {"path": str(vscode)}},
    )
    monkeypatch.setattr(support, "_CUBECLT_ROOTS", ())
    calls = []
    monkeypatch.setattr(support, "_run_bounded", lambda argv, **kwargs: calls.append(argv))
    monkeypatch.setattr(
        support,
        "_windows_file_version",
        lambda path: pe_version if Path(path) == cubemx else "1.133.0",
    )

    profile = discover_tool_support(profile_request)
    assert profile.cubemx is not None if expected_fact else profile.cubemx is None
    if expected_issue:
        assert expected_issue in {item.code for item in profile.issues}
    assert all(Path(argv[0]) not in {cubemx, vscode} for argv in calls)


@pytest.mark.parametrize(
    ("label", "observation", "expected_issue"),
    [
        ("timeout", ProcessObservation(None, b"", b"", timed_out=True), "GCC_INVALID"),
        ("nonzero", ProcessObservation(1, b"14.3.1", b""), "GCC_INVALID"),
        ("oversize", ProcessObservation(0, b"14.3.1" * 4096, b"", truncated=True), "GCC_INVALID"),
        ("invalid-utf8", ProcessObservation(0, b"\xff", b""), "GCC_INVALID"),
        ("malformed", ProcessObservation(0, b"{not-json", b""), "GCC_INVALID"),
    ],
)
def test_metadata_runner_failures_do_not_fall_back_to_known_layout(
    tmp_path: Path, monkeypatch, label: str, observation: ProcessObservation, expected_issue: str
):
    root, _gcc, cmake, ninja = _metadata_root(tmp_path)
    metadata_path = root / "STM32CubeCLT_metadata.bat"
    monkeypatch.setattr(support, "_CUBECLT_ROOTS", ())

    def runner(argv, **kwargs):
        assert Path(argv[0]) == metadata_path
        return observation

    monkeypatch.setattr(support, "_run_bounded", runner)
    profile = discover_tool_support(
        _write_profile(tmp_path, {"cubeCltRoot": str(root)}),
        probe_versions=False,
    )
    assert profile.gcc is None, label
    assert expected_issue in {item.code for item in profile.issues}


@pytest.mark.parametrize("kind", ["redirect", "non-file"])
def test_metadata_candidate_path_evidence_is_closed(tmp_path: Path, monkeypatch, kind: str):
    root, _gcc, cmake, ninja = _metadata_root(tmp_path)
    if kind == "redirect":
        value = str(tmp_path.parent / "outside-gcc.exe")
        _write_executable(Path(value))
    else:
        value = str(root / "GNU-tools-for-STM32" / "bin")
    payload = json.dumps({"GNUToolsForSTM32": value, "CMake": str(cmake), "Ninja": str(ninja)}).encode()
    metadata_path = root / "STM32CubeCLT_metadata.bat"
    monkeypatch.setattr(support, "_CUBECLT_ROOTS", ())

    def runner(argv, **kwargs):
        assert Path(argv[0]) == metadata_path
        return ProcessObservation(0, payload, b"")

    monkeypatch.setattr(support, "_run_bounded", runner)
    profile = discover_tool_support(
        _write_profile(tmp_path, {"cubeCltRoot": str(root)}), probe_versions=False
    )
    assert profile.gcc is None
    assert any(item.code == "GCC_INVALID" for item in profile.issues)


@pytest.mark.parametrize(
    ("native_observation", "expected_fact", "expected_issue"),
    [
        (ProcessObservation(0, b"arm-none-eabi-gcc 14.3.1\n", b""), True, None),
        (ProcessObservation(0, b"arm-none-eabi-gcc 9.9.9\n", b""), True, "GCC_UNSUPPORTED"),
        (ProcessObservation(1, b"14.3.1\n", b""), False, "GCC_PROBE_FAILED"),
        (ProcessObservation(None, b"", b"", timed_out=True), False, "GCC_PROBE_FAILED"),
    ],
)
def test_native_version_runner_outcomes_are_closed(
    tmp_path: Path, monkeypatch, native_observation: ProcessObservation, expected_fact: bool, expected_issue: str | None
):
    root, gcc, cmake, ninja = _metadata_root(tmp_path)
    metadata_path = root / "STM32CubeCLT_metadata.bat"
    metadata = json.dumps({"GNUToolsForSTM32": str(gcc), "CMake": str(cmake), "Ninja": str(ninja)}).encode()
    monkeypatch.setattr(support, "_CUBECLT_ROOTS", ())

    def runner(argv, **kwargs):
        if Path(argv[0]) == metadata_path:
            return ProcessObservation(0, metadata, b"")
        name = Path(argv[0]).name
        if name == gcc.name:
            return native_observation
        return ProcessObservation(0, b"14.3.1\n", b"")

    monkeypatch.setattr(support, "_run_bounded", runner)
    profile = discover_tool_support(
        _write_profile(tmp_path, {"cubeCltRoot": str(root)})
    )
    assert (profile.gcc is not None) is expected_fact
    if expected_issue:
        assert expected_issue in {item.code for item in profile.issues}
