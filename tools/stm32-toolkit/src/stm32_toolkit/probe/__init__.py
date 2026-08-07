"""Versioned, authenticated probe access primitives."""

from .backend import FlashBackendReport, ProbeAttachmentEvidence
from .flash import FlashReport, FlashRequest, flash_firmware
from .handoff import (
    CortexDebugAttachContract,
    DebugHandoffRequest,
    HandoffRestore,
    HandoffTicket,
    begin_debug_handoff,
    end_debug_handoff,
)
from .model import OperationLevel, ProbeOwnerEvidence, ProbeRequest, ProbeResponse
from .protocol import PROBE_PROTOCOL_VERSION, ProbeProtocolError, decode_request, encode_response
from .pyocd_backend import PyOCDBackend
from .supervisor import ProbeServiceConfig, ProbeServiceSupervisor

__all__ = [
    "FlashBackendReport",
    "FlashReport",
    "FlashRequest",
    "CortexDebugAttachContract",
    "DebugHandoffRequest",
    "HandoffRestore",
    "HandoffTicket",
    "OperationLevel",
    "PROBE_PROTOCOL_VERSION",
    "ProbeAttachmentEvidence",
    "ProbeOwnerEvidence",
    "ProbeProtocolError",
    "ProbeRequest",
    "ProbeResponse",
    "ProbeServiceConfig",
    "ProbeServiceSupervisor",
    "PyOCDBackend",
    "decode_request",
    "encode_response",
    "begin_debug_handoff",
    "end_debug_handoff",
    "flash_firmware",
]
