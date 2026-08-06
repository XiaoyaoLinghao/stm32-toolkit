"""Guarded ARMCC conversion planning and apply (STM32TK-0303).

Public contracts: ``plan_keil_conversion`` (read-only, deterministic) and
``apply_keil_conversion`` (guarded, atomic, rollback-capable) plus the
immutable plan models and the stable ``MigrationPlanError``.
"""

from stm32_toolkit.migration.apply import apply_keil_conversion
from stm32_toolkit.migration.model import (
    FilePatch,
    FixedSectionRequirement,
    GitBaseline,
    MigrationBlocker,
    MigrationInput,
    MigrationPlan,
    MigrationPlanError,
)
from stm32_toolkit.migration.planner import plan_keil_conversion

__all__ = [
    "apply_keil_conversion",
    "plan_keil_conversion",
    "FilePatch",
    "FixedSectionRequirement",
    "GitBaseline",
    "MigrationBlocker",
    "MigrationInput",
    "MigrationPlan",
    "MigrationPlanError",
]
