"""Fail-closed local verification primitives for the STM32 Toolkit 0.6 gates.

The module deliberately contains no network client and no hardware or product
dispatcher.  Controllers pass only local, already-derived paths to these
validators.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import importlib.util
import json
import math
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unicodedata
import zipfile
import xml.etree.ElementTree as ElementTree
from contextlib import ExitStack
from io import BytesIO
from dataclasses import dataclass
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path
from typing import Callable, Mapping, Sequence

from run_0600_gates import (
    ControllerError, native_node_framework, parse_native_node_outcomes,
    validate_portable_text,
)


CATALOG_SCHEMA = "stm32-gate-catalog/1"
PERFORMANCE_SCHEMA = "stm32-performance-catalog/1"
FROZEN_SUPPORT_PROFILE = Path(
    r"C:\tmp\stm32tk-0600-support\feasibility\profile.json"
)
EXPECTED_FAMILY_IDS = (
    "EVIDENCE-0601",
    "DIAGNOSTICS-0601",
    "ANALYTICS-0601",
    "RELEASE-0601",
    "EVIDENCE-0602",
    "DIAGNOSTICS-0602",
    "ANALYTICS-0602",
    "RELEASE-0602",
    "EVIDENCE-0603",
    "DIAGNOSTICS-0603",
    "ANALYTICS-0603",
    "RELEASE-0603",
    "HW-0400-DEFERRED",
    "HW-0600-TRANSPORT",
    "HW-0600-DIAGNOSTIC",
)
EXPECTED_HARDWARE_GATE_IDS = (
    "STM32TK-HW-0400-PROBE-ATTACH-READ",
    "STM32TK-HW-0400-FLASH-READBACK",
    "STM32TK-HW-0400-HANDOFF-REACQUIRE",
    "STM32TK-HW-0400-TYPED-READ-SAMPLE-FAULT",
    "STM32TK-HW-0400-CLI-MCP-WORKFLOWS",
    "STM32TK-HW-0600-MAILBOX",
    "STM32TK-HW-0600-RTT",
    "STM32TK-HW-0600-UART",
    "STM32TK-HW-0600-SEMIHOSTING",
    "STM32TK-HW-0600-DIAGNOSTIC-CHAIN",
)
EXPECTED_FAMILY_VALUES = {
    "EVIDENCE-0601": ("STM32TK-0601", "evidence model, storage, and canonical verification gates", "Codex/local derived agents", "windows-python", "evidence", "product-evidence", ("quick-0601", "candidate-0601", "final-windows"), (), ("tools/stm32-toolkit/src/stm32_toolkit/evidence",), ("tools/stm32-toolkit/tests",)),
    "DIAGNOSTICS-0601": ("STM32TK-0601", "host and target diagnostic evidence gates", "Codex/local derived agents", "windows-python", "diagnostics", "product-diagnostics", ("quick-0601", "candidate-0601", "final-windows"), ("EVIDENCE-0601",), ("tools/stm32-toolkit/src/stm32_toolkit",), ("tools/stm32-toolkit/tests",)),
    "ANALYTICS-0601": ("STM32TK-0601", "coverage and performance evidence gates", "Codex/local derived agents", "windows-python", "analytics", "product-analytics", ("quick-0601", "candidate-0601", "final-windows"), ("EVIDENCE-0601",), ("tools/stm32-toolkit/src/stm32_toolkit",), ("tools/stm32-toolkit/tests",)),
    "RELEASE-0601": ("STM32TK-0601", "offline release controller and verifier gates", "Codex/local derived agents", "windows-python", "release", "controller-off", ("quick-0601", "candidate-0601", "final-windows"), ("DIAGNOSTICS-0601", "ANALYTICS-0601"), ("tools/release",), ("tools/stm32-toolkit/tests/release",)),
    "EVIDENCE-0602": ("STM32TK-0602", "diagnostic-loop evidence gates", "Codex/local derived agents", "windows-python", "evidence", "product-evidence", ("quick-0602", "candidate-0602", "final-windows"), ("RELEASE-0601",), ("tools/stm32-toolkit/src/stm32_toolkit",), ("tools/stm32-toolkit/tests",)),
    "DIAGNOSTICS-0602": ("STM32TK-0602", "diagnostic-loop behavior gates", "Codex/local derived agents", "windows-python", "diagnostics", "product-diagnostics", ("quick-0602", "candidate-0602", "final-windows"), ("EVIDENCE-0602",), ("tools/stm32-toolkit/src/stm32_toolkit",), ("tools/stm32-toolkit/tests",)),
    "ANALYTICS-0602": ("STM32TK-0602", "diagnostic-loop analytics gates", "Codex/local derived agents", "windows-python", "analytics", "product-analytics", ("quick-0602", "candidate-0602", "final-windows"), ("EVIDENCE-0602",), ("tools/stm32-toolkit/src/stm32_toolkit",), ("tools/stm32-toolkit/tests",)),
    "RELEASE-0602": ("STM32TK-0602", "diagnostic-loop release gates", "Codex/local derived agents", "windows-python", "release", "controller-off", ("quick-0602", "candidate-0602", "final-windows"), ("DIAGNOSTICS-0602", "ANALYTICS-0602"), ("tools/release",), ("tools/stm32-toolkit/tests/release",)),
    "EVIDENCE-0603": ("STM32TK-0603", "analytics-product evidence gates", "Codex/local derived agents", "windows-python", "evidence", "product-evidence", ("quick-0603", "candidate-0603", "final-windows"), ("RELEASE-0602",), ("tools/stm32-toolkit/src/stm32_toolkit",), ("tools/stm32-toolkit/tests",)),
    "DIAGNOSTICS-0603": ("STM32TK-0603", "analytics-product diagnostic gates", "Codex/local derived agents", "windows-python", "diagnostics", "product-diagnostics", ("quick-0603", "candidate-0603", "final-windows"), ("EVIDENCE-0603",), ("tools/stm32-toolkit/src/stm32_toolkit",), ("tools/stm32-toolkit/tests",)),
    "ANALYTICS-0603": ("STM32TK-0603", "analytics-product quality gates", "Codex/local derived agents", "windows-python", "analytics", "product-analytics", ("quick-0603", "candidate-0603", "final-windows"), ("EVIDENCE-0603",), ("tools/stm32-toolkit/src/stm32_toolkit",), ("tools/stm32-toolkit/tests",)),
    "RELEASE-0603": ("STM32TK-0603", "final release-ledger gates", "Codex/local derived agents", "windows-python", "release", "controller-off", ("quick-0603", "candidate-0603", "final-windows"), ("DIAGNOSTICS-0603", "ANALYTICS-0603"), ("tools/release",), ("tools/stm32-toolkit/tests/release",)),
    "HW-0400-DEFERRED": ("STM32TK-0400", "historical 0.4 deferred real-board behaviors", "user", "windows-hardware", "hardware", "controller-off", ("hardware-0400",), ("RELEASE-0603",), ("tools/stm32-toolkit/src/stm32_toolkit/probe",), ("tools/stm32-toolkit/tests",)),
    "HW-0600-TRANSPORT": ("STM32TK-0600", "0.6 real-board transport gates", "user", "windows-hardware", "hardware", "controller-off", ("hardware-0600",), ("RELEASE-0603",), ("tools/stm32-toolkit/src/stm32_toolkit",), ("tools/stm32-toolkit/tests",)),
    "HW-0600-DIAGNOSTIC": ("STM32TK-0600", "0.6 real-board diagnostic-chain gate", "user", "windows-hardware", "hardware", "controller-off", ("hardware-0600",), ("HW-0600-TRANSPORT",), ("tools/stm32-toolkit/src/stm32_toolkit",), ("tools/stm32-toolkit/tests",)),
}
EXPECTED_SOURCE_BINDING_VALUES = {
    "STM32TK-HW-0400-PROBE-ATTACH-READ": ("docs/codex/returns/STM32TK-0402-PYOCD-BACKEND/implementation-report.md", 122, 124, "b8cc975899f28e30a466097b7b0934b10faaf285fef670f8e98a806226934a30"),
    "STM32TK-HW-0400-FLASH-READBACK": ("docs/codex/returns/STM32TK-0403-FLASH-HANDOFF/implementation-report.md", 130, 133, "0ffe0dd5e78aee1899da7b52f19fb6c2c6104af71d28a5ccf02b705e66dd3449"),
    "STM32TK-HW-0400-HANDOFF-REACQUIRE": ("docs/codex/returns/STM32TK-0403-FLASH-HANDOFF/implementation-report.md", 130, 133, "0ffe0dd5e78aee1899da7b52f19fb6c2c6104af71d28a5ccf02b705e66dd3449"),
    "STM32TK-HW-0400-TYPED-READ-SAMPLE-FAULT": ("docs/codex/returns/STM32TK-0404-TYPED-DEBUG/implementation-report.md", 138, 140, "9565b2053322f527ccc29b3eba95673d5cc19ada9f653e241c3f10a7e84a4bdf"),
    "STM32TK-HW-0400-CLI-MCP-WORKFLOWS": ("docs/codex/returns/STM32TK-0405-CLI-MCP-RELEASE/implementation-report.md", 140, 142, "18aef58476244b43784caafa060ee19081ecd9c7af37f81b1f7823fbcdd84f50"),
}
EXPECTED_GATE_VALUES = {
    "STM32TK-HW-0400-PROBE-ATTACH-READ": ("HW-0400-DEFERRED", "0400", ("hardware-0400",), (), ("result.json", "identity-state.json"), ("python312==3.12.10", "pyocd==0.45.1"), ("tools/stm32-toolkit/src/stm32_toolkit/probe",), ("tools/stm32-toolkit/tests/test_pyocd_backend.py",)),
    "STM32TK-HW-0400-FLASH-READBACK": ("HW-0400-DEFERRED", "0400", ("hardware-0400",), ("STM32TK-HW-0400-PROBE-ATTACH-READ",), ("result.json", "identity-state.json"), ("python312==3.12.10", "pyocd==0.45.1"), ("tools/stm32-toolkit/src/stm32_toolkit/probe",), ("tools/stm32-toolkit/tests/test_flash.py",)),
    "STM32TK-HW-0400-HANDOFF-REACQUIRE": ("HW-0400-DEFERRED", "0400", ("hardware-0400",), ("STM32TK-HW-0400-FLASH-READBACK",), ("result.json", "identity-state.json"), ("python312==3.12.10", "pyocd==0.45.1"), ("tools/stm32-toolkit/src/stm32_toolkit/probe",), ("tools/stm32-toolkit/tests/test_debug_handoff.py",)),
    "STM32TK-HW-0400-TYPED-READ-SAMPLE-FAULT": ("HW-0400-DEFERRED", "0400", ("hardware-0400",), ("STM32TK-HW-0400-HANDOFF-REACQUIRE",), ("result.json", "identity-state.json"), ("python312==3.12.10", "pyocd==0.45.1"), ("tools/stm32-toolkit/src/stm32_toolkit",), ("tools/stm32-toolkit/tests/test_debug_read.py", "tools/stm32-toolkit/tests/test_sampling.py", "tools/stm32-toolkit/tests/test_fault.py")),
    "STM32TK-HW-0400-CLI-MCP-WORKFLOWS": ("HW-0400-DEFERRED", "0400", ("hardware-0400",), ("STM32TK-HW-0400-TYPED-READ-SAMPLE-FAULT",), ("result.json", "identity-state.json"), ("python312==3.12.10", "pyocd==0.45.1"), ("tools/stm32-toolkit/src/stm32_toolkit",), ("tools/stm32-toolkit/tests/test_cli_hardware.py", "tools/stm32-toolkit/tests/test_mcp_hardware.py")),
    "STM32TK-HW-0600-MAILBOX": ("HW-0600-TRANSPORT", "0600", ("hardware-0600",), (), ("result.json", "raw-events.json"), ("python312==3.12.10", "pyocd==0.45.1"), ("tools/stm32-toolkit/src/stm32_toolkit",), ("tools/stm32-toolkit/tests",)),
    "STM32TK-HW-0600-RTT": ("HW-0600-TRANSPORT", "0600", ("hardware-0600",), ("STM32TK-HW-0600-MAILBOX",), ("result.json", "raw-events.json"), ("python312==3.12.10", "pyocd==0.45.1"), ("tools/stm32-toolkit/src/stm32_toolkit",), ("tools/stm32-toolkit/tests",)),
    "STM32TK-HW-0600-UART": ("HW-0600-TRANSPORT", "0600", ("hardware-0600",), ("STM32TK-HW-0600-RTT",), ("result.json", "raw-events.json"), ("python312==3.12.10", "pyserial==3.5"), ("tools/stm32-toolkit/src/stm32_toolkit",), ("tools/stm32-toolkit/tests",)),
    "STM32TK-HW-0600-SEMIHOSTING": ("HW-0600-TRANSPORT", "0600", ("hardware-0600",), ("STM32TK-HW-0600-UART",), ("result.json", "raw-events.json"), ("python312==3.12.10", "pyocd==0.45.1"), ("tools/stm32-toolkit/src/stm32_toolkit",), ("tools/stm32-toolkit/tests",)),
    "STM32TK-HW-0600-DIAGNOSTIC-CHAIN": ("HW-0600-DIAGNOSTIC", "0600", ("hardware-0600",), ("STM32TK-HW-0600-MAILBOX", "STM32TK-HW-0600-RTT", "STM32TK-HW-0600-UART", "STM32TK-HW-0600-SEMIHOSTING"), ("result.json", "raw-events.json"), ("python312==3.12.10", "pyocd==0.45.1", "pyserial==3.5"), ("tools/stm32-toolkit/src/stm32_toolkit",), ("tools/stm32-toolkit/tests",)),
}
RESOURCE_LOCK_TYPES = (
    "board",
    "evidence-root",
    "performance-host",
    "port",
    "probe",
    "uart",
)
HARDWARE_RESOURCE_LOCKS = {
    "board": "hardware-input:board_id",
    "probe": "hardware-input:probe_serial_hash",
    "uart": "hardware-input:uart_serial_hash",
    "evidence-root": "checkpoint:evidence_root",
}
FAMILY_KEYS = {
    "id",
    "module",
    "purpose",
    "owner_class",
    "platform_class",
    "evidence_type",
    "coverage_context",
    "matrices",
    "prerequisites",
    "impact_map",
    "reserved",
    "command_argv",
    "node_ids",
}
GATE_KEYS = {
    "id",
    "family_id",
    "contract",
    "phase",
    "owner_class",
    "platform_class",
    "evidence_type",
    "coverage_context",
    "matrices",
    "working_directory",
    "command_argv",
    "required_tools",
    "timeout_seconds",
    "evidence_files",
    "node_inventory_source",
    "node_ids",
    "prerequisites",
    "impact_map",
    "resource_locks",
    "source_binding",
}
SOURCE_BINDING_KEYS = {
    "path",
    "start_line",
    "end_line",
    "sha256",
    "claim",
}
IMPACT_MAP_KEYS = {"product_paths", "test_paths"}
HEX64 = re.compile(r"^[0-9a-f]{64}$")
HEX40 = re.compile(r"^[0-9a-f]{40}$")
UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
UTC_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z$")
REPOSITORY_URL = "https://github.com/XiaoyaoLinghao/stm32-toolkit.git"
PROGRAM_BASE = "bb6bc5e9ee937e4ce53996b31f25bf1109ffe13f"
PRODUCT_0400 = "96966c461e7e11bff965027d8d498dd40ea5fd55"
REPORT_0400 = "0ee0a5037b3bd158eea5bd312fce7feaadecbfc6"
REPORT_PATHS = {
    "0601": "docs/codex/returns/STM32TK-0601-TEST-EVIDENCE/implementation-report.md",
    "0602": "docs/codex/returns/STM32TK-0602-DIAGNOSTIC-LOOP/implementation-report.md",
}
GOVERNANCE_OWNERS = {
    "specification_owner": "Codex",
    "implementation_owner": "Codex/local derived agents",
    "reviewer": "Codex",
    "windows_evidence_owner": "Codex",
    "hardware_evidence_owner": "user",
}
VERIFIER_RELATIVE_PATH = "tools/release/verify_0600_release.py"


class CatalogError(ValueError):
    """The frozen catalog or performance profile is not the closed contract."""


class VerificationError(ValueError):
    """Local release evidence failed a closed integrity contract."""


@dataclass(frozen=True)
class SourceBinding:
    path: str
    start_line: int
    end_line: int
    sha256: str
    claim: str


@dataclass(frozen=True)
class GateFamily:
    family_id: str
    module: str
    matrices: tuple[str, ...]
    owner_class: str
    platform_class: str
    evidence_type: str
    coverage_context: str
    command_argv: tuple[str, ...]
    node_ids: tuple[str, ...]
    prerequisites: tuple[str, ...]
    reserved: bool


@dataclass(frozen=True)
class GateEntry:
    gate_id: str
    family_id: str
    contract: str
    command_argv: tuple[str, ...]
    node_ids: tuple[str, ...]
    prerequisites: tuple[str, ...]
    resource_locks: dict[str, str]
    source_binding: SourceBinding | None


@dataclass(frozen=True)
class GateCatalog:
    families: tuple[GateFamily, ...]
    gates: tuple[GateEntry, ...]

    @property
    def family_ids(self) -> tuple[str, ...]:
        return tuple(item.family_id for item in self.families)

    @property
    def gate_ids(self) -> tuple[str, ...]:
        return tuple(item.gate_id for item in self.gates)

    def reserved_entries(self) -> tuple[GateFamily, ...]:
        return tuple(item for item in self.families if item.reserved)

    def hardware_gate_ids(self, contract: str) -> tuple[str, ...]:
        if contract not in {"0400", "0600"}:
            raise CatalogError("unknown hardware contract")
        return tuple(item.gate_id for item in self.gates if item.contract == contract)


def _is_object(value: object) -> bool:
    return isinstance(value, Mapping)


def _is_integer(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _closed(value: object, keys: set[str]) -> bool:
    return _is_object(value) and set(value) == keys


def _strings(value: object, *, nonempty: bool = False) -> bool:
    return (
        isinstance(value, list)
        and all(isinstance(item, str) and (not nonempty or bool(item)) for item in value)
        and len(set(value)) == len(value)
    )


def _validate_impact_map(value: object) -> None:
    if not _closed(value, IMPACT_MAP_KEYS):
        raise CatalogError("impact map is not closed")
    assert isinstance(value, Mapping)
    if not _strings(value["product_paths"]) or not _strings(value["test_paths"]):
        raise CatalogError("impact map paths must be unique string arrays")


def _validate_dag(nodes: Sequence[str], prerequisites: Mapping[str, tuple[str, ...]]) -> None:
    known = set(nodes)
    state: dict[str, int] = {}

    def visit(node: str) -> None:
        if state.get(node) == 1:
            raise CatalogError("prerequisite cycle")
        if state.get(node) == 2:
            return
        state[node] = 1
        for dependency in prerequisites[node]:
            if dependency not in known:
                raise CatalogError("unknown prerequisite")
            visit(dependency)
        state[node] = 2

    for item in nodes:
        visit(item)


def _paragraph_bytes(repo: Path, binding: SourceBinding) -> bytes:
    path = repo.joinpath(*binding.path.split("/"))
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise CatalogError("source report is unreadable") from exc
    if binding.start_line < 1 or binding.end_line < binding.start_line or binding.end_line > len(lines):
        raise CatalogError("source paragraph range is invalid")
    return ("\n".join(lines[binding.start_line - 1 : binding.end_line]) + "\n").encode("utf-8")


def validate_catalog_data(value: object, *, repo: Path) -> GateCatalog:
    if not _closed(value, {"schema", "resource_lock_types", "families", "gates"}):
        raise CatalogError("catalog root is not closed")
    assert isinstance(value, Mapping)
    if value["schema"] != CATALOG_SCHEMA or value["resource_lock_types"] != list(RESOURCE_LOCK_TYPES):
        raise CatalogError("catalog identity is not frozen")
    raw_families = value["families"]
    raw_gates = value["gates"]
    if not isinstance(raw_families, list) or not isinstance(raw_gates, list):
        raise CatalogError("catalog collections must be arrays")

    families: list[GateFamily] = []
    for item in raw_families:
        if not _closed(item, FAMILY_KEYS):
            raise CatalogError("family is not closed")
        assert isinstance(item, Mapping)
        _validate_impact_map(item["impact_map"])
        if (
            not all(isinstance(item[name], str) and item[name] for name in (
                "id",
                "module",
                "purpose",
                "owner_class",
                "platform_class",
                "evidence_type",
                "coverage_context",
            ))
            or not _strings(item["matrices"], nonempty=True)
            or not _strings(item["prerequisites"], nonempty=True)
            or not _strings(item["command_argv"], nonempty=True)
            or not _strings(item["node_ids"], nonempty=True)
            or not isinstance(item["reserved"], bool)
        ):
            raise CatalogError("family field type is invalid")
        impact = item["impact_map"]
        assert isinstance(impact, Mapping)
        semantic = (
            item["module"], item["purpose"], item["owner_class"],
            item["platform_class"], item["evidence_type"], item["coverage_context"],
            tuple(item["matrices"]), tuple(item["prerequisites"]),
            tuple(impact["product_paths"]), tuple(impact["test_paths"]),
        )
        if semantic != EXPECTED_FAMILY_VALUES.get(str(item["id"])):
            raise CatalogError("family semantic contract is not frozen")
        families.append(
            GateFamily(
                family_id=str(item["id"]),
                module=str(item["module"]),
                matrices=tuple(item["matrices"]),
                owner_class=str(item["owner_class"]),
                platform_class=str(item["platform_class"]),
                evidence_type=str(item["evidence_type"]),
                coverage_context=str(item["coverage_context"]),
                command_argv=tuple(item["command_argv"]),
                node_ids=tuple(item["node_ids"]),
                prerequisites=tuple(item["prerequisites"]),
                reserved=bool(item["reserved"]),
            )
        )
    family_ids = tuple(item.family_id for item in families)
    if family_ids != EXPECTED_FAMILY_IDS or len(set(family_ids)) != len(family_ids):
        raise CatalogError("family inventory is not frozen")
    for family in families:
        if not family.reserved or family.command_argv or family.node_ids:
            raise CatalogError("reserved family is executable or has fabricated nodes")
    _validate_dag(family_ids, {item.family_id: item.prerequisites for item in families})

    gates: list[GateEntry] = []
    for item in raw_gates:
        if not _closed(item, GATE_KEYS):
            raise CatalogError("gate is not closed")
        assert isinstance(item, Mapping)
        _validate_impact_map(item["impact_map"])
        locks = item["resource_locks"]
        if (
            not all(isinstance(item[name], str) and item[name] for name in (
                "id",
                "family_id",
                "contract",
                "phase",
                "owner_class",
                "platform_class",
                "evidence_type",
                "coverage_context",
                "working_directory",
            ))
            or not _strings(item["matrices"], nonempty=True)
            or not _strings(item["command_argv"], nonempty=True)
            or not _strings(item["required_tools"], nonempty=True)
            or not _is_integer(item["timeout_seconds"])
            or item["timeout_seconds"] <= 0
            or not _strings(item["evidence_files"], nonempty=True)
            or item["node_inventory_source"] is not None
            or not _strings(item["node_ids"], nonempty=True)
            or not _strings(item["prerequisites"], nonempty=True)
            or not _is_object(locks)
            or set(locks) != set(HARDWARE_RESOURCE_LOCKS)
            or any(not isinstance(member, str) for member in locks.values())
        ):
            raise CatalogError("gate field type is invalid")
        binding_value = item["source_binding"]
        binding: SourceBinding | None
        if binding_value is None:
            binding = None
        else:
            if not _closed(binding_value, SOURCE_BINDING_KEYS):
                raise CatalogError("source binding is not closed")
            assert isinstance(binding_value, Mapping)
            if (
                not isinstance(binding_value["path"], str)
                or not _is_integer(binding_value["start_line"])
                or not _is_integer(binding_value["end_line"])
                or not isinstance(binding_value["sha256"], str)
                or HEX64.fullmatch(binding_value["sha256"]) is None
                or binding_value["claim"] != "new-0600-catalog-id-for-historical-deferred-behavior"
            ):
                raise CatalogError("source binding field is invalid")
            binding = SourceBinding(
                path=str(binding_value["path"]),
                start_line=int(binding_value["start_line"]),
                end_line=int(binding_value["end_line"]),
                sha256=str(binding_value["sha256"]),
                claim=str(binding_value["claim"]),
            )
            if hashlib.sha256(_paragraph_bytes(repo, binding)).hexdigest() != binding.sha256:
                raise CatalogError("source paragraph digest mismatch")
        gate = GateEntry(
            gate_id=str(item["id"]),
            family_id=str(item["family_id"]),
            contract=str(item["contract"]),
            command_argv=tuple(item["command_argv"]),
            node_ids=tuple(item["node_ids"]),
            prerequisites=tuple(item["prerequisites"]),
            resource_locks={str(key): str(member) for key, member in locks.items()},
            source_binding=binding,
        )
        gates.append(gate)

        impact = item["impact_map"]
        assert isinstance(impact, Mapping)
        semantic = (
            item["family_id"], item["contract"], tuple(item["matrices"]),
            tuple(item["prerequisites"]), tuple(item["evidence_files"]),
            tuple(item["required_tools"]), tuple(impact["product_paths"]),
            tuple(impact["test_paths"]),
        )
        if (
            semantic != EXPECTED_GATE_VALUES.get(str(item["id"]))
            or item["phase"] != "post-0603-hardware"
            or item["owner_class"] != "user"
            or item["platform_class"] != "windows-hardware"
            or item["evidence_type"] != "hardware"
            or item["coverage_context"] != "controller-off"
            or item["working_directory"] != "."
            or item["timeout_seconds"] != 900
        ):
            raise CatalogError("hardware gate semantic contract is not frozen")
        expected_binding = EXPECTED_SOURCE_BINDING_VALUES.get(str(item["id"]))
        actual_binding = None if binding is None else (
            binding.path, binding.start_line, binding.end_line, binding.sha256
        )
        if actual_binding != expected_binding:
            raise CatalogError("hardware gate source binding is not frozen")

    gate_ids = tuple(item.gate_id for item in gates)
    if gate_ids != EXPECTED_HARDWARE_GATE_IDS or len(set(gate_ids)) != len(gate_ids):
        raise CatalogError("hardware gate inventory is not frozen")
    for index, gate in enumerate(gates):
        expected_contract = "0400" if index < 5 else "0600"
        expected_family = (
            "HW-0400-DEFERRED"
            if index < 5
            else "HW-0600-DIAGNOSTIC"
            if index == 9
            else "HW-0600-TRANSPORT"
        )
        if (
            gate.contract != expected_contract
            or gate.family_id != expected_family
            or gate.command_argv
            or gate.node_ids
            or gate.resource_locks != HARDWARE_RESOURCE_LOCKS
            or (index < 5) != (gate.source_binding is not None)
        ):
            raise CatalogError("deferred hardware gate is not frozen")
    _validate_dag(gate_ids, {item.gate_id: item.prerequisites for item in gates})
    return GateCatalog(tuple(families), tuple(gates))


def _read_json_no_duplicates(path: Path) -> object:
    def pairs_hook(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise CatalogError("duplicate JSON key")
            result[key] = value
        return result

    try:
        return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=pairs_hook)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CatalogError("JSON is unreadable") from exc


def load_catalog(path: Path) -> GateCatalog:
    value = _read_json_no_duplicates(path)
    repo = path.resolve().parents[2]
    return validate_catalog_data(value, repo=repo)


def validate_performance_catalog_data(value: object) -> dict[str, object]:
    if not _closed(value, {"schema", "profiles"}):
        raise CatalogError("performance catalog root is not closed")
    assert isinstance(value, Mapping)
    if value["schema"] != PERFORMANCE_SCHEMA or not isinstance(value["profiles"], list):
        raise CatalogError("performance catalog identity is invalid")
    profiles = value["profiles"]
    assert isinstance(profiles, list)
    modules: list[str] = []
    for profile in profiles:
        if not _closed(profile, {"module", "profile_sha256", "producers"}):
            raise CatalogError("performance profile is not closed")
        assert isinstance(profile, Mapping)
        module = profile["module"]
        if module not in {"STM32TK-0601", "STM32TK-0602", "STM32TK-0603"}:
            raise CatalogError("performance profile module is invalid")
        if not isinstance(profile["profile_sha256"], str) or HEX64.fullmatch(profile["profile_sha256"]) is None:
            raise CatalogError("performance profile digest is invalid")
        producers = profile["producers"]
        if not isinstance(producers, list) or not producers:
            raise CatalogError("performance profile producers are invalid")
        producer_names: list[str] = []
        for producer in producers:
            if not _closed(producer, {"producer", "test_file", "test_file_sha256", "workloads"}):
                raise CatalogError("performance producer is not closed")
            assert isinstance(producer, Mapping)
            producer_name = producer["producer"]
            if producer_name not in {"python", "browser"}:
                raise CatalogError("performance producer is invalid")
            if (
                not isinstance(producer["test_file"], str)
                or not producer["test_file"]
                or not isinstance(producer["test_file_sha256"], str)
                or HEX64.fullmatch(producer["test_file_sha256"]) is None
                or not isinstance(producer["workloads"], list)
                or not producer["workloads"]
            ):
                raise CatalogError("performance producer identity is invalid")
            if producer["test_file"] != PERFORMANCE_TEST_FILES.get((str(module), str(producer_name))):
                raise CatalogError("performance producer test file differs from the frozen module")
            workload_ids: list[str] = []
            for workload in producer["workloads"]:
                _validate_performance_workload_contract(workload, catalog=True)
                assert isinstance(workload, Mapping)
                workload_ids.append(str(workload["id"]))
            if workload_ids != sorted(workload_ids, key=lambda item: item.encode("utf-8")) or len(workload_ids) != len(set(workload_ids)):
                raise CatalogError("performance workloads are not sorted and unique")
            expected_workloads = PERFORMANCE_MODULE_CONTRACTS[str(module)].get(str(producer_name))
            if expected_workloads is None or [
                (item["id"], item["design_maximum"],
                 item["measurement"].get("warmup_count", item["measurement"].get("warmup_seconds")),
                 item["measurement"].get("samples_per_batch", item["measurement"].get("samples_per_window")))
                for item in producer["workloads"]
            ] != list(expected_workloads):
                raise CatalogError("performance workload inventory differs from the frozen module")
            producer_names.append(str(producer_name))
        if producer_names != sorted(producer_names, key=lambda item: item.encode("utf-8")) or len(producer_names) != len(set(producer_names)):
            raise CatalogError("performance producers are not sorted and unique")
        if producer_names != sorted(PERFORMANCE_MODULE_CONTRACTS[str(module)]):
            raise CatalogError("performance producer inventory differs from the frozen module")
        digest_input = {"module": module, "producers": producers}
        if profile["profile_sha256"] != _performance_digest(digest_input):
            raise CatalogError("performance profile digest mismatch")
        modules.append(str(module))
    if modules != sorted(modules, key=lambda item: item.encode("utf-8")) or len(modules) != len(set(modules)):
        raise CatalogError("performance profiles are not sorted and unique")
    return dict(value)


def load_performance_catalog(path: Path) -> dict[str, object]:
    return validate_performance_catalog_data(_read_json_no_duplicates(path))


def canonical_json_bytes(value: object) -> bytes:
    """Encode the program's authoritative canonical JSON form."""
    _validate_json_value(value)
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def _validate_json_value(value: object, *, depth: int = 0) -> None:
    if depth > 32:
        raise VerificationError("JSON nesting exceeds the program limit")
    if value is None or isinstance(value, bool):
        return
    if isinstance(value, int):
        return
    if isinstance(value, float):
        raise VerificationError("floating point JSON is forbidden")
    if isinstance(value, str):
        if unicodedata.normalize("NFC", value) != value:
            raise VerificationError("JSON string is not NFC")
        return
    if isinstance(value, list):
        for item in value:
            _validate_json_value(item, depth=depth + 1)
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str) or unicodedata.normalize("NFC", key) != key:
                raise VerificationError("JSON object key is invalid")
            _validate_json_value(item, depth=depth + 1)
        return
    raise VerificationError("unsupported JSON value")


def _regular_file(path: Path) -> bool:
    try:
        info = path.lstat()
    except OSError:
        return False
    attributes = getattr(info, "st_file_attributes", 0)
    if not stat.S_ISREG(info.st_mode) or path.is_symlink() or bool(attributes & 0x400):
        return False
    for ancestor in path.parents:
        try:
            ancestor_info = ancestor.lstat()
        except OSError:
            return False
        if ancestor.is_symlink() or bool(getattr(ancestor_info, "st_file_attributes", 0) & 0x400):
            return False
    return True


def _safe_relative_path(text: object) -> str:
    if not isinstance(text, str) or not text or "\\" in text or ":" in text:
        raise VerificationError("relative path is invalid")
    parts = text.split("/")
    if any(part in {"", ".", ".."} for part in parts) or text.startswith("/"):
        raise VerificationError("relative path traverses or aliases")
    return text


def _file_reference(path: Path, display_path: str) -> dict[str, object]:
    if not _regular_file(path):
        raise VerificationError("evidence member is not a regular file")
    data = path.read_bytes()
    return {"path": display_path, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def verify_gate_evidence(
    root: Path,
    references: object,
    *,
    expected_paths: Sequence[str],
) -> None:
    if not root.is_absolute() or not root.is_dir() or not isinstance(references, list):
        raise VerificationError("gate evidence root or references are invalid")
    expected = tuple(_safe_relative_path(item) for item in expected_paths)
    if not expected or len(expected) != len(set(expected)) or len(expected) != len({item.casefold() for item in expected}):
        raise VerificationError("catalog evidence inventory is empty or duplicated")
    actual_files: list[str] = []
    for path in root.rglob("*"):
        if path.is_dir() and not path.is_symlink():
            continue
        relative = path.relative_to(root).as_posix()
        if not _regular_file(path):
            raise VerificationError("gate evidence root contains a linked/special member")
        actual_files.append(relative)
    if set(actual_files) != set(expected) or len(actual_files) != len(expected):
        raise VerificationError("gate evidence root differs from catalog inventory")
    seen: set[str] = set()
    seen_folded: set[str] = set()
    declared_paths: list[str] = []
    for reference in references:
        if not _closed(reference, {"path", "bytes", "sha256"}):
            raise VerificationError("gate evidence reference is not closed")
        assert isinstance(reference, Mapping)
        relative = _safe_relative_path(reference["path"])
        if (
            relative in seen
            or relative.casefold() in seen_folded
            or not _is_integer(reference["bytes"])
            or reference["bytes"] < 0
            or not isinstance(reference["sha256"], str)
            or HEX64.fullmatch(reference["sha256"]) is None
        ):
            raise VerificationError("gate evidence reference is invalid")
        member = root.joinpath(*relative.split("/"))
        try:
            member.resolve(strict=True).relative_to(root.resolve(strict=True))
        except (OSError, ValueError) as exc:
            raise VerificationError("gate evidence member escapes its root") from exc
        actual = _file_reference(member, relative)
        if actual != dict(reference):
            raise VerificationError("gate evidence bytes or digest mismatch")
        declared_paths.append(relative)
        seen.add(relative)
        seen_folded.add(relative.casefold())
    if tuple(declared_paths) != expected:
        raise VerificationError("gate evidence references differ from catalog order/inventory")


SHARD_BINDING_KEYS = {
    "owner",
    "platform",
    "run_id",
    "code_head",
    "catalog_sha256",
    "locks",
    "support_sha256",
    "status",
}
SHARD_MANIFEST_KEYS = {"schema", "binding", "members"}
PACKAGE_REFERENCE_KEYS = {"path", "bytes", "sha256"}


def _validate_shard_binding(binding: object) -> dict[str, object]:
    if not _closed(binding, SHARD_BINDING_KEYS):
        raise VerificationError("shard binding is not closed")
    assert isinstance(binding, Mapping)
    if (
        not all(isinstance(binding[key], str) and binding[key] for key in ("owner", "platform", "run_id"))
        or not isinstance(binding["code_head"], str)
        or re.fullmatch(r"[0-9a-f]{40}", binding["code_head"]) is None
        or not isinstance(binding["catalog_sha256"], str)
        or HEX64.fullmatch(binding["catalog_sha256"]) is None
        or not isinstance(binding["support_sha256"], str)
        or HEX64.fullmatch(binding["support_sha256"]) is None
        or binding["status"] not in {"PASS", "FAIL", "BLOCKED"}
        or not _strings(binding["locks"], nonempty=True)
        or binding["locks"] != sorted(binding["locks"], key=lambda item: item.encode("utf-8"))
    ):
        raise VerificationError("shard binding value is invalid")
    for key, item in binding.items():
        if any(word in key.casefold() for word in ("credential", "password", "secret", "token")):
            raise VerificationError("credential field is forbidden")
        values = item if isinstance(item, list) else [item]
        for value in values:
            if isinstance(value, str) and (re.match(r"^[A-Za-z]:[\\/]", value) or value.startswith("\\\\")):
                raise VerificationError("absolute private path is forbidden")
    return dict(binding)


def _evidence_snapshot(
    root: Path, expected_paths: Sequence[str] | None = None
) -> tuple[list[dict[str, object]], dict[str, bytes]]:
    members: list[dict[str, object]] = []
    payloads: dict[str, bytes] = {}
    folded: set[str] = set()
    if expected_paths is None:
        paths = [path for path in root.rglob("*") if not (path.is_dir() and not path.is_symlink())]
    else:
        if (
            not _strings(expected_paths, nonempty=False)
            or list(expected_paths) != sorted(expected_paths, key=lambda item: item.encode("utf-8"))
            or len(expected_paths) != len(set(expected_paths))
        ):
            raise VerificationError("expected package member inventory is invalid")
        paths = [root.joinpath(*_safe_relative_path(item).split("/")) for item in expected_paths]
    for path in paths:
        relative = path.relative_to(root).as_posix()
        _safe_relative_path(relative)
        if relative.casefold() in folded:
            raise VerificationError("case-fold duplicate package member")
        if not _regular_file(path):
            raise VerificationError("evidence member is not a regular file")
        data = path.read_bytes()
        members.append({"path": relative, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
        payloads[relative] = data
        folded.add(relative.casefold())
    members.sort(key=lambda item: str(item["path"]).encode("utf-8"))
    return members, payloads


def _zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_STORED
    info.create_system = 3
    info.external_attr = 0o100444 << 16
    return info


def create_shard_package(
    evidence_root: Path,
    package_path: Path,
    binding: object,
    *,
    member_paths: Sequence[str] | None = None,
) -> dict[str, object]:
    if not evidence_root.is_absolute() or not evidence_root.is_dir():
        raise VerificationError("evidence root must be an absolute directory")
    if not package_path.is_absolute() or package_path.exists() or not package_path.parent.is_dir():
        raise VerificationError("package output must be a new absolute file")
    frozen_binding = _validate_shard_binding(binding)
    members, payloads = _evidence_snapshot(evidence_root, member_paths)
    manifest = {
        "schema": "stm32-local-shard-package/1",
        "binding": frozen_binding,
        "members": members,
    }
    payloads["shard-manifest.json"] = canonical_json_bytes(manifest)
    with zipfile.ZipFile(package_path, "x", compression=zipfile.ZIP_STORED, allowZip64=True) as archive:
        for name in sorted(payloads, key=lambda item: item.encode("utf-8")):
            archive.writestr(_zip_info(name), payloads[name])
    data = package_path.read_bytes()
    return {"path": str(package_path), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def verify_shard_package(
    package_path: Path,
    reference: object,
    expected_binding: object,
    *,
    evidence_root: Path | None = None,
    expected_paths: Sequence[str] | None = None,
    allowed_external_paths: Sequence[str] | None = None,
    before_final_reread: Callable[[], object] | None = None,
) -> None:
    if not _closed(reference, PACKAGE_REFERENCE_KEYS):
        raise VerificationError("package reference is not closed")
    assert isinstance(reference, Mapping)
    if reference["path"] != str(package_path) or not _is_integer(reference["bytes"]):
        raise VerificationError("package reference path/type mismatch")
    data = package_path.read_bytes()
    if reference["bytes"] != len(data) or reference["sha256"] != hashlib.sha256(data).hexdigest():
        raise VerificationError("package bytes or digest mismatch")
    frozen_binding = _validate_shard_binding(expected_binding)
    external_references: list[dict[str, object]] | None = None
    external_payloads: dict[str, bytes] | None = None
    external_full_references: list[dict[str, object]] | None = None
    external_full_payloads: dict[str, bytes] | None = None
    if evidence_root is not None:
        if not evidence_root.is_absolute() or not evidence_root.is_dir():
            raise VerificationError("external evidence root is not an absolute directory")
        external_full_references, external_full_payloads = _evidence_snapshot(evidence_root)
        allowed = list(
            allowed_external_paths
            if allowed_external_paths is not None
            else expected_paths
            if expected_paths is not None
            else [str(item["path"]) for item in external_full_references]
        )
        if (
            not _strings(allowed, nonempty=True)
            or allowed != sorted(allowed, key=lambda item: item.encode("utf-8"))
            or len(allowed) != len(set(allowed))
            or [str(item["path"]) for item in external_full_references] != allowed
        ):
            raise VerificationError("external evidence inventory contains an unexpected file")
        selected = list(expected_paths) if expected_paths is not None else allowed
        if (
            not _strings(selected, nonempty=True)
            or selected != sorted(selected, key=lambda item: item.encode("utf-8"))
            or not set(selected).issubset(allowed)
        ):
            raise VerificationError("expected package inventory is not closed")
        external_references = [
            item for item in external_full_references if item["path"] in selected
        ]
        external_payloads = {
            name: external_full_payloads[name] for name in selected
        }
    try:
        archive = zipfile.ZipFile(BytesIO(data))
    except (OSError, zipfile.BadZipFile) as exc:
        raise VerificationError("package is not a ZIP") from exc
    with archive:
        infos = archive.infolist()
        names = [item.filename for item in infos]
        if names != sorted(names, key=lambda item: item.encode("utf-8")) or len(names) != len(set(names)):
            raise VerificationError("package members are not unique and sorted")
        folded: set[str] = set()
        for info in infos:
            name = _safe_relative_path(info.filename)
            if name.casefold() in folded:
                raise VerificationError("case-fold duplicate package member")
            folded.add(name.casefold())
            if (
                info.date_time != (1980, 1, 1, 0, 0, 0)
                or info.create_system != 3
                or info.external_attr != 0o100444 << 16
                or info.compress_type != zipfile.ZIP_STORED
            ):
                raise VerificationError("package metadata is not fixed")
        if "shard-manifest.json" not in names:
            raise VerificationError("inner package manifest is missing")
        manifest_bytes = archive.read("shard-manifest.json")
        try:
            manifest = json.loads(manifest_bytes.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise VerificationError("inner package manifest is invalid") from exc
        if manifest_bytes != canonical_json_bytes(manifest) or not _closed(manifest, SHARD_MANIFEST_KEYS):
            raise VerificationError("inner package manifest is not canonical/closed")
        assert isinstance(manifest, Mapping)
        if manifest["schema"] != "stm32-local-shard-package/1" or manifest["binding"] != frozen_binding:
            raise VerificationError("inner package binding mismatch")
        references = manifest["members"]
        if not isinstance(references, list):
            raise VerificationError("inner member inventory is invalid")
        if external_references is not None and references != external_references:
            raise VerificationError("archive members differ from external retained evidence")
        expected_names = [str(item["path"]) for item in references] + ["shard-manifest.json"]
        if names != sorted(expected_names, key=lambda item: item.encode("utf-8")):
            raise VerificationError("archive/manifest member discrepancy")
        seen: set[str] = set()
        for item in references:
            if not _closed(item, {"path", "bytes", "sha256"}):
                raise VerificationError("inner member reference is not closed")
            assert isinstance(item, Mapping)
            name = _safe_relative_path(item["path"])
            if name in seen or not _is_integer(item["bytes"]) or item["bytes"] < 0:
                raise VerificationError("inner member reference is invalid")
            payload = archive.read(name)
            if item["bytes"] != len(payload) or item["sha256"] != hashlib.sha256(payload).hexdigest():
                raise VerificationError("inner member bytes or digest mismatch")
            if external_payloads is not None and external_payloads.get(name) != payload:
                raise VerificationError("archive member bytes differ from external retained evidence")
            _validate_portable_package_payload(name, payload)
            seen.add(name)
    if before_final_reread is not None:
        before_final_reread()
    if package_path.read_bytes() != data:
        raise VerificationError("package changed during verification")
    if evidence_root is not None:
        final_references, final_payloads = _evidence_snapshot(evidence_root)
        if (
            final_references != external_full_references
            or final_payloads != external_full_payloads
        ):
            raise VerificationError("external retained evidence changed during verification")


ROOTED_PATH_BOUNDARY = r"(?<![A-Za-z0-9_.*?/-])"
UNC_ROOTED_PATH_BOUNDARY = r"(?<![A-Za-z0-9_.:/-])"
DRIVE_ROOTED_PATH_PATTERN = re.compile(
    ROOTED_PATH_BOUNDARY + r"[A-Za-z]:[\\/]"
)
UNC_ROOTED_PATH_PATTERN = re.compile(
    UNC_ROOTED_PATH_BOUNDARY
    + r"(?:\\\\|//)[^\\/\s\"'<>|]+[\\/][^\\/\s\"'<>|]+"
)
UNIX_ROOTED_PATH_PATTERN = re.compile(
    ROOTED_PATH_BOUNDARY + r"/(?!/)(?=[^\\/\s])"
)
WINDOWS_ROOTED_PATH_PATTERN = re.compile(
    ROOTED_PATH_BOUNDARY + r"\\(?!\\)(?=[^\\/\s])"
)
MULTI_SEPARATOR_ROOTED_PATH_PATTERN = re.compile(
    UNC_ROOTED_PATH_BOUNDARY + r"[\\/]{2,}(?=[^\\/\s])"
)
LABELED_ROOTED_PATH_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_.-])(?:path|root)\s*(?:=|:)[ \t]*"
    r"(?:[A-Za-z]:)?[\\/]+",
    re.IGNORECASE,
)
FILE_URI_ROOTED_PATH_PATTERN = re.compile(r"\bfile:[\\/]+", re.IGNORECASE)
URI_SCHEME_WITH_AUTHORITY_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_+.-])[A-Za-z][A-Za-z0-9+.-]*://"
)
REGEX_ESCAPE_TOKEN = (
    r"\\(?:[AbBdDGsSwWZz]|[fnrtv])"
    r"(?:[+*?]|\{[0-9]+(?:,[0-9]*)?\})?"
)
REGEX_ESCAPE_PATTERN = re.compile(
    REGEX_ESCAPE_TOKEN + r"(?=$|\\|[\s|$,.;:)\]}])"
)
REGEX_ESCAPE_SEQUENCE_PATTERN = re.compile(
    r"(?:" + REGEX_ESCAPE_TOKEN + r")+(?=$|[\s|$,.;:)\]}])"
)
REGEX_ESCAPE_SEQUENCE_AT_END_PATTERN = re.compile(
    ROOTED_PATH_BOUNDARY + r"(?:" + REGEX_ESCAPE_TOKEN + r")+$"
)
SENSITIVE_FIELD_NAMES = {
    "accesskey", "accesstoken", "apikey", "authentication", "authorization",
    "cookie", "credential", "password", "privatekey", "refreshtoken", "secret",
    "sessiontoken",
}
SENSITIVE_FIELD_ALIASES = {"auth", "oauth", "passwd", "pwd", "token"}
COMPACT_CREDENTIAL_ALIASES = {"githubtoken", "oauthtoken", "proxyauth"}
CREDENTIAL_VALUE_PATTERN = re.compile(
    r"(?:"
    r"\b(?:auth|authorization|proxy[-_ ]?authorization|cookie|set[-_ ]?cookie|password|passwd|secret|access[-_ ]?token|refresh[-_ ]?token|api[-_ .]?key|private[-_ .]?key)\s*[:=]"
    r"|-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----"
    r"|[a-z][a-z0-9+.-]*://[^/\s:@]+:[^/\s@]+@"
    r"|\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}"
    r"|glpat-[A-Za-z0-9_-]{20,}|xox[baprs]-[A-Za-z0-9-]{20,}"
    r"|(?:AKIA|ASIA)[0-9A-Z]{16}|AIza[A-Za-z0-9_-]{20,}"
    r"|sk-(?:proj-)?[A-Za-z0-9_-]{20,})\b"
    r")",
    re.IGNORECASE,
)
AUTHORIZATION_SCHEME_PATTERN = re.compile(
    r"\b(basic|bearer)[ \t]+([A-Za-z0-9+/=._~-]+)", re.IGNORECASE
)
CREDENTIAL_ASSIGNMENT_PATTERN = re.compile(
    r"(?=(?:(?<!:):(?!:)|(?<![A-Za-z0-9_./:-]))(?:\$env:)?[\"']?"
    r"([A-Za-z][A-Za-z0-9_. -]{0,127})[\"']?\s*(?:=|:(?!:)))",
    re.MULTILINE,
)
COMPACT_CREDENTIAL_ASSIGNMENT_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])[\"']?"
    r"(?:github[_. -]*token|oauth[_. -]*token|proxy[_. -]*auth)[\"']?"
    r"(?![A-Za-z0-9])\s*(?:=|:(?!:))",
    re.IGNORECASE | re.MULTILINE,
)


def _sensitive_field(name: object) -> bool:
    separated = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", str(name))
    tokens = tuple(
        token for token in re.split(r"[^a-z0-9]+", separated.casefold()) if token
    )
    normalized = "".join(tokens)
    return (
        any(token in SENSITIVE_FIELD_ALIASES for token in tokens)
        or any(token in normalized for token in SENSITIVE_FIELD_NAMES)
        or normalized in COMPACT_CREDENTIAL_ALIASES
    )


def _portable_regex_escape_at(value: str, start: int) -> bool:
    if REGEX_ESCAPE_PATTERN.match(value, start) is not None:
        return True
    return (
        value.startswith(r"\.", start)
        and REGEX_ESCAPE_SEQUENCE_AT_END_PATTERN.search(value[:start]) is not None
        and REGEX_ESCAPE_SEQUENCE_PATTERN.match(value, start + 2) is not None
    )


def _contains_rooted_private_path(value: str) -> bool:
    value = value.replace("<REPOSITORY_ROOT>/", "repository/").replace(
        "<REPOSITORY_ROOT>\\", "repository/"
    ).replace("<EVIDENCE_ROOT>/", "evidence/").replace(
        "<EVIDENCE_ROOT>\\", "evidence/"
    )
    stripped = value.strip()
    if stripped and not stripped.strip("\\/"):
        return True
    if any(
        pattern.search(value) is not None
        for pattern in (
            DRIVE_ROOTED_PATH_PATTERN,
            UNC_ROOTED_PATH_PATTERN,
            UNIX_ROOTED_PATH_PATTERN,
            MULTI_SEPARATOR_ROOTED_PATH_PATTERN,
            FILE_URI_ROOTED_PATH_PATTERN,
        )
    ):
        return True
    uri_schemes = tuple(URI_SCHEME_WITH_AUTHORITY_PATTERN.finditer(value))
    for labeled_root in LABELED_ROOTED_PATH_PATTERN.finditer(value):
        if not (
            labeled_root.start() > 0
            and value[labeled_root.start() - 1] == "+"
            and any(
                uri_scheme.start() < labeled_root.start()
                and uri_scheme.end() == labeled_root.end()
                for uri_scheme in uri_schemes
            )
        ):
            return True
    return any(
        not _portable_regex_escape_at(value, match.start())
        for match in WINDOWS_ROOTED_PATH_PATTERN.finditer(value)
    )


def _contains_uri_userinfo(value: str) -> bool:
    for scheme in URI_SCHEME_WITH_AUTHORITY_PATTERN.finditer(value):
        authority_end = scheme.end()
        while (
            authority_end < len(value)
            and value[authority_end] not in "/?#"
            and not value[authority_end].isspace()
        ):
            authority_end += 1
        userinfo, separator, _ = value[scheme.end():authority_end].rpartition("@")
        if separator and userinfo:
            return True
    return False


def _authorization_token_is_credential(scheme: str, token: str) -> bool:
    if scheme.casefold() == "bearer":
        return True
    if scheme.casefold() == "basic":
        unpadded = token.rstrip("=")
        if not unpadded or "=" in unpadded:
            return False
        padded = unpadded + "=" * ((-len(unpadded)) % 4)
        try:
            decoded = base64.b64decode(padded, validate=True)
        except (binascii.Error, ValueError):
            return False
        return (
            b":" in decoded
            and base64.b64encode(decoded).decode("ascii").rstrip("=") == unpadded
        )
    return False


def _validate_portable_string(value: str) -> None:
    try:
        validate_portable_text(value)
    except ControllerError as exc:
        raise VerificationError(str(exc)) from exc


def _validate_portable_package_value(value: object) -> None:
    if isinstance(value, Mapping):
        for key, member in value.items():
            if _sensitive_field(key):
                raise VerificationError("package contains a credential field")
            _validate_portable_package_value(member)
    elif isinstance(value, list):
        for member in value:
            _validate_portable_package_value(member)
    elif isinstance(value, str):
        _validate_portable_string(value)


def _validate_portable_package_payload(name: str, payload: bytes) -> None:
    suffix = Path(name).suffix.casefold()
    if suffix == ".json":
        try:
            value = json.loads(payload.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise VerificationError("package JSON payload is unreadable") from exc
        _validate_portable_package_value(value)
    elif suffix in {".log", ".txt"}:
        try:
            text = payload.decode("utf-8")
        except UnicodeError as exc:
            raise VerificationError("package text payload is not UTF-8") from exc
        _validate_portable_string(text)
    elif suffix == ".xml":
        try:
            root = ElementTree.fromstring(payload)
        except (ElementTree.ParseError, UnicodeError) as exc:
            raise VerificationError("package XML payload is unreadable") from exc
        for element in root.iter():
            for value in (*element.attrib.values(), element.text or "", element.tail or ""):
                _validate_portable_string(value)


AUDIT_ROOT_KEYS = {
    "schema",
    "network",
    "advisory",
    "cache_sha256",
    "production",
    "development",
    "exceptions",
}
AUDIT_ADVISORY_KEYS = {"source", "database_version", "generated_at_utc", "sha256"}
AUDIT_SEVERITY_KEYS = {"critical", "high", "moderate", "low"}
AUDIT_EXCEPTION_KEYS = {
    "package",
    "advisory_id",
    "reachability",
    "approved_by",
    "approved_at_utc",
    "expires_at_utc",
    "mitigation",
}


def _parse_utc(value: object) -> datetime:
    if not isinstance(value, str) or re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z", value) is None:
        raise VerificationError("UTC timestamp is not canonical")
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise VerificationError("UTC timestamp is invalid") from exc


def validate_audit_evidence(
    value: object, *, readiness_at: datetime, candidate_started_at: datetime
) -> None:
    if not _closed(value, AUDIT_ROOT_KEYS):
        raise VerificationError("audit root is not closed")
    assert isinstance(value, Mapping)
    if value["schema"] != "stm32-offline-audit/1" or value["network"] is not False:
        raise VerificationError("audit is not pinned offline evidence")
    advisory = value["advisory"]
    if not _closed(advisory, AUDIT_ADVISORY_KEYS):
        raise VerificationError("advisory record is not closed")
    assert isinstance(advisory, Mapping)
    if (
        not all(isinstance(advisory[key], str) and advisory[key] for key in ("source", "database_version"))
        or not isinstance(advisory["sha256"], str)
        or HEX64.fullmatch(advisory["sha256"]) is None
        or not isinstance(value["cache_sha256"], str)
        or HEX64.fullmatch(value["cache_sha256"]) is None
    ):
        raise VerificationError("advisory/cache identity is invalid")
    generated = _parse_utc(advisory["generated_at_utc"])
    if generated > readiness_at or (readiness_at.date() - generated.date()).days > 7:
        raise VerificationError("advisory snapshot is stale")
    for name in ("production", "development"):
        severities = value[name]
        if not _closed(severities, AUDIT_SEVERITY_KEYS):
            raise VerificationError("audit severities are not closed")
        assert isinstance(severities, Mapping)
        if any(not _is_integer(item) or item < 0 for item in severities.values()):
            raise VerificationError("audit severity count is invalid")
    production = value["production"]
    development = value["development"]
    assert isinstance(production, Mapping) and isinstance(development, Mapping)
    if any(production.values()) or development["critical"] != 0 or development["high"] != 0:
        raise VerificationError("dependency vulnerability policy failed")
    exceptions = value["exceptions"]
    if not isinstance(exceptions, list):
        raise VerificationError("audit exceptions must be an array")
    for exception in exceptions:
        if not _closed(exception, AUDIT_EXCEPTION_KEYS):
            raise VerificationError("audit exception is not closed")
        assert isinstance(exception, Mapping)
        if (
            exception["approved_by"] != "user"
            or not all(isinstance(exception[key], str) and exception[key] for key in AUDIT_EXCEPTION_KEYS)
            or _parse_utc(exception["approved_at_utc"]) >= candidate_started_at
            or _parse_utc(exception["expires_at_utc"]) <= readiness_at
        ):
            raise VerificationError("audit exception is not pre-candidate and unexpired")


def calculate_performance_threshold(
    batch_p95_values: Sequence[int], *, clock_tick: int, design_maximum: int
) -> dict[str, int]:
    if (
        len(batch_p95_values) != 3
        or any(not _is_integer(item) or item <= 0 for item in batch_p95_values)
        or not _is_integer(clock_tick)
        or clock_tick <= 0
        or not _is_integer(design_maximum)
        or design_maximum <= 0
    ):
        raise VerificationError("performance calibration inputs are invalid")
    ordered = sorted(batch_p95_values)
    baseline = ordered[1]
    deviations = sorted(abs(item - baseline) for item in batch_p95_values)
    mad = deviations[1]
    margin = max(Fraction(baseline, 4), Fraction(3 * mad), Fraction(10 * clock_tick))
    raw = Fraction(baseline) + margin
    threshold = math.ceil(raw / clock_tick) * clock_tick
    if threshold > design_maximum:
        raise VerificationError("calculated performance threshold exceeds design maximum")
    return {"baseline": baseline, "mad": mad, "absolute_threshold": threshold}


PERFORMANCE_RUN_KEYS = {
    "schema", "mode", "module", "producer", "environment", "environment_sha256",
    "profile_sha256", "test_file", "test_file_sha256", "workloads",
}
PERFORMANCE_CONTRACT_KEYS = {
    "id", "kind", "unit", "quantile", "design_maximum", "relative_limit_ppm",
    "scale", "measurement", "observation_contract",
}
PERFORMANCE_WORKLOAD_KEYS = PERFORMANCE_CONTRACT_KEYS | {
    "workload_sha256", "warmup_samples", "batches", "observed_p95", "observed_mad",
    "accepted_baseline", "absolute_threshold", "observations",
}
PERFORMANCE_BROWSER_WORKLOAD_KEYS = PERFORMANCE_WORKLOAD_KEYS | {"browser_metrics"}
PERFORMANCE_CATALOG_WORKLOAD_KEYS = PERFORMANCE_CONTRACT_KEYS | {
    "workload_sha256", "calibrations",
}
PERFORMANCE_PYTHON_ENV_KEYS = {
    "schema", "support_profile_sha256", "platform", "platform_version", "architecture",
    "cpu_model", "physical_cores", "logical_cores", "memory_bytes", "storage_model",
    "power_profile", "antivirus_state", "python_version", "python_executable_sha256",
    "gc_enabled", "monotonic_clock", "monotonic_clock_tick_ns",
}
PERFORMANCE_BROWSER_ENV_KEYS = {
    "schema", "support_profile_sha256", "platform", "platform_version", "architecture",
    "cpu_model", "physical_cores", "logical_cores", "memory_bytes", "storage_model",
    "power_profile", "antivirus_state", "browser_name", "browser_version",
    "browser_executable_sha256", "playwright_version", "monotonic_clock",
    "monotonic_clock_tick_ns",
}
PERFORMANCE_MODULE_CONTRACTS = {
    "STM32TK-0601": {
        "python": (
            ("evidence-catalog-rebuild", 10_000_000_000, 3, 20),
            ("evidence-publish-reload", 500_000_000, 5, 30),
            ("evidence-summary-list", 500_000_000, 5, 30),
            ("target-decode-publish", 3_000_000_000, 3, 20),
        ),
    },
    "STM32TK-0602": {
        "python": (
            ("diagnostic-append-reload", 250_000_000, 5, 30),
            ("diagnostic-bundle-export-reverify", 5_000_000_000, 3, 20),
            ("diagnostic-chain-verify", 3_000_000_000, 3, 20),
            ("diagnostic-materialized-read", 500_000_000, 5, 30),
        ),
    },
    "STM32TK-0603": {
        "browser": (("browser-analysis-update", 150_000_000, 120, 12),),
        "python": (
            ("analytics-comparison-request", 1_000_000_000, 5, 30),
            ("analytics-quality-computation", 750_000_000, 5, 30),
        ),
    },
}
PERFORMANCE_TEST_FILES = {
    ("STM32TK-0601", "python"): "tools/stm32-toolkit/tests/test_evidence_performance.py",
    ("STM32TK-0602", "python"): "tools/stm32-toolkit/tests/test_diagnostic_performance.py",
    ("STM32TK-0603", "python"): "tools/stm32-monitor/tests/test_analysis_performance.py",
    ("STM32TK-0603", "browser"): "tools/stm32-monitor/ui/e2e/performance.spec.ts",
}


def _performance_digest(value: object) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _positive_integer(value: object) -> bool:
    return _is_integer(value) and value > 0


def _performance_contract(value: Mapping[str, object]) -> dict[str, object]:
    return {key: value[key] for key in PERFORMANCE_CONTRACT_KEYS}


def _validate_performance_workload_contract(value: object, *, catalog: bool) -> None:
    if catalog:
        keys = PERFORMANCE_CATALOG_WORKLOAD_KEYS
    elif isinstance(value, Mapping) and value.get("kind") == "browser-latency":
        keys = PERFORMANCE_BROWSER_WORKLOAD_KEYS
    else:
        keys = PERFORMANCE_WORKLOAD_KEYS
    error = CatalogError if catalog else VerificationError
    if not _closed(value, keys):
        raise error("performance workload is not closed")
    assert isinstance(value, Mapping)
    if (
        not isinstance(value["id"], str) or not value["id"]
        or value["kind"] not in {"latency", "browser-latency"}
        or value["unit"] != "ns"
        or value["quantile"] != "nearest-rank"
        or not _positive_integer(value["design_maximum"])
        or value["relative_limit_ppm"] != 150000
        or not isinstance(value["scale"], list) or not value["scale"]
        or not isinstance(value["observation_contract"], list)
        or not isinstance(value["measurement"], Mapping)
        or not isinstance(value["workload_sha256"], str)
        or HEX64.fullmatch(value["workload_sha256"]) is None
    ):
        raise error("performance workload contract is invalid")
    measurement = value["measurement"]
    if value["kind"] == "latency":
        if (
            not _closed(measurement, {"kind", "warmup_count", "batch_count", "samples_per_batch"})
            or measurement["kind"] != "sample-batches"
            or not _positive_integer(measurement["warmup_count"])
            or measurement["batch_count"] != 3
            or not _positive_integer(measurement["samples_per_batch"])
        ):
            raise error("performance measurement contract is invalid")
    elif (
        not _closed(measurement, {"kind", "warmup_seconds", "measurement_seconds", "batch_count", "batch_duration_seconds", "cadence_seconds", "interaction_order", "samples_per_batch"})
        or measurement["kind"] != "continuous-windows"
        or measurement["warmup_seconds"] != 120
        or measurement["measurement_seconds"] != 180
        or measurement["batch_count"] != 3
        or measurement["batch_duration_seconds"] != 60
        or measurement["cadence_seconds"] != 5
        or measurement["interaction_order"] != ["compare", "quality", "marker", "table"]
        or measurement["samples_per_batch"] != 12
    ):
        raise error("browser performance measurement contract is invalid")
    for field in ("scale", "observation_contract"):
        names: list[str] = []
        for item in value[field]:
            expected = {"name", "unit", "value"} if field == "scale" else {"name", "unit"}
            if not _closed(item, expected):
                raise error(f"performance {field} item is not closed")
            assert isinstance(item, Mapping)
            if not isinstance(item["name"], str) or not item["name"] or not isinstance(item["unit"], str) or not item["unit"]:
                raise error(f"performance {field} item is invalid")
            if field == "scale" and (not _is_integer(item["value"]) or item["value"] < 0):
                raise error("performance scale value is invalid")
            names.append(str(item["name"]))
        if names != sorted(names, key=lambda item: item.encode("utf-8")) or len(names) != len(set(names)):
            raise error(f"performance {field} is not sorted and unique")
    if value["workload_sha256"] != _performance_digest(_performance_contract(value)):
        raise error("performance workload digest mismatch")
    if catalog:
        calibrations = value["calibrations"]
        if not isinstance(calibrations, list):
            raise CatalogError("performance calibrations are invalid")
        identities: list[tuple[str, str]] = []
        for calibration in calibrations:
            if not _closed(calibration, {"runtime", "environment_sha256", "clock_tick", "batch_p95", "baseline", "mad", "absolute_threshold"}):
                raise CatalogError("performance calibration is not closed")
            assert isinstance(calibration, Mapping)
            runtime = calibration["runtime"]
            if not _closed(runtime, {"kind", "version"}):
                raise CatalogError("performance calibration runtime is not closed")
            assert isinstance(runtime, Mapping)
            if runtime["kind"] not in {"cpython", "chromium"} or not isinstance(runtime["version"], str) or not runtime["version"]:
                raise CatalogError("performance calibration runtime is invalid")
            if not isinstance(calibration["environment_sha256"], str) or HEX64.fullmatch(calibration["environment_sha256"]) is None:
                raise CatalogError("performance calibration environment digest is invalid")
            threshold = calculate_performance_threshold(
                calibration["batch_p95"],
                clock_tick=calibration["clock_tick"],
                design_maximum=value["design_maximum"],
            )
            if any(calibration[name] != threshold[name] for name in ("baseline", "mad", "absolute_threshold")):
                raise CatalogError("performance calibration math mismatch")
            identities.append((str(runtime["kind"]), str(runtime["version"])))
        if identities != sorted(identities) or len(identities) != len(set(identities)):
            raise CatalogError("performance calibrations are not sorted and unique")


def _nearest_rank(samples: Sequence[int], numerator: int, denominator: int) -> int:
    ordered = sorted(samples)
    return ordered[math.ceil(numerator * len(ordered) / denominator) - 1]


def validate_performance_run(value: object) -> dict[str, object]:
    if not _closed(value, PERFORMANCE_RUN_KEYS):
        raise VerificationError("performance run root is not closed")
    assert isinstance(value, Mapping)
    producer = value["producer"]
    if (
        value["schema"] != "stm32-performance-run/1"
        or value["mode"] not in {"calibrate", "verify"}
        or value["module"] not in {"STM32TK-0601", "STM32TK-0602", "STM32TK-0603"}
        or producer not in {"python", "browser"}
        or not isinstance(value["test_file"], str) or not value["test_file"]
        or not isinstance(value["test_file_sha256"], str) or HEX64.fullmatch(value["test_file_sha256"]) is None
        or not isinstance(value["workloads"], list) or not value["workloads"]
    ):
        raise VerificationError("performance run identity is invalid")
    if value["mode"] == "calibrate":
        if value["profile_sha256"] is not None:
            raise VerificationError("calibration run has a profile digest")
    elif not isinstance(value["profile_sha256"], str) or HEX64.fullmatch(value["profile_sha256"]) is None:
        raise VerificationError("verification run profile digest is invalid")
    if value["test_file"] != PERFORMANCE_TEST_FILES.get((str(value["module"]), str(producer))):
        raise VerificationError("performance test file differs from the frozen module producer")
    environment = value["environment"]
    env_keys = PERFORMANCE_PYTHON_ENV_KEYS if producer == "python" else PERFORMANCE_BROWSER_ENV_KEYS
    if not _closed(environment, env_keys):
        raise VerificationError("performance environment is not closed")
    assert isinstance(environment, Mapping)
    expected_schema = "stm32-performance-environment/1" if producer == "python" else "stm32-browser-performance-environment/1"
    if (
        environment["schema"] != expected_schema
        or not isinstance(environment["support_profile_sha256"], str)
        or HEX64.fullmatch(environment["support_profile_sha256"]) is None
        or not _positive_integer(environment["monotonic_clock_tick_ns"])
        or environment["monotonic_clock"] not in {"perf_counter_ns", "performance.now"}
    ):
        raise VerificationError("performance environment identity is invalid")
    required_text = (
        "platform", "platform_version", "architecture", "cpu_model", "storage_model",
        "power_profile", "antivirus_state",
    )
    if any(not isinstance(environment[name], str) or not environment[name] for name in required_text):
        raise VerificationError("performance environment text field is invalid")
    if (
        not _positive_integer(environment["physical_cores"])
        or not _positive_integer(environment["logical_cores"])
        or environment["logical_cores"] < environment["physical_cores"]
        or not _positive_integer(environment["memory_bytes"])
    ):
        raise VerificationError("performance environment hardware field is invalid")
    if producer == "python":
        if not re.fullmatch(r"3\.(10|12)\.\d+", str(environment["python_version"])):
            raise VerificationError("performance Python runtime is unsupported")
        if not isinstance(environment["python_executable_sha256"], str) or HEX64.fullmatch(environment["python_executable_sha256"]) is None:
            raise VerificationError("performance Python executable digest is invalid")
    else:
        if environment["browser_name"] != "chromium" or not isinstance(environment["browser_version"], str) or not environment["browser_version"]:
            raise VerificationError("performance browser runtime is unsupported")
        if not isinstance(environment["browser_executable_sha256"], str) or HEX64.fullmatch(environment["browser_executable_sha256"]) is None:
            raise VerificationError("performance browser executable digest is invalid")
    if not isinstance(value["environment_sha256"], str) or value["environment_sha256"] != _performance_digest(environment):
        raise VerificationError("performance environment digest mismatch")
    expected_workloads = PERFORMANCE_MODULE_CONTRACTS[str(value["module"])].get(str(producer))
    if expected_workloads is None or len(value["workloads"]) != len(expected_workloads):
        raise VerificationError("performance workload inventory differs from the frozen module")
    workload_ids: list[str] = []
    for workload, expected_workload in zip(value["workloads"], expected_workloads):
        _validate_performance_workload_contract(workload, catalog=False)
        assert isinstance(workload, Mapping)
        if (producer == "python") != (workload["kind"] == "latency"):
            raise VerificationError("performance workload producer kind mismatch")
        measurement = workload["measurement"]
        assert isinstance(measurement, Mapping)
        expected_id, expected_maximum, expected_warmup, expected_samples = expected_workload
        if workload["id"] != expected_id or workload["design_maximum"] != expected_maximum:
            raise VerificationError("performance workload identity/maximum differs from the frozen module")
        if producer == "python" and (measurement["warmup_count"], measurement["samples_per_batch"]) != (expected_warmup, expected_samples):
            raise VerificationError("performance workload sample plan differs from the frozen module")
        warmups = workload["warmup_samples"]
        batches = workload["batches"]
        warmup_count = measurement["warmup_count"] if producer == "python" else measurement["warmup_seconds"] // measurement["cadence_seconds"]
        samples_per_batch = measurement["samples_per_batch"]
        if (
            not isinstance(warmups, list) or len(warmups) != warmup_count
            or any(not _positive_integer(item) for item in warmups)
            or not isinstance(batches, list) or len(batches) != 3
        ):
            raise VerificationError("performance samples are invalid")
        batch_p95: list[int] = []
        raw_browser_metrics: list[Mapping[str, object]] = []
        for index, batch in enumerate(batches):
            batch_keys = {"index", "started_offset_ns", "duration_ns", "samples", "p50", "p95", "max"}
            if producer == "browser":
                batch_keys.add("metrics")
            if not _closed(batch, batch_keys):
                raise VerificationError("performance batch is not closed")
            assert isinstance(batch, Mapping)
            samples = batch["samples"]
            if (
                batch["index"] != index or not _is_integer(batch["started_offset_ns"]) or batch["started_offset_ns"] < 0
                or not _positive_integer(batch["duration_ns"])
                or not isinstance(samples, list) or len(samples) != samples_per_batch
                or any(not _positive_integer(item) for item in samples)
            ):
                raise VerificationError("performance batch samples are invalid")
            if producer == "browser":
                if (
                    batch["started_offset_ns"] != index * 60_000_000_000
                    or batch["duration_ns"] != 60_000_000_000
                    or not isinstance(batch["metrics"], list)
                    or len(batch["metrics"]) != 12
                ):
                    raise VerificationError("browser performance batch window is not contiguous")
                for sample_index, metric in enumerate(batch["metrics"]):
                    if not _closed(metric, {"offset_ns", "interaction", "duration_ns", "retained_heap_bytes", "queue_depth", "long_task_duration_ns"}):
                        raise VerificationError("browser performance metric is not closed")
                    assert isinstance(metric, Mapping)
                    global_index = index * 12 + sample_index
                    if (
                        metric["offset_ns"] != global_index * 5_000_000_000
                        or metric["interaction"] != ("compare", "quality", "marker", "table")[global_index % 4]
                        or metric["duration_ns"] != samples[sample_index]
                        or not _positive_integer(metric["retained_heap_bytes"])
                        or not _is_integer(metric["queue_depth"]) or metric["queue_depth"] < 0
                        or not _is_integer(metric["long_task_duration_ns"]) or metric["long_task_duration_ns"] < 0
                    ):
                        raise VerificationError("browser performance metric cadence/order/sample binding failed")
                    raw_browser_metrics.append(metric)
            expected = (_nearest_rank(samples, 1, 2), _nearest_rank(samples, 95, 100), max(samples))
            if (batch["p50"], batch["p95"], batch["max"]) != expected:
                raise VerificationError("performance batch p50/p95/max mismatch")
            batch_p95.append(expected[1])
        computed = calculate_performance_threshold(
            batch_p95,
            clock_tick=environment["monotonic_clock_tick_ns"],
            design_maximum=workload["design_maximum"],
        )
        if workload["observed_p95"] != computed["baseline"] or workload["observed_mad"] != computed["mad"]:
            raise VerificationError("performance observed median/MAD mismatch")
        if value["mode"] == "calibrate":
            if workload["accepted_baseline"] is not None or workload["absolute_threshold"] is not None:
                raise VerificationError("calibration run contains accepted thresholds")
        else:
            if not _positive_integer(workload["accepted_baseline"]) or not _positive_integer(workload["absolute_threshold"]):
                raise VerificationError("verification thresholds are invalid")
            if workload["observed_p95"] > workload["absolute_threshold"] or 20 * (workload["observed_p95"] - workload["accepted_baseline"]) > 3 * workload["accepted_baseline"]:
                raise VerificationError("performance verification threshold failed")
        observations = workload["observations"]
        if not isinstance(observations, list):
            raise VerificationError("performance observations are invalid")
        expected_observations = [(item["name"], item["unit"]) for item in workload["observation_contract"]]
        actual_observations: list[tuple[object, object]] = []
        for observation in observations:
            if not _closed(observation, {"name", "unit", "values"}):
                raise VerificationError("performance observation is not closed")
            assert isinstance(observation, Mapping)
            if not isinstance(observation["values"], list) or not observation["values"] or any(not _is_integer(item) or item < 0 for item in observation["values"]):
                raise VerificationError("performance observation values are invalid")
            actual_observations.append((observation["name"], observation["unit"]))
        if actual_observations != expected_observations:
            raise VerificationError("performance observation contract mismatch")
        if producer == "browser":
            metrics = workload["browser_metrics"]
            if not _closed(metrics, {"long_tasks_ge_200ms", "retained_heap_slope_bytes_per_minute", "queue_growth"}):
                raise VerificationError("browser performance metrics are not closed")
            assert isinstance(metrics, Mapping)
            first_metric = raw_browser_metrics[0]
            last_metric = raw_browser_metrics[-1]
            elapsed_ns = last_metric["offset_ns"] - first_metric["offset_ns"]
            derived_long_tasks = sum(item["long_task_duration_ns"] >= 200_000_000 for item in raw_browser_metrics)
            derived_heap_slope = (
                (last_metric["retained_heap_bytes"] - first_metric["retained_heap_bytes"])
                * 60_000_000_000 // elapsed_ns
            )
            derived_queue_growth = last_metric["queue_depth"] - first_metric["queue_depth"]
            if (
                metrics["long_tasks_ge_200ms"] != derived_long_tasks
                or metrics["retained_heap_slope_bytes_per_minute"] != derived_heap_slope
                or metrics["queue_growth"] != derived_queue_growth
                or metrics["long_tasks_ge_200ms"] != 0
                or not _is_integer(metrics["retained_heap_slope_bytes_per_minute"])
                or metrics["retained_heap_slope_bytes_per_minute"] < 0
                or metrics["retained_heap_slope_bytes_per_minute"] > 2 * 1024 * 1024
                or metrics["queue_growth"] != 0
            ):
                raise VerificationError("browser performance invariant failed")
        workload_ids.append(str(workload["id"]))
    if workload_ids != sorted(workload_ids, key=lambda item: item.encode("utf-8")) or len(workload_ids) != len(set(workload_ids)):
        raise VerificationError("performance workloads are not sorted and unique")
    return dict(value)


def aggregate_performance_calibration(profile: str, inputs: Sequence[Path], catalog_path: Path) -> dict[str, str]:
    expected = {
        "STM32TK-0601": {("python", "3.10"), ("python", "3.12")},
        "STM32TK-0602": {("python", "3.10"), ("python", "3.12")},
        "STM32TK-0603": {("python", "3.10"), ("python", "3.12"), ("browser", "chromium")},
    }
    if profile not in expected:
        raise VerificationError("performance profile is unknown")
    runs = [validate_performance_run(_read_canonical(Path(path))[1]) for path in inputs]
    identities: set[tuple[str, str]] = set()
    for run in runs:
        environment = run["environment"]
        assert isinstance(environment, Mapping)
        identity = ("python", ".".join(str(environment["python_version"]).split(".")[:2])) if run["producer"] == "python" else ("browser", str(environment["browser_name"]))
        identities.add(identity)
        if run["mode"] != "calibrate" or run["module"] != profile:
            raise VerificationError("performance input mode/profile mismatch")
    if len(runs) != len(expected[profile]) or identities != expected[profile]:
        raise VerificationError("performance input runtime set is incomplete or duplicated")
    catalog = load_performance_catalog(catalog_path)
    matches = [item for item in catalog["profiles"] if item["module"] == profile]
    if len(matches) > 1:
        raise VerificationError("performance catalog profile is duplicated")
    if not matches:
        producers: list[dict[str, object]] = []
        for producer_name in sorted(PERFORMANCE_MODULE_CONTRACTS[profile]):
            producer_runs = [item for item in runs if item["producer"] == producer_name]
            representative = producer_runs[0]
            if any(
                item["test_file"] != representative["test_file"]
                or item["test_file_sha256"] != representative["test_file_sha256"]
                for item in producer_runs[1:]
            ):
                raise VerificationError("performance input test identity differs by runtime")
            producers.append({
                "producer": producer_name,
                "test_file": representative["test_file"],
                "test_file_sha256": representative["test_file_sha256"],
                "workloads": [
                    {**_performance_contract(item), "workload_sha256": item["workload_sha256"], "calibrations": []}
                    for item in representative["workloads"]
                ],
            })
        target = {"module": profile, "profile_sha256": "0" * 64, "producers": producers}
        catalog["profiles"].append(target)
        catalog["profiles"].sort(key=lambda item: item["module"])
    else:
        target = matches[0]
    for producer in target["producers"]:
        producer_runs = [item for item in runs if item["producer"] == producer["producer"]]
        for run in producer_runs:
            if run["test_file"] != producer["test_file"] or run["test_file_sha256"] != producer["test_file_sha256"]:
                raise VerificationError("performance input test identity mismatch")
        for workload in producer["workloads"]:
            calibrations: list[dict[str, object]] = []
            for run in producer_runs:
                measured = [item for item in run["workloads"] if item["id"] == workload["id"]]
                if len(measured) != 1 or measured[0]["workload_sha256"] != workload["workload_sha256"]:
                    raise VerificationError("performance input workload identity mismatch")
                item = measured[0]
                environment = run["environment"]
                assert isinstance(environment, Mapping)
                batch_p95 = [batch["p95"] for batch in item["batches"]]
                calculated = calculate_performance_threshold(batch_p95, clock_tick=environment["monotonic_clock_tick_ns"], design_maximum=workload["design_maximum"])
                runtime = {"kind": "cpython", "version": environment["python_version"]} if run["producer"] == "python" else {"kind": "chromium", "version": environment["browser_version"]}
                calibrations.append({"runtime": runtime, "environment_sha256": run["environment_sha256"], "clock_tick": environment["monotonic_clock_tick_ns"], "batch_p95": batch_p95, **calculated})
            workload["calibrations"] = sorted(calibrations, key=lambda item: (item["runtime"]["kind"], item["runtime"]["version"]))
    target["profile_sha256"] = _performance_digest({"module": target["module"], "producers": target["producers"]})
    validate_performance_catalog_data(catalog)
    encoded = canonical_json_bytes(catalog)
    temporary: Path | None = None
    try:
        descriptor, raw_temporary = tempfile.mkstemp(
            prefix=f".{catalog_path.name}.", suffix=".tmp", dir=catalog_path.parent
        )
        temporary = Path(raw_temporary)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, catalog_path)
    except OSError as exc:
        raise VerificationError("performance catalog update failed") from exc
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
    return {"mode": "performance-calibration", "profile": profile, "status": "PASS"}


def verify_performance_calibration_input(value: object) -> dict[str, object]:
    if not _closed(value, {"schema", "batch_p95", "clock_tick", "design_maximum"}):
        raise VerificationError("performance calibration input is not closed")
    assert isinstance(value, Mapping)
    if value["schema"] != "stm32-performance-calibration-input/1" or not isinstance(value["batch_p95"], list):
        raise VerificationError("performance calibration input identity is invalid")
    threshold = calculate_performance_threshold(
        value["batch_p95"],
        clock_tick=value["clock_tick"],
        design_maximum=value["design_maximum"],
    )
    return {"mode": "performance-calibration", "status": "PASS", **threshold}


def verify_dependency_audit_input(value: object) -> dict[str, str]:
    if not _closed(
        value,
        {"schema", "readiness_at_utc", "candidate_started_at_utc", "audit"},
    ):
        raise VerificationError("dependency audit input is not closed")
    assert isinstance(value, Mapping)
    if value["schema"] != "stm32-dependency-audit-input/1":
        raise VerificationError("dependency audit input identity is invalid")
    readiness = _parse_utc(value["readiness_at_utc"])
    candidate = _parse_utc(value["candidate_started_at_utc"])
    validate_audit_evidence(
        value["audit"], readiness_at=readiness, candidate_started_at=candidate
    )
    return {"mode": "dependency-audit", "status": "PASS"}


def parse_npm_audit_v2(value: object) -> dict[str, int]:
    """Consume only npm 11 audit-report-v2 fields used by the frozen severity policy."""
    if not isinstance(value, Mapping) or value.get("auditReportVersion") != 2:
        raise VerificationError("npm audit report version is unsupported")
    vulnerabilities = value.get("vulnerabilities")
    metadata = value.get("metadata")
    if not isinstance(vulnerabilities, Mapping) or not isinstance(metadata, Mapping):
        raise VerificationError("npm audit report structure is invalid")
    counts = metadata.get("vulnerabilities")
    required = ("info", "low", "moderate", "high", "critical", "total")
    if not isinstance(counts, Mapping) or any(not _is_integer(counts.get(name)) or counts[name] < 0 for name in required):
        raise VerificationError("npm audit severity counts are invalid")
    derived = {name: 0 for name in required[:-1]}
    for item in vulnerabilities.values():
        if not isinstance(item, Mapping) or item.get("severity") not in derived:
            raise VerificationError("npm audit vulnerability severity is invalid")
        derived[str(item["severity"])] += 1
    if sum(derived.values()) != counts["total"] or any(derived[name] != counts[name] for name in derived):
        raise VerificationError("npm audit severity summary differs from vulnerability inventory")
    return {name: int(counts[name]) for name in required}


def run_planned_dependency_audit(
    *, repository: Path, ui_root_text: str, catalog_text: str,
    support_profile: Path, evidence_root: Path,
    runner: Callable[[list[str], Path], object] | None = None,
    after_location_check: Callable[[], object] | None = None,
    _temporary_root: Path = Path(r"C:\tmp"),
) -> dict[str, str]:
    if ui_root_text != "tools/stm32-monitor/ui" or catalog_text != "tools/release/gates_0600.json":
        raise VerificationError("dependency audit repository paths are not frozen")
    repo = repository.resolve(strict=True)
    ui_root = repo.joinpath(*ui_root_text.split("/"))
    catalog = repo.joinpath(*catalog_text.split("/"))
    _canonical_absolute(str(support_profile), "dependency audit support profile")
    _canonical_absolute(str(evidence_root), "dependency audit evidence")
    for path in (ui_root / "package.json", ui_root / "package-lock.json", catalog, support_profile):
        _assert_no_reparse_chain(path, allow_absent_leaf=False)
        if not _regular_file(path):
            raise VerificationError("dependency audit frozen input is missing/linked/special")
    if _temporary_root != Path(r"C:\tmp") and "PYTEST_CURRENT_TEST" not in os.environ:
        raise VerificationError("dependency audit temporary root override is test-only")
    _require_direct_child(evidence_root, _temporary_root, "dependency audit evidence root")
    invoke = runner or (
        lambda argv, cwd: subprocess.run(
            argv, cwd=cwd, capture_output=True, check=False,
            env={**os.environ, "npm_config_offline": "true", "npm_config_audit": "true"},
        )
    )
    with ExitStack() as locks:
        temporary_lock, _ = _enter_locked_directory(locks, _temporary_root)
        if after_location_check is not None:
            after_location_check()
        secure = _secure_io()
        try:
            secure._validate_locked_coverage_directory(temporary_lock)
            _require_direct_child(evidence_root, _temporary_root, "dependency audit evidence root")
            evidence_root.mkdir()
        except (FileExistsError, secure.ControllerError) as exc:
            raise VerificationError("dependency audit evidence root create-new failed") from exc
        evidence_lock, _ = _enter_locked_directory(locks, evidence_root)
        reports: dict[str, dict[str, int]] = {}
        for name, extra in (("production", ["--omit=dev"]), ("development", [])):
            argv = ["npm.cmd", "audit", "--offline", "--json", *extra]
            child = invoke(argv, ui_root)
            stdout = getattr(child, "stdout", None)
            returncode = getattr(child, "returncode", None)
            if not isinstance(stdout, bytes) or not _is_integer(returncode):
                raise VerificationError("npm audit runner result is invalid")
            _locked_create(locks, evidence_root / f"npm-audit-{name}.json", stdout)
            try:
                native = json.loads(stdout.decode("utf-8"))
            except (UnicodeError, json.JSONDecodeError) as exc:
                raise VerificationError("npm audit native JSON is unreadable") from exc
            reports[name] = parse_npm_audit_v2(native)
        production, development = reports["production"], reports["development"]
        if any(production[name] for name in ("info", "low", "moderate", "high", "critical")):
            raise VerificationError("dependency production vulnerability policy failed")
        if development["critical"] or development["high"]:
            raise VerificationError("dependency development vulnerability policy failed")
        summary = {"schema": "stm32-npm-audit-native-summary/1", "production": production, "development": development}
        _locked_create(locks, evidence_root / "dependency-audit-native-summary.json", canonical_json_bytes(summary))
        secure._validate_locked_coverage_directory(evidence_lock)
        try:
            support = json.loads(support_profile.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise VerificationError("dependency audit support profile is unreadable") from exc
        if not isinstance(support, Mapping) or "dependency_audit" not in support:
            raise VerificationError("BLOCKED: support profile lacks pinned dependency advisory/cache inputs")
        raise VerificationError("BLOCKED: pinned dependency advisory/cache contract is not available")


RECOVERY_KEYS = {
    "classification",
    "event",
    "reviewer",
    "recorded_at_utc",
    "run_kind",
    "run_id",
    "code_head",
    "checkpoint",
    "interrupted_attempt_digest",
}
RECOVERY_EVENTS = {
    "HOST_POWER_OR_REBOOT",
    "RUNNER_LOSS_BEFORE_CHILD_RESULT",
    "PHYSICAL_USB_OR_PROBE_REMOVAL",
    "TARGET_POWER_LOSS",
}
RECOVERY_RUN_KINDS = {
    "candidate-0601",
    "candidate-0602",
    "candidate-0603",
    "final-windows",
    "hardware-0400",
    "hardware-0600",
}


def _canonical_absolute(value: object, name: str) -> str:
    if not isinstance(value, str) or not value or not value.strip():
        raise VerificationError(f"{name} is empty")
    if re.match(r"^[A-Za-z]:[^\\/]", value) or re.match(r"^[\\/](?![\\/])", value):
        raise VerificationError(f"{name} is drive/root-relative")
    if value.startswith(("\\\\?\\", "\\\\.\\", "\\??\\")):
        raise VerificationError(f"{name} is an alias path")
    if len(value) > 3 and value.endswith(("\\", "/")):
        raise VerificationError(f"{name} has a trailing separator")
    if not os.path.isabs(value) or value != os.path.abspath(value):
        raise VerificationError(f"{name} is not canonical absolute")
    return value


def validate_recovery_record(
    value: object,
    *,
    expected_run_kind: str,
    expected_run_id: str,
    expected_code_head: str,
    expected_checkpoint: Path,
    expected_attempt_digest: str,
) -> None:
    if not _closed(value, RECOVERY_KEYS):
        raise VerificationError("RecoveryRecord is not closed")
    assert isinstance(value, Mapping)
    checkpoint = _canonical_absolute(value["checkpoint"], "checkpoint")
    if (
        value["classification"] != "RECOVERABLE_INFRA_ERROR"
        or value["event"] not in RECOVERY_EVENTS
        or value["run_kind"] not in RECOVERY_RUN_KINDS
        or value["run_kind"] != expected_run_kind
        or not isinstance(value["reviewer"], str)
        or not value["reviewer"]
        or not isinstance(value["recorded_at_utc"], str)
        or UTC_PATTERN.fullmatch(value["recorded_at_utc"]) is None
        or not isinstance(value["run_id"], str)
        or UUID_PATTERN.fullmatch(value["run_id"]) is None
        or value["run_id"] != expected_run_id
        or not isinstance(value["code_head"], str)
        or HEX40.fullmatch(value["code_head"]) is None
        or value["code_head"] != expected_code_head
        or checkpoint != str(expected_checkpoint)
        or not isinstance(value["interrupted_attempt_digest"], str)
        or HEX64.fullmatch(value["interrupted_attempt_digest"]) is None
        or value["interrupted_attempt_digest"] != expected_attempt_digest
    ):
        raise VerificationError("RecoveryRecord binding or enum is invalid")
    _parse_utc(value["recorded_at_utc"])


CANDIDATE_KEYS = {
    "schema",
    "module",
    "candidate_run_id",
    "expected_code_head",
    "controller_path",
    "candidate_root",
    "evidence_root",
    "catalog_sha256",
    "performance_sha256",
    "support_profile_sha256",
    "checkpoint",
    "state",
    "created_at_utc",
    "updated_at_utc",
}
CANDIDATE_STATES = {"prepared", "running", "passed", "failed", "blocked"}
CANDIDATE_CONTROLLER_RELATIVE = "tools/release/run_0600_candidate.ps1"
CANDIDATE_DERIVED_PATHS = {
    "controller": CANDIDATE_CONTROLLER_RELATIVE,
    "verifier": VERIFIER_RELATIVE_PATH,
    "catalog": "tools/release/gates_0600.json",
    "performance": "tools/release/performance_0600.json",
}


def validate_candidate_ledger(value: object) -> dict[str, object]:
    if not _closed(value, CANDIDATE_KEYS):
        raise VerificationError("candidate ledger is not closed")
    assert isinstance(value, Mapping)
    paths = {
        name: _canonical_absolute(value[name], name)
        for name in ("controller_path", "candidate_root", "evidence_root")
    }
    checkpoint = value["checkpoint"]
    if checkpoint is not None:
        _canonical_absolute(checkpoint, "checkpoint")
    if (
        value["schema"] != "stm32-candidate-ledger/1"
        or value["module"] not in {"STM32TK-0601", "STM32TK-0602", "STM32TK-0603"}
        or not isinstance(value["candidate_run_id"], str)
        or UUID_PATTERN.fullmatch(value["candidate_run_id"]) is None
        or not isinstance(value["expected_code_head"], str)
        or HEX40.fullmatch(value["expected_code_head"]) is None
        or any(not isinstance(value[name], str) or HEX64.fullmatch(value[name]) is None for name in ("catalog_sha256", "performance_sha256", "support_profile_sha256"))
        or value["state"] not in CANDIDATE_STATES
        or not isinstance(value["created_at_utc"], str)
        or not isinstance(value["updated_at_utc"], str)
    ):
        raise VerificationError("candidate ledger value is invalid")
    created = _parse_utc(value["created_at_utc"])
    updated = _parse_utc(value["updated_at_utc"])
    if updated < created:
        raise VerificationError("candidate ledger time moved backward")
    controller = Path(paths["controller_path"])
    candidate = Path(paths["candidate_root"])
    evidence = Path(paths["evidence_root"])
    try:
        worktree = controller.parents[2]
        if controller.relative_to(worktree).as_posix() != CANDIDATE_CONTROLLER_RELATIVE:
            raise VerificationError("candidate controller path is not fixed")
        evidence.relative_to(candidate)
        if checkpoint is not None:
            Path(str(checkpoint)).relative_to(candidate)
    except (IndexError, ValueError) as exc:
        raise VerificationError("candidate paths are not root-bound") from exc
    return dict(value)


def create_candidate_ledger(
    *,
    module: str = "STM32TK-0601",
    controller_path: Path,
    candidate_root: Path,
    evidence_root: Path,
    run_id: str,
    expected_code_head: str,
    catalog_sha256: str,
    performance_sha256: str,
    support_profile_sha256: str,
    now: datetime,
) -> dict[str, object]:
    timestamp = now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    value = {
        "schema": "stm32-candidate-ledger/1",
        "module": module,
        "candidate_run_id": run_id,
        "expected_code_head": expected_code_head,
        "controller_path": str(controller_path),
        "candidate_root": str(candidate_root),
        "evidence_root": str(evidence_root),
        "catalog_sha256": catalog_sha256,
        "performance_sha256": performance_sha256,
        "support_profile_sha256": support_profile_sha256,
        "checkpoint": None,
        "state": "prepared",
        "created_at_utc": timestamp,
        "updated_at_utc": timestamp,
    }
    validate_candidate_ledger(value)
    return value


def write_candidate_ledger(path: Path, value: object, *, previous: object | None = None) -> None:
    candidate = validate_candidate_ledger(value)
    if path != Path(str(candidate["candidate_root"])) / "candidate-ledger.json":
        raise VerificationError("candidate ledger path is not wrapper-owned")
    if previous is not None:
        prior = validate_candidate_ledger(previous)
        immutable = {
            "schema",
            "module",
            "candidate_run_id",
            "expected_code_head",
            "controller_path",
            "candidate_root",
            "evidence_root",
            "catalog_sha256",
            "performance_sha256",
            "support_profile_sha256",
            "created_at_utc",
        }
        if any(prior[key] != candidate[key] for key in immutable):
            raise VerificationError("candidate immutable identity changed")
    temporary = path.with_name("candidate-ledger.json.tmp")
    temporary.write_bytes(canonical_json_bytes(candidate))
    os.replace(temporary, path)


def _default_git(repository: Path) -> Callable[[list[str]], str]:
    def run(args: list[str]) -> str:
        completed = subprocess.run(
            ["git", "-C", str(repository), *args],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            raise VerificationError("local Git verification failed")
        return completed.stdout

    return run


def _forbidden_context(value: object) -> bool:
    forbidden = {"executable", "command", "controller", "verifier", "catalog", "performance", "config"}
    if isinstance(value, Mapping):
        for key, member in value.items():
            if any(token in str(key).casefold() for token in forbidden) or _forbidden_context(member):
                return True
    elif isinstance(value, list):
        return any(_forbidden_context(item) for item in value)
    return False


def reconcile_candidate(
    ledger: object,
    *,
    git_runner: Callable[[list[str]], str] | None = None,
    invocation_context: object | None = None,
) -> Path:
    value = validate_candidate_ledger(ledger)
    if invocation_context is not None and _forbidden_context(invocation_context):
        raise VerificationError("candidate invocation context supplies an authoritative path")
    controller = Path(str(value["controller_path"]))
    worktree = controller.parents[2]
    git = git_runner or _default_git(worktree)
    if git(["rev-parse", "HEAD"]).strip() != value["expected_code_head"]:
        raise VerificationError("candidate worktree HEAD mismatch")
    if git(["config", "--get", "remote.origin.url"]).strip() != REPOSITORY_URL:
        raise VerificationError("candidate origin mismatch")
    if git(["status", "--porcelain=v1", "--untracked-files=all"]) != "":
        raise VerificationError("candidate worktree is dirty")
    derived: dict[str, Path] = {}
    for name, relative in CANDIDATE_DERIVED_PATHS.items():
        path = worktree.joinpath(*relative.split("/"))
        if not _regular_file(path):
            raise VerificationError("candidate derived file is missing/uncommitted")
        working = git(["hash-object", "--", str(path)]).strip()
        committed = git(["rev-parse", f"{value['expected_code_head']}:{relative}"]).strip()
        if HEX40.fullmatch(working) is None or working != committed:
            raise VerificationError("candidate derived file blob mismatch")
        derived[name] = path
    if hashlib.sha256(derived["catalog"].read_bytes()).hexdigest() != value["catalog_sha256"]:
        raise VerificationError("candidate catalog digest mismatch")
    if hashlib.sha256(derived["performance"].read_bytes()).hexdigest() != value["performance_sha256"]:
        raise VerificationError("candidate performance digest mismatch")
    return derived["verifier"]


def verify_loaded_script_entry(
    *,
    repository: Path,
    expected_code_head: str | None,
    script_path: Path | None = None,
    before_first_action: Callable[[], object] | None = None,
    dispatch_recorder: list[str] | None = None,
    git_runner: Callable[[list[str]], str] | None = None,
) -> str:
    repo = repository.resolve(strict=True)
    script = script_path or Path(__file__)
    try:
        verifier = script.resolve(strict=True)
        relative = verifier.relative_to(repo).as_posix()
    except (OSError, ValueError) as exc:
        raise VerificationError("loaded verifier path is outside repository") from exc
    if relative != VERIFIER_RELATIVE_PATH:
        raise VerificationError("loaded verifier path is not fixed")
    if before_first_action is not None:
        before_first_action()
    git = git_runner or _default_git(repo)
    head = git(["rev-parse", "HEAD"]).strip()
    if HEX40.fullmatch(head) is None or (expected_code_head is not None and head != expected_code_head):
        raise VerificationError("loaded verifier HEAD mismatch")
    if git(["status", "--porcelain=v1", "--untracked-files=all"]) != "":
        raise VerificationError("loaded verifier worktree is dirty")
    committed = git(["rev-parse", f"{head}:{VERIFIER_RELATIVE_PATH}"]).strip()
    working = git(["hash-object", "--", str(verifier)]).strip()
    if HEX40.fullmatch(committed) is None or working != committed:
        raise VerificationError("loaded verifier on-disk blob mismatch")
    if dispatch_recorder:
        raise VerificationError("entry check must precede gate dispatch")
    return head


LEDGER_KEYS = {
    "schema",
    "repositoryUrl",
    "programBase",
    "0400Product",
    "0400Report",
    "0601Product",
    "0601Report",
    "0602Product",
    "0602Report",
    "0603Product",
    "governance",
    "softwareInput",
    "hardwareInput",
    "hardware",
    "artifacts",
}
SOFTWARE_KEYS = {
    "repositoryUrl",
    "programBase",
    "0400Product",
    "0400Report",
    "0601Product",
    "0601Report",
    "0602Product",
    "0602Report",
    "0603Product",
    "governance",
    "artifacts",
}
IDENTITY_KEYS = (
    "repositoryUrl",
    "programBase",
    "0400Product",
    "0400Report",
    "0601Product",
    "0601Report",
    "0602Product",
    "0602Report",
    "0603Product",
)
GOVERNANCE_KEYS = {
    "specification_owner",
    "implementation_owner",
    "reviewer",
    "windows_evidence_owner",
    "hardware_evidence_owner",
    "remote_state",
    "remote_actions",
    "bounded_overrides",
}
SOURCE_REFERENCE_KEYS = {"path", "bytes", "sha256"}
HARDWARE_KEYS = {
    "schema",
    "campaign_id",
    "created_at_utc",
    "generator_code_head",
    "evidence_owner",
    "board_id",
    "board_revision",
    "mcu_part",
    "mcu_uid_hash",
    "probe_model",
    "probe_serial_hash",
    "uart_adapter_model",
    "uart_serial_hash",
    "power_identity",
    "transports",
    "support_profile",
    "support_manifest",
    "firmware_0400",
    "firmware_0600",
}
FIRMWARE_REFERENCE_KEYS = {"path", "bytes", "sha256", "build_id"}
ARTIFACT_KEYS = {"kind", "path", "bytes", "sha256"}
ARTIFACT_KINDS = {
    "catalog",
    "controller",
    "verifier",
    "spec",
    "plan",
    "lock",
    "software-support",
    "hardware-support",
    "firmware",
}
SOFTWARE_ARTIFACT_KINDS = ARTIFACT_KINDS - {"hardware-support", "firmware"}
REPOSITORY_ARTIFACT_KINDS = {
    "catalog",
    "controller",
    "verifier",
    "spec",
    "plan",
    "lock",
}

FINAL_CONTEXT_KEYS = {
    "schema", "module", "shard", "candidate_run_id", "code_head",
    "frozen_worktree", "origin_url", "candidate_root", "evidence_root",
    "support_profile", "wrapper_ledger", "catalog_sha256", "performance_sha256",
    "support_profile_sha256", "controller_sha256", "verifier_sha256",
}
FINAL_REPOSITORY_ARTIFACTS = {
    "catalog": (
        "tools/release/gates_0600.json", "tools/release/performance_0600.json",
    ),
    "controller": (
        "tools/release/path_contract_0600.ps1", "tools/release/run_0600_gates.py",
        "tools/release/run_0600_quick.ps1", "tools/release/run_0600_candidate.ps1",
        "tools/release/run_0600_final.ps1", "tools/release/run_0600_hardware.ps1",
    ),
    "verifier": (
        "tools/release/verify_0600_feasibility.py", "tools/release/verify_0600_release.py",
    ),
    "spec": tuple(f"docs/superpowers/specs/2026-08-14-stm32tk-060{n}-{suffix}" for n, suffix in (
        (0, "evidence-diagnostics-program-design.md"), (1, "test-evidence-design.md"),
        (2, "diagnostic-loop-design.md"), (3, "monitor-analytics-design.md"),
    )),
    "plan": tuple(f"docs/superpowers/plans/2026-08-14-stm32tk-060{n}-{suffix}" for n, suffix in (
        (0, "release-acceptance.md"), (1, "test-evidence.md"),
        (2, "diagnostic-loop.md"), (3, "monitor-analytics.md"),
    )),
    "lock": ("tools/stm32-monitor/ui/package-lock.json",),
}
PLACEHOLDERS = {
    "dummy", "example", "fixture", "n/a", "na", "nil", "none", "null",
    "placeholder", "redacted", "reserved", "sample", "test", "todo", "tbd",
    "unknown", "unset",
}
PLACEHOLDER_AFFIXES = {
    "dummy", "example", "fixture", "na", "nil", "none", "null", "placeholder",
    "redacted", "reserved", "sample", "test", "todo", "tbd", "unknown", "unset",
}


def _normalized_identifier_tokens(value: str) -> tuple[str, ...]:
    """Split an NFC identifier at semantic ASCII word boundaries."""
    normalized = unicodedata.normalize("NFC", value)
    coarse = re.findall(r"[a-z]+|[0-9]+", normalized.casefold())
    semantic = [
        item.casefold()
        for item in re.findall(
            r"[A-Z]+(?=[A-Z][a-z]|[0-9]|$)|[A-Z]?[a-z]+|[A-Z]+|[0-9]+",
            normalized,
        )
    ]
    component_boundaries = re.sub(
        r"(?<=[A-Z])(?=[A-Z][a-z])", " ", normalized
    )
    component_boundaries = re.sub(
        r"(?<=[a-z0-9])(?=[A-Z])", " ", component_boundaries
    )
    component_boundaries = re.sub(
        r"(?<=[A-Za-z])(?=[0-9])|(?<=[0-9])(?=[A-Za-z])",
        " ",
        component_boundaries,
    )
    if re.search(
        r"(?i)(?<![A-Za-z0-9])n\s*/\s*a(?![A-Za-z0-9])",
        component_boundaries,
    ):
        semantic.append("na")
    return tuple(dict.fromkeys([*coarse, *semantic]))


def _read_canonical(path: Path) -> tuple[bytes, object]:
    try:
        data = path.read_bytes()
        if data.startswith(b"\xef\xbb\xbf"):
            raise VerificationError("canonical JSON has a BOM")
        text = data.decode("utf-8", errors="strict")

        def pairs_hook(pairs: list[tuple[str, object]]) -> dict[str, object]:
            result: dict[str, object] = {}
            for key, value in pairs:
                if key in result:
                    raise VerificationError("canonical JSON has a duplicate key")
                result[key] = value
            return result

        value = json.loads(
            text,
            object_pairs_hook=pairs_hook,
            parse_float=lambda text: (_ for _ in ()).throw(VerificationError("float forbidden")),
            parse_constant=lambda text: (_ for _ in ()).throw(VerificationError("constant forbidden")),
        )
    except VerificationError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise VerificationError("canonical JSON is unreadable") from exc
    if data != canonical_json_bytes(value):
        raise VerificationError("JSON bytes are not canonical")
    return data, value


def _read_sidecar(path: Path, data: bytes) -> bytes:
    try:
        sidecar = path.read_bytes()
    except OSError as exc:
        raise VerificationError("digest sidecar is unreadable") from exc
    expected = (hashlib.sha256(data).hexdigest() + "\n").encode("ascii")
    if sidecar != expected:
        raise VerificationError("digest sidecar mismatch")
    return sidecar


def _validate_governance(value: object) -> None:
    if not _closed(value, GOVERNANCE_KEYS):
        raise VerificationError("governance is not closed")
    assert isinstance(value, Mapping)
    if any(value[key] != expected for key, expected in GOVERNANCE_OWNERS.items()):
        raise VerificationError("governance owner mismatch")
    remote_state = value["remote_state"]
    if not isinstance(remote_state, str) or not remote_state or len(remote_state.encode("utf-8")) > 256 or unicodedata.normalize("NFC", remote_state) != remote_state:
        raise VerificationError("remote state is invalid")
    for name in ("remote_actions", "bounded_overrides"):
        members = value[name]
        if (
            not isinstance(members, list)
            or any(not isinstance(item, str) or not item or len(item.encode("utf-8")) > 256 or unicodedata.normalize("NFC", item) != item for item in members)
            or len(members) != len(set(members))
            or members != sorted(members, key=lambda item: item.encode("utf-8"))
        ):
            raise VerificationError("governance string array is invalid")


def _validate_source_reference(
    value: object, *, expected_path: Path, data: bytes, sidecar: bytes
) -> None:
    if not _closed(value, SOURCE_REFERENCE_KEYS):
        raise VerificationError("source reference is not closed")
    assert isinstance(value, Mapping)
    digest = hashlib.sha256(data).hexdigest()
    if (
        value["path"] != str(expected_path)
        or not _is_integer(value["bytes"])
        or value["bytes"] != len(data)
        or value["sha256"] != digest
        or sidecar != (digest + "\n").encode("ascii")
    ):
        raise VerificationError("source reference mismatch")


def _bounded_identity(value: object) -> bool:
    if not isinstance(value, str):
        return False
    normalized = unicodedata.normalize("NFC", value)
    folded = normalized.casefold()
    tokens = _normalized_identifier_tokens(normalized)
    return (
        bool(value)
        and value == value.strip()
        and folded not in PLACEHOLDERS
        and bool(tokens)
        and not any(token in PLACEHOLDER_AFFIXES for token in tokens)
        and normalized == value
        and len(value.encode("utf-8")) <= 256
    )


def _validate_external_reference(value: object, keys: set[str]) -> tuple[Path, bytes]:
    if not _closed(value, keys):
        raise VerificationError("hardware file reference is not closed")
    assert isinstance(value, Mapping)
    path = Path(_canonical_absolute(value["path"], "hardware file path"))
    if not _regular_file(path):
        raise VerificationError("hardware file is missing/linked/special")
    data = path.read_bytes()
    if (
        not _is_integer(value["bytes"])
        or value["bytes"] != len(data)
        or not isinstance(value["sha256"], str)
        or value["sha256"] != hashlib.sha256(data).hexdigest()
    ):
        raise VerificationError("hardware file bytes/digest mismatch")
    return path, data


def _validate_hardware(value: object, *, product_0603: str, owner: str) -> dict[str, bytes]:
    if not _closed(value, HARDWARE_KEYS):
        raise VerificationError("hardware input root is not closed")
    assert isinstance(value, Mapping)
    if (
        value["schema"] != "stm32-hardware-campaign-inputs/1"
        or not isinstance(value["campaign_id"], str)
        or UUID_PATTERN.fullmatch(value["campaign_id"]) is None
        or not isinstance(value["created_at_utc"], str)
        or UTC_PATTERN.fullmatch(value["created_at_utc"]) is None
        or value["generator_code_head"] != product_0603
        or value["evidence_owner"] != owner
        or not _bounded_identity(value["evidence_owner"])
        or not _bounded_identity(owner)
        or value["transports"] != ["mailbox", "rtt", "semihosting", "uart"]
    ):
        raise VerificationError("hardware campaign identity is invalid")
    _parse_utc(value["created_at_utc"])
    for name in ("board_id", "board_revision", "mcu_part", "probe_model", "uart_adapter_model", "power_identity"):
        if not _bounded_identity(value[name]):
            raise VerificationError("hardware identity is empty/placeholder/unbounded")
    for name in ("mcu_uid_hash", "probe_serial_hash", "uart_serial_hash"):
        if not isinstance(value[name], str) or HEX64.fullmatch(value[name]) is None:
            raise VerificationError("hardware identity hash is invalid")
    files: dict[str, bytes] = {}
    paths: list[Path] = []
    for name in ("support_profile", "support_manifest"):
        path, data = _validate_external_reference(value[name], SOURCE_REFERENCE_KEYS)
        paths.append(path)
        files[str(path)] = data
    build_ids: list[str] = []
    for name in ("firmware_0400", "firmware_0600"):
        path, data = _validate_external_reference(value[name], FIRMWARE_REFERENCE_KEYS)
        reference = value[name]
        assert isinstance(reference, Mapping)
        if not _bounded_identity(reference["build_id"]):
            raise VerificationError("firmware build id is invalid")
        build_ids.append(str(reference["build_id"]))
        paths.append(path)
        files[str(path)] = data
    if len(paths) != len(set(paths)) or len(build_ids) != len(set(build_ids)):
        raise VerificationError("hardware files/build identities alias")
    return files


def _repository_artifact_path(repository: Path, relative: str) -> Path:
    try:
        normalized = _safe_relative_path(relative)
        path = repository.joinpath(*normalized.split("/"))
        resolved = path.resolve(strict=True)
        resolved.relative_to(repository.resolve(strict=True))
    except (OSError, ValueError) as exc:
        raise VerificationError("repository artifact escapes or is missing") from exc
    if not _regular_file(path):
        raise VerificationError("repository artifact is linked/reparse/special")
    return path


def _validate_artifact(
    item: object,
    *,
    repository: Path,
    allowed_kinds: set[str],
    retained: dict[str, bytes],
) -> dict[str, object]:
    if not _closed(item, ARTIFACT_KEYS):
        raise VerificationError("artifact is not closed")
    assert isinstance(item, Mapping)
    kind, raw_path = item["kind"], item["path"]
    if kind not in allowed_kinds or not isinstance(raw_path, str):
        raise VerificationError("artifact kind/path is invalid")
    if kind in REPOSITORY_ARTIFACT_KINDS or (kind == "software-support" and not os.path.isabs(raw_path)):
        path = _repository_artifact_path(repository, raw_path)
    else:
        path = Path(_canonical_absolute(raw_path, "external artifact path"))
        if not _regular_file(path):
            raise VerificationError("external artifact is missing/linked/special")
    data = path.read_bytes()
    if (
        not _is_integer(item["bytes"])
        or item["bytes"] < 0
        or item["bytes"] != len(data)
        or not isinstance(item["sha256"], str)
        or item["sha256"] != hashlib.sha256(data).hexdigest()
    ):
        raise VerificationError("artifact byte/digest mismatch")
    retained[str(path)] = data
    return dict(item)


def _validate_artifacts(
    items: object,
    *,
    repository: Path,
    allowed_kinds: set[str],
    retained: dict[str, bytes],
    require_sorted: bool,
) -> list[dict[str, object]]:
    if not isinstance(items, list):
        raise VerificationError("artifacts must be an array")
    validated: list[dict[str, object]] = []
    keys: set[tuple[str, str]] = set()
    paths: dict[str, str] = {}
    folded_keys: set[tuple[str, str]] = set()
    folded_paths: dict[str, str] = {}
    for item in items:
        member = _validate_artifact(item, repository=repository, allowed_kinds=allowed_kinds, retained=retained)
        key = (str(member["kind"]), str(member["path"]))
        folded_key = (key[0].casefold(), key[1].casefold())
        folded_path = key[1].casefold()
        if (
            key in keys
            or folded_key in folded_keys
            or (key[1] in paths and paths[key[1]] != key[0])
            or (
                folded_path in folded_paths
                and folded_paths[folded_path] != key[0].casefold()
            )
        ):
            raise VerificationError("artifact duplicate or same-path kind conflict")
        keys.add(key)
        paths[key[1]] = key[0]
        folded_keys.add(folded_key)
        folded_paths[folded_path] = key[0].casefold()
        validated.append(member)
    if require_sorted and validated != sorted(validated, key=lambda item: (str(item["kind"]).encode("utf-8"), str(item["path"]).encode("utf-8"))):
        raise VerificationError("artifact union order is not canonical")
    return validated


def _git_checked(git: Callable[[list[str]], str], args: list[str]) -> str:
    try:
        return git(args)
    except VerificationError:
        raise
    except Exception as exc:
        raise VerificationError("Git relationship verification failed") from exc


def _validate_git_graph(ledger: Mapping[str, object], git: Callable[[list[str]], str]) -> None:
    commits = [str(ledger[name]) for name in IDENTITY_KEYS if name != "repositoryUrl"]
    if any(HEX40.fullmatch(commit) is None for commit in commits):
        raise VerificationError("ledger commit identity is invalid")
    for commit in commits:
        _git_checked(git, ["cat-file", "-e", f"{commit}^{{commit}}"])
    for ancestor, descendant in (
        (str(ledger["programBase"]), str(ledger["0601Product"])),
        (str(ledger["0601Report"]), str(ledger["0602Product"])),
        (str(ledger["0602Report"]), str(ledger["0603Product"])),
    ):
        _git_checked(git, ["merge-base", "--is-ancestor", ancestor, descendant])
    for module, product_key, report_key in (
        ("0601", "0601Product", "0601Report"),
        ("0602", "0602Product", "0602Report"),
    ):
        report = str(ledger[report_key])
        parents = _git_checked(git, ["rev-list", "--parents", "-n", "1", report]).split()
        if parents != [report, str(ledger[product_key])]:
            raise VerificationError("report commit does not have its sole product parent")
        changed = _git_checked(git, ["diff-tree", "--no-commit-id", "--name-only", "-r", report]).splitlines()
        if changed != [REPORT_PATHS[module]]:
            raise VerificationError("report commit changes a non-report path")


def verify_release_ledger_files(
    ledger_path: Path,
    digest_path: Path,
    software_input_path: Path,
    hardware_input_path: Path,
    *,
    repository: Path | None = None,
    git_runner: Callable[[list[str]], str] | None = None,
    entry_checker: Callable[[str | None], object] | None = None,
    before_final_reread: Callable[[], object] | None = None,
    dispatch_recorder: list[str] | None = None,
) -> dict[str, str]:
    paths = [ledger_path, digest_path, software_input_path, hardware_input_path]
    for index, path in enumerate(paths):
        _canonical_absolute(str(path), f"argument {index}")
    if len({str(path).casefold() for path in paths}) != len(paths):
        raise VerificationError("release-ledger arguments alias")
    if digest_path != ledger_path.with_name(ledger_path.name + ".sha256"):
        raise VerificationError("ledger digest is not the exact adjacent sidecar")
    software_sidecar_path = software_input_path.with_name(software_input_path.name + ".sha256")
    hardware_sidecar_path = hardware_input_path.with_name(hardware_input_path.name + ".sha256")
    repo = (repository or Path(__file__).resolve().parents[2]).resolve(strict=True)
    checker = entry_checker or (
        lambda expected: verify_loaded_script_entry(
            repository=repo, expected_code_head=expected, script_path=Path(__file__)
        )
    )
    entry_head = checker(None)
    ledger_bytes, ledger_value = _read_canonical(ledger_path)
    ledger_sidecar = _read_sidecar(digest_path, ledger_bytes)
    software_bytes, software_value = _read_canonical(software_input_path)
    software_sidecar = _read_sidecar(software_sidecar_path, software_bytes)
    hardware_bytes, hardware_value = _read_canonical(hardware_input_path)
    hardware_sidecar = _read_sidecar(hardware_sidecar_path, hardware_bytes)
    if not _closed(ledger_value, LEDGER_KEYS):
        raise VerificationError("release ledger root is not closed")
    assert isinstance(ledger_value, Mapping)
    if (
        ledger_value["schema"] != "stm32-release-ledger/1"
        or ledger_value["repositoryUrl"] != REPOSITORY_URL
        or ledger_value["programBase"] != PROGRAM_BASE
        or ledger_value["0400Product"] != PRODUCT_0400
        or ledger_value["0400Report"] != REPORT_0400
    ):
        raise VerificationError("release ledger fixed identity mismatch")
    if isinstance(entry_head, str) and entry_head != ledger_value["0603Product"]:
        raise VerificationError("verify-release-ledger HEAD is not 0603Product")
    git = git_runner or _default_git(repo)
    _validate_git_graph(ledger_value, git)
    _validate_governance(ledger_value["governance"])
    _validate_source_reference(ledger_value["softwareInput"], expected_path=software_input_path, data=software_bytes, sidecar=software_sidecar)
    _validate_source_reference(ledger_value["hardwareInput"], expected_path=hardware_input_path, data=hardware_bytes, sidecar=hardware_sidecar)
    if not _closed(software_value, SOFTWARE_KEYS):
        raise VerificationError("software input root is not closed")
    assert isinstance(software_value, Mapping)
    if any(software_value[name] != ledger_value[name] for name in IDENTITY_KEYS) or software_value["governance"] != ledger_value["governance"]:
        raise VerificationError("software input identity/governance mismatch")
    _validate_governance(software_value["governance"])
    if hardware_value != ledger_value["hardware"]:
        raise VerificationError("ledger hardware is not byte-semantically equal to hardware input")
    assert isinstance(hardware_value, Mapping)
    retained_artifacts: dict[str, bytes] = {}
    hardware_files = _validate_hardware(
        hardware_value,
        product_0603=str(ledger_value["0603Product"]),
        owner=str(ledger_value["governance"]["hardware_evidence_owner"]),
    )
    software_artifacts = _validate_artifacts(
        software_value["artifacts"],
        repository=repo,
        allowed_kinds=SOFTWARE_ARTIFACT_KINDS,
        retained=retained_artifacts,
        require_sorted=False,
    )
    projections: list[dict[str, object]] = []
    for name, kind in (
        ("support_profile", "hardware-support"),
        ("support_manifest", "hardware-support"),
        ("firmware_0400", "firmware"),
        ("firmware_0600", "firmware"),
    ):
        reference = hardware_value[name]
        assert isinstance(reference, Mapping)
        projections.append({"kind": kind, "path": reference["path"], "bytes": reference["bytes"], "sha256": reference["sha256"]})
    union_by_key: dict[tuple[str, str], dict[str, object]] = {}
    union_path_kind: dict[str, str] = {}
    for member in [*software_artifacts, *projections]:
        key = (str(member["kind"]), str(member["path"]))
        previous = union_by_key.get(key)
        if previous is not None and previous != member:
            raise VerificationError("cross-source artifact duplicate diverges")
        if key[1] in union_path_kind and union_path_kind[key[1]] != key[0]:
            raise VerificationError("cross-source same-path kind conflict")
        union_by_key[key] = member
        union_path_kind[key[1]] = key[0]
    expected_union = sorted(union_by_key.values(), key=lambda item: (str(item["kind"]).encode("utf-8"), str(item["path"]).encode("utf-8")))
    actual_union = _validate_artifacts(
        ledger_value["artifacts"],
        repository=repo,
        allowed_kinds=ARTIFACT_KINDS,
        retained=retained_artifacts,
        require_sorted=True,
    )
    if actual_union != expected_union:
        raise VerificationError("ledger artifact union has missing/extra/divergent members")
    for path, data in hardware_files.items():
        retained_artifacts[path] = data
    if dispatch_recorder:
        raise VerificationError("verify-release-ledger dispatched a gate")
    if before_final_reread is not None:
        before_final_reread()
    for path, first in (
        (ledger_path, ledger_bytes),
        (digest_path, ledger_sidecar),
        (software_input_path, software_bytes),
        (software_sidecar_path, software_sidecar),
        (hardware_input_path, hardware_bytes),
        (hardware_sidecar_path, hardware_sidecar),
    ):
        if path.read_bytes() != first:
            raise VerificationError("release-ledger/source/sidecar changed during verification")
    for raw_path, first in retained_artifacts.items():
        if Path(raw_path).read_bytes() != first:
            raise VerificationError("release artifact changed during verification")
    return {"mode": "verify-release-ledger", "status": "PASS"}


class _SingleUse(argparse.Action):
    def __call__(self, parser: argparse.ArgumentParser, namespace: argparse.Namespace, values: object, option_string: str | None = None) -> None:
        if getattr(namespace, self.dest, None) is not None:
            parser.error(f"{option_string} may be supplied only once")
        setattr(namespace, self.dest, values)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="verify_0600_release.py", allow_abbrev=False)
    sub = parser.add_subparsers(dest="mode", required=True)
    performance = sub.add_parser("performance-calibration", allow_abbrev=False)
    performance.add_argument("--profile", required=True, action=_SingleUse)
    performance.add_argument("--input", required=True, action="append")
    performance.add_argument("--output", required=True, action=_SingleUse)
    audit = sub.add_parser("dependency-audit", allow_abbrev=False)
    audit.add_argument("--input", action=_SingleUse)
    for option in ("ui-root", "catalog", "support-profile", "evidence"):
        audit.add_argument(f"--{option}", action=_SingleUse)
    candidate = sub.add_parser("candidate-evidence", allow_abbrev=False)
    candidate.add_argument("--candidate-ledger", action=_SingleUse)
    for option in ("module", "candidate-run-id", "evidence", "expected-code-head", "catalog", "performance", "support-profile"):
        candidate.add_argument(f"--{option}", action=_SingleUse)
    candidate.add_argument("--expected-shards", action=_SingleUse)
    candidate.add_argument("--expected-outcome", action=_SingleUse)
    generate = sub.add_parser("final-release-inputs", allow_abbrev=False)
    for option in ("repo", "candidate-ledger", "invocation-context", "output", "digest-output"):
        generate.add_argument(f"--{option}", required=True, action=_SingleUse)
    verify_inputs = sub.add_parser("verify-final-release-inputs", allow_abbrev=False)
    for option in ("repo", "input", "digest"):
        verify_inputs.add_argument(f"--{option}", required=True, action=_SingleUse)
    readiness = sub.add_parser("final-readiness", allow_abbrev=False)
    readiness.add_argument("--input", required=True, action=_SingleUse)
    final = sub.add_parser("final-evidence", allow_abbrev=False)
    final.add_argument("--input", required=True, action=_SingleUse)
    ledger = sub.add_parser("verify-release-ledger", allow_abbrev=False)
    ledger.add_argument("--ledger", required=True, action=_SingleUse)
    ledger.add_argument("--digest", required=True, action=_SingleUse)
    ledger.add_argument("--software-input", required=True, action=_SingleUse)
    ledger.add_argument("--hardware-input", required=True, action=_SingleUse)
    return parser


def _mode_input(path_text: str, mode: str) -> object:
    _canonical_absolute(path_text, f"{mode} input")
    return _read_canonical(Path(path_text))[1]


TERMINAL_RESULT_KEYS = {
    "schema", "matrix", "module", "shard", "run_id", "code_head", "status",
    "reason", "product_bodies", "network_access", "remote_git_actions", "resume_count",
    "catalog_sha256", "performance_sha256", "support", "audit", "gate_inventory",
    "prerequisites", "gate_results", "evidence_inventory", "binding",
}
TERMINAL_AUDIT_KEYS = {"schema", "status", "reason", "evidence"}
TERMINAL_GATE_RESULT_KEYS = {"gate_id", "status", "reason", "metadata"}
TERMINAL_METADATA_KEYS = {
    "architecture", "argv", "code_head", "cwd", "duration_ms", "executable",
    "decision", "executable_version", "exit_code", "gate_id", "node_outcomes", "os",
    "retained_evidence", "run_id", "seed", "selected_nodes", "started_at_utc",
    "stderr", "stdout", "timed_out",
}
TERMINAL_DECISION_KEYS = {"precheck", "postcheck", "prerequisites"}
TERMINAL_DECISION_STATES = {"FAIL", "NOT_REQUIRED", "NOT_RUN", "PASS"}


def _reference_list(root: Path, paths: Sequence[str]) -> list[dict[str, object]]:
    return [_file_reference(root.joinpath(*name.split("/")), name) for name in paths]


def _verify_terminal_decision(
    value: object, expected_prerequisites: list[dict[str, str]]
) -> tuple[str, str]:
    if not _closed(value, TERMINAL_DECISION_KEYS):
        raise VerificationError("terminal decision facts are not closed")
    assert isinstance(value, Mapping)
    precheck, postcheck = value["precheck"], value["postcheck"]
    if precheck not in TERMINAL_DECISION_STATES or postcheck not in TERMINAL_DECISION_STATES:
        raise VerificationError("terminal precheck/postcheck fact is invalid")
    prerequisites = value["prerequisites"]
    if not isinstance(prerequisites, list):
        raise VerificationError("terminal prerequisite facts are not an array")
    for item in prerequisites:
        if (
            not _closed(item, {"gate_id", "status"})
            or not isinstance(item["gate_id"], str)
            or item["status"] not in {"BLOCKED", "FAIL", "PASS"}
        ):
            raise VerificationError("terminal prerequisite fact is not closed")
    if prerequisites != expected_prerequisites:
        raise VerificationError("terminal prerequisite facts differ from the complete catalog DAG")
    return str(precheck), str(postcheck)


def _parse_retained_native_outcomes(
    framework: str, raw: bytes, *, exit_code: int | None = None,
) -> list[dict[str, str]]:
    try:
        return [
            {"node_id": node_id, "outcome": outcome}
            for node_id, outcome in parse_native_node_outcomes(
                framework, raw, exit_code=exit_code,
            )
        ]
    except ControllerError as exc:
        raise VerificationError("terminal native node artifact is invalid") from exc


def _verify_terminal_metadata(
    value: object,
    *,
    family: GateFamily,
    run_id: str,
    code_head: str,
    unexecuted: bool,
) -> None:
    if not _closed(value, TERMINAL_METADATA_KEYS):
        raise VerificationError("terminal gate metadata is not closed")
    assert isinstance(value, Mapping)
    if (
        value["gate_id"] != family.family_id
        or value["run_id"] != run_id
        or value["code_head"] != code_head
        or value["argv"] != list(family.command_argv)
        or value["cwd"] != "."
        or not isinstance(value["architecture"], str)
        or not isinstance(value["os"], str)
        or not isinstance(value["executable"], str)
        or not isinstance(value["executable_version"], str)
        or not _is_integer(value["duration_ms"])
        or value["duration_ms"] < 0
        or not _is_integer(value["exit_code"])
        or type(value["timed_out"]) is not bool
        or value["seed"] != f"stm32tk-0600:{run_id}:{family.family_id}"
        or not isinstance(value["started_at_utc"], str)
    ):
        raise VerificationError("terminal gate metadata identity/type is invalid")
    _parse_utc(value["started_at_utc"])
    expected_executable = family.command_argv[0] if family.command_argv else "reserved"
    if value["executable"] != expected_executable:
        raise VerificationError("terminal executable identity differs from catalog argv")
    if not family.command_argv:
        expected_version = "reserved"
    elif os.path.normcase(family.command_argv[0]) == os.path.normcase(sys.executable):
        expected_version = platform.python_version()
    else:
        executable_path = Path(family.command_argv[0])
        if not executable_path.is_absolute():
            located = shutil.which(family.command_argv[0], path=os.environ.get("PATH"))
            if located is None:
                raise VerificationError("terminal executable cannot be independently resolved")
            executable_path = Path(located)
        try:
            resolved = executable_path.resolve(strict=True)
            if not _regular_file(resolved):
                raise VerificationError("terminal executable is not a regular file")
            expected_version = f"sha256:{hashlib.sha256(resolved.read_bytes()).hexdigest()}"
        except OSError as exc:
            raise VerificationError("terminal executable cannot be independently read") from exc
    if value["executable_version"] != expected_version:
        raise VerificationError("terminal executable version/bytes are not exact")
    for stream in ("stdout", "stderr"):
        reference = value[stream]
        if (
            not _closed(reference, {"bytes", "sha256"})
            or not _is_integer(reference["bytes"])
            or reference["bytes"] < 0
            or not isinstance(reference["sha256"], str)
            or HEX64.fullmatch(reference["sha256"]) is None
        ):
            raise VerificationError("terminal stream reference is invalid")
    selected_nodes = value["selected_nodes"]
    if (
        not isinstance(selected_nodes, list)
        or any(not isinstance(node, str) or not node for node in selected_nodes)
    ):
        raise VerificationError("terminal selected-node inventory is invalid")
    outcomes = value["node_outcomes"]
    if not isinstance(outcomes, list):
        raise VerificationError("terminal node outcomes are not an array")
    for outcome in outcomes:
        if (
            not _closed(outcome, {"node_id", "outcome"})
            or not isinstance(outcome["node_id"], str)
            or not outcome["node_id"]
            or not isinstance(outcome["outcome"], str)
            or not outcome["outcome"]
        ):
            raise VerificationError("terminal node outcome is not closed")
    if unexecuted and (
        selected_nodes
        or outcomes
        or value["exit_code"] != -1
        or value["timed_out"] is not False
    ):
        raise VerificationError("unexecuted terminal decision/process facts are invalid")
    retained = value["retained_evidence"]
    if not isinstance(retained, list):
        raise VerificationError("terminal retained evidence is not an array")
    if family.reserved or unexecuted:
        expected = []
    else:
        framework = native_node_framework(family.command_argv)
        extension = "xml" if framework in {"pytest-junit", "ctest-junit"} else "txt" if framework == "ctest-text" else "json"
        expected = [
        f"{family.family_id}/native-results.{extension}",
        f"{family.family_id}/result.json",
        f"{family.family_id}/stderr.log",
        f"{family.family_id}/stdout.log",
        ]
    if [item.get("path") if isinstance(item, Mapping) else None for item in retained] != expected:
        raise VerificationError("terminal retained evidence inventory differs from catalog executor")
    for item in retained:
        if (
            not _closed(item, {"path", "bytes", "sha256"})
            or not _is_integer(item["bytes"])
            or item["bytes"] < 0
            or not isinstance(item["sha256"], str)
            or HEX64.fullmatch(item["sha256"]) is None
        ):
            raise VerificationError("terminal retained evidence reference is invalid")


def _verify_terminal_result(
    checkpoint_path: Path,
    *,
    expected_head: str,
    expected_mode: str,
    catalog: GateCatalog,
    catalog_sha256: str,
    performance_sha256: str,
    support_profile_sha256: str | None,
    before_final_reread: Callable[[], object] | None = None,
) -> dict[str, object]:
    checkpoint_bytes, result = _read_canonical(checkpoint_path)
    if not _closed(result, TERMINAL_RESULT_KEYS):
        raise VerificationError("terminal controller result is not closed")
    assert isinstance(result, Mapping)
    if (
        result["schema"] != "stm32-gate-controller-result/1"
        or result["matrix"] != expected_mode
        or result["module"] != "STM32TK-0601"
        or not isinstance(result["shard"], str)
        or not result["shard"]
        or result["code_head"] != expected_head
        or not isinstance(result["run_id"], str)
        or UUID_PATTERN.fullmatch(result["run_id"]) is None
        or result["status"] not in {"PASS", "FAIL", "BLOCKED"}
        or not isinstance(result["reason"], str)
        or any(not _is_integer(result[name]) or result[name] < 0 for name in (
            "product_bodies", "network_access", "remote_git_actions", "resume_count"
        ))
        or result["network_access"] != 0
        or result["remote_git_actions"] != 0
        or result["resume_count"] not in {0, 1}
        or result["catalog_sha256"] != catalog_sha256
        or result["performance_sha256"] != performance_sha256
    ):
        raise VerificationError("terminal controller identity/status is invalid")
    support = result["support"]
    if not _closed(support, {"profile", "manifest"}):
        raise VerificationError("terminal support binding is not closed")
    for name, expected_path in (("profile", "feasibility/profile.json"), ("manifest", "support-manifest.json")):
        reference = support[name]
        if (
            not _closed(reference, {"path", "bytes", "sha256"})
            or reference["path"] != expected_path
            or not _is_integer(reference["bytes"])
            or reference["bytes"] < 0
            or not isinstance(reference["sha256"], str)
            or HEX64.fullmatch(reference["sha256"]) is None
        ):
            raise VerificationError("terminal support reference is invalid")
    if support_profile_sha256 is not None and support["profile"]["sha256"] != support_profile_sha256:
        raise VerificationError("terminal support profile digest differs from owner ledger")
    try:
        gates = __import__("run_0600_gates")
        verified_support = gates.verify_support_root(FROZEN_SUPPORT_PROFILE)
    except (OSError, ValueError) as exc:
        raise VerificationError(f"terminal support root failed full revalidation: {exc}") from exc
    if verified_support != support:
        raise VerificationError("terminal support binding differs from fully revalidated support root")
    audit = result["audit"]
    if (
        not _closed(audit, TERMINAL_AUDIT_KEYS)
        or audit["schema"] != "stm32-terminal-audit/1"
        or audit["status"] != "BLOCKED"
        or audit["reason"] != "AUDIT_GATE_RESERVED"
        or audit["evidence"] is not None
    ):
        raise VerificationError("terminal audit evidence is not recursively closed")
    evidence_root = checkpoint_path.parent
    catalog_matrix = "final-windows" if expected_mode == "final" else "candidate-0601"
    families = tuple(
        family for family in catalog.families
        if family.module == "STM32TK-0601" and catalog_matrix in family.matrices
    )
    inventory = [family.family_id for family in families]
    if result["gate_inventory"] != inventory:
        raise VerificationError("terminal gate inventory differs from catalog")
    expected_prerequisites = [
        {"gate_id": family.family_id, "requires": list(family.prerequisites)}
        for family in families
    ]
    if result["prerequisites"] != expected_prerequisites:
        raise VerificationError("terminal prerequisite inventory differs from catalog")
    rows = result["gate_results"]
    if not isinstance(rows, list) or len(rows) != len(families):
        raise VerificationError("terminal gate result inventory is incomplete")
    statuses: list[str] = []
    complete_statuses = {family.family_id: "BLOCKED" for family in catalog.families}
    for family, row in zip(families, rows):
        if not _closed(row, TERMINAL_GATE_RESULT_KEYS):
            raise VerificationError("terminal gate result is not closed")
        assert isinstance(row, Mapping)
        if (
            row["gate_id"] != family.family_id
            or row["status"] not in {"PASS", "FAIL", "BLOCKED"}
            or not isinstance(row["reason"], str)
        ):
            raise VerificationError("terminal gate result state differs from catalog")
        metadata = row["metadata"]
        if not isinstance(metadata, Mapping):
            raise VerificationError("terminal gate metadata is not an object")
        expected_prerequisite_facts = [
            {"gate_id": gate_id, "status": complete_statuses[gate_id]}
            for gate_id in family.prerequisites
        ]
        precheck, postcheck = _verify_terminal_decision(
            metadata.get("decision"), expected_prerequisite_facts
        )
        prerequisite_blocked = any(
            item["status"] != "PASS" for item in expected_prerequisite_facts
        )
        expected_row: tuple[str, str] | None = None
        unexecuted = False
        if family.reserved:
            if (precheck, postcheck) != ("NOT_RUN", "NOT_RUN"):
                raise VerificationError("reserved gate decision facts are invalid")
            expected_row = ("BLOCKED", "RESERVED_CATALOG_FAMILY")
            unexecuted = True
        elif prerequisite_blocked:
            if (precheck, postcheck) != ("NOT_RUN", "NOT_RUN"):
                raise VerificationError("blocked prerequisite decision facts are invalid")
            expected_row = ("BLOCKED", "PREREQUISITE_NOT_PASS")
            unexecuted = True
        elif expected_mode == "final" and any(status != "PASS" for status in statuses):
            if (precheck, postcheck) != ("NOT_RUN", "NOT_RUN"):
                raise VerificationError("final fail-fast decision facts are invalid")
            expected_row = ("BLOCKED", "FINAL_FAIL_FAST")
            unexecuted = True
        elif precheck == "FAIL":
            if postcheck != "NOT_RUN":
                raise VerificationError("failed precheck cannot have a postcheck result")
            expected_row = ("FAIL", "PRECHECK_FAILED")
            unexecuted = True
        elif precheck != "PASS":
            raise VerificationError("terminal precheck fact does not authorize execution")
        elif postcheck == "FAIL":
            expected_row = ("FAIL", "POSTCHECK_FAILED")
        elif postcheck != "PASS":
            raise VerificationError("terminal postcheck fact is incomplete")
        _verify_terminal_metadata(
            metadata, family=family,
            run_id=str(result["run_id"]), code_head=expected_head,
            unexecuted=unexecuted,
        )
        if not unexecuted:
            framework = native_node_framework(family.command_argv)
            extension = "xml" if framework in {"pytest-junit", "ctest-junit"} else "txt" if framework == "ctest-text" else "json"
            native_path = evidence_root / "gates" / family.family_id / f"native-results.{extension}"
            if not _regular_file(native_path):
                raise VerificationError("terminal retained native result is missing or unsafe")
            stdout_path = evidence_root / "gates" / family.family_id / "stdout.log"
            if not _regular_file(stdout_path):
                raise VerificationError("terminal retained stdout is missing or unsafe")
            stdout_bytes = stdout_path.read_bytes()
            if {
                "bytes": len(stdout_bytes),
                "sha256": hashlib.sha256(stdout_bytes).hexdigest(),
            } != metadata["stdout"]:
                raise VerificationError("terminal retained stdout differs from metadata")
            parsed_outcomes = _parse_retained_native_outcomes(
                framework, native_path.read_bytes(), exit_code=int(metadata["exit_code"]),
            )
            if (
                parsed_outcomes != metadata["node_outcomes"]
                or [item["node_id"] for item in parsed_outcomes]
                != metadata["selected_nodes"]
            ):
                raise VerificationError(
                    "terminal node outcomes differ from independently parsed stdout"
                )
        if expected_row is None:
            selected_nodes = tuple(metadata["selected_nodes"])
            outcomes = metadata["node_outcomes"]
            outcome_nodes = tuple(item["node_id"] for item in outcomes)
            if (
                len(selected_nodes) != len(set(selected_nodes))
                or selected_nodes != family.node_ids
            ):
                expected_row = ("FAIL", "NODE_INVENTORY_MISMATCH")
            elif (
                outcome_nodes != family.node_ids
                or any(item["outcome"] not in {"passed", "failed"} for item in outcomes)
            ):
                expected_row = ("FAIL", "NODE_OUTCOME_MISMATCH")
            elif metadata["timed_out"]:
                expected_row = ("FAIL", "TIMEOUT")
            elif metadata["exit_code"] != 0 or any(
                item["outcome"] == "failed" for item in metadata["node_outcomes"]
            ):
                expected_row = ("FAIL", "PRODUCT_FAILURE")
            else:
                expected_row = ("PASS", "PASS")
        if (row["status"], row["reason"]) != expected_row:
            raise VerificationError("terminal gate status/reason is not derived from decision facts")
        for reference in metadata["retained_evidence"]:
            actual = _file_reference(
                evidence_root / "gates" / Path(str(reference["path"])),
                str(reference["path"]),
            )
            if actual != reference:
                raise VerificationError("terminal retained evidence digest differs from metadata")
        if metadata["retained_evidence"]:
            for stream in ("stdout", "stderr"):
                actual_stream = _file_reference(
                    evidence_root / "gates" / family.family_id / f"{stream}.log",
                    f"{family.family_id}/{stream}.log",
                )
                if {key: actual_stream[key] for key in ("bytes", "sha256")} != metadata[stream]:
                    raise VerificationError("terminal stream metadata differs from retained log")
            process_bytes, process_value = _read_canonical(
                evidence_root / "gates" / family.family_id / "result.json"
            )
            if (
                not _closed(process_value, {"schema", "exit_code", "duration_ms", "timed_out", "selected_nodes", "node_outcomes"})
                or process_value["schema"] != "stm32-gate-process-result/1"
                or process_value["exit_code"] != metadata["exit_code"]
                or process_value["duration_ms"] != metadata["duration_ms"]
                or process_value["timed_out"] != metadata["timed_out"]
                or process_value["selected_nodes"] != metadata["selected_nodes"]
                or process_value["node_outcomes"] != metadata["node_outcomes"]
                or not process_bytes
            ):
                raise VerificationError("terminal process result differs from controller metadata")
        statuses.append(str(row["status"]))
        complete_statuses[family.family_id] = str(row["status"])
    expected_status = "FAIL" if "FAIL" in statuses else "BLOCKED" if "BLOCKED" in statuses or not families else "PASS"
    if expected_status == "FAIL":
        expected_reason = "GATE_FAILURE"
    elif expected_status == "BLOCKED":
        expected_reason = "CATALOG_FAMILIES_RESERVED" if families else "MODULE_FAMILY_MISSING"
    else:
        expected_reason = "PASS"
    if result["status"] != expected_status or result["reason"] != expected_reason:
        raise VerificationError("terminal aggregate status is not derived from gates")
    executed_count = sum(
        bool(row["metadata"]["retained_evidence"])
        for row in rows
    )
    if result["product_bodies"] != executed_count:
        raise VerificationError("terminal product-body count differs from executable catalog")
    binding = _validate_shard_binding(result["binding"])
    if (
        binding["run_id"] != result["run_id"]
        or binding["code_head"] != expected_head
        or binding["catalog_sha256"] != catalog_sha256
        or binding["support_sha256"] != support["manifest"]["sha256"]
        or binding["status"] != expected_status
    ):
        raise VerificationError("terminal shard binding differs from controller result")
    package_files = ["controller-result.json"]
    for row in rows:
        for reference in row["metadata"]["retained_evidence"]:
            package_files.append(f"gates/{reference['path']}")
    package_files.sort(key=lambda item: item.encode("utf-8"))
    if result["evidence_inventory"] != package_files:
        raise VerificationError("terminal evidence inventory differs from catalog")
    expected_files = list(package_files)
    if expected_mode == "final":
        expected_files.append("checkpoint.json")
        expected_files.sort(key=lambda item: item.encode("utf-8"))
    references = _reference_list(evidence_root, expected_files)
    verify_gate_evidence(evidence_root, references, expected_paths=expected_files)
    package_path = evidence_root.parent / f"{evidence_root.name}.shard.zip"
    sidecar_path = package_path.with_name(package_path.name + ".manifest.json")
    sidecar_bytes, package_reference = _read_canonical(sidecar_path)
    verify_shard_package(
        package_path,
        package_reference,
        binding,
        evidence_root=evidence_root,
        expected_paths=package_files,
        allowed_external_paths=expected_files,
    )
    package_bytes = package_path.read_bytes()
    evidence_snapshot = {
        name: evidence_root.joinpath(*name.split("/")).read_bytes()
        for name in expected_files
    }
    if before_final_reread is not None:
        before_final_reread()
    try:
        final_support = gates.verify_support_root(FROZEN_SUPPORT_PROFILE)
    except (OSError, ValueError) as exc:
        raise VerificationError(f"terminal support root changed during verification: {exc}") from exc
    if (
        checkpoint_path.read_bytes() != checkpoint_bytes
        or sidecar_path.read_bytes() != sidecar_bytes
        or package_path.read_bytes() != package_bytes
    ):
        raise VerificationError("terminal checkpoint/package sidecar changed during verification")
    if final_support != verified_support:
        raise VerificationError("terminal support root changed during verification")
    final_references, final_payloads = _evidence_snapshot(evidence_root)
    if (
        [str(item["path"]) for item in final_references] != expected_files
        or final_payloads != evidence_snapshot
    ):
        raise VerificationError("terminal retained evidence changed during verification")
    return dict(result)


def verify_candidate_evidence_file(
    ledger_path: Path,
    *,
    git_runner: Callable[[list[str]], str] | None = None,
    before_final_reread: Callable[[], object] | None = None,
) -> dict[str, str]:
    ledger_bytes, raw_ledger = _read_canonical(ledger_path)
    ledger = validate_candidate_ledger(raw_ledger)
    if ledger_path != Path(str(ledger["candidate_root"])) / "candidate-ledger.json":
        raise VerificationError("candidate ledger path is not wrapper-owned")
    reconcile_candidate(ledger, git_runner=git_runner)
    if ledger["state"] not in {"passed", "failed", "blocked"} or ledger["checkpoint"] is None:
        raise VerificationError("candidate ledger has no terminal checkpoint")
    checkpoint_path = Path(str(ledger["checkpoint"]))
    if checkpoint_path != Path(str(ledger["evidence_root"])) / "controller-result.json":
        raise VerificationError("candidate checkpoint path is not exact")
    repo = Path(str(ledger["controller_path"])).parents[2]
    catalog_path = repo / "tools/release/gates_0600.json"
    performance_path = repo / "tools/release/performance_0600.json"
    catalog_bytes = catalog_path.read_bytes()
    performance_bytes = performance_path.read_bytes()
    if (
        hashlib.sha256(catalog_bytes).hexdigest() != ledger["catalog_sha256"]
        or hashlib.sha256(performance_bytes).hexdigest() != ledger["performance_sha256"]
    ):
        raise VerificationError("candidate catalog/performance retained digest mismatch")
    catalog = load_catalog(catalog_path)
    load_performance_catalog(performance_path)
    result = _verify_terminal_result(
        checkpoint_path,
        expected_head=str(ledger["expected_code_head"]),
        expected_mode="candidate",
        catalog=catalog,
        catalog_sha256=str(ledger["catalog_sha256"]),
        performance_sha256=str(ledger["performance_sha256"]),
        support_profile_sha256=str(ledger["support_profile_sha256"]),
        before_final_reread=before_final_reread,
    )
    if str(result["status"]).casefold() != ledger["state"]:
        raise VerificationError("candidate ledger state differs from terminal result")
    if (
        ledger_path.read_bytes() != ledger_bytes
        or catalog_path.read_bytes() != catalog_bytes
        or performance_path.read_bytes() != performance_bytes
    ):
        raise VerificationError("candidate ledger/catalog/performance changed during verification")
    return {"mode": "candidate-evidence", "status": "PASS"}


def verify_candidate_evidence_contract(
    *, module: str, candidate_run_id: str, evidence: Path,
    expected_code_head: str, catalog: Path, performance: Path,
    support_profile: Path, expected_shards: str | None = None,
    expected_outcome: str | None = None,
) -> dict[str, str]:
    if expected_shards not in {None, "windows"}:
        raise VerificationError("candidate expected shards are invalid")
    if expected_outcome not in {None, "SOFTWARE_COMPLETE_HARDWARE_PENDING"}:
        raise VerificationError("candidate expected outcome is invalid")
    ledger_path = evidence / "candidate-ledger.json"
    _, raw = _read_canonical(ledger_path)
    ledger = validate_candidate_ledger(raw)
    if (
        ledger["module"] != module
        or ledger["candidate_run_id"] != candidate_run_id
        or ledger["candidate_root"] != str(evidence)
        or ledger["expected_code_head"] != expected_code_head
        or ledger["catalog_sha256"] != hashlib.sha256(catalog.read_bytes()).hexdigest()
        or ledger["performance_sha256"] != hashlib.sha256(performance.read_bytes()).hexdigest()
        or ledger["support_profile_sha256"] != hashlib.sha256(support_profile.read_bytes()).hexdigest()
    ):
        raise VerificationError("candidate planned arguments differ from wrapper ledger")
    verified = verify_candidate_evidence_file(ledger_path)
    _, raw_terminal = _read_canonical(Path(str(ledger["checkpoint"])))
    assert isinstance(raw_terminal, Mapping)
    if expected_shards is not None and (
        Path(str(ledger["evidence_root"])) != evidence / expected_shards
        or raw_terminal.get("shard") != expected_shards
    ):
        raise VerificationError("candidate expected shard is not ledger/terminal bound")
    frozen_catalog = load_catalog(catalog)
    matrix_name = f"candidate-{module.rsplit('-', 1)[-1]}"
    families = [family for family in frozen_catalog.families if family.module == module and matrix_name in family.matrices]
    rows = raw_terminal.get("gate_results")
    if not isinstance(rows, list):
        raise VerificationError("candidate terminal gate rows are unavailable")
    by_id = {row.get("gate_id"): row for row in rows if isinstance(row, Mapping)}
    if any(
        family.family_id not in by_id
        or (
            by_id[family.family_id].get("status") != "PASS"
            if not family.reserved
            else by_id[family.family_id].get("status") != "BLOCKED"
            or by_id[family.family_id].get("reason") != "RESERVED_CATALOG_FAMILY"
        )
        for family in families
    ):
        raise VerificationError("candidate software/reserved outcome is invalid")
    derived_outcome = (
        "SOFTWARE_COMPLETE_HARDWARE_PENDING"
        if families and any(family.reserved for family in families)
        else "PASS"
    )
    if (
        derived_outcome == "PASS" and raw_terminal.get("status") != "PASS"
        or derived_outcome == "SOFTWARE_COMPLETE_HARDWARE_PENDING"
        and (raw_terminal.get("status") != "BLOCKED" or raw_terminal.get("reason") != "CATALOG_FAMILIES_RESERVED")
    ):
        raise VerificationError("candidate terminal status does not match derived outcome")
    if expected_outcome is not None and expected_outcome != derived_outcome:
        raise VerificationError("candidate expected outcome differs from derived outcome")
    return {**verified, "outcome": derived_outcome}


def _secure_io() -> object:
    injected = globals().get("_SECURE_IO_TEST_ADAPTER")
    if injected is not None:
        if "PYTEST_CURRENT_TEST" not in os.environ:
            raise VerificationError("release locking adapter injection is test-only")
        return injected
    repo = Path(__file__).resolve().parents[2]
    controller = repo / "tools/release/run_0600_gates.py"
    git = _default_git(repo)
    head = git(["rev-parse", "HEAD"]).strip()
    if HEX40.fullmatch(head) is None or git(["config", "--get", "remote.origin.url"]).strip() != REPOSITORY_URL:
        raise VerificationError("release locking controller repository identity failed")
    committed = git(["rev-parse", f"{head}:tools/release/run_0600_gates.py"]).strip()
    working = git(["hash-object", "--", str(controller)]).strip()
    if HEX40.fullmatch(committed) is None or committed != working:
        raise VerificationError("release locking controller committed blob mismatch")
    module_name = f"_stm32tk_release_locking_{working}"
    spec = importlib.util.spec_from_file_location(module_name, controller)
    if spec is None or spec.loader is None:
        raise VerificationError("release locking controller cannot be loaded")
    secure = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = secure
    try:
        spec.loader.exec_module(secure)
    except BaseException:
        sys.modules.pop(module_name, None)
        raise
    return secure


def _require_direct_child(path: Path, parent: Path, name: str) -> None:
    if not path.is_absolute() or str(path) != os.path.abspath(path) or path.parent != parent or not path.name:
        raise VerificationError(f"{name} must be a canonical direct child of {parent}")


def _enter_locked_directory(stack: ExitStack, path: Path) -> tuple[object, object]:
    secure = _secure_io()
    try:
        directory = stack.enter_context(secure._open_locked_windows_directory(path))
        sentinel = stack.enter_context(secure._create_coverage_lock_sentinel(path))
        secure._validate_locked_coverage_directory(directory)
        secure._validate_locked_coverage_file_path(sentinel)
        return directory, sentinel
    except secure.ControllerError as exc:
        raise VerificationError("release directory lock failed") from exc


def _locked_create(stack: ExitStack, path: Path, data: bytes) -> object:
    secure = _secure_io()
    try:
        locked = stack.enter_context(secure._open_locked_windows_file(path, create_new=True, write=True))
        secure._windows_write_locked_file(locked, data)
        return locked
    except secure.ControllerError as exc:
        raise VerificationError(f"create-new locked output failed: {path.name}") from exc


def _assert_no_reparse_chain(path: Path, *, allow_absent_leaf: bool) -> None:
    current = path
    first = True
    while True:
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            if first and allow_absent_leaf:
                current = current.parent
                first = False
                continue
            raise VerificationError("path ancestor is absent")
        attributes = int(getattr(metadata, "st_file_attributes", 0))
        if stat.S_ISLNK(metadata.st_mode) or attributes & int(getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)):
            raise VerificationError("path chain contains a reparse point")
        if current.parent == current:
            return
        current = current.parent
        first = False


def _final_context(path: Path, *, repo: Path, ledger: Mapping[str, object]) -> tuple[bytes, Mapping[str, object]]:
    data, raw = _read_canonical(path)
    _read_sidecar(path.with_name(path.name + ".sha256"), data)
    if not _closed(raw, FINAL_CONTEXT_KEYS):
        raise VerificationError("candidate invocation context is not closed")
    assert isinstance(raw, Mapping)
    if (
        raw["schema"] != "stm32-candidate-invocation-context/1"
        or raw["module"] != "STM32TK-0603" or raw["shard"] != "windows"
        or raw["candidate_run_id"] != ledger["candidate_run_id"]
        or raw["code_head"] != ledger["expected_code_head"]
        or raw["frozen_worktree"] != str(repo)
        or raw["origin_url"] != REPOSITORY_URL
        or raw["candidate_root"] != ledger["candidate_root"]
        or raw["evidence_root"] != ledger["evidence_root"]
        or raw["wrapper_ledger"] != str(Path(str(ledger["candidate_root"])) / "candidate-ledger.json")
        or raw["catalog_sha256"] != ledger["catalog_sha256"]
        or raw["performance_sha256"] != ledger["performance_sha256"]
        or raw["support_profile_sha256"] != ledger["support_profile_sha256"]
    ):
        raise VerificationError("candidate invocation context binding is invalid")
    for name in ("controller_sha256", "verifier_sha256"):
        if not isinstance(raw[name], str) or HEX64.fullmatch(str(raw[name])) is None:
            raise VerificationError("candidate invocation context digest is invalid")
    if (
        raw["controller_sha256"] != hashlib.sha256((repo / CANDIDATE_CONTROLLER_RELATIVE).read_bytes()).hexdigest()
        or raw["verifier_sha256"] != hashlib.sha256((repo / VERIFIER_RELATIVE_PATH).read_bytes()).hexdigest()
    ):
        raise VerificationError("candidate invocation context fixed tool digest changed")
    return data, raw


def _artifact_record(kind: str, path_text: str, path: Path) -> dict[str, object]:
    data = path.read_bytes()
    return {"kind": kind, "path": path_text, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def _generate_final_release_inputs_body(
    *, repository: Path, candidate_ledger_path: Path, invocation_context_path: Path,
    output_path: Path, digest_output_path: Path,
    git_runner: Callable[[list[str]], str] | None = None,
    _locks: ExitStack,
) -> dict[str, str]:
    repo = repository.resolve(strict=True)
    for name, path in (("repository", repository), ("candidate ledger", candidate_ledger_path),
                       ("invocation context", invocation_context_path), ("output", output_path),
                       ("digest output", digest_output_path)):
        _canonical_absolute(str(path), name)
    for path in (repository, candidate_ledger_path, invocation_context_path):
        _assert_no_reparse_chain(path, allow_absent_leaf=False)
    if digest_output_path != output_path.with_name(output_path.name + ".sha256"):
        raise VerificationError("final release input digest is not the exact adjacent sidecar")
    if output_path.exists() or digest_output_path.exists():
        raise VerificationError("final release input output already exists")
    ledger_bytes, raw_ledger = _read_canonical(candidate_ledger_path)
    ledger = validate_candidate_ledger(raw_ledger)
    if ledger["module"] != "STM32TK-0603" or candidate_ledger_path != Path(str(ledger["candidate_root"])) / "candidate-ledger.json":
        raise VerificationError("final input candidate ledger identity is invalid")
    context_bytes, context = _final_context(invocation_context_path, repo=repo, ledger=ledger)
    context_digest_path = invocation_context_path.with_name(invocation_context_path.name + ".sha256")
    context_digest_bytes = context_digest_path.read_bytes()
    catalog = repo / "tools/release/gates_0600.json"
    performance = repo / "tools/release/performance_0600.json"
    support = Path(str(context["support_profile"]))
    verify_candidate_evidence_contract(
        module="STM32TK-0603", candidate_run_id=str(ledger["candidate_run_id"]),
        evidence=Path(str(ledger["candidate_root"])), expected_code_head=str(ledger["expected_code_head"]),
        catalog=catalog, performance=performance, support_profile=support,
        expected_shards="windows", expected_outcome="SOFTWARE_COMPLETE_HARDWARE_PENDING",
    )
    git = git_runner or _default_git(repo)
    reconcile_candidate(ledger, git_runner=git)
    reports: dict[str, str] = {}
    products: dict[str, str] = {}
    for module in ("0601", "0602"):
        report = _git_checked(git, ["log", "-1", "--format=%H", "--", REPORT_PATHS[module]]).strip()
        product = _git_checked(git, ["rev-parse", f"{report}^"]).strip()
        if HEX40.fullmatch(report) is None or HEX40.fullmatch(product) is None:
            raise VerificationError("accepted report chain identity is invalid")
        reports[module], products[module] = report, product
    artifacts: list[dict[str, object]] = []
    for kind, relatives in FINAL_REPOSITORY_ARTIFACTS.items():
        for relative in relatives:
            path = _repository_artifact_path(repo, relative)
            artifacts.append(_artifact_record(kind, relative, path))
    support_manifest = support.parents[1] / "support-manifest.json"
    for path in (support, support_manifest):
        if not _regular_file(path):
            raise VerificationError("software support artifact is missing")
        artifacts.append(_artifact_record("software-support", str(path), path))
    artifacts.sort(key=lambda item: (str(item["kind"]).encode("utf-8"), str(item["path"]).encode("utf-8")))
    value = {
        "repositoryUrl": REPOSITORY_URL, "programBase": PROGRAM_BASE,
        "0400Product": PRODUCT_0400, "0400Report": REPORT_0400,
        "0601Product": products["0601"], "0601Report": reports["0601"],
        "0602Product": products["0602"], "0602Report": reports["0602"],
        "0603Product": ledger["expected_code_head"],
        "governance": {**GOVERNANCE_OWNERS, "remote_state": "local-only; remote actions require explicit user authorization", "remote_actions": [], "bounded_overrides": []},
        "artifacts": artifacts,
    }
    data = canonical_json_bytes(value)
    _assert_no_reparse_chain(output_path, allow_absent_leaf=True)
    _assert_no_reparse_chain(digest_output_path, allow_absent_leaf=True)
    _locked_create(_locks, output_path, data)
    _locked_create(_locks, digest_output_path, (hashlib.sha256(data).hexdigest() + "\n").encode("ascii"))
    verify_final_release_inputs(output_path, digest_output_path, repository=repo, git_runner=git)
    if (
        candidate_ledger_path.read_bytes() != ledger_bytes
        or invocation_context_path.read_bytes() != context_bytes
        or context_digest_path.read_bytes() != context_digest_bytes
    ):
        raise VerificationError("final input source changed during generation")
    return {"mode": "final-release-inputs", "status": "PASS", "sha256": hashlib.sha256(data).hexdigest()}


def generate_final_release_inputs(
    *, repository: Path, candidate_ledger_path: Path, invocation_context_path: Path,
    output_path: Path, digest_output_path: Path,
    git_runner: Callable[[list[str]], str] | None = None,
    after_location_check: Callable[[], object] | None = None,
    _temporary_root: Path = Path(r"C:\tmp"),
) -> dict[str, str]:
    if _temporary_root != Path(r"C:\tmp") and "PYTEST_CURRENT_TEST" not in os.environ:
        raise VerificationError("final input temporary root override is test-only")
    for parent, name in (
        (candidate_ledger_path.parent, "candidate root"),
        (invocation_context_path.parent, "invocation context root"),
        (output_path.parent, "final output root"),
    ):
        _require_direct_child(parent, _temporary_root, name)
    with ExitStack() as locks:
        temporary_lock, _ = _enter_locked_directory(locks, _temporary_root)
        locked_directories: list[object] = []
        for parent in dict.fromkeys((candidate_ledger_path.parent, invocation_context_path.parent, output_path.parent)):
            directory, _ = _enter_locked_directory(locks, parent)
            locked_directories.append(directory)
        if after_location_check is not None:
            after_location_check()
        secure = _secure_io()
        try:
            secure._validate_locked_coverage_directory(temporary_lock)
            for directory in locked_directories:
                secure._validate_locked_coverage_directory(directory)
        except secure.ControllerError as exc:
            raise VerificationError("final input locked parent changed") from exc
        return _generate_final_release_inputs_body(
            repository=repository, candidate_ledger_path=candidate_ledger_path,
            invocation_context_path=invocation_context_path, output_path=output_path,
            digest_output_path=digest_output_path, git_runner=git_runner, _locks=locks,
        )


def verify_final_release_inputs(
    input_path: Path, digest_path: Path, *, repository: Path,
    git_runner: Callable[[list[str]], str] | None = None,
) -> dict[str, str]:
    if digest_path != input_path.with_name(input_path.name + ".sha256"):
        raise VerificationError("final release input sidecar path is invalid")
    data, raw = _read_canonical(input_path)
    sidecar = _read_sidecar(digest_path, data)
    if not _closed(raw, SOFTWARE_KEYS):
        raise VerificationError("final release input root is not closed")
    assert isinstance(raw, Mapping)
    if raw["repositoryUrl"] != REPOSITORY_URL or raw["programBase"] != PROGRAM_BASE or raw["0400Product"] != PRODUCT_0400 or raw["0400Report"] != REPORT_0400:
        raise VerificationError("final release input fixed identity is invalid")
    _validate_governance(raw["governance"])
    repo = repository.resolve(strict=True)
    _validate_git_graph(raw, git_runner or _default_git(repo))
    retained: dict[str, bytes] = {}
    _validate_artifacts(raw["artifacts"], repository=repo, allowed_kinds=SOFTWARE_ARTIFACT_KINDS, retained=retained, require_sorted=True)
    if input_path.read_bytes() != data or digest_path.read_bytes() != sidecar or any(Path(path).read_bytes() != first for path, first in retained.items()):
        raise VerificationError("final release inputs changed during verification")
    return {"mode": "verify-final-release-inputs", "status": "PASS"}


def verify_final_evidence_file(
    checkpoint_path: Path,
    *,
    expected_head: str,
    readiness: bool,
    before_final_reread: Callable[[], object] | None = None,
) -> dict[str, str]:
    checkpoint_bytes, checkpoint = _read_canonical(checkpoint_path)
    _verify_final_checkpoint(checkpoint, expected_head=expected_head, readiness=readiness)
    assert isinstance(checkpoint, Mapping)
    controller = Path(str(checkpoint["controller_path"]))
    evidence_root = Path(str(checkpoint["evidence_root"]))
    if checkpoint_path != evidence_root / "checkpoint.json":
        raise VerificationError("final checkpoint is not exact/evidence-root bound")
    try:
        repo = controller.parents[2]
        if controller.relative_to(repo).as_posix() != "tools/release/run_0600_final.ps1":
            raise VerificationError("final controller path is not fixed")
    except (IndexError, ValueError) as exc:
        raise VerificationError("final controller path is not worktree-bound") from exc
    result_path = evidence_root / "controller-result.json"
    _, raw_result = _read_canonical(result_path)
    if not isinstance(raw_result, Mapping):
        raise VerificationError("final controller result is invalid")
    catalog_path = repo / "tools/release/gates_0600.json"
    performance_path = repo / "tools/release/performance_0600.json"
    catalog_bytes = catalog_path.read_bytes()
    performance_bytes = performance_path.read_bytes()
    catalog_sha256 = hashlib.sha256(catalog_bytes).hexdigest()
    performance_sha256 = hashlib.sha256(performance_bytes).hexdigest()
    catalog = load_catalog(catalog_path)
    load_performance_catalog(performance_path)
    result = _verify_terminal_result(
        result_path,
        expected_head=expected_head,
        expected_mode="final",
        catalog=catalog,
        catalog_sha256=catalog_sha256,
        performance_sha256=performance_sha256,
        support_profile_sha256=None,
        before_final_reread=before_final_reread,
    )
    if (
        checkpoint["run_id"] != result["run_id"]
        or checkpoint["code_head"] != result["code_head"]
        or checkpoint["state"] != str(result["status"]).casefold()
        or (readiness and result["product_bodies"] != 0)
    ):
        raise VerificationError("final checkpoint differs from recursively verified evidence")
    if (
        checkpoint_path.read_bytes() != checkpoint_bytes
        or catalog_path.read_bytes() != catalog_bytes
        or performance_path.read_bytes() != performance_bytes
    ):
        raise VerificationError("final checkpoint/catalog/performance changed during verification")
    return {
        "mode": "final-readiness" if readiness else "final-evidence",
        "status": "PASS",
    }


def _verify_final_checkpoint(value: object, *, expected_head: str, readiness: bool) -> dict[str, str]:
    keys = {
        "schema",
        "run_id",
        "code_head",
        "controller_path",
        "evidence_root",
        "state",
        "resume_count",
        "interruption_event",
    }
    if not _closed(value, keys):
        raise VerificationError("final checkpoint is not closed")
    assert isinstance(value, Mapping)
    allowed_states = {"blocked", "failed", "passed"} if not readiness else {"blocked"}
    if (
        value["schema"] != "stm32-final-checkpoint/1"
        or value["code_head"] != expected_head
        or not isinstance(value["run_id"], str)
        or UUID_PATTERN.fullmatch(value["run_id"]) is None
        or value["state"] not in allowed_states
        or not _is_integer(value["resume_count"])
        or value["resume_count"] not in {0, 1}
        or (
            value["interruption_event"] is not None
            and value["interruption_event"] not in RECOVERY_EVENTS
        )
    ):
        raise VerificationError("final checkpoint identity/state is invalid")
    _canonical_absolute(value["controller_path"], "final controller path")
    _canonical_absolute(value["evidence_root"], "final evidence root")
    return {
        "mode": "final-readiness" if readiness else "final-evidence",
        "status": "PASS",
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.mode == "verify-release-ledger":
            for name, raw in (
                ("ledger", args.ledger),
                ("digest", args.digest),
                ("software-input", args.software_input),
                ("hardware-input", args.hardware_input),
            ):
                _canonical_absolute(raw, name)
            result = verify_release_ledger_files(
                Path(args.ledger),
                Path(args.digest),
                Path(args.software_input),
                Path(args.hardware_input),
            )
        else:
            repository = Path(__file__).resolve().parents[2]
            head = verify_loaded_script_entry(
                repository=repository,
                expected_code_head=None,
                script_path=Path(__file__),
            )
            if args.mode == "performance-calibration":
                for raw in args.input:
                    _canonical_absolute(raw, "performance calibration input")
                output = Path(args.output)
                fixed_output = repository / "tools/release/performance_0600.json"
                if output.resolve() != fixed_output.resolve():
                    raise VerificationError("performance calibration output is not the fixed catalog")
                result = aggregate_performance_calibration(
                    args.profile, [Path(raw) for raw in args.input], fixed_output
                )
            elif args.mode == "dependency-audit":
                if args.input is not None:
                    if any(getattr(args, name) is not None for name in ("ui_root", "catalog", "support_profile", "evidence")):
                        raise VerificationError("dependency audit forms may not be mixed")
                    result = verify_dependency_audit_input(_mode_input(args.input, args.mode))
                else:
                    if any(getattr(args, name) is None for name in ("ui_root", "catalog", "support_profile", "evidence")):
                        raise VerificationError("planned dependency audit form is incomplete")
                    result = run_planned_dependency_audit(
                        repository=repository, ui_root_text=args.ui_root, catalog_text=args.catalog,
                        support_profile=Path(args.support_profile), evidence_root=Path(args.evidence),
                    )
            elif args.mode == "candidate-evidence":
                planned_names = ("module", "candidate_run_id", "evidence", "expected_code_head", "catalog", "performance", "support_profile")
                if args.candidate_ledger is not None:
                    if any(getattr(args, name) is not None for name in planned_names + ("expected_shards", "expected_outcome")):
                        raise VerificationError("candidate evidence forms may not be mixed")
                    value = _mode_input(args.candidate_ledger, args.mode)
                    ledger = validate_candidate_ledger(value)
                    if ledger["expected_code_head"] != head:
                        raise VerificationError("candidate ledger CodeHead differs from loaded verifier HEAD")
                    result = verify_candidate_evidence_file(Path(args.candidate_ledger))
                else:
                    if any(getattr(args, name) is None for name in planned_names):
                        raise VerificationError("planned candidate evidence form is incomplete")
                    for name in ("evidence", "catalog", "performance", "support_profile"):
                        _canonical_absolute(getattr(args, name), name)
                    result = verify_candidate_evidence_contract(
                        module=args.module, candidate_run_id=args.candidate_run_id,
                        evidence=Path(args.evidence), expected_code_head=args.expected_code_head,
                        catalog=Path(args.catalog), performance=Path(args.performance),
                        support_profile=Path(args.support_profile), expected_shards=args.expected_shards,
                        expected_outcome=args.expected_outcome,
                    )
            elif args.mode == "final-release-inputs":
                for name in ("repo", "candidate_ledger", "invocation_context", "output", "digest_output"):
                    _canonical_absolute(getattr(args, name), name)
                if Path(args.repo).resolve(strict=True) != repository.resolve(strict=True):
                    raise VerificationError("final input repository differs from loaded verifier repository")
                result = generate_final_release_inputs(
                    repository=Path(args.repo), candidate_ledger_path=Path(args.candidate_ledger),
                    invocation_context_path=Path(args.invocation_context), output_path=Path(args.output),
                    digest_output_path=Path(args.digest_output),
                )
            elif args.mode == "verify-final-release-inputs":
                for name in ("repo", "input", "digest"):
                    _canonical_absolute(getattr(args, name), name)
                if Path(args.repo).resolve(strict=True) != repository.resolve(strict=True):
                    raise VerificationError("final input repository differs from loaded verifier repository")
                result = verify_final_release_inputs(
                    Path(args.input), Path(args.digest), repository=Path(args.repo)
                )
            elif args.mode == "final-readiness":
                _mode_input(args.input, args.mode)
                result = verify_final_evidence_file(
                    Path(args.input), expected_head=head, readiness=True
                )
            else:
                _mode_input(args.input, args.mode)
                result = verify_final_evidence_file(
                    Path(args.input), expected_head=head, readiness=False
                )
    except (VerificationError, OSError, subprocess.SubprocessError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    sys.stdout.buffer.write(canonical_json_bytes(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
