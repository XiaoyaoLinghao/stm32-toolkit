from __future__ import annotations

import copy
import ctypes as real_ctypes
import json
import subprocess
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest
import stm32_toolkit.tool_support as support
from stm32_toolkit.tool_support import (
    SupportProfileError,
    SupportProfileRequest,
    discover_tool_support,
)
from test_tool_support import (
    _nested_public_profile_fixture,
    _RunnerStream,
    _support_tree_snapshot,
)


def _write_payload(profile: Path, payload: dict[str, object]) -> None:
    profile.write_text(json.dumps(payload), encoding="utf-8")


class _ScopedVersionInfo(tuple):
    def __new__(cls, major: int, minor: int, micro: int):
        return super().__new__(cls, (major, minor, micro, "final", 0))

    @property
    def major(self) -> int:
        return self[0]

    @property
    def minor(self) -> int:
        return self[1]

    @property
    def micro(self) -> int:
        return self[2]


@pytest.mark.parametrize(
    "variant",
    ["nested-gcc-list", "duplicate-top-level-gcc"],
    ids=["nested-gcc-list", "duplicate-top-level-gcc"],
)
def test_public_profile_admission_rejects_invalid_nested_schema_before_dispatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, variant: str
):
    _root, profile, payload, _paths = _nested_public_profile_fixture(tmp_path)
    original_payload = copy.deepcopy(payload)
    original_snapshot = _support_tree_snapshot(tmp_path)
    tools = payload["tools"]
    assert isinstance(tools, dict)
    if variant == "nested-gcc-list":
        tools["gcc"] = [tools["gcc"]]
    else:
        payload["gcc"] = copy.deepcopy(tools["gcc"])
    _write_payload(profile, payload)
    arranged_snapshot = _support_tree_snapshot(tmp_path)
    dispatches: list[tuple[object, dict[str, object]]] = []

    def unexpected_dispatch(argv: object, **kwargs: object) -> object:
        dispatches.append((argv, kwargs))
        raise AssertionError("schema refusal must precede provider dispatch")

    monkeypatch.setattr(support, "_REAL_POPEN", unexpected_dispatch)
    with pytest.raises(SupportProfileError, match="^support profile schema is invalid$"):
        discover_tool_support(
            SupportProfileRequest(profile_path=profile, data_root=tmp_path),
            probe_versions=False,
        )
    assert dispatches == []
    assert _support_tree_snapshot(tmp_path) == arranged_snapshot

    _write_payload(profile, original_payload)
    recovered = discover_tool_support(
        SupportProfileRequest(profile_path=profile, data_root=tmp_path),
        probe_versions=False,
    )
    assert recovered.issues == ()
    assert _support_tree_snapshot(tmp_path) == original_snapshot


def test_public_profile_scoped_python_311_provider_preserves_facts_and_reports_issue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _root, profile, _payload, _paths = _nested_public_profile_fixture(tmp_path)
    control_snapshot = _support_tree_snapshot(tmp_path)
    control = discover_tool_support(
        SupportProfileRequest(profile_path=profile, data_root=tmp_path),
        probe_versions=False,
    )
    control_wire = control.to_dict()
    original_provider = support.sys
    original_global_version_info = sys.version_info
    dispatches: list[tuple[object, dict[str, object]]] = []

    def unexpected_dispatch(argv: object, **kwargs: object) -> object:
        dispatches.append((argv, kwargs))
        raise AssertionError("declared versions must avoid process dispatch")

    monkeypatch.setattr(support, "_REAL_POPEN", unexpected_dispatch)
    scoped_version_info = _ScopedVersionInfo(3, 11, 7)
    monkeypatch.setattr(
        support,
        "sys",
        SimpleNamespace(version_info=scoped_version_info),
    )
    assert scoped_version_info[:2] == (3, 11)
    assert (scoped_version_info.major, scoped_version_info.minor, scoped_version_info.micro) == (
        3,
        11,
        7,
    )
    qualified = discover_tool_support(
        SupportProfileRequest(profile_path=profile, data_root=tmp_path),
        probe_versions=False,
    )
    expected_wire = copy.deepcopy(control_wire)
    expected_wire["pythonVersion"] = "3.11.7"
    expected_wire["issues"] = [
        {
            "code": "PYTHON_UNSUPPORTED",
            "component": "python",
            "remediation": "Use CPython >=3.12,<3.13.",
        }
    ]
    assert qualified.to_dict() == expected_wire
    assert qualified.gcc == control.gcc
    assert qualified.cmake == control.cmake
    assert qualified.ninja == control.ninja
    assert qualified.cubemx == control.cubemx
    assert qualified.vscode == control.vscode
    assert dispatches == []
    assert support.sys is not original_provider
    assert sys.version_info is original_global_version_info
    monkeypatch.setattr(support, "sys", original_provider)
    recovered = discover_tool_support(
        SupportProfileRequest(profile_path=profile, data_root=tmp_path),
        probe_versions=False,
    )
    assert recovered.to_dict() == control_wire
    assert _support_tree_snapshot(tmp_path) == control_snapshot


class _TrackedStream(_RunnerStream):
    def __init__(self, payload: bytes):
        super().__init__(payload)
        self.finished = threading.Event()

    def read(self, size: int = -1) -> bytes:
        result = super().read(size)
        if not result:
            self.finished.set()
        return result


class _ReadErrorStream(_RunnerStream):
    def __init__(self):
        super().__init__(b"")
        self.finished = threading.Event()

    def read(self, size: int = -1) -> bytes:
        self.finished.set()
        raise OSError("stream read failed")


class _ImmediateProcess:
    returncode = 0

    def __init__(self, stdout: _RunnerStream, stderr: _RunnerStream):
        self.stdout = stdout
        self.stderr = stderr
        self.events: list[tuple[str, object]] = []

    def wait(self, timeout: float | None = None) -> int:
        self.events.append(("wait", timeout))
        return self.returncode

    def terminate(self) -> None:
        self.events.append(("terminate", None))

    def kill(self) -> None:
        self.events.append(("kill", None))


class _TimeoutProcess(_ImmediateProcess):
    returncode = None

    def __init__(self):
        super().__init__(_TrackedStream(b""), _TrackedStream(b""))

    def wait(self, timeout: float | None = None) -> int:
        self.events.append(("wait", timeout))
        waits = sum(name == "wait" for name, _value in self.events)
        if waits < 3:
            raise subprocess.TimeoutExpired(["arm-none-eabi-gcc.exe", "--version"], timeout)
        self.returncode = -9
        return self.returncode

    def terminate(self) -> None:
        self.events.append(("terminate", None))
        raise OSError("terminate failed")

    def kill(self) -> None:
        self.events.append(("kill", None))


def _gcc_failure_control(
    tmp_path: Path,
):
    _root, profile, payload, paths = _nested_public_profile_fixture(tmp_path)
    control = discover_tool_support(
        SupportProfileRequest(profile_path=profile, data_root=tmp_path),
        probe_versions=True,
    )
    control_wire = control.to_dict()
    original_payload = copy.deepcopy(payload)
    tools = payload["tools"]
    assert isinstance(tools, dict)
    gcc_entry = tools["gcc"]
    assert isinstance(gcc_entry, dict)
    gcc_entry.pop("version")
    _write_payload(profile, payload)
    return profile, original_payload, paths["gcc"], control_wire


@pytest.mark.parametrize(
    "failure",
    ["spawn-oserror", "read-oserror", "invalid-utf8", "timeout-reap"],
    ids=["spawn-oserror", "read-oserror", "invalid-utf8", "timeout-reap"],
)
def test_public_gcc_probe_adapter_failures_are_bounded_and_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
):
    profile, original_payload, gcc_path, control_wire = _gcc_failure_control(tmp_path)
    arranged_snapshot = _support_tree_snapshot(tmp_path)
    popen_calls: list[tuple[tuple[str, ...], dict[str, object]]] = []
    processes: list[_ImmediateProcess] = []

    def popen(argv: tuple[str, ...], **kwargs: object) -> _ImmediateProcess:
        popen_calls.append((tuple(argv), kwargs))
        if failure == "spawn-oserror":
            raise OSError("spawn failed")
        if failure == "read-oserror":
            process = _ImmediateProcess(_ReadErrorStream(), _ReadErrorStream())
        elif failure == "invalid-utf8":
            process = _ImmediateProcess(_TrackedStream(b"\xff"), _TrackedStream(b""))
        else:
            process = _TimeoutProcess()
        processes.append(process)
        return process

    monkeypatch.setattr(support, "_REAL_POPEN", popen)
    monkeypatch.setenv("PATH", "")
    result = discover_tool_support(
        SupportProfileRequest(profile_path=profile, data_root=tmp_path),
        probe_versions=True,
    )
    expected_wire = copy.deepcopy(control_wire)
    expected_wire["gcc"] = None
    expected_wire["issues"] = [
        {
            "code": "GCC_PROBE_FAILED",
            "component": "gcc",
            "remediation": "Provide readable supported version evidence.",
        }
    ]
    assert result.to_dict() == expected_wire
    assert result.gcc is None
    assert [issue.code for issue in result.issues] == ["GCC_PROBE_FAILED"]
    assert len(popen_calls) == 1
    argv, kwargs = popen_calls[0]
    assert argv == (str(gcc_path.resolve()), "--version")
    assert kwargs["shell"] is False
    assert kwargs["stdin"] is subprocess.DEVNULL
    assert kwargs["stdout"] is subprocess.PIPE
    assert kwargs["stderr"] is subprocess.PIPE
    if failure == "spawn-oserror":
        assert processes == []
    else:
        assert len(processes) == 1
        process = processes[0]
        assert isinstance(process.stdout, _RunnerStream)
        assert isinstance(process.stderr, _RunnerStream)
        assert process.stdout.finished.is_set()
        assert process.stderr.finished.is_set()
        if failure == "timeout-reap":
            assert [name for name, _value in process.events] == [
                "wait",
                "terminate",
                "wait",
                "kill",
                "wait",
            ]
            assert process.events[0][1] == 5.0
            assert process.events[2][1] == 1
            assert process.events[4][1] == 1
            assert process.returncode == -9
    assert _support_tree_snapshot(tmp_path) == arranged_snapshot

    _write_payload(profile, original_payload)
    recovered = discover_tool_support(
        SupportProfileRequest(profile_path=profile, data_root=tmp_path),
        probe_versions=True,
    )
    assert recovered.to_dict() == control_wire


class _VersionApi:
    def __init__(self, mode: str):
        self.mode = mode
        self.calls: list[tuple[str, object]] = []

    def GetFileVersionInfoSizeW(self, path: str, reserved: object) -> int:
        self.calls.append(("size", path))
        if self.mode == "size-zero":
            return 0
        return 64

    def GetFileVersionInfoW(self, path: str, handle: int, size: int, buffer: object) -> int:
        self.calls.append(("info", path))
        if self.mode == "info-failure":
            return 0
        return 1

    def VerQueryValueW(
        self, buffer: object, sub_block: str, pointer: object, length: object
    ) -> int:
        self.calls.append(("query", sub_block))
        if self.mode == "translation-failure":
            return 0
        raise AssertionError("ProductVersion query requires a valid translation pointer")


class _VersionLoader:
    def __init__(self, api: _VersionApi | None, raise_on_access: bool = False):
        self.api = api
        self.raise_on_access = raise_on_access

    @property
    def version(self) -> _VersionApi:
        if self.raise_on_access:
            raise OSError("version library unavailable")
        assert self.api is not None
        return self.api


def _ctypes_provider(version_loader: _VersionLoader) -> SimpleNamespace:
    return SimpleNamespace(
        windll=version_loader,
        create_string_buffer=real_ctypes.create_string_buffer,
        c_void_p=real_ctypes.c_void_p,
        wintypes=real_ctypes.wintypes,
        byref=real_ctypes.byref,
        cast=real_ctypes.cast,
        POINTER=real_ctypes.POINTER,
        c_ushort=real_ctypes.c_ushort,
        wstring_at=real_ctypes.wstring_at,
    )


@pytest.mark.parametrize(
    "failure",
    ["size-zero", "info-failure", "translation-failure", "version-oserror"],
    ids=["size-zero", "info-failure", "translation-failure", "version-oserror"],
)
def test_public_gui_version_adapter_failures_are_safe_and_preserve_build_facts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
):
    _root, profile, payload, _paths = _nested_public_profile_fixture(tmp_path)
    original_payload = copy.deepcopy(payload)
    control = discover_tool_support(
        SupportProfileRequest(profile_path=profile, data_root=tmp_path),
        probe_versions=True,
    )
    control_wire = control.to_dict()
    tools = payload["tools"]
    assert isinstance(tools, dict)
    for name in ("cubeMx", "vsCode"):
        entry = tools[name]
        assert isinstance(entry, dict)
        entry.pop("version")
    _write_payload(profile, payload)
    arranged_snapshot = _support_tree_snapshot(tmp_path)
    api = None if failure == "version-oserror" else _VersionApi(failure)
    loader = _VersionLoader(api, raise_on_access=failure == "version-oserror")
    monkeypatch.setattr(support, "ctypes", _ctypes_provider(loader))
    launches: list[tuple[object, dict[str, object]]] = []

    def unexpected_launch(argv: object, **kwargs: object) -> object:
        launches.append((argv, kwargs))
        raise AssertionError("GUI version probes must not launch processes")

    monkeypatch.setattr(support, "_REAL_POPEN", unexpected_launch)
    result = discover_tool_support(
        SupportProfileRequest(profile_path=profile, data_root=tmp_path),
        probe_versions=True,
    )
    expected_wire = copy.deepcopy(control_wire)
    expected_wire["cubeMx"] = None
    expected_wire["vsCode"] = None
    expected_wire["issues"] = [
        {
            "code": "CUBEMX_PROBE_FAILED",
            "component": "cubeMx",
            "remediation": "Provide readable supported version evidence.",
        },
        {
            "code": "VSCODE_PROBE_FAILED",
            "component": "vsCode",
            "remediation": "Provide readable supported version evidence.",
        },
    ]
    assert result.to_dict() == expected_wire
    assert result.cubemx is None and result.vscode is None
    assert {issue.code for issue in result.issues} == {
        "CUBEMX_PROBE_FAILED",
        "VSCODE_PROBE_FAILED",
    }
    assert result.gcc == control.gcc
    assert result.cmake == control.cmake
    assert result.ninja == control.ninja
    assert launches == []
    if failure == "version-oserror":
        assert api is None
    else:
        assert api is not None
        assert api.calls
        if failure == "size-zero":
            assert [kind for kind, _value in api.calls] == ["size", "size"]
        elif failure == "info-failure":
            assert [kind for kind, _value in api.calls] == ["size", "info", "size", "info"]
        else:
            assert [kind for kind, _value in api.calls] == [
                "size",
                "info",
                "query",
                "size",
                "info",
                "query",
            ]
            assert all(
                value == r"\VarFileInfo\Translation"
                for kind, value in api.calls
                if kind == "query"
            )
    assert _support_tree_snapshot(tmp_path) == arranged_snapshot

    _write_payload(profile, original_payload)
    recovered = discover_tool_support(
        SupportProfileRequest(profile_path=profile, data_root=tmp_path),
        probe_versions=True,
    )
    assert recovered.to_dict() == control_wire
