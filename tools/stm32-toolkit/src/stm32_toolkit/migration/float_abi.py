"""Bounded ARMCC float-ABI evidence for Keil migration (ARMCC-FLOAT-ABI).

Numeric ``uFloatingPoint`` values are not proven ABI declarations, and the
ARMCC bare-metal hardware-FPU default does not establish an ARM Linux
``softfp`` default.  This module therefore keeps only one narrow, explicitly
unverified inference for the historical ARMCC + Cortex-M4 + FPU2 target with
its ``ArmAdsMisc/RvdsVP`` selector, and otherwise fails closed.  Literal
``soft``/``softfp``/``hard`` text is retained as a project declaration only;
it never proves the original binary's ABI.

No AXF, object, library, or compiler command line is parsed here, so every
decision keeps ``baselineVerified: false``.
"""

from __future__ import annotations

from dataclasses import dataclass

from stm32_toolkit.keil import KeilInspection

#: Exact literal project declarations retained for compatibility.
_LITERAL_FLOAT_ABIS = frozenset({"soft", "softfp", "hard"})

#: The only closed Keil CPU/FPU tuple this slice can normalize.
_KEIL_FPU_EVIDENCE = {("cortex-m4", "FPU2"): "fpv4-sp-d16"}

#: Selected-target selector values allowed by the bounded historical
#: compatibility rule: absent/empty and the value 2 observed in the reference
#: project.  This is not proof of binary equivalence or a general decoding of
#: RvdsVP.  Any other non-empty value blocks the inference.
_HISTORICAL_RVDS_VP = (None, "", "2")

_BASELINE_WARNING = (
    "Project settings alone do not verify the original AXF, objects or "
    "libraries; binary float compatibility is not proven."
)

#: Stable blocker codes (and evidence identifiers) owned by this slice.
FPU_UNSUPPORTED = "MIGRATION_FPU_UNSUPPORTED"
FPU_SELECTION_UNSUPPORTED = "MIGRATION_FPU_SELECTION_UNSUPPORTED"
FLOAT_ABI_REQUIRED = "MIGRATION_FLOAT_ABI_REQUIRED"
FLOAT_ABI_REQUIRES_FPU = "MIGRATION_FLOAT_ABI_REQUIRES_FPU"
FLOAT_ABI_UNSUPPORTED = "MIGRATION_FLOAT_ABI_UNSUPPORTED"


def _blocked(
    rule_id: str,
    message: str,
    evidence: str | None,
    reason: str,
    remediation: str,
) -> "FloatAbiDecision":
    return FloatAbiDecision(
        fpu=None,
        abi=None,
        origin="blocked",
        rule_id=rule_id,
        reason=reason,
        message=message,
        evidence=evidence,
        remediation=remediation,
    )


@dataclass(frozen=True)
class FloatAbiDecision:
    """One deterministic FPU/float-ABI decision derived from inspection."""

    fpu: str | None
    abi: str | None
    origin: str  # inferred, declared, blocked, or not-applicable
    rule_id: str
    reason: str
    message: str
    evidence: str | None = None
    remediation: str | None = None
    warning: str = _BASELINE_WARNING

    @property
    def blocked(self) -> bool:
        return self.origin == "blocked"


def resolve_float_abi(inspection: KeilInspection) -> FloatAbiDecision:
    """Resolve FPU/float-ABI evidence without guessing unsupported data.

    Numeric ``uFloatingPoint`` values are rejected because they are not proven
    ABI declarations.  The single default-hard inference is restricted to
    ARMCC + Cortex-M4 + FPU2, and only when the selected target's
    ``ArmAdsMisc/RvdsVP`` selector is absent/empty or the historical value
    ``2``.  That value is allowed by this bounded rule, not proven to mean
    binary compatibility.  An explicit literal declaration never suppresses a
    conflicting or unsupported hardware selection.
    """
    raw_fpu = (inspection.fpu or "").strip()
    raw_abi = (inspection.float_abi or "").strip()
    raw_selector = inspection.rvds_vp
    selector = raw_selector.strip() if raw_selector is not None else None

    if not raw_fpu:
        if raw_abi:
            return _blocked(
                FLOAT_ABI_REQUIRES_FPU,
                "Keil float ABI evidence requires FPU evidence",
                raw_abi,
                "uFloatingPoint evidence exists without FPU evidence",
                "Inspect and retain the actual FPU/ABI evidence; there is no"
                " Toolkit override.",
            )
        return FloatAbiDecision(
            fpu=None,
            abi=None,
            origin="not-applicable",
            rule_id="MIGRATION_FLOAT_ABI_NOT_APPLICABLE",
            reason="no FPU or float ABI evidence",
            message="no FPU or float ABI evidence",
            warning=(
                "No FPU or float ABI evidence; the migration emits no -mfpu or"
                " -mfloat-abi options."
            ),
        )

    fpu = _KEIL_FPU_EVIDENCE.get((inspection.cpu.casefold(), raw_fpu.upper()))
    if fpu is None:
        return _blocked(
            FPU_UNSUPPORTED,
            "unsupported or ambiguous Keil FPU evidence",
            raw_fpu,
            f"CPU/FPU tuple {inspection.cpu}/{raw_fpu} is outside the closed evidence map",
            "Inspect the actual Keil FPU and toolchain evidence, retain it, and"
            " use a separately reviewed project-owned port; do not alter the"
            " evidence to clear this blocker.",
        )

    # The selector describes the selected target's hardware selection.  It is
    # not decoded beyond this bounded compatibility check, and it blocks even
    # when a literal ABI declaration is present.
    if raw_fpu.upper() == "FPU2" and selector not in _HISTORICAL_RVDS_VP:
        return _blocked(
            FPU_SELECTION_UNSUPPORTED,
            "unsupported or ambiguous Keil FPU hardware selection",
            raw_selector,
            f"selected target ArmAdsMisc/RvdsVP {selector!r} is outside the historical FPU2 candidate",
            "Inspect the selected target's ArmAdsMisc/RvdsVP and actual hardware"
            " selection, retain the evidence, and use a separately reviewed"
            " project-owned port; do not alter the selector to clear this blocker.",
        )

    if raw_abi:
        if raw_abi not in _LITERAL_FLOAT_ABIS:
            return _blocked(
                FLOAT_ABI_UNSUPPORTED,
                "unsupported or ambiguous Keil float ABI",
                raw_abi,
                f"uFloatingPoint value {raw_abi!r} is not a literal ABI declaration",
                "Numeric or unknown uFloatingPoint values are not ABI proof."
                " Inspect the actual compiler command lines, objects and"
                " libraries and use a separately reviewed project-owned port;"
                " do not relabel the evidence.",
            )
        return FloatAbiDecision(
            fpu=fpu,
            abi=raw_abi,
            origin="declared",
            rule_id="MIGRATION_FLOAT_ABI_DECLARED",
            reason=f"project declares {raw_abi} float linkage",
            message=f"project declares {raw_abi} float linkage; binary baseline unverified",
            remediation=(
                "Verify that the declared ABI matches the original objects and"
                " libraries; there is no Toolkit ABI override."
            ),
            warning=(
                f"The project declares {raw_abi} linkage; a declaration does not"
                " prove the original binary ABI. " + _BASELINE_WARNING
            ),
        )

    if (
        inspection.compiler == "armcc"
        and inspection.cpu.casefold() == "cortex-m4"
        and raw_fpu.upper() == "FPU2"
    ):
        return FloatAbiDecision(
            fpu=fpu,
            abi="hard",
            origin="inferred",
            rule_id="MIGRATION_FLOAT_ABI_DEFAULT_HARD_INFERRED",
            reason=(
                "ARMCC Cortex-M4 FPU2 without an explicit ABI declaration;"
                " historical default hard linkage is inferred"
            ),
            message="default hard linkage inferred from ARMCC Cortex-M4 FPU2; unverified",
            remediation=(
                "Verify the original compiler command lines, objects and"
                " libraries before relying on hard linkage; there is no Toolkit"
                " ABI override."
            ),
            warning=(
                "Hard linkage is inferred from the ARMCC Cortex-M4 FPU2 default"
                " and is not verified against the original binary. "
                + _BASELINE_WARNING
            ),
        )

    return _blocked(
        FLOAT_ABI_REQUIRED,
        "Keil FPU evidence requires an explicit float ABI",
        raw_fpu,
        f"FPU {raw_fpu!r} has no default ABI inference for compiler {inspection.compiler!r}",
        "Inspect the actual compiler command lines and build configuration,"
        " retain the current semantics, and use a separately reviewed"
        " project-owned port; there is no ABI override.",
    )


def float_abi_evidence(inspection: KeilInspection) -> dict[str, object]:
    """Return the one deterministic evidence object used by every surface.

    ``baselineVerified`` is always false: this slice never parses the original
    AXF, objects, libraries, or compiler command lines.
    """
    decision = resolve_float_abi(inspection)
    return {
        "compiler": inspection.compiler,
        "compilerVersion": inspection.compiler_version,
        "cpu": inspection.cpu,
        "rawFpu": inspection.fpu,
        "rawFloatAbi": inspection.float_abi,
        "rawRvdsVp": inspection.rvds_vp,
        "fpu": decision.fpu,
        "selectedAbi": decision.abi,
        "origin": decision.origin,
        "ruleId": decision.rule_id,
        "reason": decision.reason,
        "baselineVerified": False,
        "warning": decision.warning,
        # Compatibility guidance only.  It is deliberately not named
        # ``remediation``: that key is preflight blocker presentation and must
        # never appear in a PLAN payload.
        "nextStep": decision.remediation,
    }


__all__ = [
    "FloatAbiDecision",
    "float_abi_evidence",
    "resolve_float_abi",
]
