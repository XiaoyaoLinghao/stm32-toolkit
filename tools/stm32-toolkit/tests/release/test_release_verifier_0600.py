from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import math
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest


REPO = Path(__file__).resolve().parents[4]
RELEASE = REPO / "tools" / "release"
sys.path.insert(0, str(RELEASE))

import run_0600_gates as gates  # noqa: E402
import verify_0600_release as verifier  # noqa: E402
from run_0600_gates import (  # noqa: E402
    ControllerError,
    invoke_trusted_verifier,
    run_final_resume,
    run_wrapper_resume,
)
from verify_0600_release import (  # noqa: E402
    GOVERNANCE_OWNERS,
    REPORT_PATHS,
    VerificationError,
    calculate_performance_threshold,
    canonical_json_bytes,
    create_candidate_ledger,
    reconcile_candidate,
    validate_candidate_ledger,
    validate_recovery_record,
    verify_loaded_script_entry,
    verify_dependency_audit_input,
    verify_performance_calibration_input,
    verify_release_ledger_files,
)


RUN_ID = "123e4567-e89b-42d3-a456-426614174000"
HEADS = {
    "programBase": "bb6bc5e9ee937e4ce53996b31f25bf1109ffe13f",
    "0400Product": "96966c461e7e11bff965027d8d498dd40ea5fd55",
    "0400Report": "0ee0a5037b3bd158eea5bd312fce7feaadecbfc6",
    "0601Product": "1" * 40,
    "0601Report": "2" * 40,
    "0602Product": "3" * 40,
    "0602Report": "4" * 40,
    "0603Product": "5" * 40,
}
REPOSITORY_URL = "https://github.com/XiaoyaoLinghao/stm32-toolkit.git"


@pytest.mark.parametrize(
    ("fixture", "framework", "expected"),
    [
        ("pytest-8.4.2-junit.xml", "pytest-junit", [{"node_id": "native.pytest_fixture::test_native_pass", "outcome": "passed"}, {"node_id": "native.pytest_fixture::test_native_fail", "outcome": "failed"}]),
        ("ctest-4.3.1-junit.xml", "ctest-junit", [{"node_id": "native-pass", "outcome": "passed"}, {"node_id": "native-fail", "outcome": "failed"}]),
        ("vitest-4.1.10.json", "vitest-json", [{"node_id": "native pass", "outcome": "passed"}, {"node_id": "native fail", "outcome": "failed"}]),
        ("playwright-1.56.1-list.json", "playwright-json", [{"node_id": "chromium-1280::native/playwright.fixture.spec.mjs::native list-only", "outcome": "skipped"}]),
    ],
)
def test_terminal_verifier_reparses_controller_native_artifacts(
    fixture: str, framework: str, expected: list[dict[str, str]]
) -> None:
    """Final evidence derives nodes from the retained native runner artifact, never stdout JSONL."""
    raw = (REPO / "tools/stm32-toolkit/tests/release/fixtures/native-outcomes" / fixture).read_bytes()

    assert verifier._parse_retained_native_outcomes(framework, raw) == expected


def test_portable_validation_allows_only_the_native_evidence_root_placeholder() -> None:
    assert verifier._contains_rooted_private_path("<EVIDENCE_ROOT>/native-results.xml") is False
    assert verifier._contains_rooted_private_path("C:\\Users\\private\\native-results.xml") is True


@pytest.fixture
def tmp_path() -> Path:
    root = Path(tempfile.mkdtemp(prefix="stm32tk-0601-verifier-", dir=r"C:\tmp"))
    try:
        yield root
    finally:
        def clear_readonly(function: object, path: str, _error: object) -> None:
            os.chmod(path, stat.S_IWRITE)
            function(path)

        shutil.rmtree(root, onerror=clear_readonly)


@pytest.fixture(autouse=True)
def _trusted_secure_io_adapter(monkeypatch: pytest.MonkeyPatch) -> None:
    """Direct tests inject the already-imported controller; CLI has no such bypass."""
    monkeypatch.setattr(verifier, "_SECURE_IO_TEST_ADAPTER", gates, raising=False)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_canonical(path: Path, value: object) -> bytes:
    data = canonical_json_bytes(value)
    path.write_bytes(data)
    path.with_name(path.name + ".sha256").write_bytes((_sha(data) + "\n").encode("ascii"))
    return data


def _artifact(kind: str, path: str, file: Path) -> dict[str, object]:
    data = file.read_bytes()
    return {"kind": kind, "path": path, "bytes": len(data), "sha256": _sha(data)}


class LedgerGit:
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, args: list[str]) -> str:
        self.calls.append(tuple(args))
        if args[:2] == ["cat-file", "-e"]:
            return ""
        if args[:2] == ["merge-base", "--is-ancestor"]:
            return ""
        if args[:2] == ["rev-list", "--parents"]:
            commit = args[-1]
            parent = HEADS["0601Product"] if commit == HEADS["0601Report"] else HEADS["0602Product"]
            return f"{commit} {parent}\n"
        if args[:3] == ["diff-tree", "--no-commit-id", "--name-only"]:
            commit = args[-1]
            return REPORT_PATHS["0601"] + "\n" if commit == HEADS["0601Report"] else REPORT_PATHS["0602"] + "\n"
        if args[:2] == ["rev-parse", "HEAD"]:
            return HEADS["0603Product"] + "\n"
        if args[:2] == ["status", "--porcelain=v1"]:
            return ""
        raise AssertionError(f"unexpected git call: {args}")


@pytest.fixture
def ledger_fixture(tmp_path: Path) -> SimpleNamespace:
    repo = tmp_path / "repo"
    repo.mkdir()
    repository_members: list[dict[str, object]] = []
    for index, (kind, relative) in enumerate(
        [
            ("catalog", "tools/release/gates_0600.json"),
            ("controller", "tools/release/run_0600_final.ps1"),
            ("verifier", "tools/release/verify_0600_release.py"),
            ("spec", "docs/spec.md"),
            ("plan", "docs/plan.md"),
            ("lock", "package-lock.json"),
            ("software-support", "support/software.json"),
        ]
    ):
        path = repo.joinpath(*relative.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f"repository-{index}\n".encode())
        repository_members.append(_artifact(kind, relative, path))

    external = tmp_path / "external"
    external.mkdir()
    support_profile = external / "support-profile.json"
    support_manifest = external / "support-manifest.json"
    firmware_0400 = external / "firmware-0400.elf"
    firmware_0600 = external / "firmware-0600.elf"
    support_profile.write_bytes(b"profile\n")
    support_manifest.write_bytes(b"manifest\n")
    firmware_0400.write_bytes(b"firmware-0400\n")
    firmware_0600.write_bytes(b"firmware-0600\n")

    governance = {
        "bounded_overrides": ["Task 2 local implementation only"],
        "hardware_evidence_owner": "user",
        "implementation_owner": "Codex/local derived agents",
        "remote_actions": [],
        "remote_state": "no remote action authorized",
        "reviewer": "Codex",
        "specification_owner": "Codex",
        "windows_evidence_owner": "Codex",
    }
    software = {
        "repositoryUrl": REPOSITORY_URL,
        **HEADS,
        "governance": copy.deepcopy(governance),
        "artifacts": copy.deepcopy(repository_members),
    }
    software_path = tmp_path / "software-input.json"
    software_bytes = _write_canonical(software_path, software)

    def ref(path: Path) -> dict[str, object]:
        data = path.read_bytes()
        return {"path": str(path), "bytes": len(data), "sha256": _sha(data)}

    hardware = {
        "schema": "stm32-hardware-campaign-inputs/1",
        "campaign_id": "223e4567-e89b-42d3-a456-426614174000",
        "created_at_utc": "2026-08-15T02:03:04.123456Z",
        "generator_code_head": HEADS["0603Product"],
        "evidence_owner": "user",
        "board_id": "stm32f407-discovery-A",
        "board_revision": "D-01",
        "mcu_part": "STM32F407VGT6",
        "mcu_uid_hash": "6" * 64,
        "probe_model": "ST-LINK/V2-A",
        "probe_serial_hash": "7" * 64,
        "uart_adapter_model": "FT232R-A",
        "uart_serial_hash": "8" * 64,
        "power_identity": "bench-supply-channel-1",
        "transports": ["mailbox", "rtt", "semihosting", "uart"],
        "support_profile": ref(support_profile),
        "support_manifest": ref(support_manifest),
        "firmware_0400": {**ref(firmware_0400), "build_id": "0400-real-board-build-A"},
        "firmware_0600": {**ref(firmware_0600), "build_id": "0600-real-board-build-A"},
    }
    hardware_path = tmp_path / "hardware-input.json"
    hardware_bytes = _write_canonical(hardware_path, hardware)

    projected = [
        _artifact("hardware-support", str(support_profile), support_profile),
        _artifact("hardware-support", str(support_manifest), support_manifest),
        _artifact("firmware", str(firmware_0400), firmware_0400),
        _artifact("firmware", str(firmware_0600), firmware_0600),
    ]
    union = repository_members + projected
    union.sort(key=lambda item: (str(item["kind"]).encode(), str(item["path"]).encode()))
    ledger = {
        "schema": "stm32-release-ledger/1",
        "repositoryUrl": REPOSITORY_URL,
        **HEADS,
        "governance": copy.deepcopy(governance),
        "softwareInput": {"path": str(software_path), "bytes": len(software_bytes), "sha256": _sha(software_bytes)},
        "hardwareInput": {"path": str(hardware_path), "bytes": len(hardware_bytes), "sha256": _sha(hardware_bytes)},
        "hardware": copy.deepcopy(hardware),
        "artifacts": union,
    }
    ledger_path = tmp_path / "release-ledger.json"
    _write_canonical(ledger_path, ledger)
    return SimpleNamespace(
        repo=repo,
        ledger=ledger,
        ledger_path=ledger_path,
        digest_path=ledger_path.with_name(ledger_path.name + ".sha256"),
        software=software,
        software_path=software_path,
        hardware=hardware,
        hardware_path=hardware_path,
        git=LedgerGit(),
    )


def _verify(fixture: SimpleNamespace, **kwargs: object) -> dict[str, str]:
    return verify_release_ledger_files(
        fixture.ledger_path,
        fixture.digest_path,
        fixture.software_path,
        fixture.hardware_path,
        repository=fixture.repo,
        git_runner=fixture.git,
        entry_checker=lambda expected: None,
        **kwargs,
    )


def test_report_paths_and_governance_owner_constants_are_single_and_exact() -> None:
    """A divergent report path or owner spelling must not enter verifier fixtures."""
    assert REPORT_PATHS == {
        "0601": "docs/codex/returns/STM32TK-0601-TEST-EVIDENCE/implementation-report.md",
        "0602": "docs/codex/returns/STM32TK-0602-DIAGNOSTIC-LOOP/implementation-report.md",
    }
    assert GOVERNANCE_OWNERS == {
        "specification_owner": "Codex",
        "implementation_owner": "Codex/local derived agents",
        "reviewer": "Codex",
        "windows_evidence_owner": "Codex",
        "hardware_evidence_owner": "user",
    }


def test_valid_release_ledger_is_read_only_and_returns_only_canonical_pass(
    ledger_fixture: SimpleNamespace, capsys: pytest.CaptureFixture[str]
) -> None:
    """One complete local fixture must validate without gate dispatch or premature stdout."""
    dispatches: list[str] = []

    result = _verify(ledger_fixture, dispatch_recorder=dispatches)

    assert result == {"mode": "verify-release-ledger", "status": "PASS"}
    assert capsys.readouterr().out == ""
    assert dispatches == []


@pytest.mark.parametrize(
    "mutation",
    [
        "root-extra",
        "root-missing",
        "governance-extra",
        "governance-type",
        "software-extra",
        "hardware-extra",
        "hardware-nested-extra",
        "artifact-extra",
        "artifact-bool-bytes",
        "artifact-kind",
        "artifact-order",
        "duplicate-source-artifact",
        "casefold-source-artifact",
        "same-path-other-kind",
        "missing-union-member",
        "extra-union-member",
    ],
)
def test_release_ledger_is_recursively_closed_typed_and_exact_union(
    ledger_fixture: SimpleNamespace, mutation: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """Extra/missing/wrong-type/duplicate/conflicting members at every level must fail silently."""
    ledger = copy.deepcopy(ledger_fixture.ledger)
    software = copy.deepcopy(ledger_fixture.software)
    if mutation == "root-extra":
        ledger["extra"] = None
    elif mutation == "root-missing":
        ledger.pop("programBase")
    elif mutation == "governance-extra":
        ledger["governance"]["extra"] = None
    elif mutation == "governance-type":
        ledger["governance"]["remote_actions"] = {}
    elif mutation == "software-extra":
        software["extra"] = None
    elif mutation == "hardware-extra":
        ledger["hardware"]["extra"] = None
    elif mutation == "hardware-nested-extra":
        ledger["hardware"]["support_profile"]["extra"] = None
    elif mutation == "artifact-extra":
        ledger["artifacts"][0]["extra"] = None
    elif mutation == "artifact-bool-bytes":
        ledger["artifacts"][0]["bytes"] = True
    elif mutation == "artifact-kind":
        ledger["artifacts"][0]["kind"] = "unknown"
    elif mutation == "artifact-order":
        ledger["artifacts"].reverse()
    elif mutation == "duplicate-source-artifact":
        software["artifacts"].append(copy.deepcopy(software["artifacts"][0]))
    elif mutation == "casefold-source-artifact":
        alias = copy.deepcopy(software["artifacts"][0])
        alias["path"] = str(alias["path"]).upper()
        software["artifacts"].append(alias)
        ledger["artifacts"].append(copy.deepcopy(alias))
        ledger["artifacts"].sort(
            key=lambda item: (item["kind"].encode(), item["path"].encode())
        )
    elif mutation == "same-path-other-kind":
        conflict = copy.deepcopy(software["artifacts"][0])
        conflict["kind"] = "controller"
        software["artifacts"].append(conflict)
    elif mutation == "missing-union-member":
        ledger["artifacts"].pop()
    else:
        extra_file = ledger_fixture.repo / "extra-lock.json"
        extra_file.write_bytes(b"extra\n")
        ledger["artifacts"].append(_artifact("lock", "extra-lock.json", extra_file))
        ledger["artifacts"].sort(key=lambda item: (item["kind"].encode(), item["path"].encode()))

    if software != ledger_fixture.software:
        software_bytes = _write_canonical(ledger_fixture.software_path, software)
        ledger["softwareInput"] = {"path": str(ledger_fixture.software_path), "bytes": len(software_bytes), "sha256": _sha(software_bytes)}
    _write_canonical(ledger_fixture.ledger_path, ledger)

    with pytest.raises(VerificationError):
        _verify(ledger_fixture)
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize(
    "mutation",
    [
        "wrong-repository",
        "fixed-base",
        "bad-commit-type",
        "ancestry",
        "report-parent",
        "report-path",
    ],
)
def test_release_ledger_freezes_git_identities_ancestry_and_report_only_edges(
    ledger_fixture: SimpleNamespace, mutation: str
) -> None:
    """Fixed identities and sole-parent/report-only ancestry must be proven by Git."""
    ledger = copy.deepcopy(ledger_fixture.ledger)
    if mutation == "wrong-repository":
        ledger["repositoryUrl"] = "https://example.invalid/repo.git"
    elif mutation == "fixed-base":
        ledger["0400Product"] = "0" * 40
    elif mutation == "bad-commit-type":
        ledger_fixture.git = lambda args: (_ for _ in ()).throw(VerificationError("not commit"))
    elif mutation == "ancestry":
        original = ledger_fixture.git
        ledger_fixture.git = lambda args: (_ for _ in ()).throw(VerificationError("not ancestor")) if args[:2] == ["merge-base", "--is-ancestor"] else original(args)
    elif mutation == "report-parent":
        original = ledger_fixture.git
        ledger_fixture.git = lambda args: f"{args[2]} {'9' * 40}\n" if args[:2] == ["rev-list", "--parents"] else original(args)
    else:
        original = ledger_fixture.git
        ledger_fixture.git = lambda args: "wrong/report.md\n" if args[:3] == ["diff-tree", "--no-commit-id", "--name-only"] else original(args)
    _write_canonical(ledger_fixture.ledger_path, ledger)

    with pytest.raises(VerificationError):
        _verify(ledger_fixture)


@pytest.mark.parametrize(
    "mutation",
    [
        "software-ref",
        "hardware-ref",
        "swapped",
        "ledger-sidecar",
        "source-sidecar",
        "source-bytes",
        "artifact-bytes",
        "hardware-campaign",
        "hardware-generator",
        "hardware-owner",
        "hardware-placeholder",
        "transport-order",
        "firmware-build-id",
        "noncanonical-source",
        "noncanonical-ledger",
    ],
)
def test_source_sidecar_hardware_identity_and_artifact_mutations_fail_before_pass(
    ledger_fixture: SimpleNamespace, mutation: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """Every source/sidecar/identity/file byte remains reread-bound to the ledger."""
    ledger = copy.deepcopy(ledger_fixture.ledger)
    hardware = copy.deepcopy(ledger_fixture.hardware)
    if mutation == "software-ref":
        ledger["softwareInput"]["bytes"] += 1
    elif mutation == "hardware-ref":
        ledger["hardwareInput"]["sha256"] = "0" * 64
    elif mutation == "swapped":
        with pytest.raises(VerificationError):
            verify_release_ledger_files(
                ledger_fixture.ledger_path,
                ledger_fixture.digest_path,
                ledger_fixture.hardware_path,
                ledger_fixture.software_path,
                repository=ledger_fixture.repo,
                git_runner=ledger_fixture.git,
                entry_checker=lambda expected: None,
            )
        assert capsys.readouterr().out == ""
        return
    elif mutation == "ledger-sidecar":
        ledger_fixture.digest_path.write_bytes(("0" * 64 + "\n").encode())
    elif mutation == "source-sidecar":
        ledger_fixture.software_path.with_name(ledger_fixture.software_path.name + ".sha256").write_bytes(("0" * 64 + "\n").encode())
    elif mutation == "source-bytes":
        ledger_fixture.software_path.write_bytes(ledger_fixture.software_path.read_bytes() + b" ")
    elif mutation == "artifact-bytes":
        (ledger_fixture.repo / ledger["artifacts"][0]["path"]).write_bytes(b"changed")
    elif mutation == "hardware-campaign":
        hardware["campaign_id"] = "not-a-uuid"
    elif mutation == "hardware-generator":
        hardware["generator_code_head"] = "9" * 40
    elif mutation == "hardware-owner":
        hardware["evidence_owner"] = "Codex"
    elif mutation == "hardware-placeholder":
        hardware["board_id"] = "unknown"
    elif mutation == "transport-order":
        hardware["transports"] = ["rtt", "mailbox", "semihosting", "uart"]
    elif mutation == "firmware-build-id":
        hardware["firmware_0600"]["build_id"] = hardware["firmware_0400"]["build_id"]
    elif mutation == "noncanonical-source":
        raw = json.dumps(ledger_fixture.software, sort_keys=False).encode() + b"\n"
        ledger_fixture.software_path.write_bytes(raw)
        ledger_fixture.software_path.with_name(ledger_fixture.software_path.name + ".sha256").write_bytes((_sha(raw) + "\n").encode())
    else:
        raw = json.dumps(ledger, sort_keys=False).encode() + b"\n"
        ledger_fixture.ledger_path.write_bytes(raw)
        ledger_fixture.digest_path.write_bytes((_sha(raw) + "\n").encode())
    if hardware != ledger_fixture.hardware:
        hardware_bytes = _write_canonical(ledger_fixture.hardware_path, hardware)
        ledger["hardware"] = hardware
        ledger["hardwareInput"] = {"path": str(ledger_fixture.hardware_path), "bytes": len(hardware_bytes), "sha256": _sha(hardware_bytes)}
    if mutation not in {"ledger-sidecar", "source-sidecar", "source-bytes", "artifact-bytes", "noncanonical-source", "noncanonical-ledger"}:
        _write_canonical(ledger_fixture.ledger_path, ledger)

    with pytest.raises(VerificationError):
        _verify(ledger_fixture)
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize(
    ("field_path", "placeholder"),
    [
        (("board_id",), "board-FiXtUrE-v1"),
        (("board_revision",), "reserved-revision"),
        (("mcu_part",), "test-mcu"),
        (("probe_model",), "probeUnset"),
        (("uart_adapter_model",), "placeholder-uart"),
        (("power_identity",), "power-tbd"),
        (("firmware_0400", "build_id"), "fixture-build"),
        (("firmware_0600", "build_id"), "reservedBuild"),
        (("board_id",), "redacted-board"),
        (("board_revision",), "revision-null"),
        (("mcu_part",), "nil-mcu"),
        (("probe_model",), "noneProbe"),
        (("uart_adapter_model",), "adapter-na"),
        (("power_identity",), "power-redacted"),
        (("firmware_0400", "build_id"), "null-build"),
        (("firmware_0600", "build_id"), "buildNil"),
    ],
)
def test_every_bounded_campaign_and_firmware_identity_rejects_placeholders(
    ledger_fixture: SimpleNamespace,
    field_path: tuple[str, ...],
    placeholder: str,
) -> None:
    """Every human-readable campaign/build identity must reject normalized placeholders."""
    hardware = copy.deepcopy(ledger_fixture.hardware)
    target = hardware
    for name in field_path[:-1]:
        target = target[name]
    target[field_path[-1]] = placeholder
    hardware_bytes = _write_canonical(ledger_fixture.hardware_path, hardware)
    ledger = copy.deepcopy(ledger_fixture.ledger)
    ledger["hardware"] = hardware
    ledger["hardwareInput"] = {
        "path": str(ledger_fixture.hardware_path),
        "bytes": len(hardware_bytes),
        "sha256": _sha(hardware_bytes),
    }
    _write_canonical(ledger_fixture.ledger_path, ledger)

    with pytest.raises(VerificationError, match="identity|placeholder|build"):
        _verify(ledger_fixture)


def test_hardware_campaign_owner_rejects_placeholder_even_when_expected_matches(
    ledger_fixture: SimpleNamespace,
) -> None:
    """Caller-supplied expected owner equality cannot make a placeholder owner valid."""
    hardware = copy.deepcopy(ledger_fixture.hardware)
    hardware["evidence_owner"] = "fixture-owner"

    with pytest.raises(VerificationError, match="identity|owner|placeholder"):
        verifier._validate_hardware(
            hardware, product_0603=HEADS["0603Product"], owner="fixture-owner"
        )


@pytest.mark.parametrize(
    "owner",
    ["redacted-owner", "owner-null", "nilOwner", "owner-none", "owner-na"],
)
def test_hardware_campaign_owner_rejects_every_normalized_placeholder_affix(
    ledger_fixture: SimpleNamespace, owner: str
) -> None:
    """Every frozen normalized placeholder token is forbidden in the owner identity."""
    hardware = copy.deepcopy(ledger_fixture.hardware)
    hardware["evidence_owner"] = owner

    with pytest.raises(VerificationError, match="identity|owner|placeholder"):
        verifier._validate_hardware(hardware, product_0603=HEADS["0603Product"], owner=owner)


@pytest.mark.parametrize(
    ("field_path", "placeholder"),
    [
        (("evidence_owner",), "teamReservedOwner42"),
        (("board_id",), "boardFixtureRevA"),
        (("board_revision",), "boardTestUnit7"),
        (("mcu_part",), "mcuUnsetPart2"),
        (("probe_model",), "probeUnsetModel2"),
        (("uart_adapter_model",), "uartFixtureAdapter7"),
        (("power_identity",), "benchTestRail4"),
        (("firmware_0400", "build_id"), "fwReservedBuild42"),
        (("firmware_0600", "build_id"), "fwUnsetBuild7"),
        (("board_id",), "boardN/A"),
        (("board_id",), "boardN/A42"),
        (("board_id",), "boardN/ARev"),
    ],
)
def test_every_bounded_identity_rejects_embedded_placeholder_components(
    ledger_fixture: SimpleNamespace,
    field_path: tuple[str, ...],
    placeholder: str,
) -> None:
    """Camel, digit, and separator boundaries cannot hide a placeholder component."""
    hardware = copy.deepcopy(ledger_fixture.hardware)
    target = hardware
    for name in field_path[:-1]:
        target = target[name]
    target[field_path[-1]] = placeholder

    with pytest.raises(VerificationError, match="identity|owner|placeholder|build"):
        verifier._validate_hardware(
            hardware,
            product_0603=HEADS["0603Product"],
            owner=str(hardware["evidence_owner"]),
        )


@pytest.mark.parametrize(
    "identity",
    ["contest", "testimony", "attestation-unit-7", "protestBoard42"],
)
def test_bounded_identity_allows_placeholder_letters_without_word_boundaries(
    identity: str,
) -> None:
    """Letters spelling a placeholder inside an ordinary word are not a component."""
    assert verifier._bounded_identity(identity)


def test_external_hardware_file_rejects_a_reparse_ancestor(
    ledger_fixture: SimpleNamespace, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A regular leaf reached through a junction is still a linked hardware artifact."""
    real = tmp_path / "real-external"
    real.mkdir()
    real_firmware = real / "firmware-0600.elf"
    real_firmware.write_bytes(b"firmware-through-junction\n")
    junction = tmp_path / "external-alias"
    created = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(junction), str(real)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert created.returncode == 0, created.stderr
    try:
        hardware = copy.deepcopy(ledger_fixture.hardware)
        old_path = hardware["firmware_0600"]["path"]
        alias_firmware = junction / real_firmware.name
        data = alias_firmware.read_bytes()
        hardware["firmware_0600"] = {
            "path": str(alias_firmware),
            "bytes": len(data),
            "sha256": _sha(data),
            "build_id": "0600-real-board-build-A",
        }
        hardware_bytes = _write_canonical(ledger_fixture.hardware_path, hardware)
        ledger = copy.deepcopy(ledger_fixture.ledger)
        ledger["hardware"] = hardware
        ledger["hardwareInput"] = {
            "path": str(ledger_fixture.hardware_path),
            "bytes": len(hardware_bytes),
            "sha256": _sha(hardware_bytes),
        }
        ledger["artifacts"] = [
            _artifact("firmware", str(alias_firmware), alias_firmware)
            if item["kind"] == "firmware" and item["path"] == old_path
            else item
            for item in ledger["artifacts"]
        ]
        ledger["artifacts"].sort(
            key=lambda item: (str(item["kind"]).encode(), str(item["path"]).encode())
        )
        _write_canonical(ledger_fixture.ledger_path, ledger)

        with pytest.raises(VerificationError):
            _verify(ledger_fixture)
        assert capsys.readouterr().out == ""
    finally:
        os.rmdir(junction)


def test_mutation_between_first_read_and_final_reread_fails_silently(
    ledger_fixture: SimpleNamespace, capsys: pytest.CaptureFixture[str]
) -> None:
    """A ledger/source TOCTOU mutation after validation must fail the unchanged reread."""
    def mutate() -> None:
        ledger_fixture.hardware_path.write_bytes(ledger_fixture.hardware_path.read_bytes() + b" ")

    with pytest.raises(VerificationError):
        _verify(ledger_fixture, before_final_reread=mutate)
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize(
    ("batches", "tick", "maximum", "expected"),
    [
        ([900, 1000, 1100], 10, 2000, (1000, 100, 1300)),
        ([1000, 1000, 1000], 10, 1200, None),
        ([993, 1003, 1013], 8, 2000, (1003, 10, 1256)),
    ],
)
def test_performance_threshold_math_is_unclamped_tick_rounded_and_exact(
    batches: list[int], tick: int, maximum: int, expected: tuple[int, int, int] | None
) -> None:
    """Changing MAD/max/tick rounding or clamping an over-maximum threshold must fail vectors."""
    if expected is None:
        with pytest.raises(VerificationError):
            calculate_performance_threshold(batches, clock_tick=tick, design_maximum=maximum)
    else:
        result = calculate_performance_threshold(batches, clock_tick=tick, design_maximum=maximum)
        assert (result["baseline"], result["mad"], result["absolute_threshold"]) == expected


def test_performance_and_dependency_subcommands_validate_closed_authoritative_inputs() -> None:
    """The named verifier modes must execute their closed math/policy contract, not remain stubs."""
    performance = {
        "schema": "stm32-performance-calibration-input/1",
        "batch_p95": [900, 1000, 1100],
        "clock_tick": 10,
        "design_maximum": 2000,
    }
    audit = {
        "schema": "stm32-dependency-audit-input/1",
        "readiness_at_utc": "2026-08-15T02:03:04.123456Z",
        "candidate_started_at_utc": "2026-08-15T02:03:04.123456Z",
        "audit": {
            "schema": "stm32-offline-audit/1",
            "network": False,
            "advisory": {
                "source": "npm-advisory-snapshot",
                "database_version": "2026-08-14",
                "generated_at_utc": "2026-08-14T00:00:00.000000Z",
                "sha256": "a" * 64,
            },
            "cache_sha256": "b" * 64,
            "production": {"critical": 0, "high": 0, "moderate": 0, "low": 0},
            "development": {"critical": 0, "high": 0, "moderate": 1, "low": 1},
            "exceptions": [],
        },
    }

    assert verify_performance_calibration_input(performance) == {
        "absolute_threshold": 1300,
        "baseline": 1000,
        "mad": 100,
        "mode": "performance-calibration",
        "status": "PASS",
    }
    assert verify_dependency_audit_input(audit) == {
        "mode": "dependency-audit",
        "status": "PASS",
    }


def _recovery(checkpoint: Path) -> dict[str, object]:
    return {
        "checkpoint": str(checkpoint),
        "classification": "RECOVERABLE_INFRA_ERROR",
        "code_head": "a" * 40,
        "event": "HOST_POWER_OR_REBOOT",
        "interrupted_attempt_digest": "b" * 64,
        "recorded_at_utc": "2026-08-15T02:03:04.123456Z",
        "reviewer": "Codex",
        "run_id": RUN_ID,
        "run_kind": "candidate-0601",
    }


def test_program_recovery_record_exact_schema_and_enums(tmp_path: Path) -> None:
    """The one reviewer-authored recovery schema must validate exact run/checkpoint identity."""
    checkpoint = tmp_path / "checkpoint.json"
    checkpoint.write_bytes(b"retained")
    value = _recovery(checkpoint)

    validate_recovery_record(
        value,
        expected_run_kind="candidate-0601",
        expected_run_id=RUN_ID,
        expected_code_head="a" * 40,
        expected_checkpoint=checkpoint,
        expected_attempt_digest="b" * 64,
    )


@pytest.mark.parametrize("mutation", ["extra", "missing", "classification", "disk-event", "run-kind", "relative", "bool", "mismatch"])
def test_recovery_record_rejects_every_non_program_or_mismatched_form(
    tmp_path: Path, mutation: str
) -> None:
    """Disk/product events, coercion, and inferred identity must never authorize resume."""
    checkpoint = tmp_path / "checkpoint.json"
    checkpoint.write_bytes(b"retained")
    value = _recovery(checkpoint)
    if mutation == "extra":
        value["extra"] = None
    elif mutation == "missing":
        value.pop("reviewer")
    elif mutation == "classification":
        value["classification"] = "PRODUCT_FAILURE"
    elif mutation == "disk-event":
        value["event"] = "DISK_FULL"
    elif mutation == "run-kind":
        value["run_kind"] = "candidate-9999"
    elif mutation == "relative":
        value["checkpoint"] = "checkpoint.json"
    elif mutation == "bool":
        value["reviewer"] = True
    else:
        value["run_id"] = "223e4567-e89b-42d3-a456-426614174000"

    with pytest.raises(VerificationError):
        validate_recovery_record(value, expected_run_kind="candidate-0601", expected_run_id=RUN_ID, expected_code_head="a" * 40, expected_checkpoint=checkpoint, expected_attempt_digest="b" * 64)


def _candidate(tmp_path: Path) -> tuple[dict[str, object], dict[str, Path]]:
    worktree = tmp_path / "repo"
    paths = {
        "controller": worktree / "tools/release/run_0600_candidate.ps1",
        "verifier": worktree / "tools/release/verify_0600_release.py",
        "catalog": worktree / "tools/release/gates_0600.json",
        "performance": worktree / "tools/release/performance_0600.json",
        "support": tmp_path / "support/profile.json",
    }
    for name, path in paths.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f"{name}\n".encode())
    candidate_root = tmp_path / "candidate"
    evidence_root = candidate_root / "evidence"
    candidate_root.mkdir()
    ledger = create_candidate_ledger(
        controller_path=paths["controller"],
        candidate_root=candidate_root,
        evidence_root=evidence_root,
        run_id=RUN_ID,
        expected_code_head="a" * 40,
        catalog_sha256=_sha(paths["catalog"].read_bytes()),
        performance_sha256=_sha(paths["performance"].read_bytes()),
        support_profile_sha256=_sha(paths["support"].read_bytes()),
        now=datetime(2026, 8, 15, 2, 3, 4, 123456, tzinfo=timezone.utc),
    )
    return ledger, paths


def test_candidate_ledger_closed_schema_and_immutable_identity(tmp_path: Path) -> None:
    """Only the wrapper-owned ledger may bind candidate roots/hashes/checkpoint/state."""
    ledger, _ = _candidate(tmp_path)

    validate_candidate_ledger(ledger)

    assert set(ledger) == {
        "schema", "module", "candidate_run_id", "expected_code_head", "controller_path",
        "candidate_root", "evidence_root", "catalog_sha256", "performance_sha256",
        "support_profile_sha256", "checkpoint", "state", "created_at_utc", "updated_at_utc",
    }
    assert ledger["schema"] == "stm32-candidate-ledger/1"
    assert ledger["module"] == "STM32TK-0601"
    assert ledger["state"] == "prepared"


@pytest.mark.parametrize("mutation", ["extra", "missing", "relative", "wrong-state", "bool", "wrong-module", "checkpoint-relative"])
def test_candidate_ledger_rejects_extra_missing_relative_and_wrong_types(
    tmp_path: Path, mutation: str
) -> None:
    """An orchestration context or coerced value cannot substitute for the authoritative ledger."""
    ledger, _ = _candidate(tmp_path)
    if mutation == "extra":
        ledger["verifier_path"] = "supplied.py"
    elif mutation == "missing":
        ledger.pop("catalog_sha256")
    elif mutation == "relative":
        ledger["evidence_root"] = "evidence"
    elif mutation == "wrong-state":
        ledger["state"] = "resuming"
    elif mutation == "bool":
        ledger["checkpoint"] = False
    elif mutation == "wrong-module":
        ledger["module"] = "STM32TK-0604"
    else:
        ledger["checkpoint"] = "checkpoint.json"

    with pytest.raises(VerificationError):
        validate_candidate_ledger(ledger)


class CandidateGit:
    def __init__(self, worktree: Path, head: str = "a" * 40, origin: str = REPOSITORY_URL, dirty: str = "") -> None:
        self.worktree = worktree
        self.head = head
        self.origin = origin
        self.dirty = dirty
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, args: list[str]) -> str:
        self.calls.append(tuple(args))
        if args == ["rev-parse", "HEAD"]:
            return self.head + "\n"
        if args == ["config", "--get", "remote.origin.url"]:
            return self.origin + "\n"
        if args == ["status", "--porcelain=v1", "--untracked-files=all"]:
            return self.dirty
        if args[:2] == ["hash-object", "--"]:
            path = Path(args[2])
            return _sha(path.read_bytes())[:40] + "\n"
        if args[0] == "rev-parse" and ":" in args[1]:
            relative = args[1].split(":", 1)[1]
            path = self.worktree.joinpath(*relative.split("/"))
            return _sha(path.read_bytes())[:40] + "\n"
        raise AssertionError(args)


def test_candidate_reconciliation_rederives_only_committed_paths_and_exact_worktree(
    tmp_path: Path,
) -> None:
    """Clean HEAD/origin/blob/hash checks must precede returning the sole verifier executable."""
    ledger, paths = _candidate(tmp_path)
    git = CandidateGit(paths["controller"].parents[2])

    result = reconcile_candidate(ledger, git_runner=git)

    assert result == paths["verifier"]
    assert ("status", "--porcelain=v1", "--untracked-files=all") in git.calls


def test_candidate_evidence_recursively_verifies_catalog_inventory_package_and_retained_files(
    tmp_path: Path,
) -> None:
    """Candidate PASS is impossible unless the checkpoint, inventory, external files, and ZIP all close."""
    candidate_root = tmp_path / "candidate-closed"
    evidence = candidate_root / "evidence"
    head = subprocess.run(
        ["git", "-C", str(REPO), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    result = gates.run_wrapper_contract(
        kind="candidate", matrix="candidate", module="STM32TK-0601", _candidate_temporary_root=tmp_path,
        shard="release-contract", run_id=RUN_ID, evidence_root=evidence,
        expected_code_head=head, gate_catalog=RELEASE / "gates_0600.json",
        performance_catalog=RELEASE / "performance_0600.json",
        support_profile=Path(r"C:\tmp\stm32tk-0600-support\feasibility\profile.json"),
        controller_path=RELEASE / "run_0600_candidate.ps1",
        verifier_blob_checker=lambda _repo, _head: RELEASE / "verify_0600_release.py",
        verifier_invoker=lambda _repo, _head, _argv: SimpleNamespace(returncode=0),
        now=lambda: datetime(2026, 8, 15, 2, 3, 4, 123456, tzinfo=timezone.utc),
    )
    ledger_path = candidate_root / "candidate-ledger.json"

    verified = verifier.verify_candidate_evidence_file(
        ledger_path,
        git_runner=CandidateGit(REPO, head=head),
    )

    assert verified == {"mode": "candidate-evidence", "status": "PASS"}
    assert result["status"] == "BLOCKED"

    checkpoint = evidence / "controller-result.json"
    checkpoint_value = json.loads(checkpoint.read_text(encoding="utf-8"))
    checkpoint_value["gate_inventory"] = checkpoint_value["gate_inventory"][:-1]
    checkpoint.write_bytes(canonical_json_bytes(checkpoint_value))
    with pytest.raises(VerificationError, match="inventory|package|evidence"):
        verifier.verify_candidate_evidence_file(
            ledger_path,
            git_runner=CandidateGit(REPO, head=head),
        )


def test_final_evidence_recursively_binds_checkpoint_and_shard_package(tmp_path: Path) -> None:
    """Final evidence must bind the final checkpoint to the complete catalog-derived shard."""
    evidence = tmp_path / "final-closed"
    head = subprocess.run(
        ["git", "-C", str(REPO), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    gates.run_wrapper_contract(
        kind="final", matrix="final", module="STM32TK-0601", shard="windows",
        run_id=RUN_ID, evidence_root=evidence, expected_code_head=head,
        gate_catalog=RELEASE / "gates_0600.json",
        performance_catalog=RELEASE / "performance_0600.json",
        support_profile=Path(r"C:\tmp\stm32tk-0600-support\feasibility\profile.json"),
        controller_path=RELEASE / "run_0600_final.ps1",
        verifier_blob_checker=lambda _repo, _head: RELEASE / "verify_0600_release.py",
        verifier_invoker=lambda _repo, _head, _argv: SimpleNamespace(returncode=0),
        now=lambda: datetime(2026, 8, 15, 2, 3, 4, 123456, tzinfo=timezone.utc),
    )
    checkpoint = evidence / "checkpoint.json"

    assert verifier.verify_final_evidence_file(
        checkpoint, expected_head=head, readiness=False
    ) == {"mode": "final-evidence", "status": "PASS"}

    value = json.loads(checkpoint.read_text(encoding="utf-8"))
    value["run_id"] = "223e4567-e89b-42d3-a456-426614174000"
    checkpoint.write_bytes(canonical_json_bytes(value))
    with pytest.raises(VerificationError, match="checkpoint|evidence|run"):
        verifier.verify_final_evidence_file(checkpoint, expected_head=head, readiness=False)


@pytest.mark.parametrize(
    "mutation",
    [
        "root-extra", "support-extra", "support-missing", "support-bool",
        "prerequisite-extra", "result-extra", "metadata-extra", "binding-extra",
        "inventory-order", "inventory-duplicate", "evidence-extra",
    ],
)
def test_candidate_terminal_schema_rejects_every_nested_shape_and_order_mutation(
    tmp_path: Path, mutation: str
) -> None:
    """Every nested terminal object, array order, duplicate, and exact scalar type fails closed."""
    candidate_root = tmp_path / "candidate-mutations"
    evidence = candidate_root / "evidence"
    head = subprocess.run(
        ["git", "-C", str(REPO), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    gates.run_wrapper_contract(
        kind="candidate", matrix="candidate", module="STM32TK-0601", shard="release", _candidate_temporary_root=tmp_path,
        run_id=RUN_ID, evidence_root=evidence, expected_code_head=head,
        gate_catalog=RELEASE / "gates_0600.json",
        performance_catalog=RELEASE / "performance_0600.json",
        support_profile=Path(r"C:\tmp\stm32tk-0600-support\feasibility\profile.json"),
        controller_path=RELEASE / "run_0600_candidate.ps1",
        verifier_blob_checker=lambda _repo, _head: RELEASE / "verify_0600_release.py",
        verifier_invoker=lambda _repo, _head, _argv: SimpleNamespace(returncode=0),
    )
    checkpoint = evidence / "controller-result.json"
    value = json.loads(checkpoint.read_text(encoding="utf-8"))
    if mutation == "root-extra":
        value["extra"] = None
    elif mutation == "support-extra":
        value["support"]["extra"] = None
    elif mutation == "support-missing":
        value["support"].pop("manifest")
    elif mutation == "support-bool":
        value["support"]["profile"]["bytes"] = False
    elif mutation == "prerequisite-extra":
        value["prerequisites"][0]["extra"] = None
    elif mutation == "result-extra":
        value["gate_results"][0]["extra"] = None
    elif mutation == "metadata-extra":
        value["gate_results"][0]["metadata"]["extra"] = None
    elif mutation == "binding-extra":
        value["binding"]["extra"] = None
    elif mutation == "inventory-order":
        value["gate_inventory"] = list(reversed(value["gate_inventory"]))
    elif mutation == "inventory-duplicate":
        value["gate_inventory"].append(value["gate_inventory"][0])
    else:
        value["evidence_inventory"].append("extra.json")
    checkpoint.write_bytes(canonical_json_bytes(value))

    with pytest.raises(VerificationError):
        verifier.verify_candidate_evidence_file(
            candidate_root / "candidate-ledger.json",
            git_runner=CandidateGit(REPO, head=head),
        )


@pytest.mark.parametrize("mutation", ["dirty", "head", "origin", "catalog-hash", "missing", "context-executable"])
def test_candidate_reconciliation_rejects_dirty_wrong_identity_uncommitted_and_context_paths(
    tmp_path: Path, mutation: str
) -> None:
    """No context-supplied executable/config path or mismatched worktree may reach process creation."""
    ledger, paths = _candidate(tmp_path)
    worktree = paths["controller"].parents[2]
    git = CandidateGit(worktree)
    context = None
    if mutation == "dirty":
        git.dirty = "?? untracked.txt\n"
    elif mutation == "head":
        git.head = "b" * 40
    elif mutation == "origin":
        git.origin = "https://example.invalid/repo.git"
    elif mutation == "catalog-hash":
        ledger["catalog_sha256"] = "0" * 64
    elif mutation == "missing":
        paths["verifier"].unlink()
    else:
        context = {"verifier_path": str(tmp_path / "attacker.py")}

    with pytest.raises(VerificationError):
        reconcile_candidate(ledger, git_runner=git, invocation_context=context)


def test_candidate_resume_validates_recovery_once_then_uses_only_rederived_verifier(
    tmp_path: Path,
) -> None:
    """A resume must bind retained bytes, reconcile, update once, and invoke only the fixed verifier."""
    ledger, paths = _candidate(tmp_path)
    evidence = Path(ledger["evidence_root"])
    evidence.mkdir()
    checkpoint = evidence / "controller-result.json"
    checkpoint_value = {
        "schema": "stm32-gate-controller-result/1",
        "matrix": "candidate",
        "module": "STM32TK-0601",
        "shard": "release-contract",
        "run_id": RUN_ID,
        "code_head": "a" * 40,
        "status": "BLOCKED",
        "reason": "RUNNER_LOSS_BEFORE_CHILD_RESULT",
        "product_bodies": 0,
        "network_access": 0,
        "remote_git_actions": 0,
        "resume_count": 0,
        "catalog_sha256": ledger["catalog_sha256"],
        "performance_sha256": ledger["performance_sha256"],
            "support": {
            "profile": {"path": "feasibility/profile.json", "bytes": 1, "sha256": ledger["support_profile_sha256"]},
                "manifest": {"path": "support-manifest.json", "bytes": 1, "sha256": "b" * 64},
            },
            "audit": {
                "schema": "stm32-terminal-audit/1", "status": "BLOCKED",
                "reason": "AUDIT_GATE_RESERVED", "evidence": None,
            },
        "gate_inventory": [],
        "prerequisites": [],
        "gate_results": [],
        "evidence_inventory": ["controller-result.json"],
        "binding": {
            "owner": "Codex", "platform": "windows-amd64", "run_id": RUN_ID,
            "code_head": "a" * 40, "catalog_sha256": ledger["catalog_sha256"],
            "locks": [], "support_sha256": "b" * 64, "status": "BLOCKED",
        },
    }
    checkpoint.write_bytes(canonical_json_bytes(checkpoint_value))
    ledger["checkpoint"] = str(checkpoint)
    ledger["state"] = "blocked"
    ledger_path = Path(ledger["candidate_root"]) / "candidate-ledger.json"
    ledger_path.write_bytes(canonical_json_bytes(ledger))
    recovery = _recovery(checkpoint)
    recovery["interrupted_attempt_digest"] = _sha(checkpoint.read_bytes())
    recovery_path = tmp_path / "recovery.json"
    recovery_path.write_bytes(canonical_json_bytes(recovery))
    git = CandidateGit(paths["controller"].parents[2])
    invoked: list[tuple[Path, str, list[str]]] = []

    checkpoint_value["resume_count"] = False
    checkpoint.write_bytes(canonical_json_bytes(checkpoint_value))
    recovery["event"] = "RUNNER_LOSS_BEFORE_CHILD_RESULT"
    recovery["interrupted_attempt_digest"] = _sha(checkpoint.read_bytes())
    recovery_path.write_bytes(canonical_json_bytes(recovery))
    with pytest.raises(ControllerError, match="resume_count|single-resume"):
        run_wrapper_resume(
            kind="candidate",
            candidate_ledger_path=ledger_path,
            recovery_record_path=recovery_path,
            git_runner=git,
            verifier_invoker=lambda repo, head, argv: SimpleNamespace(returncode=0),
        )
    checkpoint_value["resume_count"] = 0

    checkpoint_value["reason"] = "PRODUCT_FAILURE"
    checkpoint.write_bytes(canonical_json_bytes(checkpoint_value))
    recovery["interrupted_attempt_digest"] = _sha(checkpoint.read_bytes())
    recovery_path.write_bytes(canonical_json_bytes(recovery))
    with pytest.raises(ControllerError, match="recoverable event"):
        run_wrapper_resume(
            kind="candidate",
            candidate_ledger_path=ledger_path,
            recovery_record_path=recovery_path,
            git_runner=git,
            verifier_invoker=lambda repo, head, argv: invoked.append((repo, head, argv)),
        )
    assert invoked == []

    checkpoint_value["reason"] = "HOST_POWER_OR_REBOOT"
    checkpoint.write_bytes(canonical_json_bytes(checkpoint_value))
    recovery["event"] = "HOST_POWER_OR_REBOOT"
    recovery["interrupted_attempt_digest"] = _sha(checkpoint.read_bytes())
    recovery_path.write_bytes(canonical_json_bytes(recovery))

    ledger_before = ledger_path.read_bytes()
    checkpoint_before = checkpoint.read_bytes()
    with pytest.raises(ControllerError, match="verifier child failed"):
        run_wrapper_resume(
            kind="candidate",
            candidate_ledger_path=ledger_path,
            recovery_record_path=recovery_path,
            git_runner=git,
            verifier_invoker=lambda repo, head, argv: SimpleNamespace(returncode=7),
        )
    assert ledger_path.read_bytes() == ledger_before
    assert checkpoint.read_bytes() == checkpoint_before

    result = run_wrapper_resume(
        kind="candidate",
        candidate_ledger_path=ledger_path,
        recovery_record_path=recovery_path,
        git_runner=git,
        verifier_invoker=lambda repo, head, argv: invoked.append((repo, head, argv)) or SimpleNamespace(returncode=0),
        now=lambda: datetime(2026, 8, 15, 2, 5, tzinfo=timezone.utc),
    )

    assert result["status"] == "RESUMED"
    assert invoked == [
        (
            paths["controller"].parents[2],
            "a" * 40,
            ["candidate-evidence", "--candidate-ledger", str(ledger_path)],
        )
    ]
    assert json.loads(checkpoint.read_text(encoding="utf-8"))["resume_count"] == 1
    with pytest.raises(ControllerError, match="single-resume"):
        run_wrapper_resume(
            kind="candidate",
            candidate_ledger_path=ledger_path,
            recovery_record_path=recovery_path,
            git_runner=git,
            verifier_invoker=lambda repo, head, argv: SimpleNamespace(returncode=0),
        )


def test_final_resume_binds_one_run_and_codehead_and_consumes_recovery_once(
    tmp_path: Path,
) -> None:
    """Final recovery must stay on one logical run/CodeHead and permit only one affected-shard resume."""
    worktree = tmp_path / "repo"
    controller = worktree / "tools/release/run_0600_final.ps1"
    verifier_path = worktree / "tools/release/verify_0600_release.py"
    controller.parent.mkdir(parents=True)
    controller.write_bytes(b"final-controller\n")
    verifier_path.write_bytes(b"verifier\n")
    evidence = tmp_path / "final-evidence"
    evidence.mkdir()
    checkpoint_path = evidence / "checkpoint.json"
    checkpoint = {
        "schema": "stm32-final-checkpoint/1",
        "run_id": RUN_ID,
        "code_head": "a" * 40,
        "controller_path": str(controller),
        "evidence_root": str(evidence),
        "state": "blocked",
        "resume_count": 0,
        "interruption_event": "HOST_POWER_OR_REBOOT",
    }
    checkpoint_path.write_bytes(canonical_json_bytes(checkpoint))
    recovery = _recovery(checkpoint_path)
    recovery["run_kind"] = "final-windows"
    recovery["interrupted_attempt_digest"] = _sha(checkpoint_path.read_bytes())
    recovery_path = tmp_path / "recovery.json"
    recovery_path.write_bytes(canonical_json_bytes(recovery))
    invoked: list[tuple[Path, str, list[str]]] = []

    checkpoint["resume_count"] = False
    checkpoint_path.write_bytes(canonical_json_bytes(checkpoint))
    recovery["interrupted_attempt_digest"] = _sha(checkpoint_path.read_bytes())
    recovery_path.write_bytes(canonical_json_bytes(recovery))
    with pytest.raises(ControllerError, match="resume_count|single-resume"):
        run_final_resume(
            checkpoint_path=checkpoint_path,
            recovery_record_path=recovery_path,
            verifier_invoker=lambda repo, head, argv: SimpleNamespace(returncode=0),
        )
    checkpoint["resume_count"] = 0
    checkpoint_path.write_bytes(canonical_json_bytes(checkpoint))
    recovery["interrupted_attempt_digest"] = _sha(checkpoint_path.read_bytes())
    recovery_path.write_bytes(canonical_json_bytes(recovery))

    checkpoint_before = checkpoint_path.read_bytes()
    with pytest.raises(ControllerError, match="verifier child failed"):
        run_final_resume(
            checkpoint_path=checkpoint_path,
            recovery_record_path=recovery_path,
            verifier_invoker=lambda repo, head, argv: SimpleNamespace(returncode=3),
        )
    assert checkpoint_path.read_bytes() == checkpoint_before

    result = run_final_resume(
        checkpoint_path=checkpoint_path,
        recovery_record_path=recovery_path,
        verifier_invoker=lambda repo, head, argv: invoked.append((repo, head, argv)) or SimpleNamespace(returncode=0),
    )

    assert result["status"] == "RESUMED"
    assert invoked == [
        (
            worktree,
            "a" * 40,
            ["final-evidence", "--input", str(checkpoint_path)],
        )
    ]
    with pytest.raises(ControllerError, match="single-resume"):
        run_final_resume(
            checkpoint_path=checkpoint_path,
            recovery_record_path=recovery_path,
            verifier_invoker=lambda repo, head, argv: SimpleNamespace(returncode=0),
        )


def _git_repo_with_verifier(tmp_path: Path) -> tuple[Path, Path, str]:
    repo = tmp_path / "repo"
    script = repo / "tools/release/verify_0600_release.py"
    script.parent.mkdir(parents=True)
    script.write_bytes((RELEASE / "verify_0600_release.py").read_bytes())
    for args in (
        ["init"],
        ["config", "user.email", "test@example.invalid"],
        ["config", "user.name", "test"],
        ["config", "core.autocrlf", "false"],
        ["add", "."],
        ["commit", "-m", "fixture"],
    ):
        subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)
    head = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
    return repo, script, head


def test_caller_mutation_after_cached_check_is_rejected_before_interpreter_spawn(tmp_path: Path) -> None:
    """The mandatory immediate pre-spawn blob check must catch a post-cache whole-file replacement."""
    repo, script, head = _git_repo_with_verifier(tmp_path)
    spawned: list[list[str]] = []

    with pytest.raises(ControllerError):
        invoke_trusted_verifier(
            repo=repo,
            expected_code_head=head,
            verifier_args=["candidate-evidence"],
            after_first_check=lambda: script.write_bytes(b"replaced\n"),
            process_factory=lambda argv: spawned.append(argv),
        )
    assert spawned == []


def test_real_wrapper_path_rechecks_verifier_mutation_before_any_evidence(tmp_path: Path) -> None:
    """The initial wrapper path must reject a whole-file swap before creating evidence or running gates."""
    repo, script, head = _git_repo_with_verifier(tmp_path)
    controller = repo / "tools/release/run_0600_quick.ps1"
    catalog = repo / "tools/release/gates_0600.json"
    performance = repo / "tools/release/performance_0600.json"
    controller.write_bytes(b"quick\n")
    catalog.write_bytes((RELEASE / "gates_0600.json").read_bytes())
    performance.write_bytes((RELEASE / "performance_0600.json").read_bytes())
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", "caller"], check=True, capture_output=True)
    head = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    evidence = tmp_path / "must-not-exist"

    with pytest.raises(ControllerError, match="verifier|blob"):
        gates.run_wrapper_contract(
            kind="quick", matrix="quick", module="STM32TK-0601", shard="fixture",
            run_id=RUN_ID, evidence_root=evidence, expected_code_head=head,
            gate_catalog=catalog, performance_catalog=performance,
            support_profile=Path(r"C:\tmp\stm32tk-0600-support\feasibility\profile.json"),
            controller_path=controller,
            after_first_verifier_check=lambda: script.write_bytes(b"whole-file-swap\n"),
        )
    assert not evidence.exists()


def test_loaded_trusted_script_detects_on_disk_mutation_at_first_action_seam(tmp_path: Path) -> None:
    """Known-good loaded code must reject its on-disk mutation before evidence/output/dispatch."""
    repo, script, head = _git_repo_with_verifier(tmp_path)
    dispatches: list[str] = []

    with pytest.raises(VerificationError):
        verify_loaded_script_entry(
            repository=repo,
            expected_code_head=head,
            script_path=script,
            before_first_action=lambda: script.write_bytes(b"mutated-after-load\n"),
            dispatch_recorder=dispatches,
        )
    assert dispatches == []


def test_verify_release_ledger_parser_is_closed_and_success_stdout_is_sole_canonical_object(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """Unknown args must fail and successful mode must emit exactly one compact object plus LF."""
    paths = [tmp_path / name for name in ("ledger.json", "ledger.json.sha256", "software.json", "hardware.json")]
    for path in paths:
        path.write_bytes(b"x")
    monkeypatch.setattr(verifier, "verify_release_ledger_files", lambda *args, **kwargs: {"mode": "verify-release-ledger", "status": "PASS"})

    code = verifier.main([
        "verify-release-ledger", "--ledger", str(paths[0]), "--digest", str(paths[1]),
        "--software-input", str(paths[2]), "--hardware-input", str(paths[3]),
    ])

    assert code == 0
    assert capsys.readouterr().out == '{"mode":"verify-release-ledger","status":"PASS"}\n'
    with pytest.raises(SystemExit):
        verifier.main(["verify-release-ledger", "--unknown", "x"])


def test_verify_release_ledger_rejects_path_normalization_before_path_object_conversion(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """A forward-slash/mixed spelling must not be normalized by Path before validation."""
    paths = [tmp_path / name for name in ("ledger.json", "ledger.json.sha256", "software.json", "hardware.json")]
    for path in paths:
        path.write_bytes(b"x")
    calls: list[object] = []
    monkeypatch.setattr(
        verifier,
        "verify_release_ledger_files",
        lambda *args, **kwargs: calls.append(args) or {"mode": "verify-release-ledger", "status": "PASS"},
    )
    mixed = str(paths[0]).replace("\\", "/")

    code = verifier.main([
        "verify-release-ledger", "--ledger", mixed, "--digest", str(paths[1]),
        "--software-input", str(paths[2]), "--hardware-input", str(paths[3]),
    ])

    assert code == 2
    assert calls == []
    assert capsys.readouterr().out == ""


def test_verifier_exposes_only_eight_closed_modes() -> None:
    """Adding an implicit mutation/dispatch mode must change the frozen command surface."""
    parser = verifier.build_parser()
    subparsers = next(action for action in parser._actions if action.dest == "mode")
    assert set(subparsers.choices) == {
        "performance-calibration",
        "dependency-audit",
        "candidate-evidence",
        "final-readiness",
        "final-evidence",
        "verify-release-ledger",
        "final-release-inputs",
        "verify-final-release-inputs",
    }


def test_frozen_060x_reconciliation_argv_are_accepted_by_closed_parser() -> None:
    """Exact command names/options are dynamically sourced from all three frozen plans."""
    plans = tuple((REPO / "docs/superpowers/plans").glob("2026-08-14-stm32tk-060[123]-*.md"))
    lines = [line for plan in plans for line in plan.read_text(encoding="utf-8").splitlines()]
    candidate_lines = [line for line in lines if " candidate-evidence " in line]
    assert len(candidate_lines) == 3
    parser = verifier.build_parser()
    for module, extra in (
        ("STM32TK-0601", []),
        ("STM32TK-0602", ["--expected-shards", "windows", "--expected-outcome", "SOFTWARE_COMPLETE_HARDWARE_PENDING"]),
        ("STM32TK-0603", []),
    ):
        parser.parse_args([
            "candidate-evidence", "--module", module,
            "--candidate-run-id", RUN_ID, *extra,
            "--evidence", r"C:\tmp\candidate", "--expected-code-head", "a" * 40,
            "--catalog", r"C:\tmp\catalog.json", "--performance", r"C:\tmp\performance.json",
            "--support-profile", r"C:\tmp\profile.json",
        ])


def test_frozen_0603_audit_and_final_input_argv_are_accepted_by_closed_parser() -> None:
    plan = REPO / "docs/superpowers/plans/2026-08-14-stm32tk-0603-monitor-analytics.md"
    lines = plan.read_text(encoding="utf-8").splitlines()
    for token in (" dependency-audit ", " final-release-inputs ", " verify-final-release-inputs "):
        assert sum(token in line for line in lines) == 1
    parser = verifier.build_parser()
    parser.parse_args(["dependency-audit", "--ui-root", "tools/stm32-monitor/ui", "--catalog", "tools/release/gates_0600.json", "--support-profile", r"C:\tmp\profile.json", "--evidence", r"C:\tmp\audit"])
    parser.parse_args(["final-release-inputs", "--repo", str(REPO), "--candidate-ledger", r"C:\tmp\candidate-ledger.json", "--invocation-context", r"C:\tmp\context.json", "--output", r"C:\tmp\final-release-inputs.json", "--digest-output", r"C:\tmp\final-release-inputs.json.sha256"])
    parser.parse_args(["verify-final-release-inputs", "--repo", str(REPO), "--input", r"C:\tmp\final-release-inputs.json", "--digest", r"C:\tmp\final-release-inputs.json.sha256"])


def test_npm_11_audit_parser_consumes_real_zero_vulnerability_fixture() -> None:
    """Fixture bytes come from the frozen npm 11.16.0 `audit --offline --json` command."""
    fixture = Path(__file__).parent / "fixtures/npm-audit-v11-zero.json"
    value = json.loads(fixture.read_text(encoding="utf-8"))
    assert verifier.parse_npm_audit_v2(value) == {
        "info": 0, "low": 0, "moderate": 0, "high": 0, "critical": 0, "total": 0,
    }
    broken = copy.deepcopy(value)
    broken["metadata"]["vulnerabilities"]["total"] = 1
    with pytest.raises(VerificationError, match="summary"):
        verifier.parse_npm_audit_v2(broken)


def test_secure_io_loader_allows_unrelated_dirty_product_but_rejects_controller_blob(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Task 12 may be product-dirty; skip-worktree cannot hide changed controller bytes."""
    monkeypatch.delattr(verifier, "_SECURE_IO_TEST_ADAPTER", raising=False)
    calls: list[tuple[str, ...]] = []
    committed = "a" * 40
    def trusted_git(args: list[str]) -> str:
        calls.append(tuple(args))
        if args == ["rev-parse", "HEAD"]:
            return "b" * 40 + "\n"
        if args == ["config", "--get", "remote.origin.url"]:
            return REPOSITORY_URL + "\n"
        if args[0] == "rev-parse" and ":tools/release/run_0600_gates.py" in args[1]:
            return committed + "\n"
        if args[:2] == ["hash-object", "--"]:
            return committed + "\n"
        if args[0] == "status":
            return " M tools/stm32-monitor/src/stm32_monitor/runtime.py\n"
        raise AssertionError(args)
    monkeypatch.setattr(verifier, "_default_git", lambda _repo: trusted_git)
    assert verifier._secure_io().__name__.startswith("_stm32tk_release_locking_")
    assert not any(call[0] == "status" for call in calls)
    def tampered_git(args: list[str]) -> str:
        if args[:2] == ["hash-object", "--"]:
            return "c" * 40 + "\n"
        return trusted_git(args)
    monkeypatch.setattr(verifier, "_default_git", lambda _repo: tampered_git)
    with pytest.raises(VerificationError, match="committed blob mismatch"):
        verifier._secure_io()


def test_planned_dependency_audit_runs_native_offline_then_blocks_on_missing_support_pins(tmp_path: Path) -> None:
    """The frozen argv reaches native npm output, not controller grammar, before the real support blocker."""
    support = Path(r"C:\tmp\stm32tk-0600-support\feasibility\profile.json")
    assert support.is_file()
    evidence = tmp_path / "dependency-audit"
    parent_attack: list[int] = []
    def attack_parent() -> None:
        moved = tmp_path.with_name(tmp_path.name + "-moved")
        parent_attack.append(subprocess.run(
            [sys.executable, "-c", "import os,sys;os.rename(sys.argv[1],sys.argv[2])", str(tmp_path), str(moved)],
            capture_output=True, check=False,
        ).returncode)
    with pytest.raises(VerificationError, match="BLOCKED: support profile lacks pinned"):
        verifier.run_planned_dependency_audit(
            repository=REPO, ui_root_text="tools/stm32-monitor/ui",
            catalog_text="tools/release/gates_0600.json", support_profile=support,
            evidence_root=evidence, after_location_check=attack_parent, _temporary_root=tmp_path,
        )
    assert parent_attack == [1]
    fixture = json.loads((Path(__file__).parent / "fixtures/npm-audit-v11-zero.json").read_text(encoding="utf-8"))
    for name in ("production", "development"):
        native = json.loads((evidence / f"npm-audit-{name}.json").read_text(encoding="utf-8"))
        assert verifier.parse_npm_audit_v2(native) == verifier.parse_npm_audit_v2(fixture)
    retained = {path.name: path.read_bytes() for path in evidence.iterdir()}
    with pytest.raises(VerificationError, match="create-new failed"):
        verifier.run_planned_dependency_audit(
            repository=REPO, ui_root_text="tools/stm32-monitor/ui",
            catalog_text="tools/release/gates_0600.json", support_profile=support,
            evidence_root=evidence, _temporary_root=tmp_path,
        )
    assert {path.name: path.read_bytes() for path in evidence.iterdir()} == retained


@pytest.mark.parametrize("module", ["STM32TK-0601", "STM32TK-0602", "STM32TK-0603"])
def test_candidate_ledger_identity_supports_all_frozen_modules(tmp_path: Path, module: str) -> None:
    controller = tmp_path / "tools/release/run_0600_candidate.ps1"
    controller.parent.mkdir(parents=True)
    controller.write_text("# fixture", encoding="utf-8")
    candidate = tmp_path / "candidate"
    evidence = candidate / "windows"
    value = create_candidate_ledger(
        module=module, controller_path=controller, candidate_root=candidate,
        evidence_root=evidence, run_id=RUN_ID, expected_code_head="a" * 40,
        catalog_sha256="b" * 64, performance_sha256="c" * 64,
        support_profile_sha256="d" * 64, now=datetime.now(timezone.utc),
    )
    assert validate_candidate_ledger(value)["module"] == module


@pytest.mark.parametrize("mutation", ["wrong-shard", "software-fail", "general-blocked"])
def test_planned_candidate_reconciliation_rejects_false_software_pending(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutation: str,
) -> None:
    """A general BLOCKED/FAIL or a non-windows result cannot masquerade as deferred hardware."""
    candidate = tmp_path / "candidate"
    evidence = candidate / "windows"
    evidence.mkdir(parents=True)
    catalog = tmp_path / "catalog.json"
    performance = tmp_path / "performance.json"
    support = tmp_path / "support.json"
    for path, data in ((catalog, b"catalog\n"), (performance, b"performance\n"), (support, b"support\n")):
        path.write_bytes(data)
    checkpoint = evidence / "controller-result.json"
    rows = [
        {"gate_id": "SOFTWARE", "status": "PASS", "reason": "PASS"},
        {"gate_id": "HARDWARE", "status": "BLOCKED", "reason": "RESERVED_CATALOG_FAMILY"},
    ]
    terminal = {"shard": "windows", "gate_results": rows}
    if mutation == "wrong-shard":
        terminal["shard"] = "linux"
    elif mutation == "software-fail":
        rows[0].update(status="FAIL", reason="GATE_FAILURE")
    else:
        rows[0].update(status="BLOCKED", reason="PREREQUISITE_NOT_PASS")
    checkpoint.write_bytes(canonical_json_bytes(terminal))
    ledger = create_candidate_ledger(
        module="STM32TK-0602", controller_path=tmp_path / "tools/release/run_0600_candidate.ps1",
        candidate_root=candidate, evidence_root=evidence, run_id=RUN_ID,
        expected_code_head="a" * 40, catalog_sha256=_sha(catalog.read_bytes()),
        performance_sha256=_sha(performance.read_bytes()), support_profile_sha256=_sha(support.read_bytes()),
        now=datetime.now(timezone.utc),
    )
    ledger.update(checkpoint=str(checkpoint), state="blocked")
    (candidate / "candidate-ledger.json").write_bytes(canonical_json_bytes(ledger))
    families = (
        SimpleNamespace(family_id="SOFTWARE", module="STM32TK-0602", matrices=("candidate-0602",), reserved=False),
        SimpleNamespace(family_id="HARDWARE", module="STM32TK-0602", matrices=("candidate-0602",), reserved=True),
    )
    monkeypatch.setattr(verifier, "load_catalog", lambda _path: SimpleNamespace(families=families))
    monkeypatch.setattr(verifier, "verify_candidate_evidence_file", lambda _path: {"mode": "candidate-evidence", "status": "PASS"})

    with pytest.raises(VerificationError):
        verifier.verify_candidate_evidence_contract(
            module="STM32TK-0602", candidate_run_id=RUN_ID, evidence=candidate,
            expected_code_head="a" * 40, catalog=catalog, performance=performance,
            support_profile=support, expected_shards="windows",
            expected_outcome="SOFTWARE_COMPLETE_HARDWARE_PENDING",
        )


def test_final_release_inputs_are_canonical_create_new_and_sidecar_bound(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Task 13 generation preserves a first attempt and requires a new output on retry."""
    candidate = tmp_path / "candidate"
    evidence = candidate / "windows"
    evidence.mkdir(parents=True)
    support = tmp_path / "support/feasibility/profile.json"
    support.parent.mkdir(parents=True)
    support.write_bytes(b"profile\n")
    (support.parents[1] / "support-manifest.json").write_bytes(b"manifest\n")
    catalog = REPO / "tools/release/gates_0600.json"
    performance = REPO / "tools/release/performance_0600.json"
    ledger = create_candidate_ledger(
        module="STM32TK-0603", controller_path=REPO / "tools/release/run_0600_candidate.ps1",
        candidate_root=candidate, evidence_root=evidence, run_id=RUN_ID,
        expected_code_head="5" * 40, catalog_sha256=_sha(catalog.read_bytes()),
        performance_sha256=_sha(performance.read_bytes()), support_profile_sha256=_sha(support.read_bytes()),
        now=datetime.now(timezone.utc),
    )
    ledger.update(checkpoint=str(evidence / "controller-result.json"), state="blocked")
    ledger_path = candidate / "candidate-ledger.json"
    ledger_path.write_bytes(canonical_json_bytes(ledger))
    context = {
        "schema": "stm32-candidate-invocation-context/1", "module": "STM32TK-0603", "shard": "windows",
        "candidate_run_id": RUN_ID, "code_head": "5" * 40, "frozen_worktree": str(REPO),
        "origin_url": REPOSITORY_URL, "candidate_root": str(candidate), "evidence_root": str(evidence),
        "support_profile": str(support), "wrapper_ledger": str(ledger_path),
        "catalog_sha256": _sha(catalog.read_bytes()), "performance_sha256": _sha(performance.read_bytes()),
        "support_profile_sha256": _sha(support.read_bytes()),
        "controller_sha256": _sha((REPO / "tools/release/run_0600_candidate.ps1").read_bytes()),
        "verifier_sha256": _sha((REPO / "tools/release/verify_0600_release.py").read_bytes()),
    }
    context_root = tmp_path / "context-root"
    context_root.mkdir()
    context_path = context_root / "context.json"
    _write_canonical(context_path, context)
    monkeypatch.setattr(verifier, "verify_candidate_evidence_contract", lambda **_kwargs: {"status": "PASS"})
    monkeypatch.setattr(verifier, "reconcile_candidate", lambda *_args, **_kwargs: REPO / "tools/release/verify_0600_release.py")
    reports = {"0601": "2" * 40, "0602": "4" * 40}
    products = {"2" * 40: "1" * 40, "4" * 40: "3" * 40}
    def git(args: list[str]) -> str:
        if args[:4] == ["log", "-1", "--format=%H", "--"]:
            return reports["0601" if "0601" in args[4] else "0602"] + "\n"
        if args[0] == "rev-parse" and args[1].endswith("^"):
            return products[args[1][:-1]] + "\n"
        if args[0] in {"cat-file", "merge-base"}:
            return ""
        if args[:3] == ["rev-list", "--parents", "-n"]:
            report = args[4]
            return f"{report} {products[report]}\n"
        if args[0] == "diff-tree":
            return REPORT_PATHS["0601" if args[-1] == reports["0601"] else "0602"] + "\n"
        raise AssertionError(args)
    output_root = tmp_path / "output-root"
    output_root.mkdir()
    output = output_root / "final-release-inputs.json"
    digest = output_root / "final-release-inputs.json.sha256"
    result = verifier.generate_final_release_inputs(
        repository=REPO, candidate_ledger_path=ledger_path, invocation_context_path=context_path,
        output_path=output, digest_output_path=digest, git_runner=git, _temporary_root=tmp_path,
    )
    assert result["status"] == "PASS"
    assert digest.read_text(encoding="ascii") == _sha(output.read_bytes()) + "\n"
    with pytest.raises(VerificationError, match="already exists"):
        verifier.generate_final_release_inputs(
            repository=REPO, candidate_ledger_path=ledger_path, invocation_context_path=context_path,
            output_path=output, digest_output_path=digest, git_runner=git, _temporary_root=tmp_path,
        )

    real_verify = verifier.verify_final_release_inputs
    monkeypatch.setattr(verifier, "verify_final_release_inputs", lambda *_args, **_kwargs: (_ for _ in ()).throw(VerificationError("late verification")))
    failed_output = output_root / "failed-final-release-inputs.json"
    failed_digest = output_root / "failed-final-release-inputs.json.sha256"
    with pytest.raises(VerificationError, match="late verification"):
        verifier.generate_final_release_inputs(
            repository=REPO, candidate_ledger_path=ledger_path, invocation_context_path=context_path,
            output_path=failed_output, digest_output_path=failed_digest, git_runner=git, _temporary_root=tmp_path,
        )
    failed_bytes = failed_output.read_bytes(), failed_digest.read_bytes()
    monkeypatch.setattr(verifier, "verify_final_release_inputs", real_verify)
    retry_output = output_root / "retry-final-release-inputs.json"
    retry_digest = output_root / "retry-final-release-inputs.json.sha256"
    verifier.generate_final_release_inputs(
        repository=REPO, candidate_ledger_path=ledger_path, invocation_context_path=context_path,
        output_path=retry_output, digest_output_path=retry_digest, git_runner=git, _temporary_root=tmp_path,
    )
    assert (failed_output.read_bytes(), failed_digest.read_bytes()) == failed_bytes
    assert retry_output.read_bytes() == failed_output.read_bytes()
    attack_output = output_root / "attack-final-release-inputs.json"
    attack_digest = output_root / "attack-final-release-inputs.json.sha256"
    external = tmp_path / "external-output"
    external.mkdir()
    parent_attack: list[int] = []
    def attack_parent() -> None:
        moved = output_root.with_name("output-root-moved")
        parent_attack.append(subprocess.run(
            [sys.executable, "-c", "import os,sys;os.rename(sys.argv[1],sys.argv[2])", str(output_root), str(moved)],
            capture_output=True, check=False,
        ).returncode)
    verifier.generate_final_release_inputs(
        repository=REPO, candidate_ledger_path=ledger_path, invocation_context_path=context_path,
        output_path=attack_output, digest_output_path=attack_digest, git_runner=git,
        after_location_check=attack_parent, _temporary_root=tmp_path,
    )
    assert parent_attack == [1]
    assert list(external.iterdir()) == []




def _performance_environment(version: str = "3.12.10") -> dict[str, object]:
    return {
        "schema": "stm32-performance-environment/1",
        "support_profile_sha256": "a" * 64,
        "platform": "Windows",
        "platform_version": "10.0.26200",
        "architecture": "AMD64",
        "cpu_model": "AMD Ryzen 7 5800U",
        "physical_cores": 8,
        "logical_cores": 16,
        "memory_bytes": 16 * 1024**3,
        "storage_model": "NVMe",
        "power_profile": "balanced",
        "antivirus_state": "enabled",
        "python_version": version,
        "python_executable_sha256": "b" * 64,
        "gc_enabled": True,
        "monotonic_clock": "perf_counter_ns",
        "monotonic_clock_tick_ns": 100,
    }


def _fixture_sha(value: object) -> str:
    return hashlib.sha256(
        (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()
    ).hexdigest()


def _performance_workload(
    workload_id: str = "evidence-publish-reload", design_maximum: int = 500_000_000,
    warmup_count: int = 5, samples_per_batch: int = 30,
) -> dict[str, object]:
    batches = []
    for index, base in enumerate((1000, 1100, 1200)):
        samples = [base + offset for offset in range(samples_per_batch)]
        batches.append({
            "index": index,
            "started_offset_ns": index * 1_000_000,
            "duration_ns": 500_000,
            "samples": samples,
            "p50": samples[(samples_per_batch + 1) // 2 - 1],
            "p95": samples[math.ceil(.95 * samples_per_batch) - 1],
            "max": samples[-1],
        })
    contract = {
        "id": workload_id,
        "kind": "latency",
        "unit": "ns",
        "quantile": "nearest-rank",
        "design_maximum": design_maximum,
        "relative_limit_ppm": 150000,
        "scale": [
            {"name": "artifact_bytes", "unit": "bytes", "value": 1048576},
            {"name": "artifact_count", "unit": "count", "value": 32},
        ],
        "measurement": {
            "kind": "sample-batches", "warmup_count": warmup_count,
            "batch_count": 3, "samples_per_batch": samples_per_batch,
        },
        "observation_contract": [
            {"name": "serialized_bytes", "unit": "bytes"},
        ],
    }
    return {
        **contract,
        "workload_sha256": _fixture_sha(contract),
        "warmup_samples": [900 + index for index in range(warmup_count)],
        "batches": batches,
        "observed_p95": batches[1]["p95"],
        "observed_mad": 100,
        "accepted_baseline": None,
        "absolute_threshold": None,
        "observations": [
            {"name": "serialized_bytes", "unit": "bytes", "values": [1048576]},
        ],
    }


def _performance_run(version: str = "3.12.10", module: str = "STM32TK-0601") -> dict[str, object]:
    environment = _performance_environment(version)
    specifications = verifier.PERFORMANCE_MODULE_CONTRACTS[module]["python"]
    test_files = {
        "STM32TK-0601": "tools/stm32-toolkit/tests/test_evidence_performance.py",
        "STM32TK-0602": "tools/stm32-toolkit/tests/test_diagnostic_performance.py",
        "STM32TK-0603": "tools/stm32-monitor/tests/test_analysis_performance.py",
    }
    return {
        "schema": "stm32-performance-run/1",
        "mode": "calibrate",
        "module": module,
        "producer": "python",
        "environment": environment,
        "environment_sha256": _fixture_sha(environment),
        "profile_sha256": None,
        "test_file": test_files[module],
        "test_file_sha256": "c" * 64,
        "workloads": [_performance_workload(*specification) for specification in specifications],
    }


def _browser_performance_run() -> dict[str, object]:
    value = _performance_run(module="STM32TK-0603")
    environment = {
        key: item for key, item in value["environment"].items()
        if key not in {"python_version", "python_executable_sha256", "gc_enabled"}
    }
    environment.update({
        "schema": "stm32-browser-performance-environment/1",
        "browser_name": "chromium", "browser_version": "139.0.7258.5",
        "browser_executable_sha256": "d" * 64, "playwright_version": "1.54.2",
        "monotonic_clock": "performance.now",
    })
    workload = _performance_workload("browser-analysis-update", 150_000_000, 120, 12)
    workload["kind"] = "browser-latency"
    workload["measurement"] = {
        "kind": "continuous-windows", "warmup_seconds": 120, "measurement_seconds": 180,
        "batch_count": 3, "batch_duration_seconds": 60, "cadence_seconds": 5,
        "interaction_order": ["compare", "quality", "marker", "table"],
        "samples_per_batch": 12,
    }
    workload["warmup_samples"] = [900 + index for index in range(24)]
    interactions = ("compare", "quality", "marker", "table")
    for batch_index, batch in enumerate(workload["batches"]):
        batch["started_offset_ns"] = batch_index * 60_000_000_000
        batch["duration_ns"] = 60_000_000_000
        metrics = []
        for sample_index, duration in enumerate(batch["samples"]):
            global_index = batch_index * 12 + sample_index
            metrics.append({
                "offset_ns": global_index * 5_000_000_000,
                "interaction": interactions[global_index % 4],
                "duration_ns": duration,
                "retained_heap_bytes": 100_000_000 + global_index * 50_000,
                "queue_depth": 0,
                "long_task_duration_ns": 0,
            })
        batch["metrics"] = metrics
    workload["workload_sha256"] = _fixture_sha({
        key: workload[key] for key in PERFORMANCE_CONTRACT_FIXTURE_KEYS
    })
    workload["browser_metrics"] = {
        "long_tasks_ge_200ms": 0, "retained_heap_slope_bytes_per_minute": 600_000,
        "queue_growth": 0,
    }
    value.update({
        "producer": "browser", "environment": environment,
        "environment_sha256": _fixture_sha(environment),
        "test_file": "tools/stm32-monitor/ui/e2e/performance.spec.ts",
        "test_file_sha256": "d" * 64,
        "workloads": [workload],
    })
    return value


PERFORMANCE_CONTRACT_FIXTURE_KEYS = {
    "id", "kind", "unit", "quantile", "design_maximum", "relative_limit_ppm",
    "scale", "measurement", "observation_contract",
}


def _reserved_performance_catalog(module: str = "STM32TK-0601", *, browser: bool = False) -> dict[str, object]:
    python_run = _performance_run(module=module)
    contract_keys = {
        "id", "kind", "workload_sha256", "unit", "quantile", "design_maximum",
        "relative_limit_ppm", "scale", "measurement", "observation_contract",
    }
    producer = {
        "producer": "python",
        "test_file": python_run["test_file"],
        "test_file_sha256": "c" * 64,
        "workloads": [
            {**{key: copy.deepcopy(value) for key, value in workload.items() if key in contract_keys}, "calibrations": []}
            for workload in python_run["workloads"]
        ],
    }
    producers = [producer]
    if browser:
        browser_run = _browser_performance_run()
        browser_workload = browser_run["workloads"][0]
        producers.append({
            "producer": "browser", "test_file": browser_run["test_file"],
            "test_file_sha256": browser_run["test_file_sha256"],
            "workloads": [{
                **{key: copy.deepcopy(browser_workload[key]) for key in contract_keys},
                "calibrations": [],
            }],
        })
    producers.sort(key=lambda item: item["producer"])
    without_digest = {"module": module, "producers": producers}
    return {
        "schema": "stm32-performance-catalog/1",
        "profiles": [{**without_digest, "profile_sha256": _fixture_sha(without_digest)}],
    }


def test_shared_performance_run_recomputes_real_batches_and_rejects_wrong_p95() -> None:
    """Removing raw-batch recomputation would accept a forged release measurement."""
    valid = _performance_run()
    assert verifier.validate_performance_run(valid)["producer"] == "python"

    forged = copy.deepcopy(valid)
    forged["workloads"][0]["batches"][0]["p95"] = 1
    with pytest.raises(VerificationError, match="p95|batch"):
        verifier.validate_performance_run(forged)


def test_shared_performance_run_accepts_only_the_closed_browser_producer_shape() -> None:
    value = _browser_performance_run()
    assert verifier.validate_performance_run(value)["producer"] == "browser"
    value["environment"]["user_agent"] = "unstable"
    with pytest.raises(VerificationError, match="environment"):
        verifier.validate_performance_run(value)


def _rehash_browser_workload(value: dict[str, object]) -> None:
    workload = value["workloads"][0]
    workload["workload_sha256"] = _fixture_sha({
        key: workload[key] for key in PERFORMANCE_CONTRACT_FIXTURE_KEYS
    })


@pytest.mark.parametrize(
    "mutation", ["gap", "overlap", "short-window", "wrong-order", "cadence-gap", "sample-mismatch"],
)
def test_browser_continuous_measurement_rejects_noncontiguous_or_unbound_raw_points(mutation: str) -> None:
    value = _browser_performance_run()
    workload = value["workloads"][0]
    if mutation == "gap":
        workload["batches"][1]["started_offset_ns"] += 1
    elif mutation == "overlap":
        workload["batches"][1]["started_offset_ns"] -= 1
    elif mutation == "short-window":
        workload["batches"][0]["duration_ns"] -= 1
    elif mutation == "wrong-order":
        workload["measurement"]["interaction_order"] = ["quality", "compare", "marker", "table"]
        _rehash_browser_workload(value)
    elif mutation == "cadence-gap":
        workload["batches"][1]["metrics"][0]["offset_ns"] += 1
    else:
        workload["batches"][2]["metrics"][0]["duration_ns"] += 1
    with pytest.raises(VerificationError, match="browser|batch|measurement"):
        verifier.validate_performance_run(value)


@pytest.mark.parametrize(
    ("field", "bad_value"),
    [("long_tasks_ge_200ms", 1), ("retained_heap_slope_bytes_per_minute", 2 * 1024 * 1024 + 1), ("queue_growth", 1)],
)
def test_browser_continuous_windows_enforce_zero_and_heap_invariants(field: str, bad_value: int) -> None:
    value = _browser_performance_run()
    assert value["workloads"][0]["measurement"] == {
        "kind": "continuous-windows", "warmup_seconds": 120, "measurement_seconds": 180,
        "batch_count": 3, "batch_duration_seconds": 60, "cadence_seconds": 5,
        "interaction_order": ["compare", "quality", "marker", "table"], "samples_per_batch": 12,
    }
    value["workloads"][0]["browser_metrics"][field] = bad_value
    with pytest.raises(VerificationError, match="browser performance invariant"):
        verifier.validate_performance_run(value)


@pytest.mark.parametrize("mutation", ["missing-workload", "raised-maximum", "wrong-test-file", "browser-on-0601"])
def test_performance_module_inventory_is_exact(mutation: str) -> None:
    value = _performance_run()
    if mutation == "missing-workload":
        value["workloads"].pop()
    elif mutation == "raised-maximum":
        value["workloads"][0]["design_maximum"] += 1
    elif mutation == "wrong-test-file":
        value["test_file"] = "tools/stm32-toolkit/tests/test_diagnostic_performance.py"
    else:
        value = _browser_performance_run()
        value["module"] = "STM32TK-0601"
    with pytest.raises(VerificationError):
        verifier.validate_performance_run(value)


@pytest.mark.parametrize("mutation", ["extra", "bool", "environment-digest", "workload-digest", "runtime"])
def test_shared_performance_run_is_closed_and_identity_bound(mutation: str) -> None:
    """Weakening a producer/runtime/digest boundary would mix incomparable calibrations."""
    value = _performance_run()
    if mutation == "extra":
        value["extra"] = None
    elif mutation == "bool":
        value["workloads"][0]["design_maximum"] = True
    elif mutation == "environment-digest":
        value["environment_sha256"] = "0" * 64
    elif mutation == "workload-digest":
        value["workloads"][0]["workload_sha256"] = "0" * 64
    else:
        value["environment"]["python_version"] = "3.13.0"
    with pytest.raises(VerificationError):
        verifier.validate_performance_run(value)


def test_performance_aggregation_requires_dual_python_and_atomically_updates_catalog(tmp_path: Path) -> None:
    """Accepting one runtime or partially writing on failure would violate the frozen calibration."""
    catalog = tmp_path / "performance_0600.json"
    catalog.write_bytes(canonical_json_bytes(_reserved_performance_catalog()))
    inputs = []
    for version in ("3.10.11", "3.12.10"):
        path = tmp_path / f"run-{version}.json"
        path.write_bytes(canonical_json_bytes(_performance_run(version)))
        inputs.append(path)

    result = verifier.aggregate_performance_calibration("STM32TK-0601", inputs, catalog)

    assert result == {"mode": "performance-calibration", "profile": "STM32TK-0601", "status": "PASS"}
    profile = json.loads(catalog.read_text(encoding="utf-8"))["profiles"][0]
    calibrations = profile["producers"][0]["workloads"][0]["calibrations"]
    assert [item["runtime"] for item in calibrations] == [
        {"kind": "cpython", "version": "3.10.11"},
        {"kind": "cpython", "version": "3.12.10"},
    ]
    assert [item["absolute_threshold"] for item in calibrations] == [2200, 2200]

    retained = catalog.read_bytes()
    with pytest.raises(VerificationError, match="runtime|input"):
        verifier.aggregate_performance_calibration("STM32TK-0601", inputs[:1], catalog)
    assert catalog.read_bytes() == retained


@pytest.mark.parametrize(
    ("module", "with_browser", "expected_count"),
    [("STM32TK-0602", False, 8), ("STM32TK-0603", True, 5)],
)
def test_performance_aggregation_closes_each_frozen_module_runtime_set(
    tmp_path: Path, module: str, with_browser: bool, expected_count: int
) -> None:
    catalog = tmp_path / "performance_0600.json"
    catalog.write_bytes(canonical_json_bytes(_reserved_performance_catalog(module, browser=with_browser)))
    runs = [_performance_run(version, module) for version in ("3.10.11", "3.12.10")]
    if with_browser:
        runs.append(_browser_performance_run())
    inputs = []
    for index, run in enumerate(runs):
        path = tmp_path / f"run-{index}.json"
        path.write_bytes(canonical_json_bytes(run))
        inputs.append(path)

    verifier.aggregate_performance_calibration(module, inputs, catalog)

    profile = json.loads(catalog.read_text(encoding="utf-8"))["profiles"][0]
    assert sum(len(workload["calibrations"]) for producer in profile["producers"] for workload in producer["workloads"]) == expected_count


def test_performance_aggregation_initializes_an_empty_catalog_without_a_reserved_profile(tmp_path: Path) -> None:
    catalog = tmp_path / "performance_0600.json"
    catalog.write_bytes(canonical_json_bytes({"schema": "stm32-performance-catalog/1", "profiles": []}))
    inputs = []
    for version in ("3.10.11", "3.12.10"):
        path = tmp_path / f"run-{version}.json"
        path.write_bytes(canonical_json_bytes(_performance_run(version)))
        inputs.append(path)

    verifier.aggregate_performance_calibration("STM32TK-0601", inputs, catalog)

    loaded = verifier.load_performance_catalog(catalog)
    assert [profile["module"] for profile in loaded["profiles"]] == ["STM32TK-0601"]


def test_performance_calibration_cli_accepts_only_repeated_inputs_with_profile_and_output() -> None:
    args = verifier.build_parser().parse_args([
        "performance-calibration", "--profile", "STM32TK-0602",
        "--input", r"C:\tmp\run-310.json", "--input", r"C:\tmp\run-312.json",
        "--output", "tools/release/performance_0600.json",
    ])
    assert args.input == [r"C:\tmp\run-310.json", r"C:\tmp\run-312.json"]
