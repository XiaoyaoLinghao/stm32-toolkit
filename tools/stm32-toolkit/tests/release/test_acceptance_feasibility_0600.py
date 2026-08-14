"""Behavior tests for the closed Windows-only 0600 feasibility verifier."""

from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest


RELEASE_DIR = Path(__file__).resolve().parents[3] / "release"
sys.path.insert(0, str(RELEASE_DIR))

from verify_0600_feasibility import (  # noqa: E402
    _run,
    expected_chromium_argv,
    managed_chromium_version,
    verify_committed_verifier,
    verify_feasibility,
    verify_result,
)

import verify_0600_feasibility as feasibility  # noqa: E402


def _digest(number: int) -> str:
    return f"{number:064x}"


VERSION_EVIDENCE = b"""<assembly manifestVersion='1.0'>
  <assemblyIdentity name='141.0.7390.37' version='141.0.7390.37' type='win32'/>
</assembly>"""
PROFILE_LOCAL_STATE = '{"profile":{"exit_type":"Normal"}}\n'


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _test_directory() -> Path:
    return Path(tempfile.mkdtemp(prefix="stm32tk-0600-feasibility-test-", dir=r"C:\tmp"))


def _expected_chromium_argv(
    evidence_root: str, support_root: str = r"C:\tmp\support"
) -> list[str]:
    """Hand-derived frozen argv; it intentionally does not call production helpers."""
    return [
        "--headless=new",
        "--disable-gpu",
        "--no-first-run",
        "--no-default-browser-check",
        f"--user-data-dir={evidence_root}\\managed-chromium-profile",
        "--dump-dom",
        "file:///" + support_root.replace("\\", "/") + "/feasibility/blank.html",
    ]


def _materialization_bytes(evidence_root: str) -> bytes:
    local_state = PROFILE_LOCAL_STATE.encode("utf-8")
    return (
        json.dumps(
            {
                "schema": "stm32tk-0600-managed-chromium-profile-materialization/1",
                "id": "stm32tk-0600-feasibility",
                "seed": {
                    "path": "feasibility/chromium-profile-seed.json",
                    "sha256": _digest(33),
                },
                "profile_path": evidence_root + r"\managed-chromium-profile",
                "files": [
                    {
                        "path": "Local State",
                        "bytes": len(local_state),
                        "sha256": _sha256(local_state),
                    }
                ],
            },
            sort_keys=True,
        ).encode("utf-8")
        + b"\n"
    )


def _entry(root: Path, relative: str) -> dict[str, object]:
    payload = (root / relative).read_bytes()
    return {"path": relative, "bytes": len(payload), "sha256": _sha256(payload)}


def _write_controlled_support(root: Path, profile: dict[str, object]) -> Path:
    """Build a real, disposable support tree with a controlled local browser executable."""
    root.mkdir()
    profile = copy.deepcopy(profile)
    tools = profile["tools"]
    chromium = profile["chromium"]
    fixture = profile["firmware_fixture"]
    assert isinstance(tools, dict)
    assert isinstance(chromium, dict)
    assert isinstance(fixture, dict)

    for name, declared in tools.items():
        assert isinstance(declared, dict)
        path = root / str(declared["record"])
        path.parent.mkdir(parents=True, exist_ok=True)
        if name == "wheelhouse":
            record = {
                "schema": "stm32tk-0600-tool-record/1",
                "name": name,
                "version": declared["version"],
                "path": "wheelhouse",
            }
            (root / "wheelhouse").mkdir()
            (root / "wheelhouse" / "controlled.whl").write_bytes(b"controlled wheel")
        elif name in {"pyocd", "pyserial"}:
            record = {
                "schema": "stm32tk-0600-tool-record/1",
                "name": name,
                "version": declared["version"],
                "python": r"C:\\controlled\\python.exe",
            }
        else:
            record = {
                "schema": "stm32tk-0600-tool-record/1",
                "name": name,
                "version": declared["version"],
                "executable": r"C:\\controlled\\tool.exe",
            }
        path.write_bytes(json.dumps(record, sort_keys=True).encode("utf-8"))

    chrome = root / "chromium" / "chrome.cmd"
    chrome.parent.mkdir(parents=True)
    chrome.write_text(
        "@echo off\r\necho ^<!doctype html^>^<html^>controlled^</html^>\r\nexit /b 0\r\n",
        encoding="utf-8",
    )
    version = root / "chromium" / "chrome-version.manifest"
    version.write_bytes(VERSION_EVIDENCE)
    blank = root / "feasibility" / "blank.html"
    blank.parent.mkdir(parents=True)
    blank.write_bytes(b"<!doctype html><html><body></body></html>\n")
    seed = root / "feasibility" / "chromium-profile-seed.json"
    seed_data = {
        "schema": "stm32tk-0600-managed-chromium-profile-seed/1",
        "id": "stm32tk-0600-feasibility",
        "local_state": PROFILE_LOCAL_STATE,
    }
    seed.write_bytes(json.dumps(seed_data, sort_keys=True).encode("utf-8") + b"\n")
    firmware = root / "firmware" / "feasibility.bin"
    firmware.parent.mkdir()
    firmware.write_bytes(b"controlled firmware")

    chromium["executable"] = "chromium/chrome.cmd"
    chromium["executable_sha256"] = _entry(root, "chromium/chrome.cmd")["sha256"]
    chromium["version_evidence"] = {
        "path": "chromium/chrome-version.manifest",
        "sha256": _entry(root, "chromium/chrome-version.manifest")["sha256"],
    }
    chromium["blank_page"] = {
        "path": "feasibility/blank.html",
        "sha256": _entry(root, "feasibility/blank.html")["sha256"],
    }
    chromium["managed_profile"] = {
        "id": "stm32tk-0600-feasibility",
        "seed": "feasibility/chromium-profile-seed.json",
        "sha256": _entry(root, "feasibility/chromium-profile-seed.json")["sha256"],
        "files": [
            {
                "path": "Local State",
                "bytes": len(PROFILE_LOCAL_STATE.encode("utf-8")),
                "sha256": _sha256(PROFILE_LOCAL_STATE.encode("utf-8")),
            }
        ],
    }
    package_entries = sorted(
        [_entry(root, "chromium/chrome.cmd"), _entry(root, "chromium/chrome-version.manifest")],
        key=lambda entry: str(entry["path"]),
    )
    chromium["package_root"] = "chromium"
    chromium["package_tree_sha256"] = _sha256(
        json.dumps(package_entries, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    fixture["bytes"] = len(firmware.read_bytes())
    fixture["sha256"] = _entry(root, "firmware/feasibility.bin")["sha256"]

    profile_path = root / "feasibility" / "profile.json"
    profile_path.write_bytes(json.dumps(profile, sort_keys=True).encode("utf-8") + b"\n")
    entries = [_entry(root, path.relative_to(root).as_posix()) for path in root.rglob("*") if path.is_file()]
    (root / "support-manifest.json").write_bytes(
        json.dumps({"schema": "stm32tk-0600-support-manifest/1", "files": entries}, sort_keys=True).encode("utf-8")
        + b"\n"
    )
    return profile_path


@pytest.fixture
def valid_profile() -> dict[str, object]:
    versions = {
        "python310": "3.10.11",
        "python312": "3.12.10",
        "powershell": "5.1",
        "cmake": "4.3.1",
        "ctest": "4.3.1",
        "pyocd": "0.45.1",
        "pyserial": "3.5",
        "node": "24.18.0",
        "npm": "11.16.0",
        "wheelhouse": "offline-wheelhouse/1",
    }
    return {
        "schema": "stm32tk-0600-feasibility-profile/1",
        "windows_owner": "Codex",
        "host": {
            "platform": "Windows",
            "architecture": "AMD64",
            "host_id": _digest(29),
            "windows_version": {
                "release": "11",
                "version": "10.0.26100",
                "build": "26100",
            },
        },
        "tools": {
            name: {"record": f"tools/{name}.json", "version": version}
            for name, version in versions.items()
        },
        "chromium": {
            "executable": "chromium/chrome.exe",
            "executable_sha256": _digest(31),
            "version": "141.0.7390.37",
            "package_root": "chromium",
            "package_tree_sha256": _digest(32),
            "managed_profile": {
                "id": "stm32tk-0600-feasibility",
                "seed": "feasibility/chromium-profile-seed.json",
                "sha256": _digest(33),
                "files": [
                    {
                        "path": "Local State",
                        "bytes": len(PROFILE_LOCAL_STATE.encode("utf-8")),
                        "sha256": _sha256(PROFILE_LOCAL_STATE.encode("utf-8")),
                    }
                ],
            },
            "version_evidence": {
                "path": "chromium/chrome-version.manifest",
                "sha256": _sha256(VERSION_EVIDENCE),
            },
            "blank_page": {"path": "feasibility/blank.html", "sha256": _digest(34)},
        },
        "firmware_fixture": {
            "path": "firmware/feasibility.bin",
            "bytes": 19,
            "sha256": _digest(35),
        },
        "capabilities": {
            "ram": [{"start": 536870912, "size": 32768}],
            "mailbox": {"address": 536870912, "size": 4096},
            "rtt": {"channel": 0},
            "uart": {"port": "COM7", "baud": 115200},
            "semihosting": {"declared": True},
        },
    }


@pytest.fixture
def valid_manifest(valid_profile: dict[str, object]) -> dict[str, object]:
    profile = valid_profile
    tools = profile["tools"]
    assert isinstance(tools, dict)
    files = [
        {
            "path": record["record"],
            "bytes": 100 + index,
            "sha256": _digest(index + 1),
        }
        for index, record in enumerate(tools.values())
        if isinstance(record, dict)
    ]
    files.extend(
        [
            {"path": "chromium/chrome.exe", "bytes": 101, "sha256": _digest(31)},
            {
                "path": "chromium/chrome-version.manifest",
                "bytes": len(VERSION_EVIDENCE),
                "sha256": _sha256(VERSION_EVIDENCE),
            },
            {
                "path": "feasibility/chromium-profile-seed.json",
                "bytes": 102,
                "sha256": _digest(33),
            },
            {"path": "feasibility/blank.html", "bytes": 103, "sha256": _digest(34)},
            {"path": "firmware/feasibility.bin", "bytes": 19, "sha256": _digest(35)},
            {"path": "feasibility/profile.json", "bytes": 104, "sha256": _digest(36)},
        ]
    )
    return {"schema": "stm32tk-0600-support-manifest/1", "files": files}


@pytest.fixture
def valid_result(
    valid_profile: dict[str, object], valid_manifest: dict[str, object]
) -> dict[str, object]:
    profile = valid_profile
    manifest = valid_manifest
    tools = profile["tools"]
    chromium = profile["chromium"]
    assert isinstance(tools, dict)
    assert isinstance(chromium, dict)
    evidence_directory = _test_directory()
    evidence_root = str(evidence_directory)
    support_root = r"C:\tmp\support"
    result = {
        "schema": "stm32tk-0600-feasibility-result/1",
        "owner": "Codex",
        "host": copy.deepcopy(profile["host"]),
        "profile": {"path": "feasibility/profile.json", "sha256": _digest(36)},
        "support_manifest": {"sha256": _digest(37)},
        "run": {
            "kind": "windows-software-fixture",
            "status": "PASS",
            "code_head": "a" * 40,
            "machine": "local",
            "evidence_root": evidence_root,
        },
        "tools": {
            name: {
                "record": record["record"],
                "sha256": valid_manifest["files"][index]["sha256"],
                "version": record["version"],
            }
            for index, (name, record) in enumerate(tools.items())
            if isinstance(record, dict)
        },
        "chromium": {
            "executable": chromium["executable"],
            "executable_sha256": chromium["executable_sha256"],
            "version": chromium["version"],
            "package_tree_sha256": chromium["package_tree_sha256"],
            "managed_profile_id": chromium["managed_profile"]["id"],
            "managed_profile_path": evidence_root + r"\managed-chromium-profile",
            "managed_profile_seed": {
                "path": chromium["managed_profile"]["seed"],
                "sha256": chromium["managed_profile"]["sha256"],
            },
            "version_evidence": copy.deepcopy(chromium["version_evidence"]),
            "blank_page": chromium["blank_page"]["path"],
            "argv": _expected_chromium_argv(evidence_root),
            "exit_code": 0,
        },
        "firmware_fixture": copy.deepcopy(profile["firmware_fixture"]),
        "capabilities": copy.deepcopy(profile["capabilities"]),
        "hardware": {"status": "PENDING"},
        "evidence": {},
    }
    expected_argv = _expected_chromium_argv(evidence_root)
    launch = {
        "argv": expected_argv,
        "exit_code": 0,
        "stderr": "",
        "stdout": "<!doctype html><html><head></head><body></body></html>",
    }
    launch_bytes = json.dumps(launch, sort_keys=True).encode("utf-8")
    (evidence_directory / "chromium-launch.json").write_bytes(launch_bytes)
    (evidence_directory / "chromium-version.txt").write_bytes(VERSION_EVIDENCE)
    profile_directory = evidence_directory / "managed-chromium-profile"
    profile_directory.mkdir()
    (profile_directory / "Local State").write_bytes(PROFILE_LOCAL_STATE.encode("utf-8"))
    materialization_bytes = _materialization_bytes(evidence_root)
    (profile_directory / "stm32tk-0600-seed-binding.json").write_bytes(materialization_bytes)
    (evidence_directory / "chromium-profile-materialization.json").write_bytes(
        materialization_bytes
    )
    result["evidence"] = {
        "chromium_launch": {
            "path": "chromium-launch.json",
            "bytes": len(launch_bytes),
            "sha256": _sha256(launch_bytes),
        },
        "chromium_version": {
            "path": "chromium-version.txt",
            "bytes": len(VERSION_EVIDENCE),
            "sha256": _sha256(VERSION_EVIDENCE),
        },
        "chromium_profile_seed": {
            "path": "chromium-profile-materialization.json",
            "bytes": len(materialization_bytes),
            "sha256": _sha256(materialization_bytes),
        },
    }
    return result


def test_feasibility_requires_windows_support_contract(valid_profile: dict[str, object]) -> None:
    """Removing a required Windows tool must make the profile unusable."""
    del valid_profile["tools"]["ctest"]

    result = verify_feasibility(valid_profile)

    assert result.code == "FEASIBILITY_CAPABILITY_MISSING"


def test_feasibility_accepts_complete_windows_profile(valid_profile: dict[str, object]) -> None:
    """A complete, declared four-transport profile is accepted without hardware execution."""
    result = verify_feasibility(valid_profile)

    assert result.code == "PASS"
    assert result.details["hardware_status"] == "PENDING"


def test_feasibility_requires_frozen_nonempty_windows_host_identity(
    valid_profile: dict[str, object]
) -> None:
    """An AMD64 label alone must not allow another Windows machine to reuse this profile."""
    host = valid_profile["host"]
    assert isinstance(host, dict)
    del host["host_id"]

    missing_identifier = verify_feasibility(valid_profile)

    assert missing_identifier.code == "FEASIBILITY_CAPABILITY_MISSING"
    host["host_id"] = _digest(29)
    host["windows_version"]["build"] = ""
    missing_windows_version = verify_feasibility(valid_profile)

    assert missing_windows_version.code == "FEASIBILITY_CAPABILITY_MISSING"


@pytest.mark.parametrize(
    ("mutate", "code"),
    [
        (lambda profile: profile.__setitem__("windows_owner", ""), "FEASIBILITY_CAPABILITY_MISSING"),
        (
            lambda profile: profile["host"].__setitem__("platform", "Linux"),
            "FEASIBILITY_FORBIDDEN_EVIDENCE",
        ),
        (
            lambda profile: profile["chromium"].pop("managed_profile"),
            "FEASIBILITY_CAPABILITY_MISSING",
        ),
    ],
)
def test_feasibility_rejects_missing_owner_linux_and_unmanaged_chromium(
    valid_profile: dict[str, object], mutate: object, code: str
) -> None:
    """The verifier must not substitute a Linux or unmanaged-browser contract."""
    mutate(valid_profile)

    result = verify_feasibility(valid_profile)

    assert result.code == code


def test_feasibility_requires_manifest_bound_chromium_version_evidence(
    valid_profile: dict[str, object]
) -> None:
    """A launch alone cannot substitute for the exact managed-browser version proof."""
    del valid_profile["chromium"]["version_evidence"]

    result = verify_feasibility(valid_profile)

    assert result.code == "FEASIBILITY_CAPABILITY_MISSING"


def test_managed_chromium_version_uses_assembly_identity_not_xml_manifest_version() -> None:
    """The browser proof must not mistake XML's manifest format version for Chrome's version."""
    evidence = b"""<assembly manifestVersion='1.0'>
      <assemblyIdentity name='141.0.7390.37' version='141.0.7390.37' type='win32'/>
    </assembly>"""

    assert managed_chromium_version(evidence) == "141.0.7390.37"


def test_expected_chromium_argv_matches_the_hand_derived_non_product_invocation(
    valid_profile: dict[str, object], valid_result: dict[str, object]
) -> None:
    """A production argv helper change must not silently redefine the launch contract."""
    chromium = valid_profile["chromium"]
    assert isinstance(chromium, dict)
    evidence_root = str(valid_result["run"]["evidence_root"])
    expected = _expected_chromium_argv(evidence_root)

    assert expected_chromium_argv(chromium, r"C:\tmp\support", evidence_root) == expected
    assert valid_result["chromium"]["argv"] == expected


def test_result_binds_exact_profile_manifest_tools_fixture_and_blank_launch(
    valid_profile: dict[str, object],
    valid_manifest: dict[str, object],
    valid_result: dict[str, object],
) -> None:
    """Wrong tool, fixture, argv, or result paths must invalidate the observable contract."""
    result = verify_result(
        valid_profile,
        valid_manifest,
        valid_result,
        expected_code_head="a" * 40,
        expected_profile_sha256=_digest(36),
        expected_manifest_sha256=_digest(37),
        support_root=r"C:\tmp\support",
    )

    assert result.code == "PASS"
    assert result.details["hardware_status"] == "PENDING"


def test_result_rejects_a_different_windows_host_even_when_amd64_matches(
    valid_profile: dict[str, object],
    valid_manifest: dict[str, object],
    valid_result: dict[str, object],
) -> None:
    """A copied local PASS must bind the support profile's exact host and Windows version."""
    result_host = valid_result["host"]
    assert isinstance(result_host, dict)
    result_host["host_id"] = _digest(30)

    result = verify_result(
        valid_profile,
        valid_manifest,
        valid_result,
        expected_code_head="a" * 40,
        expected_profile_sha256=_digest(36),
        expected_manifest_sha256=_digest(37),
        support_root=r"C:\tmp\support",
    )

    assert result.code == "FEASIBILITY_RESULT_MISMATCH"


@pytest.mark.parametrize(
    ("mutate", "code"),
    [
        (
            lambda result: result["tools"]["ctest"].__setitem__("version", "0.0.0"),
            "FEASIBILITY_RESULT_MISMATCH",
        ),
        (
            lambda result: result["tools"]["ctest"].__setitem__("sha256", _digest(98)),
            "FEASIBILITY_RESULT_MISMATCH",
        ),
        (
            lambda result: result["firmware_fixture"].__setitem__("bytes", 20),
            "FEASIBILITY_RESULT_MISMATCH",
        ),
        (
            lambda result: result["chromium"]["argv"].append("https://example.test"),
            "FEASIBILITY_RESULT_MISMATCH",
        ),
        (
            lambda result: result["chromium"]["version_evidence"].__setitem__(
                "sha256", _digest(97)
            ),
            "FEASIBILITY_RESULT_MISMATCH",
        ),
        (
            lambda result: result["evidence"]["chromium_launch"].__setitem__(
                "path", "chromium-version.txt"
            ),
            "FEASIBILITY_EVIDENCE_PATH_INVALID",
        ),
        (
            lambda result: result["run"].__setitem__("status", "SKIP"),
            "FEASIBILITY_RESULT_INVALID",
        ),
        (
            lambda result: result["run"].__setitem__("code_head", "b" * 40),
            "FEASIBILITY_STALE_RESULT",
        ),
        (
            lambda result: result["hardware"].__setitem__("status", "PASS"),
            "FEASIBILITY_FORBIDDEN_EVIDENCE",
        ),
        (
            lambda result: result.__setitem__("evidence_channel", "cross-machine"),
            "FEASIBILITY_FORBIDDEN_EVIDENCE",
        ),
        (
            lambda result: result.__setitem__("browser_product_flow", {"status": "PASS"}),
            "FEASIBILITY_FORBIDDEN_EVIDENCE",
        ),
        (
            lambda result: result["chromium"].__setitem__("platform", "Linux"),
            "FEASIBILITY_FORBIDDEN_EVIDENCE",
        ),
        (
            lambda result: result["run"].__setitem__("machine", "remote"),
            "FEASIBILITY_FORBIDDEN_EVIDENCE",
        ),
        (
            lambda result: result.__setitem__("package", {"machine": "other"}),
            "FEASIBILITY_FORBIDDEN_EVIDENCE",
        ),
    ],
)
def test_result_rejects_fake_skip_stale_cross_profile_and_forbidden_evidence(
    valid_profile: dict[str, object],
    valid_manifest: dict[str, object],
    valid_result: dict[str, object],
    mutate: object,
    code: str,
) -> None:
    """Only local Windows feasibility evidence may report PASS."""
    mutate(valid_result)

    result = verify_result(
        valid_profile,
        valid_manifest,
        valid_result,
        expected_code_head="a" * 40,
        expected_profile_sha256=_digest(36),
        expected_manifest_sha256=_digest(37),
        support_root=r"C:\tmp\support",
    )

    assert result.code == code


def test_result_rejects_cross_profile_before_accepting_a_pass(
    valid_profile: dict[str, object],
    valid_manifest: dict[str, object],
    valid_result: dict[str, object],
) -> None:
    """A PASS from another profile digest cannot be recycled locally."""
    valid_result["profile"]["sha256"] = _digest(99)

    result = verify_result(
        valid_profile,
        valid_manifest,
        valid_result,
        expected_code_head="a" * 40,
        expected_profile_sha256=_digest(36),
        expected_manifest_sha256=_digest(37),
        support_root=r"C:\tmp\support",
    )

    assert result.code == "FEASIBILITY_PROFILE_MISMATCH"


def test_result_rejects_fabricated_or_non_blank_launch_evidence(
    valid_profile: dict[str, object],
    valid_manifest: dict[str, object],
    valid_result: dict[str, object],
) -> None:
    """A PASS requires actual local bytes and a launch record for the declared blank page."""
    evidence_root = Path(valid_result["run"]["evidence_root"])
    launch_path = evidence_root / "chromium-launch.json"
    launch = {
        "argv": ["--headless=new", "https://example.test"],
        "exit_code": 0,
        "stderr": "",
        "stdout": "<!doctype html><html><body></body></html>",
    }
    launch_bytes = json.dumps(launch, sort_keys=True).encode("utf-8")
    launch_path.write_bytes(launch_bytes)
    valid_result["evidence"]["chromium_launch"]["bytes"] = len(launch_bytes)
    valid_result["evidence"]["chromium_launch"]["sha256"] = _sha256(launch_bytes)

    result = verify_result(
        valid_profile,
        valid_manifest,
        valid_result,
        expected_code_head="a" * 40,
        expected_profile_sha256=_digest(36),
        expected_manifest_sha256=_digest(37),
        support_root=r"C:\tmp\support",
    )

    assert result.code == "FEASIBILITY_EVIDENCE_INVALID"


def test_result_rejects_mismatched_local_evidence_bytes(
    valid_profile: dict[str, object],
    valid_manifest: dict[str, object],
    valid_result: dict[str, object],
) -> None:
    """A claimed hash cannot replace rereading the retained local evidence file."""
    evidence_root = Path(valid_result["run"]["evidence_root"])
    (evidence_root / "chromium-version.txt").write_text("forged", encoding="utf-8")

    result = verify_result(
        valid_profile,
        valid_manifest,
        valid_result,
        expected_code_head="a" * 40,
        expected_profile_sha256=_digest(36),
        expected_manifest_sha256=_digest(37),
        support_root=r"C:\tmp\support",
    )

    assert result.code == "FEASIBILITY_EVIDENCE_MISMATCH"


def test_result_requires_materialized_seed_binding_in_the_fresh_profile(
    valid_profile: dict[str, object],
    valid_manifest: dict[str, object],
    valid_result: dict[str, object],
) -> None:
    """A declared seed must be retained inside the actual --user-data-dir profile."""
    profile_directory = Path(valid_result["chromium"]["managed_profile_path"])
    (profile_directory / "stm32tk-0600-seed-binding.json").unlink()

    result = verify_result(
        valid_profile,
        valid_manifest,
        valid_result,
        expected_code_head="a" * 40,
        expected_profile_sha256=_digest(36),
        expected_manifest_sha256=_digest(37),
        support_root=r"C:\tmp\support",
    )

    assert result.code == "FEASIBILITY_EVIDENCE_INVALID"


def test_result_rejects_seed_content_changed_after_the_browser_launch(
    valid_profile: dict[str, object],
    valid_manifest: dict[str, object],
    valid_result: dict[str, object],
) -> None:
    """The retained declaration cannot stand in for the materialized Local State bytes."""
    profile_directory = Path(valid_result["chromium"]["managed_profile_path"])
    (profile_directory / "Local State").write_text('{"forged":true}\n', encoding="utf-8")

    result = verify_result(
        valid_profile,
        valid_manifest,
        valid_result,
        expected_code_head="a" * 40,
        expected_profile_sha256=_digest(36),
        expected_manifest_sha256=_digest(37),
        support_root=r"C:\tmp\support",
    )

    assert result.code == "FEASIBILITY_EVIDENCE_MISMATCH"


@pytest.mark.parametrize(
    ("path", "code"),
    [
        ("CHROMIUM-LAUNCH.JSON", "FEASIBILITY_EVIDENCE_PATH_INVALID"),
        ("chromium-version.txt. ", "FEASIBILITY_EVIDENCE_PATH_INVALID"),
    ],
)
def test_result_rejects_windows_casefold_and_trailing_aliases_in_evidence_paths(
    valid_profile: dict[str, object],
    valid_manifest: dict[str, object],
    valid_result: dict[str, object],
    path: str,
    code: str,
) -> None:
    """Windows aliases cannot make two retained-evidence entries appear distinct."""
    valid_result["evidence"]["chromium_version"]["path"] = path

    result = verify_result(
        valid_profile,
        valid_manifest,
        valid_result,
        expected_code_head="a" * 40,
        expected_profile_sha256=_digest(36),
        expected_manifest_sha256=_digest(37),
        support_root=r"C:\tmp\support",
    )

    assert result.code == code


def test_result_rejects_boolean_rtt_channel_and_browser_exit(
    valid_profile: dict[str, object],
    valid_manifest: dict[str, object],
    valid_result: dict[str, object],
) -> None:
    """JSON booleans must never satisfy exact integer transport or exit-code fields."""
    valid_profile["capabilities"]["rtt"]["channel"] = True
    profile_result = verify_feasibility(valid_profile)
    valid_profile["capabilities"]["rtt"]["channel"] = 0
    valid_result["chromium"]["exit_code"] = False

    result = verify_result(
        valid_profile,
        valid_manifest,
        valid_result,
        expected_code_head="a" * 40,
        expected_profile_sha256=_digest(36),
        expected_manifest_sha256=_digest(37),
        support_root=r"C:\tmp\support",
    )

    assert profile_result.code == "FEASIBILITY_CAPABILITY_MISSING"
    assert result.code == "FEASIBILITY_RESULT_MISMATCH"


def test_collector_materializes_the_bound_seed_and_runs_a_controlled_browser_fixture(
    valid_profile: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Collection must retain the seed in the actual profile before a controlled blank launch."""
    root = _test_directory() / "support"
    profile_path = _write_controlled_support(root, valid_profile)
    evidence_root = root.parent / "evidence"
    host = copy.deepcopy(valid_profile["host"])

    monkeypatch.setattr(
        feasibility,
        "verify_committed_verifier",
        lambda _repo, _script: SimpleNamespace(code="PASS", details={"code_head": "c" * 40}),
    )
    monkeypatch.setattr(feasibility, "local_windows_identity", lambda: host)
    monkeypatch.setattr(
        feasibility,
        "_run_tool_version",
        lambda name, _record: valid_profile["tools"][name]["version"],
    )

    result = _run(
        SimpleNamespace(
            repo=str(Path.cwd()),
            support=str(root),
            profile=str(profile_path),
            evidence=str(evidence_root),
        )
    )

    assert result.code == "PASS"
    collected = json.loads((evidence_root / "result.json").read_text(encoding="utf-8"))
    assert collected["host"] == host
    assert collected["chromium"]["argv"] == _expected_chromium_argv(
        str(evidence_root), str(root)
    )
    retained = json.loads(
        (evidence_root / "chromium-profile-materialization.json").read_text(encoding="utf-8")
    )
    assert retained["seed"] == {
        "path": "feasibility/chromium-profile-seed.json",
        "sha256": collected["chromium"]["managed_profile_seed"]["sha256"],
    }
    assert (evidence_root / "managed-chromium-profile" / "Local State").read_text(
        encoding="utf-8"
    ) == PROFILE_LOCAL_STATE
    assert (
        evidence_root / "managed-chromium-profile" / "stm32tk-0600-seed-binding.json"
    ).read_bytes() == (evidence_root / "chromium-profile-materialization.json").read_bytes()


def test_verifier_must_match_the_repository_code_head_blob() -> None:
    """A copied or edited verifier cannot claim an unrelated repository CodeHead."""
    repo = _test_directory() / "repo"
    script = repo / "tools" / "release" / "verify_0600_feasibility.py"
    script.parent.mkdir(parents=True)
    script.write_text("trusted\n", encoding="utf-8")
    for args in (
        ["init"],
        ["config", "user.email", "test@example.invalid"],
        ["config", "user.name", "test"],
        ["config", "core.autocrlf", "false"],
        ["add", "."],
        ["commit", "-m", "fixture"],
    ):
        subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)

    trusted = verify_committed_verifier(repo, script)
    script.write_text("tampered\n", encoding="utf-8")
    tampered = verify_committed_verifier(repo, script)

    assert trusted.code == "PASS"
    assert tampered.code == "FEASIBILITY_CODEHEAD_MISMATCH"
