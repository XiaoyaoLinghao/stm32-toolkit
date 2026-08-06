"""Managed GCC/CMake and VS Code configuration generation (STM32TK-0304).

Public contracts: ``plan_project_configuration`` (read-only, deterministic)
and ``apply_project_configuration`` (guarded, atomic, rollback-capable) plus
the immutable plan models and the stable ``GenerationError``.
"""

from stm32_toolkit.generation.configure import (
    apply_project_configuration,
    plan_project_configuration,
)
from stm32_toolkit.generation.managed_files import (
    GenerationBlocker,
    GenerationError,
    GeneratedFile,
    GenerationInput,
    GenerationPlan,
    ManagedFileRecord,
)

__all__ = [
    "GenerationError",
    "GenerationInput",
    "ManagedFileRecord",
    "GeneratedFile",
    "GenerationBlocker",
    "GenerationPlan",
    "plan_project_configuration",
    "apply_project_configuration",
]
