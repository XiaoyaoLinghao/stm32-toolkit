"""Bounded ARM GNU build, MAP validation, and firmware identity (STM32TK-0305).

Public contracts: ``BuildRequest``, ``MemoryUsage``, ``FirmwareIdentity``,
``BuildReport``, and ``run_build``.
"""

from stm32_toolkit.build.model import (
    BuildError,
    BuildReport,
    BuildRequest,
    FirmwareIdentity,
    MemoryUsage,
    build_error,
)
from stm32_toolkit.build.runner import run_build

__all__ = [
    "BuildRequest",
    "MemoryUsage",
    "FirmwareIdentity",
    "BuildReport",
    "run_build",
    "BuildError",
    "build_error",
]
