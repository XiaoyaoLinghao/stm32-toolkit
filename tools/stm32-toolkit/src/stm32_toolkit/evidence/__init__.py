"""Immutable canonical evidence records (STM32TK-0601)."""

from .gc import GcStoreChangedError
from .model import (
    EVIDENCE_CORRUPT,
    EVIDENCE_INVALID,
    EVIDENCE_LIMIT_EXCEEDED,
    EVIDENCE_PATH_UNSAFE,
    ArtifactRef,
    EvidenceEnvelope,
    EvidenceIdentity,
    EvidenceIdentityContext,
    EvidenceValidationError,
    calculate_evidence_id,
    canonical_json_bytes,
)

__all__ = [
    "ArtifactRef",
    "EvidenceEnvelope",
    "EvidenceIdentity",
    "EvidenceIdentityContext",
    "EvidenceValidationError",
    "EVIDENCE_CORRUPT",
    "EVIDENCE_INVALID",
    "EVIDENCE_LIMIT_EXCEEDED",
    "EVIDENCE_PATH_UNSAFE",
    "GcStoreChangedError",
    "calculate_evidence_id",
    "canonical_json_bytes",
]
