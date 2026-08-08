"""Public STM32 Toolkit package contracts."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .monitor_observation import (
        MonitorObservationError,
        MonitorObservationRequest,
        MonitorObservationSeams,
        MonitorObservationSession,
        open_monitor_observation,
    )

__version__ = "0.4.0"

__all__ = [
    "MonitorObservationError",
    "MonitorObservationRequest",
    "MonitorObservationSeams",
    "MonitorObservationSession",
    "open_monitor_observation",
]

_LAZY_EXPORTS = frozenset(__all__)


def __getattr__(name: str) -> object:
    if type(name) is not str or name not in _LAZY_EXPORTS:
        raise AttributeError(f"module {__name__!r} has no such public attribute")

    from . import monitor_observation

    value = getattr(monitor_observation, name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | _LAZY_EXPORTS)
