"""Behavior tests for the closed Windows-only 0600 feasibility verifier."""

from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest


RELEASE_DIR = Path(__file__).resolve().parents[3] / "release"
sys.path.insert(0, str(RELEASE_DIR))

from verify_0600_feasibility import (  # noqa: E402
    expected_chromium_argv,
    verify_feasibility,
    verify_result,
)


def _digest(number: int) -> str:
    return f"{number:064x}"


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
        "host": {"platform": "Windows", "architecture": "AMD64"},
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
            },
            "version_evidence": {
                "path": "chromium/chrome-version.manifest",
                "sha256": _digest(40),
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
                "bytes": 105,
                "sha256": _digest(40),
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
    evidence_root = r"C:\tmp\evidence\0600-run"
    support_root = r"C:\tmp\support"
    return {
        "schema": "stm32tk-0600-feasibility-result/1",
        "owner": "Codex",
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
            "version_evidence": copy.deepcopy(chromium["version_evidence"]),
            "blank_page": chromium["blank_page"]["path"],
            "argv": expected_chromium_argv(
                chromium, support_root, evidence_root
            ),
            "exit_code": 0,
        },
        "firmware_fixture": copy.deepcopy(profile["firmware_fixture"]),
        "capabilities": copy.deepcopy(profile["capabilities"]),
        "hardware": {"status": "PENDING"},
        "evidence": {
            "chromium_launch": {
                "path": "chromium-launch.json",
                "sha256": _digest(38),
            },
            "chromium_version": {
                "path": "chromium-version.txt",
                "sha256": _digest(39),
            },
        },
    }


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
