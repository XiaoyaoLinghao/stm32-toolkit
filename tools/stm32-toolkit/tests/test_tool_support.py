from __future__ import annotations

import hashlib
import io
import json
import os
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
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


def test_overlapping_discoveries_keep_static_issues_on_their_own_call(tmp_path: Path, monkeypatch):
    barrier = threading.Barrier(2)
    invalid_returned = threading.Event()
    missing_written = threading.Event()
    local = threading.local()

    class InterleavingIssues(dict[str, ToolSupportIssue]):
        def clear(self):
            # The pre-fix implementation clears this process-global store for
            # every call. Keep the seam stable while forcing the overwrite.
            return None

        def __setitem__(self, key, value):
            super().__setitem__(key, value)
            if getattr(local, "marker", None) == "missing" and key == "cubeMx":
                missing_written.set()

        def get(self, key, default=None):
            if getattr(local, "marker", None) == "invalid" and key == "cubeMx":
                assert missing_written.wait(2)
            return super().get(key, default)

    monkeypatch.setattr(support, "_LAST_DISCOVERY_ISSUES", InterleavingIssues(), raising=False)
    monkeypatch.setattr(support, "_CUBECLT_ROOTS", ())
    monkeypatch.setattr(support, "_standard_tier", lambda component: support.CandidateTier("standard", ()))
    monkeypatch.setattr(support, "_path_tier", lambda component: support.CandidateTier("path", ()))

    def fake_static(payload, component, *, probe_versions):
        if component == "cubeMx":
            barrier.wait(2)
            if local.marker == "invalid":
                invalid_returned.set()
            else:
                assert invalid_returned.wait(2)
            issue = ToolSupportIssue(
                "CUBEMX_INVALID" if local.marker == "invalid" else "CUBEMX_MISSING",
                "cubeMx",
                local.marker,
            )
            return support.CandidateResolution(None, issue)
        return support.CandidateResolution(
            None, ToolSupportIssue("VSCODE_MISSING", "vsCode", "missing")
        )

    monkeypatch.setattr(support, "_resolve_static", fake_static)

    def discover(marker: str):
        local.marker = marker
        profile = discover_tool_support(
            SupportProfileRequest(data_root=tmp_path), probe_versions=False
        )
        return {issue.code for issue in profile.issues}

    with ThreadPoolExecutor(max_workers=2) as executor:
        invalid = executor.submit(discover, "invalid")
        missing = executor.submit(discover, "missing")

    assert "CUBEMX_INVALID" in invalid.result()
    assert "CUBEMX_MISSING" in missing.result()


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


def test_stale_app_paths_value_is_invalid_registry_evidence(tmp_path: Path, monkeypatch):
    stale = tmp_path / "uninstalled" / "Code.exe"

    class FakeWinreg:
        HKEY_LOCAL_MACHINE = "HKLM"
        HKEY_CURRENT_USER = "HKCU"

        @staticmethod
        def OpenKey(hive, _subkey):
            if hive == FakeWinreg.HKEY_LOCAL_MACHINE:
                return object()
            raise OSError("missing HKCU")

        @staticmethod
        def QueryValueEx(_key, _name):
            return str(stale), 1

    monkeypatch.setattr(support.os, "name", "nt")
    monkeypatch.setitem(sys.modules, "winreg", FakeWinreg)
    monkeypatch.setattr(support, "_VS_CODE_PATHS", ())
    monkeypatch.setattr(support, "_CUBEMX_PATHS", ())
    monkeypatch.setattr(support, "_CUBECLT_ROOTS", ())
    monkeypatch.setenv("PATH", "")

    profile = discover_tool_support(SupportProfileRequest(data_root=tmp_path), probe_versions=False)

    assert profile.vscode is None
    assert any(issue.code == "VSCODE_INVALID" for issue in profile.issues)


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


class _RunnerStream:
    def __init__(self, payload: bytes):
        self._stream = io.BytesIO(payload)

    def read(self, size: int = -1) -> bytes:
        return self._stream.read(size)

    def close(self) -> None:
        self._stream.close()


def test_bounded_runner_has_one_total_capture_limit_and_marks_oversize(monkeypatch):
    capture_limit = 32

    class FakeProcess:
        returncode = 0

        def __init__(self):
            self.stdout = _RunnerStream(b"o" * (capture_limit + 9))
            self.stderr = _RunnerStream(b"e" * (capture_limit + 9))
            self.terminated = False
            self.killed = False
            self.wait_calls = 0

        def communicate(self, timeout=None):
            return (
                b"o" * (capture_limit + 9),
                b"e" * (capture_limit + 9),
            )

        def wait(self, timeout=None):
            self.wait_calls += 1
            return self.returncode

        def terminate(self):
            self.terminated = True

        def kill(self):
            self.killed = True

    process = FakeProcess()
    seen = {}

    def popen(argv, **kwargs):
        seen.update(kwargs)
        return process

    monkeypatch.setattr(support, "_REAL_POPEN", popen)
    observation = support._run_bounded(("tool",), capture_limit=capture_limit)

    assert observation.truncated is True
    assert len(observation.stdout) + len(observation.stderr) <= capture_limit
    assert seen["shell"] is False
    assert seen["stdin"] is subprocess.DEVNULL


def test_bounded_runner_timeout_terminates_and_reaps(monkeypatch):
    class TimeoutProcess:
        returncode = None

        def __init__(self):
            self.stdout = _RunnerStream(b"")
            self.stderr = _RunnerStream(b"")
            self.terminated = False
            self.killed = False
            self.wait_calls = 0

        def communicate(self, timeout=None):
            raise subprocess.TimeoutExpired(["tool"], timeout)

        def wait(self, timeout=None):
            self.wait_calls += 1
            if not self.terminated:
                raise subprocess.TimeoutExpired(["tool"], timeout)
            self.returncode = -15
            return self.returncode

        def terminate(self):
            self.terminated = True

        def kill(self):
            self.killed = True

    process = TimeoutProcess()
    monkeypatch.setattr(support, "_REAL_POPEN", lambda argv, **kwargs: process)

    observation = support._run_bounded(("tool",), timeout_seconds=0.01)

    assert observation.timed_out is True
    assert process.terminated is True
    assert process.wait_calls >= 1


@pytest.mark.parametrize(
    ("label", "payload"),
    [
        ("unknown-key", {"ambient": True}),
        ("malformed-tools", {"tools": []}),
        ("wrong-tool-entry", {"gcc": "not-an-entry"}),
        ("extension-value", {"vsCodeExtensions": {"ms-vscode.cpptools": 1}}),
    ],
)
def test_support_profile_schema_is_closed_without_ambient_fallback(
    tmp_path: Path, monkeypatch, label: str, payload: dict[str, object]
):
    profile_path = tmp_path / f"{label}.json"
    profile_path.write_text(json.dumps(payload), encoding="utf-8")
    candidate = _write_executable(tmp_path / "path" / "arm-none-eabi-gcc.exe")
    monkeypatch.setenv("PATH", str(candidate.parent))
    monkeypatch.setattr(support, "_CUBECLT_ROOTS", ())
    monkeypatch.setattr(support, "_CUBEMX_PATHS", ())
    monkeypatch.setattr(support, "_VS_CODE_PATHS", ())
    monkeypatch.setattr(support, "_registry_candidates", lambda component: ())
    calls = []
    monkeypatch.setattr(support, "_run_bounded", lambda argv, **kwargs: calls.append(argv))

    with pytest.raises(SupportProfileError):
        discover_tool_support(SupportProfileRequest(profile_path=profile_path, data_root=tmp_path))

    assert calls == []
    assert candidate.exists()


@pytest.mark.parametrize(
    ("label", "content"),
    [
        ("oversize", b"{}" + b" " * (support._MAX_METADATA_BYTES + 1)),
        ("invalid-utf8", b"\xff"),
        ("invalid-json", b"{not-json"),
    ],
    ids=["oversize", "invalid-utf8", "invalid-json"],
)
def test_support_profile_content_failures_are_closed(
    tmp_path: Path, label: str, content: bytes
):
    profile_path = tmp_path / f"{label}.json"
    profile_path.write_bytes(content)

    with pytest.raises(SupportProfileError):
        discover_tool_support(SupportProfileRequest(profile_path=profile_path, data_root=tmp_path))


def test_missing_support_profile_is_closed(tmp_path: Path):
    with pytest.raises(SupportProfileError):
        discover_tool_support(
            SupportProfileRequest(profile_path=tmp_path / "missing.json", data_root=tmp_path)
        )


@pytest.mark.parametrize(
    ("version", "supported"),
    [("6.18.1", True), ("6.18.1-RC2", True), ("6.180.0", False), ("6.18x", False)],
)
def test_cubemx_version_requires_dotted_618_prefix(
    tmp_path: Path, monkeypatch, version: str, supported: bool
):
    cubemx = _write_executable(tmp_path / "STM32CubeMX.exe")
    monkeypatch.setattr(support, "_CUBECLT_ROOTS", ())
    monkeypatch.setattr(support, "_CUBEMX_PATHS", ())
    monkeypatch.setattr(support, "_VS_CODE_PATHS", ())
    monkeypatch.setattr(support, "_registry_candidates", lambda component: ())
    monkeypatch.setenv("PATH", "")
    profile = discover_tool_support(
        _write_profile(tmp_path, {"cubeMx": {"path": str(cubemx), "version": version}}),
        probe_versions=False,
    )

    assert (profile.cubemx is not None) is True
    assert ("CUBEMX_UNSUPPORTED" in {issue.code for issue in profile.issues}) is (not supported)


def _support_tree_snapshot(root: Path) -> tuple[tuple[str, str, bytes | None], ...]:
    entries: list[tuple[str, str, bytes | None]] = []
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        relative = path.relative_to(root).as_posix()
        if path.is_dir():
            entries.append((relative, "directory", None))
        else:
            entries.append((relative, "file", path.read_bytes()))
    return tuple(entries)


def _nested_public_profile_fixture(tmp_path: Path) -> tuple[Path, Path, dict[str, object], dict[str, Path]]:
    root = tmp_path / "cubeclt"
    root.mkdir()
    specifications = {
        "cubeMx": ("CubeMX/STM32CubeMX.exe", "6.18.1"),
        "vsCode": ("VSCode/Code.exe", "1.133.0"),
        "gcc": ("GNU-tools-for-STM32/bin/arm-none-eabi-gcc.exe", "14.3.1"),
        "cmake": ("CMake/bin/cmake.exe", "4.3.1"),
        "ninja": ("Ninja/bin/ninja.exe", "1.13.2"),
    }
    paths: dict[str, Path] = {}
    entries: dict[str, dict[str, str]] = {}
    for name, (relative, version) in specifications.items():
        path = _write_executable(root / relative, name.encode("ascii"))
        paths[name] = path
        entries[name] = {"path": str(path), "version": version}
    payload: dict[str, object] = {"cubeCltRoot": str(root), "tools": entries}
    profile = tmp_path / "profile.json"
    profile.write_text(json.dumps(payload), encoding="utf-8")
    return root, profile, payload, paths


def _metadata_public_fixture(tmp_path: Path) -> tuple[Path, Path, Path, dict[str, Path]]:
    root = tmp_path / "cubeclt"
    root.mkdir()
    static_paths = {
        "cubeMx": _write_executable(root / "CubeMX" / "STM32CubeMX.exe", b"cube-mx"),
        "vsCode": _write_executable(root / "VSCode" / "Code.exe", b"vs-code"),
    }
    build_paths = {
        "gcc": _write_executable(root / "GNU-tools-for-STM32" / "bin" / "arm-none-eabi-gcc.exe", b"gcc"),
        "cmake": _write_executable(root / "CMake" / "bin" / "cmake.exe", b"cmake"),
        "ninja": _write_executable(root / "Ninja" / "bin" / "ninja.exe", b"ninja"),
    }
    metadata = _write_executable(root / "STM32CubeCLT_metadata.bat", b"metadata")
    payload: dict[str, object] = {
        "cubeCltRoot": str(root),
        "cubeMx": {"path": str(static_paths["cubeMx"]), "version": "6.18.1"},
        "vsCode": {"path": str(static_paths["vsCode"]), "version": "1.133.0"},
    }
    request = _write_profile(tmp_path, payload)
    return root, metadata, request.profile_path, {**static_paths, **build_paths}


def test_public_profile_rejects_valid_json_nonobject_without_dispatch(tmp_path: Path, monkeypatch):
    _root, profile, _payload, _paths = _nested_public_profile_fixture(tmp_path)
    profile.write_text("[]", encoding="utf-8")
    calls: list[tuple[str, ...]] = []

    def runner(argv, **kwargs):
        calls.append(tuple(argv))
        raise AssertionError("schema refusal must precede bounded provider dispatch")

    monkeypatch.setattr(support, "_run_bounded", runner)
    before = _support_tree_snapshot(tmp_path)
    with pytest.raises(SupportProfileError, match="^support profile schema is invalid$"):
        discover_tool_support(SupportProfileRequest(profile_path=profile, data_root=tmp_path), probe_versions=False)
    assert calls == []
    assert _support_tree_snapshot(tmp_path) == before


def test_public_profile_requires_trusted_data_root_without_dispatch(tmp_path: Path, monkeypatch):
    _root, profile, _payload, _paths = _nested_public_profile_fixture(tmp_path)
    calls: list[tuple[str, ...]] = []

    def runner(argv, **kwargs):
        calls.append(tuple(argv))
        raise AssertionError("trust refusal must precede bounded provider dispatch")

    monkeypatch.setattr(support, "_run_bounded", runner)
    before = _support_tree_snapshot(tmp_path)
    with pytest.raises(SupportProfileError, match="^support profile is outside trusted data root$"):
        discover_tool_support(SupportProfileRequest(profile_path=profile, data_root=None), probe_versions=False)
    assert calls == []
    assert _support_tree_snapshot(tmp_path) == before


def test_public_profile_accepts_nested_tools_entries_and_returns_wire(tmp_path: Path, monkeypatch):
    root, profile, _payload, paths = _nested_public_profile_fixture(tmp_path)
    calls: list[tuple[str, ...]] = []

    def runner(argv, **kwargs):
        calls.append(tuple(argv))
        raise AssertionError("explicit profile versions must avoid process probes")

    monkeypatch.setattr(support, "_run_bounded", runner)
    before = _support_tree_snapshot(tmp_path)
    discovered = discover_tool_support(
        SupportProfileRequest(profile_path=profile, data_root=tmp_path),
        probe_versions=False,
    )
    wire = discovered.to_dict()
    assert discovered.cubeclt_root == root.resolve()
    assert {name: getattr(discovered, name).source for name in paths} == {
        name: "explicit" for name in paths
    }
    assert {name: getattr(discovered, name).version for name in paths} == {
        "cubeMx": "6.18.1",
        "vsCode": "1.133.0",
        "gcc": "14.3.1",
        "cmake": "4.3.1",
        "ninja": "1.13.2",
    }
    assert discovered.issues == ()
    assert wire["cubeCltRoot"] == root.resolve().as_posix()
    assert all(wire[name]["source"] == "explicit" for name in paths)
    assert all(wire[name]["executableSha256"] == hashlib.sha256(paths[name].read_bytes()).hexdigest() for name in paths)
    assert calls == []
    assert _support_tree_snapshot(tmp_path) == before


def test_public_profile_rejects_duplicate_cubeclt_root_keys_without_dispatch(tmp_path: Path, monkeypatch):
    _root, profile, payload, _paths = _nested_public_profile_fixture(tmp_path)
    payload["cubeclt_root"] = payload["cubeCltRoot"]
    profile.write_text(json.dumps(payload), encoding="utf-8")
    calls: list[tuple[str, ...]] = []

    def runner(argv, **kwargs):
        calls.append(tuple(argv))
        raise AssertionError("schema refusal must precede bounded provider dispatch")

    monkeypatch.setattr(support, "_run_bounded", runner)
    before = _support_tree_snapshot(tmp_path)
    with pytest.raises(SupportProfileError, match="^support profile schema is invalid$"):
        discover_tool_support(SupportProfileRequest(profile_path=profile, data_root=tmp_path), probe_versions=False)
    assert calls == []
    assert _support_tree_snapshot(tmp_path) == before


def test_public_profile_rejects_missing_cubeclt_root_without_dispatch(tmp_path: Path, monkeypatch):
    _root, profile, payload, _paths = _nested_public_profile_fixture(tmp_path)
    payload["cubeCltRoot"] = str(tmp_path / "missing-cubeclt-root")
    profile.write_text(json.dumps(payload), encoding="utf-8")
    calls: list[tuple[str, ...]] = []

    def runner(argv, **kwargs):
        calls.append(tuple(argv))
        raise AssertionError("root validation must precede bounded provider dispatch")

    monkeypatch.setattr(support, "_run_bounded", runner)
    before = _support_tree_snapshot(tmp_path)
    with pytest.raises(SupportProfileError, match="^support profile cubeclt root is invalid$"):
        discover_tool_support(SupportProfileRequest(profile_path=profile, data_root=tmp_path), probe_versions=False)
    assert calls == []
    assert _support_tree_snapshot(tmp_path) == before


def test_public_profile_rejects_unknown_nested_entry_key_without_dispatch(tmp_path: Path, monkeypatch):
    _root, profile, payload, _paths = _nested_public_profile_fixture(tmp_path)
    payload["tools"]["gcc"]["unexpected"] = True  # type: ignore[index]
    profile.write_text(json.dumps(payload), encoding="utf-8")
    calls: list[tuple[str, ...]] = []

    def runner(argv, **kwargs):
        calls.append(tuple(argv))
        raise AssertionError("entry schema refusal must precede bounded provider dispatch")

    monkeypatch.setattr(support, "_run_bounded", runner)
    before = _support_tree_snapshot(tmp_path)
    with pytest.raises(SupportProfileError, match="^support profile schema is invalid$"):
        discover_tool_support(SupportProfileRequest(profile_path=profile, data_root=tmp_path), probe_versions=False)
    assert calls == []
    assert _support_tree_snapshot(tmp_path) == before


def test_public_profile_rejects_nonregular_nested_candidate_without_dispatch(tmp_path: Path, monkeypatch):
    root, profile, payload, _paths = _nested_public_profile_fixture(tmp_path)
    invalid = root / "bad-gcc.exe"
    invalid.mkdir()
    payload["tools"]["gcc"]["path"] = str(invalid)  # type: ignore[index]
    profile.write_text(json.dumps(payload), encoding="utf-8")
    calls: list[tuple[str, ...]] = []

    def runner(argv, **kwargs):
        calls.append(tuple(argv))
        raise AssertionError("candidate validation must precede bounded provider dispatch")

    monkeypatch.setattr(support, "_run_bounded", runner)
    before = _support_tree_snapshot(tmp_path)
    with pytest.raises(SupportProfileError, match="^support profile candidate is invalid$"):
        discover_tool_support(SupportProfileRequest(profile_path=profile, data_root=tmp_path), probe_versions=False)
    assert calls == []
    assert _support_tree_snapshot(tmp_path) == before


def test_public_metadata_resolves_relative_paths_and_dispatches_expected_probes(tmp_path: Path, monkeypatch):
    root, metadata_path, profile, paths = _metadata_public_fixture(tmp_path)
    metadata = json.dumps(
        {
            "gcc": "GNU-tools-for-STM32/bin/arm-none-eabi-gcc.exe",
            "cmake": "CMake/bin/cmake.exe",
            "ninja": "Ninja/bin/ninja.exe",
        }
    ).encode()
    versions = {"arm-none-eabi-gcc.exe": b"arm-none-eabi-gcc 14.3.1\n", "cmake.exe": b"cmake version 4.3.1\n", "ninja.exe": b"1.13.2\n"}
    calls: list[tuple[str, ...]] = []

    def runner(argv, **kwargs):
        call = tuple(argv)
        calls.append(call)
        if Path(argv[0]).name == metadata_path.name:
            assert call == (str(metadata_path), "-j")
            return ProcessObservation(0, metadata, b"")
        assert call[1:] == ("--version",)
        return ProcessObservation(0, versions[Path(argv[0]).name], b"")

    monkeypatch.setattr(support, "_run_bounded", runner)
    before = _support_tree_snapshot(tmp_path)
    discovered = discover_tool_support(
        SupportProfileRequest(profile_path=profile, data_root=tmp_path),
        probe_versions=True,
    )
    assert {name: getattr(discovered, name).source for name in ("gcc", "cmake", "ninja")} == {
        "gcc": "cubeclt-metadata",
        "cmake": "cubeclt-metadata",
        "ninja": "cubeclt-metadata",
    }
    assert {name: getattr(discovered, name).version for name in ("gcc", "cmake", "ninja")} == {
        "gcc": "14.3.1",
        "cmake": "4.3.1",
        "ninja": "1.13.2",
    }
    assert {name: getattr(discovered, name).path for name in ("gcc", "cmake", "ninja")} == {
        "gcc": paths["gcc"].resolve(),
        "cmake": paths["cmake"].resolve(),
        "ninja": paths["ninja"].resolve(),
    }
    assert discovered.issues == ()
    assert calls == [
        (str(metadata_path), "-j"),
        (str(paths["gcc"].resolve()), "--version"),
        (str(paths["cmake"].resolve()), "--version"),
        (str(paths["ninja"].resolve()), "--version"),
    ]
    assert _support_tree_snapshot(tmp_path) == before
    assert root.is_dir()


def test_public_metadata_directory_marker_is_invalid_without_fallback(tmp_path: Path, monkeypatch):
    root, metadata_path, profile, _paths = _metadata_public_fixture(tmp_path)
    metadata_path.unlink()
    metadata_path.mkdir()
    monkeypatch.setenv("PATH", "")
    calls: list[tuple[str, ...]] = []

    def runner(argv, **kwargs):
        calls.append(tuple(argv))
        raise AssertionError("unsafe metadata marker must not be dispatched")

    monkeypatch.setattr(support, "_run_bounded", runner)
    before = _support_tree_snapshot(tmp_path)
    discovered = discover_tool_support(
        SupportProfileRequest(profile_path=profile, data_root=tmp_path),
        probe_versions=False,
    )
    assert discovered.gcc is None and discovered.cmake is None and discovered.ninja is None
    assert {issue.code for issue in discovered.issues} == {"CMAKE_INVALID", "GCC_INVALID", "NINJA_INVALID"}
    assert {issue.remediation for issue in discovered.issues} == {"Provide a safe supported executable."}
    assert calls == []
    assert _support_tree_snapshot(tmp_path) == before
    assert root.is_dir()


@pytest.mark.parametrize(
    ("label", "payload"),
    [
        ("nonobject", b"[]"),
        ("known-nonstring", b'{"gcc": 123}'),
        ("no-component-alias", b'{"other": "value"}'),
    ],
)
def test_public_metadata_wire_invalidations_refuse_fallback(
    tmp_path: Path, monkeypatch, label: str, payload: bytes
):
    _root, metadata_path, profile, _paths = _metadata_public_fixture(tmp_path)
    monkeypatch.setenv("PATH", "")
    calls: list[tuple[str, ...]] = []

    def runner(argv, **kwargs):
        call = tuple(argv)
        calls.append(call)
        assert call == (str(metadata_path), "-j"), label
        return ProcessObservation(0, payload, b"")

    monkeypatch.setattr(support, "_run_bounded", runner)
    before = _support_tree_snapshot(tmp_path)
    discovered = discover_tool_support(
        SupportProfileRequest(profile_path=profile, data_root=tmp_path),
        probe_versions=False,
    )
    assert discovered.gcc is None and discovered.cmake is None and discovered.ninja is None
    assert {issue.code for issue in discovered.issues} == {"CMAKE_INVALID", "GCC_INVALID", "NINJA_INVALID"}, label
    assert calls == [(str(metadata_path), "-j")], label
    assert _support_tree_snapshot(tmp_path) == before


def test_public_metadata_candidate_directory_is_invalid_without_path_fallback(tmp_path: Path, monkeypatch):
    root, metadata_path, profile, _paths = _metadata_public_fixture(tmp_path)
    candidate = root / "GNU-tools-for-STM32" / "bin" / "arm-none-eabi-gcc.exe"
    candidate.unlink()
    candidate.mkdir(parents=True)
    payload = json.dumps({"gcc": "GNU-tools-for-STM32/bin/arm-none-eabi-gcc.exe"}).encode()
    monkeypatch.setenv("PATH", "")
    calls: list[tuple[str, ...]] = []

    def runner(argv, **kwargs):
        call = tuple(argv)
        calls.append(call)
        assert call == (str(metadata_path), "-j")
        return ProcessObservation(0, payload, b"")

    monkeypatch.setattr(support, "_run_bounded", runner)
    before = _support_tree_snapshot(tmp_path)
    discovered = discover_tool_support(
        SupportProfileRequest(profile_path=profile, data_root=tmp_path),
        probe_versions=False,
    )
    assert discovered.gcc is None
    gcc_issue = next(issue for issue in discovered.issues if issue.component == "gcc")
    assert gcc_issue.code == "GCC_INVALID"
    assert gcc_issue.remediation == "Provide a safe supported executable."
    assert discovered.cmake is None and discovered.ninja is None
    assert {issue.code for issue in discovered.issues} == {"CMAKE_INVALID", "GCC_INVALID", "NINJA_INVALID"}
    assert calls == [(str(metadata_path), "-j")]
    assert _support_tree_snapshot(tmp_path) == before
