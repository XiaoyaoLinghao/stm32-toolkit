"""Offline evidence tests for DOCTOR-READINESS.

Every observation is synthetic: no test launches a real editor, executes a
batch file, contacts hardware, installs software, or mutates the environment.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from stm32_toolkit import doctor_readiness as readiness
from stm32_toolkit.doctor import run_doctor
from stm32_toolkit.tool_support import (
    ProcessObservation,
    ToolFact,
    ToolSupportProfile,
)


def _write(path: Path, payload: bytes = b"x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def _launcher(hash_component: str | None) -> bytes:
    script = "%~dp0..\\resources\\app\\out\\cli.js"
    if hash_component is not None:
        script = f"%~dp0..\\{hash_component}\\resources\\app\\out\\cli.js"
    return (
        "@echo off\n"
        "setlocal\n"
        "set VSCODE_DEV=\n"
        "set ELECTRON_RUN_AS_NODE=1\n"
        f'"%~dp0..\\Code.exe" "{script}" %*\n'
        "IF %ERRORLEVEL% NEQ 0 EXIT /b %ERRORLEVEL%\n"
        "endlocal\n"
    ).encode()


def _normal_install(root: Path) -> tuple[Path, Path, Path]:
    executable = _write(root / "Code.exe", b"exe")
    script = _write(root / "resources" / "app" / "out" / "cli.js", b"cli")
    locator = _write(root / "bin" / "code.cmd", _launcher(None))
    return executable, script, locator


def _hash_install(
    root: Path, hash_component: str = "e646868227"
) -> tuple[Path, Path, Path]:
    executable = _write(root / "Code.exe", b"exe")
    script = _write(
        root / hash_component / "resources" / "app" / "out" / "cli.js", b"cli"
    )
    locator = _write(root / "bin" / "code.cmd", _launcher(hash_component))
    return executable, script, locator


def _no_keil(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(readiness, "_path_binary", lambda name: None)
    monkeypatch.setattr(readiness, "_UV4_STANDARD_PATHS", ())
    monkeypatch.setattr(readiness, "_ARMCC_STANDARD_PATHS", ())


def _fake_runner(
    monkeypatch: pytest.MonkeyPatch, observation: ProcessObservation
) -> list[dict[str, object]]:
    calls: list[dict[str, object]] = []

    def runner(argv, **kwargs):
        calls.append({"argv": argv, **kwargs})
        return observation

    monkeypatch.setattr(readiness, "_run_bounded", runner)
    return calls


def _forbid_process(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        readiness,
        "_run_bounded",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError(f"unexpected process: {args}")
        ),
    )


def _collect(monkeypatch: pytest.MonkeyPatch, **kwargs) -> dict[str, object]:
    _no_keil(monkeypatch)
    return readiness.collect_doctor_readiness(**kwargs)


# ---------------------------------------------------------------------------
# VS Code extension inventory
# ---------------------------------------------------------------------------


def test_complete_listing_observes_case_insensitive_duplicates_and_exact_argv(
    monkeypatch, tmp_path: Path
):
    root = tmp_path / "vscode"
    executable, script, _locator = _normal_install(root)
    listing = (
        b"MS-VSCODE.CPPTOOLS@1.21.0\r\n"
        b"ms-vscode.cpptools@1.21.0\n"
        b"ms-vscode.cmake-tools@1.14.0\n"
        b"marus25.cortex-debug@1.12.1\n"
        b"other.ext@9.9.9\n"
    )
    calls = _fake_runner(monkeypatch, ProcessObservation(0, listing, b""))
    environment_before = dict(os.environ)

    result = _collect(
        monkeypatch, probe_vscode_extensions=True, vscode_path=root / "Code.exe"
    )

    assert dict(os.environ) == environment_before
    assert len(calls) == 1
    call = calls[0]
    assert call["argv"] == (
        str(executable),
        str(script),
        "--list-extensions",
        "--show-versions",
    )
    assert call["timeout_seconds"] == readiness.EXTENSION_LIST_TIMEOUT_SECONDS
    assert call["capture_limit"] == readiness.EXTENSION_LIST_CAPTURE_LIMIT
    environment = call["env"]
    assert environment["ELECTRON_RUN_AS_NODE"] == "1"
    assert environment["VSCODE_DEV"] == ""
    assert "--profile" not in call["argv"]

    extensions = result["vscodeExtensions"]
    assert extensions["ms-vscode.cpptools"] == {
        "installed": True,
        "version": "1.21.0",
        "status": "installed",
        "code": None,
        "remediation": None,
    }
    assert extensions["ms-vscode.cmake-tools"]["version"] == "1.14.0"
    cortex = extensions["marus25.cortex-debug"]
    assert cortex["version"] == "1.12.1"
    assert cortex["profileVersion"] == "1.12.1"
    assert cortex["profileMatch"] == "match"

    observation = result["vscodeExtensionObservation"]
    assert observation["status"] == "observed"
    assert observation["completeInventory"] is True
    assert observation["scope"] == "local-default-profile"
    assert observation["source"] == "explicit"
    assert observation["executable"] == executable.as_posix()
    assert observation["cliScript"] == script.as_posix()
    assert observation["locator"] is None
    assert observation["returnCode"] == 0
    assert not [
        item for item in result["diagnostics"] if item["component"] == "vsCode"
    ]


def test_empty_successful_listing_is_valid_absence(monkeypatch, tmp_path: Path):
    root = tmp_path / "vscode"
    _normal_install(root)
    _fake_runner(monkeypatch, ProcessObservation(0, b"", b""))

    result = _collect(
        monkeypatch, probe_vscode_extensions=True, vscode_path=root / "Code.exe"
    )

    for extension, entry in result["vscodeExtensions"].items():
        assert entry["installed"] is False
        assert entry["version"] is None
        assert entry["status"] == "absent"
        assert entry["code"] == "VSCODE_EXTENSION_MISSING"
        assert extension in entry["remediation"]
    assert result["vscodeExtensionObservation"]["completeInventory"] is True
    missing = [
        item
        for item in result["diagnostics"]
        if item["code"] == "VSCODE_EXTENSION_MISSING"
    ]
    assert len(missing) == 3


def test_skip_makes_no_process_call_and_keeps_unknown_values(monkeypatch):
    _forbid_process(monkeypatch)

    result = _collect(monkeypatch, probe_vscode_extensions=False)

    for entry in result["vscodeExtensions"].values():
        assert entry["installed"] is None
        assert entry["version"] is None
        assert entry["status"] == "skipped"
        assert entry["code"] is None
    observation = result["vscodeExtensionObservation"]
    assert observation["status"] == "skipped"
    assert observation["completeInventory"] is False


@pytest.mark.parametrize(
    ("observation", "status"),
    [
        (
            ProcessObservation(None, b"ms-vscode.cpptools@1.0.0\n", b"", timed_out=True),
            "timeout",
        ),
        (ProcessObservation(7, b"ms-vscode.cpptools@1.0.0\n", b""), "nonzero"),
        (
            ProcessObservation(0, b"ms-vscode.cpptools@1.0.0\n", b"", truncated=True),
            "truncated",
        ),
        (
            ProcessObservation(0, b"ms-vscode.cpptools@1.0.0\n", b"", incomplete=True),
            "incomplete",
        ),
        (ProcessObservation(0, b"\xff", b""), "invalid-output"),
        (ProcessObservation(None, b"", b""), "start-error"),
        (
            ProcessObservation(2, b"ms-vscode.cpptools@1.0.0\n", b"secret-stderr"),
            "nonzero",
        ),
    ],
)
def test_partial_or_invalid_output_never_becomes_installed_or_absent(
    monkeypatch, tmp_path: Path, observation: ProcessObservation, status: str
):
    root = tmp_path / "vscode"
    _normal_install(root)
    _fake_runner(monkeypatch, observation)

    result = _collect(
        monkeypatch, probe_vscode_extensions=True, vscode_path=root / "Code.exe"
    )

    for entry in result["vscodeExtensions"].values():
        assert entry["installed"] is None
        assert entry["version"] is None
        assert entry["status"] == status
    assert result["vscodeExtensionObservation"]["completeInventory"] is False
    serialized = json.dumps(result, default=str)
    assert "ms-vscode.cpptools@1.0.0" not in serialized
    assert "secret-stderr" not in serialized


@pytest.mark.parametrize(
    ("listing", "status"),
    [
        (b"garbage line\n", "malformed-output"),
        (
            b"ms-vscode.cpptools@1.0.0\nms-vscode.cpptools@1.0.1\n",
            "conflicting-versions",
        ),
        (b"publisher.extension@1.0\n", "observed"),
    ],
)
def test_malformed_or_conflicting_records_fail_closed(
    monkeypatch, tmp_path: Path, listing: bytes, status: str
):
    root = tmp_path / "vscode"
    _normal_install(root)
    _fake_runner(monkeypatch, ProcessObservation(0, listing, b""))

    result = _collect(
        monkeypatch, probe_vscode_extensions=True, vscode_path=root / "Code.exe"
    )

    assert result["vscodeExtensionObservation"]["status"] == status
    if status != "observed":
        assert all(
            entry["installed"] is None
            for entry in result["vscodeExtensions"].values()
        )


def test_conflicting_unrelated_versions_are_ignored(monkeypatch, tmp_path: Path):
    root = tmp_path / "vscode"
    _normal_install(root)
    _fake_runner(
        monkeypatch,
        ProcessObservation(0, b"other.ext@1.0\nother.ext@2.0\n", b""),
    )

    result = _collect(
        monkeypatch, probe_vscode_extensions=True, vscode_path=root / "Code.exe"
    )

    assert result["vscodeExtensionObservation"]["status"] == "observed"
    assert all(
        entry["installed"] is False for entry in result["vscodeExtensions"].values()
    )


def test_cortex_version_is_compared_with_declared_profile(monkeypatch, tmp_path: Path):
    root = tmp_path / "vscode"
    _normal_install(root)
    _fake_runner(
        monkeypatch,
        ProcessObservation(0, b"marus25.cortex-debug@1.12.0\n", b""),
    )

    result = _collect(
        monkeypatch, probe_vscode_extensions=True, vscode_path=root / "Code.exe"
    )

    cortex = result["vscodeExtensions"]["marus25.cortex-debug"]
    assert cortex["version"] == "1.12.0"
    assert cortex["profileVersion"] == "1.12.1"
    assert cortex["profileMatch"] == "mismatch"
    assert cortex["profileMatchBasis"] == (
        "observed-extension-version-vs-declared-handoff-profile"
    )
    assert "cpptools" not in json.dumps(cortex)


# ---------------------------------------------------------------------------
# VS Code installation selection
# ---------------------------------------------------------------------------


def test_hash_layout_is_derived_from_the_launcher_literal_without_executing_it(
    monkeypatch, tmp_path: Path
):
    root = tmp_path / "vscode"
    executable, script, locator = _hash_install(root)
    calls = _fake_runner(monkeypatch, ProcessObservation(0, b"", b""))

    result = _collect(
        monkeypatch, probe_vscode_extensions=True, vscode_path=locator
    )

    assert len(calls) == 1
    argv = calls[0]["argv"]
    assert argv == (
        str(executable),
        str(script),
        "--list-extensions",
        "--show-versions",
    )
    assert Path(argv[0]).name.casefold() == "code.exe"
    observation = result["vscodeExtensionObservation"]
    assert observation["source"] == "explicit"
    assert observation["executable"] == executable.as_posix()
    assert observation["cliScript"] == script.as_posix()
    assert observation["locator"] == locator.as_posix()


def test_code_exe_selects_the_same_installations_hash_script(
    monkeypatch, tmp_path: Path
):
    root = tmp_path / "vscode"
    executable, script, _locator = _hash_install(root)
    calls = _fake_runner(monkeypatch, ProcessObservation(0, b"", b""))

    result = _collect(
        monkeypatch, probe_vscode_extensions=True, vscode_path=root / "Code.exe"
    )

    assert calls[0]["argv"] == (
        str(executable),
        str(script),
        "--list-extensions",
        "--show-versions",
    )
    assert result["vscodeExtensionObservation"]["locator"].endswith("bin/code.cmd")


def test_invalid_explicit_path_never_falls_back(monkeypatch, tmp_path: Path):
    valid_root = tmp_path / "valid"
    _normal_install(valid_root)
    _forbid_process(monkeypatch)
    monkeypatch.setattr(
        readiness, "_path_locator", lambda: valid_root / "bin" / "code.cmd"
    )

    result = _collect(
        monkeypatch,
        probe_vscode_extensions=True,
        vscode_path=tmp_path / "missing" / "Code.exe",
    )

    observation = result["vscodeExtensionObservation"]
    assert observation["status"] == "invalid"
    assert observation["source"] == "explicit"
    assert observation["code"] == "VSCODE_PATH_INVALID"
    assert observation["completeInventory"] is False
    assert all(
        entry["installed"] is None for entry in result["vscodeExtensions"].values()
    )
    assert any(
        item["component"] == "vsCode"
        and item["field"] == "vscodePath"
        and item["cliOption"] == "--vscode-path"
        for item in result["diagnostics"]
    )


def test_relative_or_directory_explicit_path_is_invalid(monkeypatch, tmp_path: Path):
    _forbid_process(monkeypatch)
    for explicit in (Path("Code.exe"), tmp_path / "Code.exe"):
        if explicit.is_absolute():
            explicit.mkdir()
        result = _collect(
            monkeypatch, probe_vscode_extensions=True, vscode_path=explicit
        )
        assert result["vscodeExtensionObservation"]["status"] == "invalid"


def test_unsupported_layouts_are_reported_without_search(
    monkeypatch, tmp_path: Path
):
    _forbid_process(monkeypatch)
    bare = _write(tmp_path / "bare" / "Code.exe")
    result = _collect(
        monkeypatch, probe_vscode_extensions=True, vscode_path=bare
    )
    assert result["vscodeExtensionObservation"]["status"] == "unsupported-layout"

    root = tmp_path / "arbitrary"
    _write(root / "Code.exe")
    _write(root / "resources" / "app" / "out" / "cli.js")
    locator = _write(root / "bin" / "code.cmd", b"@echo off\nanything\n")
    result = _collect(
        monkeypatch, probe_vscode_extensions=True, vscode_path=locator
    )
    assert result["vscodeExtensionObservation"]["status"] == "unsupported-layout"


def test_redirected_explicit_parent_is_invalid(monkeypatch, tmp_path: Path):
    root = tmp_path / "real"
    _normal_install(root)
    link = tmp_path / "link"
    try:
        link.symlink_to(root, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlink unavailable")
    _forbid_process(monkeypatch)

    result = _collect(
        monkeypatch, probe_vscode_extensions=True, vscode_path=link / "Code.exe"
    )

    assert result["vscodeExtensionObservation"]["status"] == "invalid"


def test_standard_layout_ambiguity_and_missing_are_distinct(
    monkeypatch, tmp_path: Path
):
    first = tmp_path / "first"
    second = tmp_path / "second"
    _normal_install(first)
    _normal_install(second)
    monkeypatch.setattr(readiness, "_path_locator", lambda: None)
    monkeypatch.setattr(
        readiness,
        "_vscode_standard_candidates",
        lambda: (first / "Code.exe", second / "Code.exe"),
    )
    _forbid_process(monkeypatch)

    ambiguous = _collect(monkeypatch, probe_vscode_extensions=True)
    assert ambiguous["vscodeExtensionObservation"]["status"] == "ambiguous"
    assert all(
        entry["installed"] is None
        for entry in ambiguous["vscodeExtensions"].values()
    )

    monkeypatch.setattr(readiness, "_vscode_standard_candidates", lambda: ())
    missing = _collect(monkeypatch, probe_vscode_extensions=True)
    assert missing["vscodeExtensionObservation"]["status"] == "missing"
    assert missing["vscodeExtensionObservation"]["code"] == "VSCODE_CLI_NOT_FOUND"


def test_path_and_support_profile_sources_are_selected_consistently(
    monkeypatch, tmp_path: Path
):
    root = tmp_path / "vscode"
    executable, script, locator = _normal_install(root)
    _fake_runner(monkeypatch, ProcessObservation(0, b"", b""))
    monkeypatch.setattr(readiness, "_path_locator", lambda: locator)

    from_path = _collect(monkeypatch, probe_vscode_extensions=True)
    observation = from_path["vscodeExtensionObservation"]
    assert observation["source"] == "path"
    assert observation["executable"] == executable.as_posix()
    assert observation["cliScript"] == script.as_posix()
    assert observation["locator"] == locator.as_posix()

    fact = ToolFact("vsCode", root / "Code.exe", "1.100.0", "explicit", "0" * 64)
    profile = ToolSupportProfile(
        "3.12.0", None, None, None, None, None, fact, (), ()
    )
    from_profile = _collect(
        monkeypatch, support_profile=profile, probe_vscode_extensions=True
    )
    observation = from_profile["vscodeExtensionObservation"]
    assert observation["source"] == "support-profile"
    assert observation["executable"] == executable.as_posix()


# ---------------------------------------------------------------------------
# UV4 and ARMCC
# ---------------------------------------------------------------------------


def test_uv4_uses_static_version_and_is_never_executed(monkeypatch, tmp_path: Path):
    uv4 = _write(tmp_path / "Keil_v5" / "UV4" / "UV4.exe")
    _forbid_process(monkeypatch)
    monkeypatch.setattr(readiness, "_windows_file_version", lambda path: "5.06")

    result = _collect(
        monkeypatch, probe_vscode_extensions=False, uv4_path=uv4
    )

    record = result["keilTools"]["uv4"]
    assert record["available"] is True
    assert record["source"] == "explicit"
    assert record["path"] == uv4.as_posix()
    assert record["status"] == "ok"
    assert record["version"] == "5.06"
    assert record["returnCode"] is None
    assert not [
        item for item in result["diagnostics"] if item["component"] == "uv4"
    ]


def test_uv4_version_unknown_is_presence_not_missing(monkeypatch, tmp_path: Path):
    uv4 = _write(tmp_path / "Keil_v5" / "UV4" / "UV4.exe")
    _forbid_process(monkeypatch)
    monkeypatch.setattr(readiness, "_windows_file_version", lambda path: None)

    result = _collect(
        monkeypatch, probe_vscode_extensions=False, uv4_path=uv4
    )

    record = result["keilTools"]["uv4"]
    assert record["available"] is True
    assert record["status"] == "version-unknown"
    assert record["version"] is None
    assert record["code"] == "UV4_VERSION_UNKNOWN"
    assert any(item["code"] == "UV4_VERSION_UNKNOWN" for item in result["diagnostics"])


def test_uv4_invalid_explicit_and_ambiguity(monkeypatch, tmp_path: Path):
    _forbid_process(monkeypatch)
    invalid = _collect(
        monkeypatch,
        probe_vscode_extensions=False,
        uv4_path=tmp_path / "missing" / "UV4.exe",
    )
    record = invalid["keilTools"]["uv4"]
    assert record["available"] is None
    assert record["status"] == "invalid"
    assert record["code"] == "UV4_PATH_INVALID"

    first = _write(tmp_path / "first" / "UV4" / "UV4.exe")
    second = _write(tmp_path / "second" / "UV4" / "UV4.exe")
    monkeypatch.setattr(readiness, "_path_binary", lambda name: None)
    monkeypatch.setattr(readiness, "_UV4_STANDARD_PATHS", (first, second))
    monkeypatch.setattr(readiness, "_ARMCC_STANDARD_PATHS", ())
    ambiguous = readiness.collect_doctor_readiness(probe_vscode_extensions=False)
    record = ambiguous["keilTools"]["uv4"]
    assert record["available"] is None
    assert record["status"] == "ambiguous"
    assert record["code"] == "UV4_AMBIGUOUS"


def test_armcc_probes_only_vsn_and_derives_from_selected_uv4(
    monkeypatch, tmp_path: Path
):
    root = tmp_path / "Keil_v5"
    uv4 = _write(root / "UV4" / "UV4.exe")
    armcc = _write(root / "ARM" / "ARMCC" / "bin" / "armcc.exe")
    calls = _fake_runner(
        monkeypatch,
        ProcessObservation(0, b"Product: ARM Compiler 5.06 update 7\nTool: armcc\n", b""),
    )
    monkeypatch.setattr(readiness, "_windows_file_version", lambda path: "5.06")
    monkeypatch.setattr(readiness, "_path_binary", lambda name: None)
    monkeypatch.setattr(readiness, "_ARMCC_STANDARD_PATHS", ())

    result = _collect(
        monkeypatch, probe_vscode_extensions=False, uv4_path=uv4
    )

    assert len(calls) == 1
    assert calls[0]["argv"] == (str(armcc), "--vsn")
    assert calls[0]["timeout_seconds"] == readiness.ARMCC_TIMEOUT_SECONDS
    assert calls[0]["capture_limit"] == readiness.ARMCC_CAPTURE_LIMIT
    assert "--version" not in calls[0]["argv"]
    record = result["keilTools"]["armcc"]
    assert record["available"] is True
    assert record["source"] == "uv4-installation"
    assert record["path"] == armcc.as_posix()
    assert record["status"] == "ok"
    assert record["version"] == "ARM Compiler 5.06 update 7"
    assert record["returnCode"] == 0


@pytest.mark.parametrize(
    ("observation", "status", "return_code"),
    [
        (ProcessObservation(None, b"", b"", timed_out=True), "timeout", None),
        (ProcessObservation(3, b"", b""), "nonzero", 3),
        (ProcessObservation(None, b"", b""), "start-error", None),
        (ProcessObservation(0, b"Product: ARM\n", b"", truncated=True), "truncated", 0),
        (ProcessObservation(0, b"Product: ARM\n", b"", incomplete=True), "incomplete", 0),
        (ProcessObservation(0, b"\xff", b""), "invalid-output", 0),
        (ProcessObservation(0, b"   \n", b""), "version-unknown", 0),
    ],
)
def test_armcc_failures_do_not_manufacture_versions(
    monkeypatch, tmp_path: Path, observation: ProcessObservation, status: str,
    return_code: int | None,
):
    armcc = _write(tmp_path / "armcc.exe")
    _fake_runner(monkeypatch, observation)

    result = _collect(
        monkeypatch, probe_vscode_extensions=False, armcc_path=armcc
    )

    record = result["keilTools"]["armcc"]
    assert record["available"] is True
    assert record["status"] == status
    assert record["version"] is None
    assert record["returnCode"] == return_code
    assert record["code"]


def test_armcc_invalid_explicit_never_falls_back(monkeypatch, tmp_path: Path):
    valid = _write(tmp_path / "valid" / "armcc.exe")
    invalid = _write(tmp_path / "armclang.exe")
    _forbid_process(monkeypatch)
    monkeypatch.setattr(
        readiness, "_path_binary", lambda name: valid if name == "armcc" else None
    )
    monkeypatch.setattr(readiness, "_UV4_STANDARD_PATHS", ())
    monkeypatch.setattr(readiness, "_ARMCC_STANDARD_PATHS", ())

    result = readiness.collect_doctor_readiness(
        probe_vscode_extensions=False, armcc_path=invalid
    )

    record = result["keilTools"]["armcc"]
    assert record["available"] is None
    assert record["status"] == "invalid"
    assert record["code"] == "ARMCC_PATH_INVALID"


def test_armcc_path_and_standard_sources(monkeypatch, tmp_path: Path):
    armcc = _write(tmp_path / "tools" / "armcc.exe")
    calls = _fake_runner(
        monkeypatch, ProcessObservation(0, b"Product: ARM Compiler 5.06\n", b"")
    )
    monkeypatch.setattr(
        readiness, "_path_binary", lambda name: armcc if name == "armcc" else None
    )
    monkeypatch.setattr(readiness, "_UV4_STANDARD_PATHS", ())
    monkeypatch.setattr(readiness, "_ARMCC_STANDARD_PATHS", ())

    from_path = readiness.collect_doctor_readiness(probe_vscode_extensions=False)
    assert from_path["keilTools"]["armcc"]["source"] == "path"
    assert len(calls) == 1

    monkeypatch.setattr(readiness, "_path_binary", lambda name: None)
    monkeypatch.setattr(readiness, "_ARMCC_STANDARD_PATHS", (armcc,))
    from_standard = readiness.collect_doctor_readiness(probe_vscode_extensions=False)
    assert from_standard["keilTools"]["armcc"]["source"] == "standard"


def test_missing_keil_tools_are_missing_and_do_not_unlock_a_backend(
    monkeypatch,
):
    _forbid_process(monkeypatch)

    result = _collect(monkeypatch, probe_vscode_extensions=False)

    uv4 = result["keilTools"]["uv4"]
    armcc = result["keilTools"]["armcc"]
    assert uv4["available"] is False and uv4["status"] == "missing"
    assert armcc["available"] is False and armcc["status"] == "missing"
    assert result["keilTools"]["toolkitNativeBuildSupported"] is False
    assert result["keilTools"]["routes"] == [
        "keil-migration",
        "external-firmware",
    ]
    assert "No native Keil/ARMCC build backend" in result["keilTools"][
        "nativeBuildReason"
    ]
    assert result["readiness"]["toolkitNativeBuildSupported"] is False


# ---------------------------------------------------------------------------
# run_doctor integration
# ---------------------------------------------------------------------------


def test_run_doctor_keeps_declared_profile_separate_from_live_observation(
    monkeypatch, tmp_path: Path
):
    root = tmp_path / "vscode"
    _normal_install(root)
    project = tmp_path / "project"
    project.mkdir()
    _fake_runner(monkeypatch, ProcessObservation(0, b"", b""))
    _no_keil(monkeypatch)
    monkeypatch.setattr("stm32_toolkit.doctor.shutil.which", lambda name: None)
    fact = ToolFact("vsCode", root / "Code.exe", "1.100.0", "explicit", "0" * 64)
    profile = ToolSupportProfile(
        "3.12.0",
        None,
        None,
        None,
        None,
        None,
        fact,
        (("ms-vscode.cpptools", "9.9.9"),),
        (),
    )

    result = run_doctor(project, support_profile=profile)
    data = result.data

    assert data["creationSupport"]["vsCodeExtensions"] == [
        {"id": "ms-vscode.cpptools", "version": "9.9.9"}
    ]
    observed = data["vscodeExtensions"]["ms-vscode.cpptools"]
    assert observed["installed"] is False
    assert observed["version"] is None
    assert data["vscodeExtensionObservation"]["source"] == "support-profile"
    assert data["vscodeExtensionObservation"]["completeInventory"] is True
    assert data["keilTools"]["toolkitNativeBuildSupported"] is False
    assert data["readiness"]["reportCollected"] is True
    assert data["mutated"] is False
    assert json.loads(json.dumps(result.to_dict()))["ok"] is True
