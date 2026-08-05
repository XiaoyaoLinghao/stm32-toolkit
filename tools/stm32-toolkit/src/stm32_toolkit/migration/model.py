"""Frozen public models and stable errors for ARMCC conversion planning.

This module performs no filesystem, subprocess, or network I/O.  It owns
immutable containers, JSON-safe serialization, canonical hashing payloads,
portable-path validation, and stable error construction.  Every public
container is a frozen dataclass; tuples are used instead of lists and
``to_dict()`` returns a fresh JSON-safe mapping that omits ``project_root``,
the inspection object, and raw before/after bytes.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

from stm32_toolkit import __version__
from stm32_toolkit.keil import KeilInspection

_PLAN_LIMIT_BYTES = 64 * 1024 * 1024

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_FULL_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_DRIVE_PREFIX_RE = re.compile(r"^[A-Za-z]:")


class MigrationPlanError(Exception):
    """A stable planning failure carrying a code and frozen details.

    ``details`` never contains host exception text, absolute paths, raw Git
    output, source bytes, or environment values.
    """

    def __init__(
        self,
        code: str,
        message: str,
        details: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = dict(details if details is not None else {})


def _raise(code: str, message: str, details: dict[str, object]) -> MigrationPlanError:
    return MigrationPlanError(code, message, details)


# ---------------------------------------------------------------------------
# public frozen models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MigrationInput:
    path: str
    sha256: str
    size: int

    def to_dict(self) -> dict[str, object]:
        return {"path": self.path, "sha256": self.sha256, "size": self.size}


@dataclass(frozen=True)
class MigrationBlocker:
    code: str
    rule_id: str
    path: str
    line: int
    column: int
    evidence: str
    message: str

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "rule_id": self.rule_id,
            "path": self.path,
            "line": self.line,
            "column": self.column,
            "evidence": self.evidence,
            "message": self.message,
        }


@dataclass(frozen=True)
class FixedSectionRequirement:
    section: str
    address: int
    source_path: str
    line: int
    symbol: str

    def to_dict(self) -> dict[str, object]:
        return {
            "section": self.section,
            "address": self.address,
            "source_path": self.source_path,
            "line": self.line,
            "symbol": self.symbol,
        }


@dataclass(frozen=True)
class FilePatch:
    path: str
    before_sha256: str | None
    after_sha256: str
    before_size: int | None
    after_size: int
    rule_ids: tuple[str, ...]
    unified_diff: str
    before_bytes: bytes | None  # omitted from to_dict()
    after_bytes: bytes  # omitted from to_dict()

    def to_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "before_sha256": self.before_sha256,
            "after_sha256": self.after_sha256,
            "before_size": self.before_size,
            "after_size": self.after_size,
            "rule_ids": list(self.rule_ids),
            "unified_diff": self.unified_diff,
        }


@dataclass(frozen=True)
class GitBaseline:
    head: str
    root_marker: str  # always "."

    def to_dict(self) -> dict[str, object]:
        return {"head": self.head, "root_marker": self.root_marker}


@dataclass(frozen=True)
class IgnoredObservation:
    """An ARMCC construct observed as GCC-compatible and deliberately left byte-identical.

    Internal bookkeeping for the conversion report; not part of the public
    ``__init__`` exports.
    """

    rule_id: str
    path: str
    line: int
    column: int
    evidence: str

    def to_dict(self) -> dict[str, object]:
        return {
            "rule_id": self.rule_id,
            "path": self.path,
            "line": self.line,
            "column": self.column,
            "evidence": self.evidence,
        }


@dataclass(frozen=True)
class MigrationPlan:
    project_root: Path  # omitted from to_dict()
    inspection: KeilInspection  # omitted from to_dict()
    plan_version: int  # exactly 1
    plan_id: str  # lowercase SHA-256 hex
    inspection_sha256: str
    git: GitBaseline
    inputs: tuple[MigrationInput, ...]
    patches: tuple[FilePatch, ...]
    fixed_sections: tuple[FixedSectionRequirement, ...]
    blockers: tuple[MigrationBlocker, ...]

    def __post_init__(self) -> None:
        # Ignored-compatible observations are carried privately; they are not
        # public contract fields, are not serialized, and are not part of the
        # canonical plan-ID payload.
        object.__setattr__(self, "_ignored", ())

    def to_dict(self) -> dict[str, object]:
        return {
            "plan_version": self.plan_version,
            "plan_id": self.plan_id,
            "inspection_sha256": self.inspection_sha256,
            "git": self.git.to_dict(),
            "inputs": [entry.to_dict() for entry in self.inputs],
            "patches": [patch.to_dict() for patch in self.patches],
            "fixed_sections": [section.to_dict() for section in self.fixed_sections],
            "blockers": [blocker.to_dict() for blocker in self.blockers],
        }


# ---------------------------------------------------------------------------
# canonical hashing
# ---------------------------------------------------------------------------


def canonical_json_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def inspection_sha256_for(inspection: KeilInspection) -> str:
    """SHA-256 over canonical portable JSON of ``inspection.to_dict()``."""
    return hashlib.sha256(canonical_json_bytes(inspection.to_dict())).hexdigest()


def _plan_id_payload(plan: MigrationPlan) -> dict[str, object]:
    """Canonical JSON-safe payload for the deterministic plan ID.

    Excludes ``project_root``, the inspection object, ``plan_id`` itself,
    raw bytes, and unified diffs.  Includes the plan version, inspection
    hash, Git head, all input and patch metadata/digests, fixed sections,
    blockers, the Toolkit version, and the SHA-256 of the proposed
    concatenated patch content.
    """
    patch_content = b"".join(patch.unified_diff.encode("utf-8") for patch in plan.patches)
    return {
        "plan_version": plan.plan_version,
        "inspection_sha256": plan.inspection_sha256,
        "git": plan.git.to_dict(),
        "inputs": [entry.to_dict() for entry in plan.inputs],
        "patches": [
            {
                "path": patch.path,
                "before_sha256": patch.before_sha256,
                "after_sha256": patch.after_sha256,
                "before_size": patch.before_size,
                "after_size": patch.after_size,
                "rule_ids": list(patch.rule_ids),
            }
            for patch in plan.patches
        ],
        "fixed_sections": [section.to_dict() for section in plan.fixed_sections],
        "blockers": [blocker.to_dict() for blocker in plan.blockers],
        "toolkit_version": __version__,
        "patch_content_sha256": hashlib.sha256(patch_content).hexdigest(),
    }


def plan_id_for(plan: MigrationPlan) -> str:
    """Lowercase SHA-256 hex plan ID over the canonical payload."""
    return hashlib.sha256(canonical_json_bytes(_plan_id_payload(plan))).hexdigest()


# ---------------------------------------------------------------------------
# portable-path validation
# ---------------------------------------------------------------------------

#: Reasons returned by :func:`portable_path_error`; every one maps to the
#: caller's stable ``withinProjectRoot`` / ``portablePath`` rule.
_PATH_REASONS = ("empty", "nul", "absolute", "drivePrefix", "unc", "component")


def portable_path_error(path: object) -> str | None:
    """Return a stable reason when ``path`` is not a portable repository-relative path.

    Public paths use ``/``, are relative to the canonical project root, and
    contain no empty/``.``/``..`` component, drive prefix, UNC prefix, NUL,
    or absolute form.  ``None`` means the path is portable.
    """
    if not isinstance(path, str) or not path:
        return "empty"
    if "\x00" in path:
        return "nul"
    if path.startswith("/") or path.startswith("\\"):
        return "absolute"
    if _DRIVE_PREFIX_RE.match(path):
        return "drivePrefix"
    if path.startswith("\\\\") or path.startswith("//"):
        return "unc"
    for component in re.split(r"[/\\]", path):
        if not component:
            return "component"
        if component in (".", ".."):
            return "component"
    return None


def full_sha_error(value: object) -> str | None:
    if not isinstance(value, str) or not _FULL_SHA_RE.match(value):
        return "head"
    return None


def sha256_error(value: object) -> str | None:
    if not isinstance(value, str) or not _SHA256_RE.match(value):
        return "sha256"
    return None
