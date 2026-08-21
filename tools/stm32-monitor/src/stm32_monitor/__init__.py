"""Project-isolated monitoring service for STM32 Toolkit."""

from .models import MonitorConfig, ProbeConnectRequest, WatchGroup, WatchItem
from .protocol import MONITOR_PROTOCOL_VERSION, ProtocolResult
from .replay import (
    EVIDENCE_INTEGRITY_FAILURE,
    ENVIRONMENT_FAILURE,
    MONITOR_REPLAY_INVALID,
    OPERATION_CONFLICT,
    MonitorReplayDocument,
    MonitorReplayError,
    MonitorRunRef,
    canonical_replay_json_bytes,
    ingest_monitor_replay,
)


__version__ = "0.5.0"

__all__ = [
    "MONITOR_PROTOCOL_VERSION",
    "MonitorConfig",
    "ProbeConnectRequest",
    "ProtocolResult",
    "WatchGroup",
    "WatchItem",
    "EVIDENCE_INTEGRITY_FAILURE",
    "ENVIRONMENT_FAILURE",
    "MONITOR_REPLAY_INVALID",
    "OPERATION_CONFLICT",
    "MonitorReplayDocument",
    "MonitorReplayError",
    "MonitorRunRef",
    "canonical_replay_json_bytes",
    "ingest_monitor_replay",
    "__version__",
]
