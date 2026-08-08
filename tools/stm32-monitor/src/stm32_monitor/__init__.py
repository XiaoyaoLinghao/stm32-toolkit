"""Project-isolated monitoring service for STM32 Toolkit."""

from .models import MonitorConfig, ProbeConnectRequest, WatchGroup, WatchItem
from .protocol import MONITOR_PROTOCOL_VERSION, ProtocolResult


__version__ = "0.4.0"

__all__ = [
    "MONITOR_PROTOCOL_VERSION",
    "MonitorConfig",
    "ProbeConnectRequest",
    "ProtocolResult",
    "WatchGroup",
    "WatchItem",
    "__version__",
]
