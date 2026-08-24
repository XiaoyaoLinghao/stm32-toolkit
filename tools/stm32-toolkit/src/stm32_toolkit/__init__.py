from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

__version__ = "0.9.0"

__all__ = [
    "MonitorObservationError",
    "MonitorObservationRequest",
    "MonitorObservationSeams",
    "MonitorObservationSession",
    "open_monitor_observation",
]

if TYPE_CHECKING:  # pragma: no cover - imports exist only for static analyzers
    from .monitor_observation import (
        MonitorObservationError,
        MonitorObservationRequest,
        MonitorObservationSeams,
        MonitorObservationSession,
        open_monitor_observation,
    )


def __getattr__(name: str) -> Any:
    if name not in __all__:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(".monitor_observation", __name__), name)
    globals()[name] = value
    return value
