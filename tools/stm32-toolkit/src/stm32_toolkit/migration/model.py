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
from stm32_toolkit.extra_regions import ExtraRegion
from stm32_toolkit.keil import KeilInspection
from stm32_toolkit.memory_layout import MemoryLayout, MemoryLayoutResolution
from stm32_toolkit.migration.float_abi import float_abi_evidence

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


#: Trusted internal remediation hints on ``MigrationBlocker``.  They are set
#: only by rule code that already knows the bounded cause; presentation code
#: compares these constants and never parses a path, message, or evidence.
BLOCKER_HINT_DEPENDENCY_ENCODING = "dependency-encoding"
BLOCKER_HINT_DEPENDENCY_PATH = "dependency-path"


@dataclass(frozen=True)
class MigrationBlocker:
    code: str
    rule_id: str
    path: str
    line: int
    column: int
    evidence: str
    message: str
    #: Optional internal classification hint for remediation presentation.  It
    #: is intentionally omitted from ``to_dict`` and from plan identity, so the
    #: public blocker contract and apply replanning bytes are unchanged.
    diagnostic: str | None = None

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
class IncludeMerge:
    """Reviewed evidence for one group/file include-only scope directory.

    ``decision`` is ``added`` when the directory is newly appended to the
    target include search list, or ``already-present`` when the same physical
    directory is already exposed (the original spelling is retained).
    ``inventory_sha256``/``inventory_files`` record the bounded directory
    inventory for an added directory so a fresh apply replan detects any
    content, addition, or removal that could invalidate the conflict decision;
    they are ``None`` for an already-present directory.
    """

    scope: str  # group or file
    owner: str  # group name or root-relative source path
    path: str  # normalized root-relative directory ("." for the root)
    decision: str  # added or already-present
    inventory_sha256: str | None
    inventory_files: int | None

    def to_dict(self) -> dict[str, object]:
        return {
            "scope": self.scope,
            "owner": self.owner,
            "path": self.path,
            "decision": self.decision,
            "inventory_sha256": self.inventory_sha256,
            "inventory_files": self.inventory_files,
        }

    def to_report_dict(self) -> dict[str, object]:
        """Camel-case presentation used by preflight analysis and the report."""
        return {
            "scope": self.scope,
            "owner": self.owner,
            "path": self.path,
            "decision": self.decision,
            "inventorySha256": self.inventory_sha256,
            "inventoryFiles": self.inventory_files,
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
class StartupOptions:
    """Immutable, reviewed CMSIS startup-generation request.

    ``strategy`` is either absent or ``generate-cmsis-gcc``.  ``source`` is
    absent only when exactly one included non-empty ARMCC assembly source is
    an unambiguous startup candidate.
    """

    strategy: str
    source: str | None

    def to_dict(self) -> dict[str, object]:
        return {"strategy": self.strategy, "source": self.source}


@dataclass(frozen=True)
class StartupVectorEntry:
    index: int
    symbol: str | None
    reserved: bool
    line: int

    def to_dict(self) -> dict[str, object]:
        return {
            "index": self.index,
            "symbol": self.symbol,
            "reserved": self.reserved,
            "line": self.line,
        }


@dataclass(frozen=True)
class StartupHandler:
    name: str
    kind: str  # reset, individual, or default-alias
    line: int

    def to_dict(self) -> dict[str, object]:
        return {"name": self.name, "kind": self.kind, "line": self.line}


@dataclass(frozen=True)
class StartupDiagnostic:
    code: str
    path: str
    line: int
    column: int
    evidence: str
    message: str

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "path": self.path,
            "line": self.line,
            "column": self.column,
            "evidence": self.evidence,
            "message": self.message,
        }


@dataclass(frozen=True)
class StartupAnalysis:
    """Read-only evidence for one supported ARMCC startup analysis.

    ``status`` is ``ready`` when a GCC startup file may be generated, or
    ``unsupported`` when one or more portable diagnostics explain why not.
    Every field is JSON-safe and contains no host paths.
    """

    strategy: str
    status: str
    source_path: str
    source_sha256: str
    source_size: int
    core: str | None
    stack_size: int | None
    heap_size: int | None
    vector_count: int
    reserved_count: int
    vectors: tuple[StartupVectorEntry, ...]
    handlers: tuple[StartupHandler, ...]
    reset_pattern: str
    generated_path: str | None
    generated_sha256: str | None
    generated_size: int | None
    warnings: tuple[str, ...]
    diagnostics: tuple[StartupDiagnostic, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "strategy": self.strategy,
            "status": self.status,
            "source_path": self.source_path,
            "source_sha256": self.source_sha256,
            "source_size": self.source_size,
            "core": self.core,
            "stack_size": self.stack_size,
            "heap_size": self.heap_size,
            "vector_count": self.vector_count,
            "reserved_count": self.reserved_count,
            "vectors": [entry.to_dict() for entry in self.vectors],
            "handlers": [handler.to_dict() for handler in self.handlers],
            "reset_pattern": self.reset_pattern,
            "generated_path": self.generated_path,
            "generated_sha256": self.generated_sha256,
            "generated_size": self.generated_size,
            "warnings": list(self.warnings),
            "diagnostics": [diagnostic.to_dict() for diagnostic in self.diagnostics],
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
    startup: StartupAnalysis | None = None
    startup_options: StartupOptions | None = None
    #: The explicit reviewed layout request; ``None`` keeps the implicit
    #: single-Flash/single-RAM behavior (or a selection requirement).
    memory_layout: MemoryLayout | None = None
    #: Decision evidence exposed to preflight/plan consumers.  Only the
    #: explicit request itself participates in the plan identity.
    memory_layout_resolution: MemoryLayoutResolution | None = None
    #: Reviewed include-only scope merges.  Empty for plans without a merged
    #: scoped directory, so historical plan identities stay byte-identical.
    include_merges: tuple[IncludeMerge, ...] = ()
    #: Reviewed explicit external-RAM request.  Empty for plans without one, so
    #: historical plan bytes and identities stay unchanged.
    extra_regions: tuple[ExtraRegion, ...] = ()

    def __post_init__(self) -> None:
        # Ignored-compatible observations are carried privately; they are not
        # public contract fields, are not serialized, and are not part of the
        # canonical plan-ID payload.
        object.__setattr__(self, "_ignored", ())

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "plan_version": self.plan_version,
            "plan_id": self.plan_id,
            "inspection_sha256": self.inspection_sha256,
            "git": self.git.to_dict(),
            "inputs": [entry.to_dict() for entry in self.inputs],
            "patches": [patch.to_dict() for patch in self.patches],
            "fixed_sections": [section.to_dict() for section in self.fixed_sections],
            "blockers": [blocker.to_dict() for blocker in self.blockers],
            # Derived from the bound inspection; never stored separately, so a
            # caller cannot forge evidence independently of the inspection.
            "floatAbi": float_abi_evidence(self.inspection),
        }
        if self.startup is not None:
            payload["startup"] = self.startup.to_dict()
        if self.startup_options is not None:
            payload["startup_options"] = self.startup_options.to_dict()
        if self.memory_layout_resolution is not None:
            payload["memory_layout"] = self.memory_layout_resolution.to_dict()
        if self.include_merges:
            payload["include_merges"] = [merge.to_dict() for merge in self.include_merges]
        if self.extra_regions:
            payload["extra_regions"] = [
                region.to_dict() for region in self.extra_regions
            ]
        return payload


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
    blockers, the derived float-ABI evidence, the Toolkit version, and the
    SHA-256 of the proposed concatenated patch content.
    """
    patch_content = b"".join(patch.unified_diff.encode("utf-8") for patch in plan.patches)
    payload: dict[str, object] = {
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
        "floatAbi": float_abi_evidence(plan.inspection),
        "toolkit_version": __version__,
        "patch_content_sha256": hashlib.sha256(patch_content).hexdigest(),
    }
    if plan.startup is not None:
        payload["startup"] = plan.startup.to_dict()
    if plan.startup_options is not None:
        payload["startup_options"] = plan.startup_options.to_dict()
    # An omitted layout is not added, so implicit single-region plans keep
    # their historical identity payload.
    if plan.memory_layout is not None:
        payload["memory_layout"] = plan.memory_layout.to_dict()
    # Scope evidence participates only when a scoped include directory was
    # actually analyzed, so no-scope plans keep their historical identity.
    if plan.include_merges:
        payload["include_merges"] = [merge.to_dict() for merge in plan.include_merges]
    # Only a non-empty reviewed request participates, so historical no-extra
    # plan identities stay byte-identical.
    if plan.extra_regions:
        payload["extra_regions"] = [
            region.to_dict() for region in plan.extra_regions
        ]
    return payload


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
