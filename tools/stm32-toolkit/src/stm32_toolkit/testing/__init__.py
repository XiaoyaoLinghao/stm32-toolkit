"""Common test protocol and Host execution public API."""

from .host import HostTestRunner
from .model import (
    CASE_STATES,
    EVENT_KINDS,
    MAX_FRAME_PAYLOAD_BYTES,
    MAX_RUN_STREAM_BYTES,
    RUN_STATES,
    TEST_SCHEMA,
    TestCaseResult,
    TestInventory,
    TestProtocolError,
    TestRunManifest,
    calculate_host_build_inventory_digest,
    calculate_host_test_executable_inventory_digest,
    calculate_inventory_digest,
    create_inventory,
    host_target_device,
    validate_host_identity,
)
from .protocol import assemble_test_run, validate_event_payload

__all__ = [
    "CASE_STATES",
    "EVENT_KINDS",
    "HostTestRunner",
    "MAX_FRAME_PAYLOAD_BYTES",
    "MAX_RUN_STREAM_BYTES",
    "RUN_STATES",
    "TEST_SCHEMA",
    "TestCaseResult",
    "TestInventory",
    "TestProtocolError",
    "TestRunManifest",
    "assemble_test_run",
    "calculate_host_build_inventory_digest",
    "calculate_host_test_executable_inventory_digest",
    "calculate_inventory_digest",
    "create_inventory",
    "host_target_device",
    "validate_event_payload",
    "validate_host_identity",
]
