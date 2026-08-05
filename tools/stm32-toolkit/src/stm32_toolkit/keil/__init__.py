"""Read-only Keil inspection and AXF/MAP baseline capture."""

from stm32_toolkit.keil.baseline import capture_keil_baseline
from stm32_toolkit.keil.model import (
    KeilArtifactEvidence,
    KeilBaseline,
    KeilEvidence,
    KeilFinding,
    KeilInspection,
    KeilInspectionError,
    KeilInputDigest,
    KeilMemoryRegion,
    KeilOutputSpec,
    KeilProgramSize,
    KeilScopedOptions,
    KeilSectionEvidence,
    KeilSource,
    KeilSymbolEvidence,
    KeilWarning,
)
from stm32_toolkit.keil.uvprojx import inspect_keil

__all__ = [
    "capture_keil_baseline",
    "inspect_keil",
    "KeilArtifactEvidence",
    "KeilBaseline",
    "KeilEvidence",
    "KeilFinding",
    "KeilInspection",
    "KeilInspectionError",
    "KeilInputDigest",
    "KeilMemoryRegion",
    "KeilOutputSpec",
    "KeilProgramSize",
    "KeilScopedOptions",
    "KeilSectionEvidence",
    "KeilSource",
    "KeilSymbolEvidence",
    "KeilWarning",
]
