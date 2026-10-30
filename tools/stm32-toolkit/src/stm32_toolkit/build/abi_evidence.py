"""Bounded conversion-report float-ABI provenance for build evidence.

The migration conversion report is the only authority for *reported* float
ABI provenance.  This leaf reads that one fixed project-local report without
following links or reparse points, validates its exact closed object,
reconstructs the deterministic resolver output from the recorded raw Keil
fields, and checks the result against the actual project model.  A missing
report is simply optional evidence; a present report that is unsafe,
malformed, mismatched, blocked or already verified is reported as honestly
unavailable with a fixed warning.  No source file, compiler flag, project
model or hardware state is changed, no exception text is retained, and the
original binary ABI always stays unverified.
"""

from __future__ import annotations

import json
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from stm32_toolkit.generation.managed_files import (
    _reject_duplicate_json_keys,
    sha256_hex,
)

if TYPE_CHECKING:  # pragma: no cover - typing only, never imported at runtime
    from stm32_toolkit.project_model import ProjectModel

#: The one fixed, project-relative conversion report this slice may read.
CONVERSION_REPORT_PATH = "artifacts/migration/conversion-report.json"

#: Bounded read: at most 1 MiB of report bytes is ever examined.
CONVERSION_REPORT_LIMIT_BYTES = 1024 * 1024

#: Fixed warnings.  They carry no exception text and no recorded values.
UNAVAILABLE_WARNING = (
    "Float ABI provenance is unavailable: artifacts/migration/conversion-report.json"
    " does not provide valid project-consistent ABI evidence, so no ABI"
    " provenance was recorded and binary float compatibility remains unproven."
)
CHANGED_WARNING = (
    "Float ABI provenance is unavailable: the conversion report changed while"
    " the build ran, so no ABI provenance was recorded for these outputs."
)

#: Exact resolved evidence fields, in the resolver's deterministic order.
FLOAT_ABI_RESOLVED_FIELDS = (
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
)

#: Exact identity/receipt evidence fields: the resolved object plus capture.
FLOAT_ABI_EVIDENCE_FIELDS = FLOAT_ABI_RESOLVED_FIELDS + (
    "reportPath",
    "reportSha256",
)

#: Closed, non-blocked origins.  ``blocked`` evidence is never admitted.
_ALLOWED_ORIGINS = frozenset({"inferred", "declared", "not-applicable"})
_ALLOWED_ABIS = frozenset({"soft", "softfp", "hard"})
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

_REPARSE_POINT = 0x400

_STATUS_ABSENT = "absent"
_STATUS_OK = "ok"
_STATUS_UNSAFE = "unsafe"
_STATUS_INVALID = "invalid"


def _optional_text(value: object) -> bool:
    return value is None or isinstance(value, str)


def _validate_fields(value: object, fields: tuple[str, ...]) -> dict[str, object]:
    """Return a fresh ordered copy of one closed evidence object or raise.

    ``TypeError`` marks a non-object; ``ValueError`` marks a closed-shape,
    type or semantic violation.  Forged nulls, JSON booleans, blocked
    evidence, already-verified evidence and cross-schema extras never pass.
    """
    if not isinstance(value, dict):
        raise TypeError("floatAbi evidence must be an object")
    if set(value) != set(fields):
        raise ValueError("floatAbi evidence fields do not match the closed shape")
    compiler = value["compiler"]
    cpu = value["cpu"]
    if not isinstance(compiler, str) or not compiler:
        raise ValueError("floatAbi compiler must be a non-empty string")
    if not isinstance(cpu, str) or not cpu:
        raise ValueError("floatAbi cpu must be a non-empty string")
    for field in (
        "compilerVersion",
        "rawFpu",
        "rawFloatAbi",
        "rawRvdsVp",
        "fpu",
        "selectedAbi",
        "nextStep",
    ):
        if not _optional_text(value[field]):
            raise ValueError(f"floatAbi {field} must be a string or null")
    selected_abi = value["selectedAbi"]
    if isinstance(selected_abi, str) and selected_abi not in _ALLOWED_ABIS:
        raise ValueError("floatAbi selectedAbi is outside the closed literal set")
    origin = value["origin"]
    if not isinstance(origin, str) or origin not in _ALLOWED_ORIGINS:
        raise ValueError("floatAbi origin is not admitted evidence")
    for field in ("ruleId", "reason", "warning"):
        if not isinstance(value[field], str) or not value[field]:
            raise ValueError(f"floatAbi {field} must be a non-empty string")
    if value["baselineVerified"] is not False:
        raise ValueError("floatAbi baselineVerified must be exactly false")
    if "reportPath" in value:
        if value["reportPath"] != CONVERSION_REPORT_PATH:
            raise ValueError("floatAbi reportPath is not the fixed report path")
        report_sha = value["reportSha256"]
        if not isinstance(report_sha, str) or _SHA256_RE.fullmatch(report_sha) is None:
            raise ValueError("floatAbi reportSha256 must be a lowercase SHA-256")
    return {field: value[field] for field in fields}


def validate_float_abi_resolved(value: object) -> dict[str, object]:
    """Validate the 14-key resolver object as recorded in the report.

    Shape alone is not enough: every recorded decision field must be exactly
    what the deterministic resolver reconstructs from the recorded raw fields.
    """
    recorded = _validate_fields(value, FLOAT_ABI_RESOLVED_FIELDS)
    _require_resolver_consistency(recorded)
    return recorded


def validate_float_abi_evidence(value: object) -> dict[str, object]:
    """Validate the 16-key identity/receipt object (resolved plus capture).

    The closed capture path/digest and the full resolver semantics are both
    required, so a relabelled or hand-edited decision never validates.
    """
    evidence = _validate_fields(value, FLOAT_ABI_EVIDENCE_FIELDS)
    _require_resolver_consistency(evidence)
    return evidence


@dataclass(frozen=True)
class _ResolverInspection:
    """Minimal inspection adapter for the deterministic resolver."""

    compiler: str
    compiler_version: str | None
    cpu: str
    fpu: str | None
    float_abi: str | None
    rvds_vp: str | None


def _resolver_evidence(recorded: dict[str, object]) -> dict[str, object]:
    """Reconstruct the resolver's 14-key object from recorded raw fields."""
    from stm32_toolkit.migration.float_abi import float_abi_evidence

    inspection = _ResolverInspection(
        compiler=recorded["compiler"],  # type: ignore[arg-type]
        compiler_version=recorded["compilerVersion"],  # type: ignore[arg-type]
        cpu=recorded["cpu"],  # type: ignore[arg-type]
        fpu=recorded["rawFpu"],  # type: ignore[arg-type]
        float_abi=recorded["rawFloatAbi"],  # type: ignore[arg-type]
        rvds_vp=recorded["rawRvdsVp"],  # type: ignore[arg-type]
    )
    return dict(float_abi_evidence(inspection))


def _require_resolver_consistency(recorded: dict[str, object]) -> None:
    """Require the recorded decision to match the deterministic resolver.

    The raw Keil fields are the resolver's own inputs, so its full 14-field
    output is reconstructed here and every recorded field must agree.  This
    is a leaf helper: it never calls back into the public validators, and
    resolver failures become the same fixed ``ValueError`` as a mismatch.
    """
    try:
        resolved = _resolver_evidence(recorded)
    except (AttributeError, ImportError, KeyError, TypeError, ValueError):
        raise ValueError(
            "floatAbi evidence is not deterministically resolvable"
        ) from None
    if set(resolved) != set(FLOAT_ABI_RESOLVED_FIELDS):
        raise ValueError("floatAbi resolver output is not the closed shape")
    for field in FLOAT_ABI_RESOLVED_FIELDS:
        if resolved[field] != recorded[field]:
            raise ValueError(
                f"floatAbi {field} does not match the deterministic resolver"
            )


def _matches_project(recorded: dict[str, object], model: "ProjectModel") -> bool:
    """Require the recorded FPU/ABI/CPU to agree with the actual project."""
    target = getattr(model, "target", None)
    if target is None:
        return False
    core = getattr(target, "core", None)
    if not isinstance(core, str) or not core:
        return False
    if recorded["fpu"] != getattr(target, "fpu", None):
        return False
    if recorded["selectedAbi"] != getattr(target, "float_abi", None):
        return False
    cpu = recorded["cpu"]
    return isinstance(cpu, str) and cpu.casefold() == core.casefold()


def _is_redirect(info: os.stat_result) -> bool:
    """True for a symlink or a Windows reparse point (junction) component."""
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0) & _REPARSE_POINT
    )


def _read_report(root: Path) -> tuple[str, bytes | None]:
    """Classify and read the fixed report without following any redirect.

    Every parent component must be an ordinary directory and the leaf an
    ordinary regular file, inspected with ``lstat`` before it is opened.  A
    missing ordinary component is true absence; anything else is unsafe.  The
    read itself is bounded to one byte past the limit so oversize reports are
    rejected rather than truncated.
    """
    parts = CONVERSION_REPORT_PATH.split("/")
    current = root
    for part in parts[:-1]:
        current = current / part
        try:
            info = os.lstat(current)
        except FileNotFoundError:
            return _STATUS_ABSENT, None
        except OSError:
            return _STATUS_UNSAFE, None
        if _is_redirect(info) or not stat.S_ISDIR(info.st_mode):
            return _STATUS_UNSAFE, None
    leaf = current / parts[-1]
    try:
        info = os.lstat(leaf)
    except FileNotFoundError:
        return _STATUS_ABSENT, None
    except OSError:
        return _STATUS_UNSAFE, None
    if _is_redirect(info) or not stat.S_ISREG(info.st_mode):
        return _STATUS_UNSAFE, None
    try:
        with leaf.open("rb") as handle:
            data = handle.read(CONVERSION_REPORT_LIMIT_BYTES + 1)
    except OSError:
        return _STATUS_UNSAFE, None
    if len(data) > CONVERSION_REPORT_LIMIT_BYTES:
        return _STATUS_INVALID, None
    return _STATUS_OK, data


def capture_float_abi_evidence(
    root: Path, model: "ProjectModel"
) -> tuple[dict[str, object] | None, tuple[str, ...]]:
    """Capture validated float-ABI provenance from the fixed report.

    Returns ``(evidence, warnings)``.  A truly missing report is optional
    evidence: ``(None, ())``.  A present report that is unsafe, unreadable,
    malformed, structurally invalid, resolver-mismatched or model-mismatched
    yields ``(None, (UNAVAILABLE_WARNING,))``.  Valid evidence returns the
    recorded resolver warning so a fresh build exposes the same ABI warning as
    a reused one.  Never raises and never retains exception text or recorded
    values in a warning.
    """
    status, data = _read_report(root)
    if status == _STATUS_ABSENT:
        return None, ()
    if status != _STATUS_OK or data is None:
        return None, (UNAVAILABLE_WARNING,)
    try:
        document = json.loads(
            data.decode("utf-8"), object_pairs_hook=_reject_duplicate_json_keys
        )
    except (UnicodeDecodeError, ValueError, TypeError, RecursionError):
        return None, (UNAVAILABLE_WARNING,)
    if not isinstance(document, dict) or "floatAbi" not in document:
        return None, (UNAVAILABLE_WARNING,)
    try:
        recorded = validate_float_abi_resolved(document["floatAbi"])
    except (TypeError, ValueError):
        return None, (UNAVAILABLE_WARNING,)
    if not _matches_project(recorded, model):
        return None, (UNAVAILABLE_WARNING,)
    evidence = dict(recorded)
    evidence["reportPath"] = CONVERSION_REPORT_PATH
    evidence["reportSha256"] = sha256_hex(data)
    return evidence, (str(recorded["warning"]),)


__all__ = [
    "CHANGED_WARNING",
    "CONVERSION_REPORT_LIMIT_BYTES",
    "CONVERSION_REPORT_PATH",
    "FLOAT_ABI_EVIDENCE_FIELDS",
    "FLOAT_ABI_RESOLVED_FIELDS",
    "UNAVAILABLE_WARNING",
    "capture_float_abi_evidence",
    "validate_float_abi_evidence",
    "validate_float_abi_resolved",
]
