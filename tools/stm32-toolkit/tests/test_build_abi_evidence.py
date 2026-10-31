"""v1.3.6 conversion-report float-ABI provenance in build evidence.

These regressions cover only the optional conversion-report evidence captured
by the bounded build path: the deterministic resolver is the authority for the
*reported* migration decision (never for binary equivalence, so
``baselineVerified`` stays false), the fixed project-local report is read
without following redirects, captured evidence is exposed identically on the
identity, the typed identity, the receipt and the public warnings, and only an
unchanged pre/post capture is used for a fresh build.  Incremental reuse never
relabels unchanged outputs with newly read metadata, missing evidence stays
optional without invented provenance, and malformed, mismatched, blocked,
redirected or non-regular reports become bounded unavailability rather than an
exception.

The fixture projects use the existing offline fake ``cmake``/``git`` doubles
from ``test_build_runner``; no probe client, network or hardware is touched.
"""

from __future__ import annotations

import json
import os
import pathlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from stm32_toolkit import __version__
from stm32_toolkit.build import BuildRequest, run_build
from stm32_toolkit.build import abi_evidence as abi_evidence_mod
from stm32_toolkit.build import runner as runner_mod
from stm32_toolkit.build.abi_evidence import (
    CHANGED_WARNING,
    CONVERSION_REPORT_LIMIT_BYTES,
    CONVERSION_REPORT_PATH,
    UNAVAILABLE_WARNING,
    validate_float_abi_evidence,
    validate_float_abi_resolved,
)
from stm32_toolkit.build.identity import compute_build_id, validate_identity_document
from stm32_toolkit.build.model import BuildError, FirmwareIdentity
from stm32_toolkit.context import build_project_context
from stm32_toolkit.generation.managed_files import canonical_json_bytes, sha256_hex
from stm32_toolkit.migration.float_abi import float_abi_evidence
from stm32_toolkit.probe.flash import _FlashFailure, load_fresh_firmware_facts
from stm32_toolkit.project_model import load_project_model

from test_build_runner import (
    build_map_text,
    hit_records,
    install_fake_cmake,
    install_fake_git,
    prepare_project,
    read_json,
)
from test_flash import _elf_with_flash_segment

DEBUG_LOG = "artifacts/migration/build.log"
DEBUG_RESULT = "artifacts/migration/build-result.json"
RELEASE_LOG = "artifacts/migration/arm-release/build.log"
RELEASE_RESULT = "artifacts/migration/arm-release/build-result.json"

#: The fixture's ARMCC Cortex-M4/FPU2 target, with an explicit declared softfp
#: variant that replaces the whole target object before generation.
HARD_TARGET = {
    "device": "STM32F407VGTx",
    "core": "cortex-m4",
    "fpu": "fpv4-sp-d16",
    "floatAbi": "hard",
}
SOFTFP_TARGET = {**HARD_TARGET, "floatAbi": "softfp"}

INFERRED_RULE = "MIGRATION_FLOAT_ABI_DEFAULT_HARD_INFERRED"
DECLARED_RULE = "MIGRATION_FLOAT_ABI_DECLARED"


def project_file(root: Path, rel: str) -> Path:
    return root.joinpath(*rel.split("/"))


def report_path(root: Path) -> Path:
    return project_file(root, CONVERSION_REPORT_PATH)


def identity_path(root: Path, preset: str = "arm-debug") -> Path:
    return project_file(root, f"build/{preset}/firmware-identity.json")


def receipt_path(root: Path, preset: str = "arm-debug") -> Path:
    return project_file(root, DEBUG_RESULT if preset == "arm-debug" else RELEASE_RESULT)


def artifact_paths(record: dict) -> set[str]:
    return {entry["path"] for entry in record["artifacts"]}


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _inspection(target: dict) -> SimpleNamespace:
    """A minimal typed/simple Keil inspection for the deterministic resolver.

    The raw FPU selector evidence describes the historical ARMCC Cortex-M4
    FPU2 target; ``float_abi`` is absent for the inferred default and the
    literal declaration otherwise.
    """
    declared = target["floatAbi"]
    return SimpleNamespace(
        compiler="armcc",
        compiler_version="5.06 update 6 (build 750)",
        cpu="cortex-m4",
        fpu="FPU2",
        float_abi=None if declared == "hard" else declared,
        rvds_vp="2",
    )


def _captured(target: dict, digest: str = "0" * 64) -> dict:
    """The resolver's recorded decision plus the fixed capture fields."""
    evidence = {
        **float_abi_evidence(_inspection(target)),
        "reportPath": CONVERSION_REPORT_PATH,
        "reportSha256": digest,
    }
    return evidence


def _write_raw_report(root: Path, data: bytes) -> None:
    path = report_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def write_report(
    root: Path,
    inspection: SimpleNamespace,
    *,
    indent: int = 2,
    extra: dict | None = None,
) -> bytes:
    """Write a report whose ``floatAbi`` object is the resolver's object."""
    document: dict = {"floatAbi": float_abi_evidence(inspection)}
    if extra:
        document.update(extra)
    data = (json.dumps(document, indent=indent) + "\n").encode("utf-8")
    _write_raw_report(root, data)
    return data


def _prepare_no_git(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, **kwargs) -> Path:
    """A snapshot-identity project with a deterministic unavailable Git double."""
    root = prepare_project(tmp_path, git_repo=False, **kwargs)
    install_fake_git(monkeypatch, tmp_path, "exit1")
    return root


def _install_programmable_firmware(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> Path:
    """Install the fake CMake and publish fixture firmware after a real build.

    The generic fake build omits a ``PT_LOAD`` segment, which is enough for
    build evidence but not for offline flash admission.  These tests keep
    every real stage execution and hit record and, only after a successful
    build stage (before artifact validation and identity publication),
    replace the selected preset's ELF/MAP with the flash-segment fixtures.
    With ``FAKE_CMAKE_NO_OUTPUT=1`` the outputs stay untouched so incremental
    reuse remains real.
    """
    hit_file = install_fake_cmake(monkeypatch, tmp_path)
    real_run_stage = runner_mod._run_stage

    def stage_with_programmable_firmware(
        stage: str,
        argv: tuple[str, ...],
        boundary_root: Path,
        timeout_seconds: int,
        sections: list[dict],
        log_rel: str,
    ):
        outcome = real_run_stage(
            stage, argv, boundary_root, timeout_seconds, sections, log_rel
        )
        if (
            stage == "build"
            and outcome.error is None
            and os.environ.get("FAKE_CMAKE_NO_OUTPUT") != "1"
        ):
            preset = argv[argv.index("--preset") + 1]
            out_dir = boundary_root / "build" / preset
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / "firmware.elf").write_bytes(_elf_with_flash_segment())
            (out_dir / "firmware.map").write_bytes(
                build_map_text(
                    sections=(
                        (".isr_vector", 0x08000000, 0x40, None),
                        (".text", 0x08000040, 0x100, None),
                    )
                ).encode("utf-8")
            )
        return outcome

    monkeypatch.setattr(runner_mod, "_run_stage", stage_with_programmable_firmware)
    return hit_file


def _norm_path(value: object) -> str:
    return os.path.normcase(os.path.abspath(os.fspath(value)))


# ---------------------------------------------------------------------------
# successful capture from a valid report
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("git_repo", [True, False], ids=["schema1", "schema2"])
@pytest.mark.parametrize(
    "target", [HARD_TARGET, SOFTFP_TARGET], ids=["inferred-hard", "declared-softfp"]
)
def test_success_captures_the_same_validated_provenance_everywhere(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, git_repo: bool, target: dict
):
    root = prepare_project(tmp_path, overrides={"target": target}, git_repo=git_repo)
    if not git_repo:
        install_fake_git(monkeypatch, tmp_path, "exit1")
    install_fake_cmake(monkeypatch, tmp_path)
    inspection = _inspection(target)
    written = write_report(root, inspection)

    result = run_build(BuildRequest(project_root=root, preset="arm-debug"))

    assert result.ok is True, result.to_dict()
    identity = read_json(identity_path(root))
    receipt = read_json(receipt_path(root))
    on_disk = report_path(root).read_bytes()
    assert on_disk == written
    digest = sha256_hex(on_disk)

    expected_origin = "inferred" if target["floatAbi"] == "hard" else "declared"
    captured = identity["floatAbi"]
    assert captured["origin"] == expected_origin
    assert captured["selectedAbi"] == target["floatAbi"]
    assert captured["baselineVerified"] is False
    assert captured["fpu"] == target["fpu"]
    assert captured["cpu"] == target["core"]
    assert captured["rawFpu"] == "FPU2"
    assert captured["rawRvdsVp"] == "2"
    assert captured["rawFloatAbi"] == (
        None if expected_origin == "inferred" else target["floatAbi"]
    )
    assert captured["ruleId"] == (
        INFERRED_RULE if expected_origin == "inferred" else DECLARED_RULE
    )
    assert captured["reportPath"] == CONVERSION_REPORT_PATH
    assert captured["reportSha256"] == digest
    expected = dict(float_abi_evidence(inspection))
    expected.update({"reportPath": CONVERSION_REPORT_PATH, "reportSha256": digest})
    assert captured == expected
    assert validate_float_abi_evidence(captured) == captured

    expected_schema = 1 if git_repo else 2
    assert identity["schemaVersion"] == expected_schema
    assert identity["toolkitVersion"] == __version__
    typed = result.data.identity
    assert isinstance(typed, FirmwareIdentity)
    assert typed.to_dict() == identity
    assert typed.to_dict()["floatAbi"] == captured
    assert typed.float_abi == captured

    report_dict = result.data.to_dict()
    assert report_dict["identity"]["floatAbi"] == captured
    assert report_dict["warnings"] == receipt["warnings"]

    envelope = result.to_dict()
    assert envelope["data"]["identity"]["floatAbi"] == captured
    assert envelope["data"]["warnings"] == receipt["warnings"]

    assert receipt["schemaVersion"] == expected_schema
    assert receipt["toolkitVersion"] == __version__
    assert receipt["floatAbi"] == captured
    assert receipt["warnings"].count(captured["warning"]) == 1
    assert list(result.data.warnings) == receipt["warnings"]

    # A declared softfp target stays softfp; nothing rewrites the manifest.
    manifest = read_json(root / ".stm32-project.json")
    assert manifest["target"]["floatAbi"] == target["floatAbi"]
    assert load_project_model(root).target.float_abi == target["floatAbi"]


# ---------------------------------------------------------------------------
# preset switching without a clean build
# ---------------------------------------------------------------------------


def test_release_then_debug_switching_keeps_independent_receipts_and_debug_admission(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root = prepare_project(tmp_path)
    hit_file = _install_programmable_firmware(monkeypatch, tmp_path)

    release_first = run_build(BuildRequest(project_root=root, preset="arm-release"))
    assert release_first.ok is True, release_first.to_dict()
    release_identity_one = read_json(identity_path(root, "arm-release"))
    debug_first = run_build(BuildRequest(project_root=root, preset="arm-debug"))
    assert debug_first.ok is True, debug_first.to_dict()
    debug_identity_one = read_json(identity_path(root))

    # Unchanged outputs on re-entry prove both presets reuse their own prior
    # evidence instead of requiring --clean-first.
    monkeypatch.setenv("FAKE_CMAKE_NO_OUTPUT", "1")
    release_second = run_build(BuildRequest(project_root=root, preset="arm-release"))
    assert release_second.ok is True, release_second.to_dict()
    debug_second = run_build(BuildRequest(project_root=root, preset="arm-debug"))
    assert debug_second.ok is True, debug_second.to_dict()

    debug_identity = read_json(identity_path(root))
    release_identity = read_json(identity_path(root, "arm-release"))
    debug_record = read_json(receipt_path(root))
    release_record = read_json(receipt_path(root, "arm-release"))

    assert debug_second.data.identity.build_id == debug_identity_one["buildId"]
    assert release_second.data.identity.build_id == release_identity_one["buildId"]
    assert debug_record["buildId"] == debug_identity["buildId"]
    assert debug_identity["buildId"] == debug_identity_one["buildId"]
    assert release_record["buildId"] == release_identity["buildId"]
    assert release_identity["buildId"] == release_identity_one["buildId"]
    assert debug_record["toolkitVersion"] == __version__
    assert release_record["toolkitVersion"] == __version__
    assert debug_record["preset"] == "arm-debug"
    assert release_record["preset"] == "arm-release"
    assert artifact_paths(debug_record) == {
        DEBUG_LOG,
        DEBUG_RESULT,
        "build/arm-debug/firmware-identity.json",
        "build/arm-debug/firmware.elf",
        "build/arm-debug/firmware.map",
    }
    assert artifact_paths(release_record) == {
        RELEASE_LOG,
        RELEASE_RESULT,
        "build/arm-release/firmware-identity.json",
        "build/arm-release/firmware.elf",
        "build/arm-release/firmware.map",
    }
    assert "arm-release" not in json.dumps(debug_record["artifacts"])
    assert "arm-debug" not in json.dumps(release_record["artifacts"])

    records = hit_records(hit_file)
    assert [record["argv"] for record in records] == [
        ["--preset", "arm-release"],
        ["--build", "--preset", "arm-release"],
        ["--preset", "arm-debug"],
        ["--build", "--preset", "arm-debug"],
        ["--preset", "arm-release"],
        ["--build", "--preset", "arm-release"],
        ["--preset", "arm-debug"],
        ["--build", "--preset", "arm-debug"],
    ]

    context = build_project_context(root, tmp_path / "data", "session-a")
    assert context.ok is True, context.to_dict()
    build = context.data["build"]
    assert build["elfFresh"] is True
    assert build["preset"] == "arm-debug"
    assert build["buildId"] == debug_identity["buildId"]
    assert build["elfSha256"] == debug_identity["elfSha256"]

    # Offline fresh-firmware admission reads only local evidence and artifacts.
    facts = load_fresh_firmware_facts(root)
    assert facts.build_id == debug_identity["buildId"]
    assert facts.elf_sha256 == debug_identity["elfSha256"]
    assert facts.elf_path == "build/arm-debug/firmware.elf"
    assert facts.target_device == debug_identity["targetDevice"]


# ---------------------------------------------------------------------------
# newly written failure receipts
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "preset, result_rel",
    [("arm-debug", DEBUG_RESULT), ("arm-release", RELEASE_RESULT)],
    ids=["debug", "release"],
)
def test_new_failure_receipts_record_the_executing_toolkit_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, preset: str, result_rel: str
):
    root = prepare_project(tmp_path)
    install_fake_cmake(monkeypatch, tmp_path, env={"FAKE_CMAKE_EXIT": "3"})

    result = run_build(BuildRequest(project_root=root, preset=preset))

    assert result.ok is False
    assert result.code == "BUILD_CONFIGURE_FAILED"
    receipt = read_json(project_file(root, result_rel))
    assert receipt["status"] == "failure"
    assert receipt["preset"] == preset
    assert receipt["code"] == "BUILD_CONFIGURE_FAILED"
    assert receipt["toolkitVersion"] == __version__
    assert not identity_path(root, preset).exists()


# ---------------------------------------------------------------------------
# missing / legacy / incremental evidence
# ---------------------------------------------------------------------------


def test_missing_report_is_optional_and_a_legacy_receipt_stays_readable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root = _prepare_no_git(tmp_path, monkeypatch)
    install_fake_cmake(monkeypatch, tmp_path)

    first = run_build(BuildRequest(project_root=root, preset="arm-debug"))
    assert first.ok is True, first.to_dict()
    identity = read_json(identity_path(root))
    receipt = read_json(receipt_path(root))
    assert "floatAbi" not in identity
    assert "floatAbi" not in receipt
    assert receipt["toolkitVersion"] == __version__
    # A genuinely missing report is no ABI warning at all.
    assert not any(
        warning.startswith("Float ABI provenance") for warning in receipt["warnings"]
    )
    assert list(first.data.warnings) == receipt["warnings"]

    # A receipt written before the optional field existed remains readable.
    legacy = {key: value for key, value in receipt.items() if key != "toolkitVersion"}
    write_json(receipt_path(root), legacy)
    monkeypatch.setenv("FAKE_CMAKE_NO_OUTPUT", "1")

    reused = run_build(BuildRequest(project_root=root, preset="arm-debug"))

    assert reused.ok is True, reused.to_dict()
    assert reused.data.identity.build_id == first.data.identity.build_id
    republished = read_json(receipt_path(root))
    assert republished["toolkitVersion"] == __version__
    assert "floatAbi" not in republished


def test_incremental_reuse_does_not_retrofit_evidence_for_unchanged_outputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root = _prepare_no_git(tmp_path, monkeypatch)
    install_fake_cmake(monkeypatch, tmp_path)

    first = run_build(BuildRequest(project_root=root, preset="arm-debug"))
    assert first.ok is True, first.to_dict()
    first_identity = read_json(identity_path(root))
    assert "floatAbi" not in first_identity

    # Late optional evidence must not be attached to already-built outputs.
    write_report(root, _inspection(HARD_TARGET))
    monkeypatch.setenv("FAKE_CMAKE_NO_OUTPUT", "1")

    second = run_build(BuildRequest(project_root=root, preset="arm-debug"))

    assert second.ok is True, second.to_dict()
    identity = read_json(identity_path(root))
    receipt = read_json(receipt_path(root))
    assert identity["buildId"] == first_identity["buildId"]
    assert "floatAbi" not in identity
    assert "floatAbi" not in receipt
    assert not any(
        warning.startswith("Float ABI provenance") for warning in receipt["warnings"]
    )


def test_incremental_reuse_preserves_prior_captured_evidence_when_report_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root = _prepare_no_git(tmp_path, monkeypatch)
    install_fake_cmake(monkeypatch, tmp_path)
    original = write_report(root, _inspection(HARD_TARGET))

    first = run_build(BuildRequest(project_root=root, preset="arm-debug"))
    assert first.ok is True, first.to_dict()
    captured = read_json(identity_path(root))["floatAbi"]
    assert captured["reportSha256"] == sha256_hex(original)

    rewritten = write_report(
        root,
        _inspection(HARD_TARGET),
        indent=4,
        extra={"note": "rewritten after the first build"},
    )
    assert rewritten != original
    monkeypatch.setenv("FAKE_CMAKE_NO_OUTPUT", "1")

    second = run_build(BuildRequest(project_root=root, preset="arm-debug"))

    assert second.ok is True, second.to_dict()
    identity = read_json(identity_path(root))
    receipt = read_json(receipt_path(root))
    assert identity["buildId"] == first.data.identity.build_id
    assert identity["floatAbi"] == captured
    assert receipt["floatAbi"] == captured
    assert identity["floatAbi"]["reportSha256"] == sha256_hex(original)
    assert sha256_hex(report_path(root).read_bytes()) != captured["reportSha256"]
    assert receipt["warnings"].count(captured["warning"]) == 1


def test_report_change_during_a_fresh_build_is_not_relabelled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root = _prepare_no_git(tmp_path, monkeypatch)
    hit_file = install_fake_cmake(monkeypatch, tmp_path)
    write_report(root, _inspection(HARD_TARGET))

    real_run_stage = runner_mod._run_stage

    def stage_with_report_change(
        stage: str,
        argv: tuple[str, ...],
        boundary_root: Path,
        timeout_seconds: int,
        sections: list[dict],
        log_rel: str,
    ):
        outcome = real_run_stage(
            stage, argv, boundary_root, timeout_seconds, sections, log_rel
        )
        if stage == "build":
            write_report(
                root,
                _inspection(HARD_TARGET),
                indent=4,
                extra={"revision": 2},
            )
        return outcome

    monkeypatch.setattr(runner_mod, "_run_stage", stage_with_report_change)

    result = run_build(BuildRequest(project_root=root, preset="arm-debug"))

    assert result.ok is True, result.to_dict()
    identity = read_json(identity_path(root))
    receipt = read_json(receipt_path(root))
    assert "floatAbi" not in identity
    assert "floatAbi" not in receipt
    assert receipt["warnings"].count(CHANGED_WARNING) == 1
    assert UNAVAILABLE_WARNING not in receipt["warnings"]
    assert list(result.data.warnings) == receipt["warnings"]
    # The wrapper preserved the real fake-tool stages and output validation.
    assert [record["argv"] for record in hit_records(hit_file)] == [
        ["--preset", "arm-debug"],
        ["--build", "--preset", "arm-debug"],
    ]
    assert len(identity["elfSha256"]) == 64
    assert len(identity["mapSha256"]) == 64


# ---------------------------------------------------------------------------
# bounded unavailability instead of raising
# ---------------------------------------------------------------------------


def _malformed_report() -> bytes:
    return b"{not-json\n"


def _duplicate_key_report() -> bytes:
    body = json.dumps(float_abi_evidence(_inspection(HARD_TARGET)))
    return ('{"floatAbi": ' + body + ', "floatAbi": ' + body + "}").encode("utf-8")


def _over_limit_report() -> bytes:
    return b" " * (CONVERSION_REPORT_LIMIT_BYTES + 1)


def _deeply_nested_report() -> bytes:
    return b'{"floatAbi": ' + b"[" * 3000 + b"]" * 3000 + b"}"


def _model_mismatch_report() -> bytes:
    # A resolver-consistent inferred-hard report in a declared-softfp project.
    return json.dumps(
        {"floatAbi": float_abi_evidence(_inspection(HARD_TARGET))}
    ).encode("utf-8")


def _blocked_report() -> bytes:
    inspection = SimpleNamespace(
        compiler="armcc",
        compiler_version=None,
        cpu="cortex-m4",
        fpu="FPU1",
        float_abi=None,
        rvds_vp="2",
    )
    return json.dumps({"floatAbi": float_abi_evidence(inspection)}).encode("utf-8")


def _forged_report() -> bytes:
    evidence = dict(float_abi_evidence(_inspection(HARD_TARGET)))
    evidence["reason"] = "hand-edited reason the deterministic resolver never emits"
    return json.dumps({"floatAbi": evidence}).encode("utf-8")


_UNSAFE_REPORTS = {
    "blocked-decision": (HARD_TARGET, _blocked_report),
    "deeply-nested": (HARD_TARGET, _deeply_nested_report),
    "duplicate-key": (HARD_TARGET, _duplicate_key_report),
    "forged-decision": (HARD_TARGET, _forged_report),
    "malformed": (HARD_TARGET, _malformed_report),
    "model-mismatch": (SOFTFP_TARGET, _model_mismatch_report),
    "over-limit": (HARD_TARGET, _over_limit_report),
}


@pytest.mark.parametrize("case", sorted(_UNSAFE_REPORTS))
def test_unsafe_or_invalid_reports_are_bounded_unavailability(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: str
):
    target, builder = _UNSAFE_REPORTS[case]
    root = prepare_project(
        tmp_path, overrides={"target": target}, git_repo=False
    )
    install_fake_git(monkeypatch, tmp_path, "exit1")
    install_fake_cmake(monkeypatch, tmp_path)
    _write_raw_report(root, builder())

    result = run_build(BuildRequest(project_root=root, preset="arm-debug"))

    assert result.ok is True, (case, result.to_dict())
    identity = read_json(identity_path(root))
    receipt = read_json(receipt_path(root))
    assert "floatAbi" not in identity
    assert "floatAbi" not in receipt
    assert receipt["warnings"].count(UNAVAILABLE_WARNING) == 1
    assert list(result.data.warnings) == receipt["warnings"]
    assert receipt["toolkitVersion"] == __version__


def test_nonregular_report_is_bounded_unavailability(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root = _prepare_no_git(tmp_path, monkeypatch)
    install_fake_cmake(monkeypatch, tmp_path)
    # A directory at the fixed leaf is never a readable regular report.
    report_path(root).mkdir(parents=True)

    result = run_build(BuildRequest(project_root=root, preset="arm-debug"))

    assert result.ok is True, result.to_dict()
    identity = read_json(identity_path(root))
    receipt = read_json(receipt_path(root))
    assert "floatAbi" not in identity
    assert "floatAbi" not in receipt
    assert receipt["warnings"].count(UNAVAILABLE_WARNING) == 1


def test_redirected_report_is_refused_without_reading_any_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root = _prepare_no_git(tmp_path, monkeypatch)
    install_fake_cmake(monkeypatch, tmp_path)
    valid = write_report(root, _inspection(HARD_TARGET))
    outside = tmp_path / "outside-conversion-report.json"
    outside.write_bytes(valid)
    outside_digest = sha256_hex(outside.read_bytes())
    report_abs = _norm_path(report_path(root))
    outside_abs = _norm_path(outside)

    # Controlled lstat seam: only the fixed leaf reports the Windows reparse
    # attribute.  This is not a real symlink capability test and creates
    # nothing on the host filesystem.
    real_lstat = os.lstat

    def reparse_lstat(path, *args, **kwargs):
        info = real_lstat(path, *args, **kwargs)
        if _norm_path(path) == report_abs:
            return SimpleNamespace(st_mode=info.st_mode, st_file_attributes=0x400)
        return info

    monkeypatch.setattr(abi_evidence_mod, "os", SimpleNamespace(lstat=reparse_lstat))

    opened: list[str] = []
    real_open = pathlib.Path.open

    def recording_open(self, *args, **kwargs):
        opened.append(_norm_path(self))
        return real_open(self, *args, **kwargs)

    monkeypatch.setattr(pathlib.Path, "open", recording_open)

    result = run_build(BuildRequest(project_root=root, preset="arm-debug"))

    assert result.ok is True, result.to_dict()
    # The redirected leaf and the outside decoy are never opened.
    assert report_abs not in opened
    assert outside_abs not in opened

    identity = read_json(identity_path(root))
    receipt = read_json(receipt_path(root))
    assert "floatAbi" not in identity
    assert "floatAbi" not in receipt
    assert receipt["warnings"].count(UNAVAILABLE_WARNING) == 1
    assert outside_digest not in json.dumps({"identity": identity, "record": receipt})


# ---------------------------------------------------------------------------
# public validator boundary: strict types, closed keys, resolver semantics
# ---------------------------------------------------------------------------


def test_float_abi_evidence_validator_accepts_exact_captured_evidence():
    evidence = _captured(HARD_TARGET, digest=sha256_hex(b"report bytes"))
    validated = validate_float_abi_evidence(evidence)
    assert validated == evidence
    assert validated["origin"] == "inferred"
    assert validated["selectedAbi"] == "hard"
    assert validated["baselineVerified"] is False
    assert validated["reportPath"] == CONVERSION_REPORT_PATH
    assert validated["reportSha256"] == sha256_hex(b"report bytes")


@pytest.mark.parametrize(
    "mutation",
    [
        {"origin": "blocked"},
        {"baselineVerified": True},
        {"compiler": None},
        {"cpu": ""},
        {"rawFloatAbi": True},
        {"selectedAbi": "softfp"},
        {"ruleId": DECLARED_RULE},
        {"reportPath": "artifacts/migration/conversion-report.json.bak"},
        {"reportSha256": "A" * 64},
        {"unexpected": "field"},
    ],
)
def test_float_abi_evidence_validator_rejects_null_boolean_extra_or_mismatch(
    mutation: dict,
):
    evidence = {**_captured(HARD_TARGET), **mutation}
    with pytest.raises(ValueError):
        validate_float_abi_evidence(evidence)


@pytest.mark.parametrize(
    "key", ["reportPath", "reportSha256", "origin", "baselineVerified", "nextStep"]
)
def test_float_abi_evidence_validator_requires_the_closed_key_set(key: str):
    evidence = {k: v for k, v in _captured(HARD_TARGET).items() if k != key}
    with pytest.raises(ValueError):
        validate_float_abi_evidence(evidence)


def test_resolved_validator_is_closed_and_accepts_only_the_reported_decision():
    resolved = dict(float_abi_evidence(_inspection(HARD_TARGET)))
    assert validate_float_abi_resolved(resolved) == resolved
    # Capture fields are identity/receipt keys, not conversion-report keys.
    with pytest.raises(ValueError):
        validate_float_abi_resolved(_captured(HARD_TARGET))
    with pytest.raises(ValueError):
        validate_float_abi_evidence(resolved)


@pytest.mark.parametrize(
    "mutation",
    [{"baselineVerified": True}, {"unexpectedKey": "x"}],
    ids=["verified", "extra-key"],
)
def test_identity_rejects_forged_or_extra_float_abi_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutation: dict
):
    root = _prepare_no_git(tmp_path, monkeypatch)
    install_fake_cmake(monkeypatch, tmp_path)
    write_report(root, _inspection(HARD_TARGET))
    assert run_build(BuildRequest(project_root=root, preset="arm-debug")).ok is True
    identity = read_json(identity_path(root))
    assert "floatAbi" in identity

    forged = {**identity, "floatAbi": {**identity["floatAbi"], **mutation}}
    forged["buildId"] = compute_build_id(forged)

    with pytest.raises(BuildError):
        validate_identity_document(forged)


@pytest.mark.parametrize(
    "mutation",
    [
        {"reason": "shape-valid but hand-edited resolver reason"},
        {"origin": "declared"},
    ],
    ids=["reason", "origin"],
)
def test_identity_rejects_semantically_altered_float_abi_even_with_recomputed_build_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutation: dict
):
    root = _prepare_no_git(tmp_path, monkeypatch)
    install_fake_cmake(monkeypatch, tmp_path)
    write_report(root, _inspection(HARD_TARGET))
    assert run_build(BuildRequest(project_root=root, preset="arm-debug")).ok is True
    identity = read_json(identity_path(root))
    assert identity["floatAbi"]["origin"] == "inferred"

    # The alteration keeps the closed shape (a non-empty reason literal, an
    # admitted origin) and the hash is rebuilt, so only resolver semantics can
    # reject the relabelled decision.
    altered = {**identity, "floatAbi": {**identity["floatAbi"], **mutation}}
    altered["buildId"] = compute_build_id(altered)
    assert altered["buildId"] != identity["buildId"]

    with pytest.raises(BuildError):
        validate_identity_document(altered)


def test_legacy_identity_hash_is_unchanged_and_present_evidence_changes_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root = _prepare_no_git(tmp_path, monkeypatch)
    install_fake_cmake(monkeypatch, tmp_path)
    assert run_build(BuildRequest(project_root=root, preset="arm-debug")).ok is True
    identity = read_json(identity_path(root))
    assert "floatAbi" not in identity

    # The historical identity hash covers every field except the three fixed
    # exclusions; absence of optional evidence keeps that exact algorithm.
    legacy_payload = {
        key: value
        for key, value in identity.items()
        if key not in ("schemaVersion", "buildId", "builtAtUtc")
    }
    legacy_digest = sha256_hex(canonical_json_bytes(legacy_payload))
    assert compute_build_id(identity) == legacy_digest
    assert identity["buildId"] == legacy_digest
    assert FirmwareIdentity.from_document(identity).to_dict() == identity

    evidence = _captured(HARD_TARGET)
    widened = {**identity, "floatAbi": evidence}
    widened_digest = compute_build_id(widened)
    assert widened_digest != legacy_digest
    widened["buildId"] = widened_digest
    validate_identity_document(widened)
    typed = FirmwareIdentity.from_document(widened)
    assert typed.to_dict() == widened
    assert typed.float_abi == evidence

    changed = {**widened, "floatAbi": {**evidence, "reportSha256": "f" * 64}}
    changed_digest = compute_build_id(changed)
    assert changed_digest != widened_digest
    changed["buildId"] = changed_digest
    validate_identity_document(changed)

    restored = {key: value for key, value in widened.items() if key != "floatAbi"}
    assert compute_build_id(restored) == legacy_digest


# ---------------------------------------------------------------------------
# optional receipt/identity provenance in managed consumers
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("git_repo", [True, False], ids=["schema1", "schema2"])
def test_one_sided_receipt_evidence_is_not_admitted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, git_repo: bool
):
    root = prepare_project(tmp_path, git_repo=git_repo)
    if not git_repo:
        install_fake_git(monkeypatch, tmp_path, "exit1")
    install_fake_cmake(monkeypatch, tmp_path)
    assert run_build(BuildRequest(project_root=root, preset="arm-debug")).ok is True
    receipt = read_json(receipt_path(root))
    assert "floatAbi" not in receipt
    # A receipt-only evidence object is never a valid provenance pair.
    receipt["floatAbi"] = _captured(HARD_TARGET)
    write_json(receipt_path(root), receipt)

    context = build_project_context(root, tmp_path / "data", "session-a")
    assert context.ok is True, context.to_dict()
    assert context.data["build"]["elfFresh"] is False
    assert context.data["build"]["buildId"] is None

    with pytest.raises(_FlashFailure) as error:
        load_fresh_firmware_facts(root)
    assert error.value.code == "FIRMWARE_IDENTITY_MISMATCH"
    assert error.value.details.get("field") == "buildResult"


@pytest.mark.parametrize(
    "payload",
    [None, True, {**_captured(HARD_TARGET), "unexpected": "field"}],
    ids=["null", "bool", "extra-key"],
)
def test_malformed_receipt_float_abi_is_not_admitted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, payload: object
):
    root = prepare_project(tmp_path)
    install_fake_cmake(monkeypatch, tmp_path)
    assert run_build(BuildRequest(project_root=root, preset="arm-debug")).ok is True
    identity = read_json(identity_path(root))
    receipt = read_json(receipt_path(root))
    assert "floatAbi" not in identity and "floatAbi" not in receipt
    # A forged null, boolean or arbitrary extra never becomes usable evidence.
    receipt["floatAbi"] = payload
    write_json(receipt_path(root), receipt)

    context = build_project_context(root, tmp_path / "data", "session-a")
    assert context.ok is True, context.to_dict()
    assert context.data["build"]["elfFresh"] is False
    assert context.data["build"]["buildId"] is None

    with pytest.raises(_FlashFailure) as error:
        load_fresh_firmware_facts(root)
    assert error.value.code == "FIRMWARE_IDENTITY_MISMATCH"
    assert error.value.details.get("field") == "buildResult"
    assert error.value.details.get("rule") == "identity"


@pytest.mark.parametrize("git_repo", [True, False], ids=["schema1", "schema2"])
def test_forged_toolkit_version_is_not_admitted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, git_repo: bool
):
    root = prepare_project(tmp_path, git_repo=git_repo)
    if not git_repo:
        install_fake_git(monkeypatch, tmp_path, "exit1")
    install_fake_cmake(monkeypatch, tmp_path)
    assert run_build(BuildRequest(project_root=root, preset="arm-debug")).ok is True

    forged = "0.0.0-forged"
    identity = read_json(identity_path(root))
    receipt = read_json(receipt_path(root))
    identity["toolkitVersion"] = forged
    identity["buildId"] = compute_build_id(identity)
    receipt["toolkitVersion"] = forged
    receipt["buildId"] = identity["buildId"]
    write_json(identity_path(root), identity)
    write_json(receipt_path(root), receipt)

    with pytest.raises(_FlashFailure) as error:
        load_fresh_firmware_facts(root)
    assert error.value.code == "FIRMWARE_IDENTITY_MISMATCH"
    assert error.value.details.get("field") == "toolkitVersion"
    assert error.value.details.get("rule") == "current"

    context = build_project_context(root, tmp_path / "data", "session-a")
    assert context.ok is True, context.to_dict()
    if not git_repo:
        # Schema-2 context compares the executing toolkit version; schema-1
        # context keeps its historical Git-shaped freshness checks (only the
        # flash admission compares toolkitVersion for schema 1).
        assert context.data["build"]["elfFresh"] is False
        assert context.data["build"]["buildId"] is None


@pytest.mark.parametrize("git_repo", [True, False], ids=["schema1", "schema2"])
def test_receipt_only_wrong_toolkit_version_is_not_admitted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, git_repo: bool
):
    root = prepare_project(tmp_path, git_repo=git_repo)
    if not git_repo:
        install_fake_git(monkeypatch, tmp_path, "exit1")
    install_fake_cmake(monkeypatch, tmp_path)
    assert run_build(BuildRequest(project_root=root, preset="arm-debug")).ok is True
    identity = read_json(identity_path(root))
    receipt = read_json(receipt_path(root))
    assert identity["toolkitVersion"] == __version__

    # Only the receipt is relabelled; the identity and its build ID stay as
    # written, so this is a receipt/identity disagreement, never a stale build.
    receipt["toolkitVersion"] = "0.0.0-forged"
    write_json(receipt_path(root), receipt)

    context = build_project_context(root, tmp_path / "data", "session-a")
    assert context.ok is True, context.to_dict()
    assert context.data["build"]["elfFresh"] is False
    assert context.data["build"]["buildId"] is None

    with pytest.raises(_FlashFailure) as error:
        load_fresh_firmware_facts(root)
    assert error.value.code == "FIRMWARE_IDENTITY_MISMATCH"
    assert error.value.details.get("field") == "buildResult"
    assert error.value.details.get("rule") == "identity"


@pytest.mark.parametrize("git_repo", [True, False], ids=["schema1", "schema2"])
def test_legacy_receipt_without_optional_fields_remains_admitted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, git_repo: bool
):
    root = prepare_project(tmp_path, git_repo=git_repo)
    if not git_repo:
        install_fake_git(monkeypatch, tmp_path, "exit1")
    _install_programmable_firmware(monkeypatch, tmp_path)
    assert run_build(BuildRequest(project_root=root, preset="arm-debug")).ok is True
    identity = read_json(identity_path(root))
    receipt = read_json(receipt_path(root))
    assert "floatAbi" not in identity and "floatAbi" not in receipt

    # Untouched absent optional fields stay compatible for older receipts.
    legacy = {key: value for key, value in receipt.items() if key != "toolkitVersion"}
    write_json(receipt_path(root), legacy)

    facts = load_fresh_firmware_facts(root)
    assert facts.build_id == identity["buildId"]
    assert facts.elf_sha256 == identity["elfSha256"]

    context = build_project_context(root, tmp_path / "data", "session-a")
    assert context.ok is True, context.to_dict()
    assert context.data["build"]["elfFresh"] is True
    assert context.data["build"]["buildId"] == identity["buildId"]

