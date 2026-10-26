"""Shared optional-Git source provenance forms.

A source identity has exactly two mutually exclusive provenance forms:

* the legacy form records a real Git commit and strict dirty boolean;
* the snapshot form records a real input snapshot digest, the
  ``input-snapshot-v1`` discriminator, explicit null Git fields and the same
  bounded ``{status, code, rule}`` unavailable-Git record the build already
  emits.

Missing Git is an ordinary supported operation.  It is never represented by a
synthetic commit, a false "clean" flag or a zero snapshot digest.  The generic
``revision`` used by authorizations is the recorded Git commit for the legacy
form and the explicitly namespaced ``input-snapshot-v1:<snapshot>`` content
revision for the snapshot form; a namespaced value is never a Git field.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import re
from types import MappingProxyType
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:  # pragma: no cover - typing only, avoids an import cycle
    from stm32_toolkit.build.identity import GitEvidence, GitUnavailableEvidence

#: The shared provenance literals live in this low-level validation leaf so
#: that importing this module never initializes the ``stm32_toolkit.build``
#: package.  ``stm32_toolkit.build.model`` imports and re-exports the same
#: objects for its historical callers.
SOURCE_BASELINE_INPUT_SNAPSHOT = "input-snapshot-v1"
GIT_DIAGNOSTIC_UNAVAILABLE = "unavailable"
BUILD_GIT_INVALID = "BUILD_GIT_INVALID"

GIT_DIAGNOSTIC_RULES = frozenset({"head", "status"})
GIT_EVIDENCE_FIELDS = frozenset({"status", "code", "rule"})
SNAPSHOT_CONTENT_REVISION_PREFIX = f"{SOURCE_BASELINE_INPUT_SNAPSHOT}:"
#: The exact closed wire fields of a snapshot source binding.  Once a binding
#: carries either marker below, all three are required together.  A legacy Git
#: binding still records ``input_snapshot_sha256``; that field alone never
#: discriminates the snapshot form.
SNAPSHOT_BINDING_FIELDS = frozenset(
    {"input_snapshot_sha256", "source_baseline", "git_evidence"}
)
#: The two wire fields whose presence alone marks the snapshot form.  The
#: shared ``input_snapshot_sha256`` is deliberately not a marker.
SNAPSHOT_MARKER_FIELDS = frozenset({"source_baseline", "git_evidence"})

_GIT_SHA1 = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def unavailable_git_evidence(value: object) -> dict[str, str]:
    """Return a fresh copy of one bounded unavailable-Git record.

    Only the fixed public codes and rules emitted by ``build.identity`` are
    accepted.  Anything else, including extra keys, non-strings or unknown
    rules, raises ``ValueError`` so a caller can fail closed before effects.
    """
    if not isinstance(value, Mapping) or set(value) != GIT_EVIDENCE_FIELDS:
        raise ValueError("Git unavailable evidence is not a closed bounded record")
    status = value["status"]
    code = value["code"]
    rule = value["rule"]
    if (
        status != GIT_DIAGNOSTIC_UNAVAILABLE
        or code != BUILD_GIT_INVALID
        or not isinstance(rule, str)
        or rule not in GIT_DIAGNOSTIC_RULES
    ):
        raise ValueError("Git unavailable evidence is not a closed bounded record")
    return {"status": status, "code": code, "rule": rule}


def is_unavailable_git_evidence(value: object) -> bool:
    """True only for the exact bounded unavailable-Git record."""
    try:
        unavailable_git_evidence(value)
    except ValueError:
        return False
    return True


def snapshot_content_revision(input_snapshot_sha256: object) -> str:
    """The namespaced generic revision for one real input snapshot."""
    if not isinstance(input_snapshot_sha256, str) or _SHA256.fullmatch(
        input_snapshot_sha256
    ) is None:
        raise ValueError("input_snapshot_sha256 must be a lowercase SHA-256")
    return SNAPSHOT_CONTENT_REVISION_PREFIX + input_snapshot_sha256


def source_revision(
    *,
    git_commit: object,
    source_baseline: object,
    input_snapshot_sha256: object,
) -> str:
    """Derive the one generic revision admitted for a provenance form.

    The legacy form's generic revision is the recorded Git commit and must be
    a real lowercase 40-digit SHA-1: a namespaced snapshot value may never be
    mistaken for a commit.  The snapshot form's revision is the explicitly
    namespaced content revision bound to the given input snapshot digest.
    """
    if source_baseline is None:
        if not isinstance(git_commit, str) or _GIT_SHA1.fullmatch(git_commit) is None:
            raise ValueError("legacy provenance requires a lowercase Git SHA-1")
        return git_commit
    if source_baseline != SOURCE_BASELINE_INPUT_SNAPSHOT:
        raise ValueError("source_baseline is invalid")
    if git_commit is not None:
        raise ValueError("snapshot provenance requires null Git fields")
    return snapshot_content_revision(input_snapshot_sha256)


def is_snapshot_content_revision(value: object) -> bool:
    """True only for a value shaped as a namespaced snapshot content revision."""
    return isinstance(value, str) and value.startswith(SNAPSHOT_CONTENT_REVISION_PREFIX)


def snapshot_provenance(
    *,
    revision: object,
    input_snapshot_sha256: object,
    source_baseline: object,
    git_evidence: object,
) -> "SourceProvenance":
    """Validate one snapshot binding whose generic revision names its snapshot.

    A snapshot binding carries the explicit baseline, the bounded
    unavailable-Git pair and null Git state; its generic revision must be the
    exact namespaced content revision of the same snapshot.  Any partial or
    mixed form raises ``ValueError`` so a caller can fail closed before
    effects.
    """
    provenance = SourceProvenance(
        git_commit=None,
        git_dirty=None,
        input_snapshot_sha256=cast(str, input_snapshot_sha256),
        source_baseline=cast(str, source_baseline),
        git_evidence=cast(Mapping[str, str], git_evidence),
    )
    if revision != provenance.revision:
        raise ValueError("revision does not name the bound input snapshot")
    return provenance


@dataclass(frozen=True)
class SourceProvenance:
    """One validated optional-Git provenance form plus its content digest."""

    git_commit: str | None
    git_dirty: bool | None
    input_snapshot_sha256: str
    source_baseline: str | None = None
    git_evidence: Mapping[str, str] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.input_snapshot_sha256, str) or _SHA256.fullmatch(
            self.input_snapshot_sha256
        ) is None:
            raise ValueError("input_snapshot_sha256 must be a lowercase SHA-256")
        if self.source_baseline is None and self.git_evidence is None:
            if (
                not isinstance(self.git_commit, str)
                or _GIT_SHA1.fullmatch(self.git_commit) is None
            ):
                raise ValueError("git_commit must be a lowercase Git SHA-1")
            if type(self.git_dirty) is not bool:
                raise ValueError("git_dirty must be a boolean")
            return
        if self.source_baseline != SOURCE_BASELINE_INPUT_SNAPSHOT:
            raise ValueError("source_baseline is invalid")
        if self.git_commit is not None or self.git_dirty is not None:
            raise ValueError("snapshot provenance requires null Git fields")
        object.__setattr__(
            self,
            "git_evidence",
            MappingProxyType(unavailable_git_evidence(self.git_evidence)),
        )

    @property
    def is_snapshot(self) -> bool:
        return self.source_baseline is not None

    @property
    def revision(self) -> str:
        return source_revision(
            git_commit=self.git_commit,
            source_baseline=self.source_baseline,
            input_snapshot_sha256=self.input_snapshot_sha256,
        )

    def git_evidence_document(self) -> dict[str, str] | None:
        if self.git_evidence is None:
            return None
        return dict(self.git_evidence)

    @classmethod
    def from_collected_git(
        cls,
        collected: "GitEvidence | GitUnavailableEvidence",
        input_snapshot_sha256: str,
    ) -> "SourceProvenance":
        """Map the bounded build collector result onto one provenance form."""
        from stm32_toolkit.build.identity import (
            GitEvidence,
            GitUnavailableEvidence,
        )

        if isinstance(collected, GitUnavailableEvidence):
            return cls(
                git_commit=None,
                git_dirty=None,
                input_snapshot_sha256=input_snapshot_sha256,
                source_baseline=SOURCE_BASELINE_INPUT_SNAPSHOT,
                git_evidence=collected.to_dict(),
            )
        if isinstance(collected, GitEvidence):
            return cls(
                git_commit=collected.head,
                git_dirty=collected.dirty,
                input_snapshot_sha256=input_snapshot_sha256,
            )
        raise TypeError("Git collector result is not a bounded provenance value")

    @classmethod
    def from_firmware_facts(cls, facts: object) -> "SourceProvenance":
        """Read the provenance pair from one admitted firmware fact record."""
        return cls(
            git_commit=getattr(facts, "git_commit", None),
            git_dirty=getattr(facts, "git_dirty", None),
            input_snapshot_sha256=getattr(facts, "input_snapshot_sha256", None),
            source_baseline=getattr(facts, "source_baseline", None),
            git_evidence=getattr(facts, "git_evidence", None),
        )


__all__ = [
    "BUILD_GIT_INVALID",
    "GIT_DIAGNOSTIC_RULES",
    "GIT_DIAGNOSTIC_UNAVAILABLE",
    "GIT_EVIDENCE_FIELDS",
    "SNAPSHOT_BINDING_FIELDS",
    "SNAPSHOT_CONTENT_REVISION_PREFIX",
    "SNAPSHOT_MARKER_FIELDS",
    "SOURCE_BASELINE_INPUT_SNAPSHOT",
    "SourceProvenance",
    "is_snapshot_content_revision",
    "is_unavailable_git_evidence",
    "snapshot_content_revision",
    "snapshot_provenance",
    "source_revision",
    "unavailable_git_evidence",
]
