"""ARMCC-FLOAT-ABI bounded compatibility slice.

These tests are entirely offline and synthetic.  They pin the approved
behavior: numeric ``uFloatingPoint`` values are not ABI evidence, literal
``soft``/``softfp``/``hard`` text is a project declaration only, the narrow
ARMCC + Cortex-M4 + FPU2 default-hard candidate stays explicitly inferred and
unverified, and every other combination fails closed.  No AXF or binary
baseline is parsed, so ``baselineVerified`` is always false.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from stm32_toolkit.generation import plan_project_configuration
from stm32_toolkit.keil import inspect_keil
from stm32_toolkit.migration import (
    apply_keil_conversion,
    apply_keil_delivery,
    plan_keil_conversion,
    plan_keil_delivery,
)
from stm32_toolkit.migration.float_abi import (
    float_abi_evidence,
    resolve_float_abi,
)
from stm32_toolkit.migration.model import (
    inspection_sha256_for,
    plan_id_for,
)
from stm32_toolkit.migration.preflight import preflight_keil_conversion
from stm32_toolkit.project_model import load_project_model

from test_migration_delivery import REPORT_PATH as DELIVERY_REPORT_PATH
from test_migration_delivery import make_repo as _delivery_repo
from test_migration_delivery import output_parent as _delivery_output_parent
from test_migration_plan import (
    CONVERSION_PRODUCTS,
    CORE_CPU,
    CORE_CPU_NO_FPU,
    FRAMEWORK_INCLUDE,
    _add_file_scoped_controls,
    _add_group_scoped_controls,
    _commit_scoped_project,
    build_repo,
    manifest_json,
)

ARMCC = "5060750::V5.06 update 7 (build 750)::ARMCC"
ARMCLANG = "6190000::V6.19::ARMCLANG"
UNKNOWN_COMPILER = "1::V1::OTHER-TOOLCHAIN"
MAIN = "int main(void) { return 0; }\n"
EVIDENCE_KEYS = {
    "compiler",
    "compilerVersion",
    "cpu",
    "rawFpu",
    "rawFloatAbi",
    "rawRvdsVp",
    "fpu",
    "selectedAbi",
    "origin",
    "ruleId",
    "reason",
    "baselineVerified",
    "warning",
    "nextStep",
}


def _repo(
    tmp_path: Path,
    *,
    name: str = "abi",
    abi: str | None = None,
    rvds_vp: str | None = None,
    cpu: str = CORE_CPU,
    pcc: str = ARMCC,
    compiler_misc: str = "",
    commit: bool = True,
) -> Path:
    """Build one disposable Git repository with a single C source."""
    return build_repo(
        tmp_path,
        name=name,
        files={"Main/main.c": MAIN},
        commit=commit,
        uvprojx_kwargs={
            "cpu": cpu,
            "fpu": abi,
            "rvds_vp": rvds_vp,
            "pcc": pcc,
            "compiler_misc": compiler_misc,
            "groups": (("Main", (("main.c", "1", "Main/main.c"),)),),
            "includes": f"Main;{FRAMEWORK_INCLUDE}",
        },
    )


def _preflight_evidence(repo: Path) -> dict[str, object]:
    data = preflight_keil_conversion(repo, inspect_keil(repo))
    evidence = data["analysis"]["floatAbi"]
    assert isinstance(evidence, dict)
    return evidence


def _plan_and_manifest(repo: Path):
    plan = plan_keil_conversion(repo, inspect_keil(repo))
    patch = next(p for p in plan.patches if p.path == ".stm32-project.json")
    return plan, manifest_json(patch)


def _report(repo: Path) -> dict[str, object]:
    return json.loads(
        (repo / "artifacts/migration/conversion-report.json").read_text(
            encoding="utf-8"
        )
    )


def _cmake_flags(repo: Path, directive: str) -> list[str]:
    configuration = plan_project_configuration(load_project_model(repo))
    cmake = next(file for file in configuration.files if file.path == "CMakeLists.txt")
    text = cmake.after_bytes.decode("utf-8")
    start = text.index(f"{directive}(")
    private = text.index(" PRIVATE\n", start)
    end = text.index("\n)", private)
    return [
        token
        for token in text[start:end].split()
        if token.startswith(("-mfpu=", "-mfloat-abi="))
    ]


def _assert_no_products(repo: Path) -> None:
    for rel in CONVERSION_PRODUCTS:
        assert not (repo / rel).exists()


# ---------------------------------------------------------------------------
# evidence shape and parity
# ---------------------------------------------------------------------------


def test_preflight_plan_report_share_one_deterministic_evidence_object(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path, rvds_vp=None)
    inspection = inspect_keil(repo)
    preflight = _preflight_evidence(repo)
    plan = plan_keil_conversion(repo, inspection)
    plan_evidence = plan.to_dict()["floatAbi"]

    assert preflight == plan_evidence == float_abi_evidence(plan.inspection)
    assert set(preflight) == EVIDENCE_KEYS
    assert preflight["origin"] == "inferred"
    assert preflight["selectedAbi"] == "hard"
    assert preflight["baselineVerified"] is False
    assert "abiChanged" not in preflight
    # ``remediation`` is preflight-only blocker presentation; PLAN evidence
    # carries compatibility guidance as ``nextStep`` instead.
    assert "remediation" not in plan_evidence

    result = apply_keil_conversion(plan)
    assert result.ok is True
    report = _report(repo)
    assert report["floatAbi"] == preflight
    assert report["floatAbi"]["baselineVerified"] is False
    assert "abiChanged" not in report["floatAbi"]


def test_not_applicable_evidence_emits_no_abi_options(tmp_path: Path) -> None:
    repo = _repo(tmp_path, cpu=CORE_CPU_NO_FPU)
    preflight = _preflight_evidence(repo)
    assert preflight["origin"] == "not-applicable"
    assert preflight["selectedAbi"] is None
    assert preflight["fpu"] is None
    assert preflight["baselineVerified"] is False

    plan, manifest = _plan_and_manifest(repo)
    assert not plan.blockers
    assert "fpu" not in manifest["target"]
    assert "floatAbi" not in manifest["target"]
    assert apply_keil_conversion(plan).ok is True

    report = _report(repo)
    assert report["floatAbi"] == preflight
    for directive in ("target_compile_options", "target_link_options"):
        flags = _cmake_flags(repo, directive)
        assert not any(flag.startswith("-mfpu=") for flag in flags)
        assert not any(flag.startswith("-mfloat-abi=") for flag in flags)


# ---------------------------------------------------------------------------
# numeric uFloatingPoint values are not ABI declarations
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("raw", ["0", "1", "2", "3"])
def test_numeric_float_abi_is_rejected_not_mapped(tmp_path: Path, raw: str) -> None:
    # The historical selector value does not turn a numeric value into ABI
    # evidence.
    repo = _repo(tmp_path, abi=raw, rvds_vp="2")
    inspection = inspect_keil(repo)
    assert inspection.float_abi == raw
    assert inspection.rvds_vp == "2"

    preflight = _preflight_evidence(repo)
    assert preflight["origin"] == "blocked"
    assert preflight["ruleId"] == "MIGRATION_FLOAT_ABI_UNSUPPORTED"
    assert preflight["rawFloatAbi"] == raw
    assert preflight["selectedAbi"] is None
    assert preflight["fpu"] is None
    assert preflight["baselineVerified"] is False

    plan, manifest = _plan_and_manifest(repo)
    assert "fpu" not in manifest["target"]
    assert "floatAbi" not in manifest["target"]
    blockers = [b for b in plan.blockers if b.code == "MIGRATION_FLOAT_ABI_UNSUPPORTED"]
    assert [(b.path, b.evidence) for b in blockers] == [("app.uvprojx", raw)]
    assert plan.to_dict()["floatAbi"] == preflight

    result = apply_keil_conversion(plan)
    assert result.ok is False
    assert result.code == "MIGRATION_BLOCKED"
    assert list(result.details["blockerCodes"]) == ["MIGRATION_FLOAT_ABI_UNSUPPORTED"]
    _assert_no_products(repo)


# ---------------------------------------------------------------------------
# literal declarations are project intent, never a verified baseline
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("abi", ["soft", "softfp", "hard"])
def test_literal_declaration_is_reported_as_declared(
    tmp_path: Path, abi: str
) -> None:
    repo = _repo(tmp_path, abi=abi)
    preflight = _preflight_evidence(repo)
    assert preflight["origin"] == "declared"
    assert preflight["ruleId"] == "MIGRATION_FLOAT_ABI_DECLARED"
    assert preflight["selectedAbi"] == abi
    assert preflight["fpu"] == "fpv4-sp-d16"
    assert preflight["baselineVerified"] is False
    assert "declaration does not prove" in str(preflight["warning"])

    plan, manifest = _plan_and_manifest(repo)
    assert not plan.blockers
    assert manifest["target"]["fpu"] == "fpv4-sp-d16"
    assert manifest["target"]["floatAbi"] == abi
    assert plan.to_dict()["floatAbi"] == preflight
    assert apply_keil_conversion(plan).ok is True

    for directive in ("target_compile_options", "target_link_options"):
        flags = _cmake_flags(repo, directive)
        assert flags.count("-mfpu=fpv4-sp-d16") == 1
        assert flags.count(f"-mfloat-abi={abi}") == 1
    assert _report(repo)["floatAbi"] == preflight


# ---------------------------------------------------------------------------
# narrow default-hard inference
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("rvds_vp", [None, "", "2"])
def test_historical_selector_keeps_inferred_unverified_hard(
    tmp_path: Path, rvds_vp: str | None
) -> None:
    repo = _repo(tmp_path, abi=None, rvds_vp=rvds_vp)
    inspection = inspect_keil(repo)
    assert inspection.rvds_vp == rvds_vp

    preflight = _preflight_evidence(repo)
    assert preflight["origin"] == "inferred"
    assert preflight["ruleId"] == "MIGRATION_FLOAT_ABI_DEFAULT_HARD_INFERRED"
    assert preflight["selectedAbi"] == "hard"
    assert preflight["fpu"] == "fpv4-sp-d16"
    assert preflight["rawFloatAbi"] is None
    assert preflight["rawRvdsVp"] == rvds_vp
    assert preflight["baselineVerified"] is False
    warning = str(preflight["warning"])
    assert "inferred" in warning
    assert "not verified" in warning

    plan, manifest = _plan_and_manifest(repo)
    assert not plan.blockers
    assert manifest["target"] == {
        "device": "STM32F429ZGTx",
        "core": "cortex-m4",
        "fpu": "fpv4-sp-d16",
        "floatAbi": "hard",
        "devicePack": "Keil.STM32F4xx_DFP.2.16.1",
    }
    assert apply_keil_conversion(plan).ok is True

    for directive in ("target_compile_options", "target_link_options"):
        flags = _cmake_flags(repo, directive)
        assert flags.count("-mfpu=fpv4-sp-d16") == 1
        assert flags.count("-mfloat-abi=hard") == 1
    assert _report(repo)["floatAbi"] == preflight


@pytest.mark.parametrize(
    ("pcc", "cpu", "fpu_token", "expected_rule", "apply_code"),
    [
        (
            ARMCLANG,
            CORE_CPU,
            "FPU2",
            "MIGRATION_FLOAT_ABI_REQUIRED",
            "MIGRATION_PLAN_INVALID",
        ),
        (
            UNKNOWN_COMPILER,
            CORE_CPU,
            "FPU2",
            "MIGRATION_FLOAT_ABI_REQUIRED",
            "MIGRATION_PLAN_INVALID",
        ),
        (
            ARMCC,
            CORE_CPU.replace('"Cortex-M4"', '"Cortex-M7"'),
            "FPU2",
            "MIGRATION_FPU_UNSUPPORTED",
            "MIGRATION_BLOCKED",
        ),
        (
            ARMCC,
            CORE_CPU.replace("FPU2", "FPU3"),
            "FPU3",
            "MIGRATION_FPU_UNSUPPORTED",
            "MIGRATION_BLOCKED",
        ),
    ],
)
def test_other_compiler_or_fpu_combinations_fail_closed(
    tmp_path: Path,
    pcc: str,
    cpu: str,
    fpu_token: str,
    expected_rule: str,
    apply_code: str,
) -> None:
    repo = _repo(tmp_path, cpu=cpu, pcc=pcc)
    inspection = inspect_keil(repo)
    assert inspection.fpu == fpu_token

    preflight = _preflight_evidence(repo)
    assert preflight["origin"] == "blocked"
    assert preflight["ruleId"] == expected_rule
    assert preflight["selectedAbi"] is None
    assert preflight["baselineVerified"] is False

    plan, manifest = _plan_and_manifest(repo)
    assert "fpu" not in manifest["target"]
    assert "floatAbi" not in manifest["target"]
    codes = [b.code for b in plan.blockers]
    assert codes.count(expected_rule) == 1
    assert apply_keil_conversion(plan).code == apply_code
    _assert_no_products(repo)


# ---------------------------------------------------------------------------
# ArmAdsMisc/RvdsVP bounded compatibility selection
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("selector", ["0", "1", "3", "weird"])
def test_nonhistorical_selector_blocks_inference(
    tmp_path: Path, selector: str
) -> None:
    repo = _repo(tmp_path, abi=None, rvds_vp=selector)
    preflight = _preflight_evidence(repo)
    assert preflight["origin"] == "blocked"
    assert preflight["ruleId"] == "MIGRATION_FPU_SELECTION_UNSUPPORTED"
    assert preflight["rawRvdsVp"] == selector
    assert preflight["selectedAbi"] is None
    assert preflight["baselineVerified"] is False

    plan, manifest = _plan_and_manifest(repo)
    assert "fpu" not in manifest["target"]
    assert "floatAbi" not in manifest["target"]
    blockers = [
        b for b in plan.blockers if b.code == "MIGRATION_FPU_SELECTION_UNSUPPORTED"
    ]
    assert [(b.path, b.evidence) for b in blockers] == [("app.uvprojx", selector)]
    assert apply_keil_conversion(plan).code == "MIGRATION_BLOCKED"
    _assert_no_products(repo)

    data = preflight_keil_conversion(repo, inspect_keil(repo))
    public = next(
        b
        for b in data["analysis"]["blockers"]
        if b["code"] == "MIGRATION_FPU_SELECTION_UNSUPPORTED"
    )
    assert public["remediation"]["category"] == "unsupported"
    summary = public["remediation"]["summary"].lower()
    assert "inspect" in summary
    assert "retain" in summary
    assert "project-owned port" in summary


def test_literal_declaration_with_historical_selector_is_declared(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path, abi="softfp", rvds_vp="2")
    preflight = _preflight_evidence(repo)
    assert preflight["origin"] == "declared"
    assert preflight["selectedAbi"] == "softfp"
    assert preflight["rawRvdsVp"] == "2"
    plan, manifest = _plan_and_manifest(repo)
    assert not plan.blockers
    assert manifest["target"]["floatAbi"] == "softfp"


@pytest.mark.parametrize("abi", ["soft", "softfp", "hard"])
def test_literal_declaration_cannot_bypass_conflicting_selector(
    tmp_path: Path, abi: str
) -> None:
    repo = _repo(tmp_path, abi=abi, rvds_vp="0")
    preflight = _preflight_evidence(repo)
    assert preflight["origin"] == "blocked"
    assert preflight["ruleId"] == "MIGRATION_FPU_SELECTION_UNSUPPORTED"

    plan, manifest = _plan_and_manifest(repo)
    assert "fpu" not in manifest["target"]
    assert "floatAbi" not in manifest["target"]
    assert [b.code for b in plan.blockers] == [
        "MIGRATION_FPU_SELECTION_UNSUPPORTED"
    ]
    assert apply_keil_conversion(plan).code == "MIGRATION_BLOCKED"
    _assert_no_products(repo)


def test_literal_declaration_cannot_bypass_unsupported_fpu(tmp_path: Path) -> None:
    repo = _repo(tmp_path, abi="hard", cpu=CORE_CPU.replace("FPU2", "FPU3"))
    preflight = _preflight_evidence(repo)
    assert preflight["origin"] == "blocked"
    assert preflight["ruleId"] == "MIGRATION_FPU_UNSUPPORTED"
    assert preflight["rawFloatAbi"] == "hard"

    plan, manifest = _plan_and_manifest(repo)
    assert "fpu" not in manifest["target"]
    assert "floatAbi" not in manifest["target"]
    assert [b.code for b in plan.blockers] == ["MIGRATION_FPU_UNSUPPORTED"]
    assert apply_keil_conversion(plan).code == "MIGRATION_BLOCKED"
    _assert_no_products(repo)


# ---------------------------------------------------------------------------
# existing misc-control blockers remain in force
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("scope", "apply_code"),
    [
        # A target misc control keeps its historical empty-path blocker, which
        # apply's legacy plan validation reports as MIGRATION_PLAN_INVALID.
        ("target", "MIGRATION_PLAN_INVALID"),
        ("group", "MIGRATION_BLOCKED"),
        ("file", "MIGRATION_BLOCKED"),
    ],
)
def test_misc_controls_still_block_even_with_inferred_evidence(
    tmp_path: Path, scope: str, apply_code: str
) -> None:
    if scope == "target":
        repo = _repo(
            tmp_path,
            name="misc-target",
            rvds_vp="2",
            compiler_misc="--apcs=/softfp",
        )
    else:
        repo = _repo(tmp_path, name=f"misc-{scope}", rvds_vp="2", commit=False)
        if scope == "group":
            _add_group_scoped_controls(
                repo, "Main", misc_controls="--apcs=/softfp"
            )
        else:
            _add_file_scoped_controls(
                repo, "Main/main.c", misc_controls="--apcs=/softfp"
            )
        _commit_scoped_project(repo)

    preflight = _preflight_evidence(repo)
    assert preflight["origin"] == "inferred"
    assert preflight["selectedAbi"] == "hard"

    plan, manifest = _plan_and_manifest(repo)
    assert any(
        blocker.code == "ARMCC_OPTION_UNSUPPORTED" for blocker in plan.blockers
    )
    # The inferred evidence is not an authorization and does not rewrite the
    # project's misc controls.
    assert manifest["target"]["floatAbi"] == "hard"
    result = apply_keil_conversion(plan)
    assert result.ok is False
    assert result.code == apply_code
    _assert_no_products(repo)


# ---------------------------------------------------------------------------
# plan identity, tamper, and stale rejection
# ---------------------------------------------------------------------------


def test_plan_identity_binds_derived_float_abi_evidence(tmp_path: Path) -> None:
    repo = _repo(tmp_path, rvds_vp="2")
    inspection = inspect_keil(repo)
    plan = plan_keil_conversion(repo, inspection)
    evidence = float_abi_evidence(plan.inspection)

    assert plan.to_dict()["floatAbi"] == evidence
    assert plan_id_for(plan) == plan.plan_id
    assert inspection_sha256_for(plan.inspection) == plan.inspection_sha256

    repeated = plan_keil_conversion(repo, inspect_keil(repo))
    assert repeated.plan_id == plan.plan_id
    assert repeated.to_dict()["floatAbi"] == evidence


def test_forged_float_abi_state_is_rejected_without_writes(tmp_path: Path) -> None:
    repo = _repo(tmp_path, rvds_vp=None)
    plan = plan_keil_conversion(repo, inspect_keil(repo))

    # Rewrite the bound inspection's selector and honestly recompute both
    # digests; the fresh project still disagrees, so apply must refuse.
    forged_inspection = replace(plan.inspection, rvds_vp="0")
    forged = replace(
        plan,
        inspection=forged_inspection,
        inspection_sha256=inspection_sha256_for(forged_inspection),
    )
    forged = replace(forged, plan_id=plan_id_for(forged))
    assert forged.to_dict()["floatAbi"]["ruleId"] == (
        "MIGRATION_FPU_SELECTION_UNSUPPORTED"
    )

    result = apply_keil_conversion(forged)
    assert result.ok is False
    assert result.code == "MIGRATION_PLAN_INVALID"
    assert result.details == {"rule": "freshInspection"}
    _assert_no_products(repo)


def test_stale_project_bytes_after_plan_are_rejected(tmp_path: Path) -> None:
    repo = _repo(tmp_path, rvds_vp="2")
    plan = plan_keil_conversion(repo, inspect_keil(repo))
    project = repo / "app.uvprojx"
    project.write_bytes(project.read_bytes() + b"\n")

    result = apply_keil_conversion(plan)
    assert result.ok is False
    assert result.code == "MIGRATION_INPUT_CHANGED"
    assert result.details.get("path") == "app.uvprojx"
    _assert_no_products(repo)


def test_resolve_decision_is_pure_and_matches_evidence(tmp_path: Path) -> None:
    repo = _repo(tmp_path, abi=None, rvds_vp="2")
    inspection = inspect_keil(repo)
    first = resolve_float_abi(inspection)
    second = resolve_float_abi(inspection)
    assert first == second
    assert first.origin == "inferred"
    assert first.abi == "hard"
    assert first.blocked is False


# ---------------------------------------------------------------------------
# independent delivery PLAN/APPLY presentation
# ---------------------------------------------------------------------------


def _delivery_fixture(tmp_path: Path, *, name: str, abi: str | None = None):
    """Disposable no-Git delivery source plus one absent destination."""
    repo = _delivery_repo(
        tmp_path,
        name=name,
        uvprojx_kwargs={"cpu": CORE_CPU, "fpu": abi},
    )
    destination = (
        _delivery_output_parent(tmp_path, f"{name}-out") / "gcc-project"
    )
    plan = plan_keil_delivery(repo, destination, inspect_keil(repo))
    return repo, destination, plan


def test_delivery_plan_and_apply_expose_inferred_float_abi(
    tmp_path: Path,
) -> None:
    repo, destination, plan = _delivery_fixture(
        tmp_path, name="delivery-inferred"
    )
    evidence = float_abi_evidence(plan.inspection)
    # Absent uFloatingPoint on ARMCC Cortex-M4 FPU2 keeps the narrow
    # default-hard inference, still unverified against the binary.
    assert evidence["origin"] == "inferred"
    assert evidence["selectedAbi"] == "hard"
    assert evidence["rawFloatAbi"] is None
    assert evidence["baselineVerified"] is False

    preview = plan.to_dict()
    assert preview["floatAbi"] == evidence
    # The ABI warning is added beside, never instead of, the existing
    # delivery warning.
    assert len(preview["warnings"]) == 2
    assert evidence["warning"] in preview["warnings"]
    assert any(
        "Inputs outside the source tree" in warning
        for warning in preview["warnings"]
    )

    result = apply_keil_delivery(plan, authorized=True, plan_id=plan.plan_id)
    assert result.ok is True, result.to_dict()
    data = result.to_dict()["data"]
    assert data["floatAbi"] == evidence
    assert data["warnings"] == preview["warnings"]

    report = json.loads(
        (destination / DELIVERY_REPORT_PATH).read_text(encoding="utf-8")
    )
    assert report["floatAbi"] == evidence
    assert not (repo / ".git").exists()


def test_delivery_plan_and_apply_expose_declared_softfp(tmp_path: Path) -> None:
    _repo_path, destination, plan = _delivery_fixture(
        tmp_path, name="delivery-softfp", abi="softfp"
    )
    evidence = float_abi_evidence(plan.inspection)
    assert evidence["origin"] == "declared"
    assert evidence["selectedAbi"] == "softfp"
    assert evidence["rawFloatAbi"] == "softfp"
    assert evidence["baselineVerified"] is False

    preview = plan.to_dict()
    assert preview["floatAbi"] == evidence
    assert len(preview["warnings"]) == 2
    assert evidence["warning"] in preview["warnings"]
    assert any(
        "Inputs outside the source tree" in warning
        for warning in preview["warnings"]
    )

    result = apply_keil_delivery(plan, authorized=True, plan_id=plan.plan_id)
    assert result.ok is True, result.to_dict()
    data = result.to_dict()["data"]
    assert data["floatAbi"] == evidence
    assert data["warnings"] == preview["warnings"]

    report = json.loads(
        (destination / DELIVERY_REPORT_PATH).read_text(encoding="utf-8")
    )
    assert report["floatAbi"] == evidence
