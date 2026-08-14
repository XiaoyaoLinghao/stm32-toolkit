"""Fail-closed local verification primitives for the STM32 Toolkit 0.6 gates.

The module deliberately contains no network client and no hardware or product
dispatcher.  Controllers pass only local, already-derived paths to these
validators.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import stat
import subprocess
import sys
import unicodedata
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path
from typing import Callable, Mapping, Sequence


CATALOG_SCHEMA = "stm32-gate-catalog/1"
PERFORMANCE_SCHEMA = "stm32-performance-catalog/1"
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
        families.append(
            GateFamily(
                family_id=str(item["id"]),
                module=str(item["module"]),
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
    if value["profiles"]:
        raise CatalogError("Task 2 performance catalog must be empty")
    return {"profiles": [], "schema": PERFORMANCE_SCHEMA}


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


def verify_gate_evidence(root: Path, references: object) -> None:
    if not root.is_absolute() or not root.is_dir() or not isinstance(references, list):
        raise VerificationError("gate evidence root or references are invalid")
    seen: set[str] = set()
    seen_folded: set[str] = set()
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
        seen.add(relative)
        seen_folded.add(relative.casefold())


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


def _evidence_members(root: Path) -> list[dict[str, object]]:
    members: list[dict[str, object]] = []
    folded: set[str] = set()
    for path in root.rglob("*"):
        if path.is_dir() and not path.is_symlink():
            continue
        relative = path.relative_to(root).as_posix()
        _safe_relative_path(relative)
        if relative.casefold() in folded:
            raise VerificationError("case-fold duplicate package member")
        members.append(_file_reference(path, relative))
        folded.add(relative.casefold())
    members.sort(key=lambda item: str(item["path"]).encode("utf-8"))
    return members


def _zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_STORED
    info.create_system = 3
    info.external_attr = 0o100444 << 16
    return info


def create_shard_package(
    evidence_root: Path, package_path: Path, binding: object
) -> dict[str, object]:
    if not evidence_root.is_absolute() or not evidence_root.is_dir():
        raise VerificationError("evidence root must be an absolute directory")
    if not package_path.is_absolute() or package_path.exists() or not package_path.parent.is_dir():
        raise VerificationError("package output must be a new absolute file")
    frozen_binding = _validate_shard_binding(binding)
    members = _evidence_members(evidence_root)
    manifest = {
        "schema": "stm32-local-shard-package/1",
        "binding": frozen_binding,
        "members": members,
    }
    payloads = {str(item["path"]): evidence_root.joinpath(*str(item["path"]).split("/")).read_bytes() for item in members}
    payloads["shard-manifest.json"] = canonical_json_bytes(manifest)
    with zipfile.ZipFile(package_path, "x", compression=zipfile.ZIP_STORED, allowZip64=True) as archive:
        for name in sorted(payloads, key=lambda item: item.encode("utf-8")):
            archive.writestr(_zip_info(name), payloads[name])
    data = package_path.read_bytes()
    return {"path": str(package_path), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def verify_shard_package(
    package_path: Path, reference: object, expected_binding: object
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
    try:
        archive = zipfile.ZipFile(package_path)
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
            seen.add(name)


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
        or value["module"] != "STM32TK-0601"
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
        "module": "STM32TK-0601",
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
    "software-support",
}
PLACEHOLDERS = {"unknown", "none", "n/a", "na", "placeholder", "todo", "tbd"}


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
    return (
        isinstance(value, str)
        and bool(value)
        and value.casefold() not in PLACEHOLDERS
        and unicodedata.normalize("NFC", value) == value
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
    if kind in REPOSITORY_ARTIFACT_KINDS:
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
    performance.add_argument("--input", required=True, action=_SingleUse)
    audit = sub.add_parser("dependency-audit", allow_abbrev=False)
    audit.add_argument("--input", required=True, action=_SingleUse)
    candidate = sub.add_parser("candidate-evidence", allow_abbrev=False)
    candidate.add_argument("--candidate-ledger", required=True, action=_SingleUse)
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
                result = verify_performance_calibration_input(
                    _mode_input(args.input, args.mode)
                )
            elif args.mode == "dependency-audit":
                result = verify_dependency_audit_input(_mode_input(args.input, args.mode))
            elif args.mode == "candidate-evidence":
                value = _mode_input(args.candidate_ledger, args.mode)
                ledger = validate_candidate_ledger(value)
                if ledger["expected_code_head"] != head:
                    raise VerificationError("candidate ledger CodeHead differs from loaded verifier HEAD")
                reconcile_candidate(ledger)
                result = {"mode": "candidate-evidence", "status": "PASS"}
            elif args.mode == "final-readiness":
                result = _verify_final_checkpoint(
                    _mode_input(args.input, args.mode), expected_head=head, readiness=True
                )
            else:
                result = _verify_final_checkpoint(
                    _mode_input(args.input, args.mode), expected_head=head, readiness=False
                )
    except (VerificationError, OSError, subprocess.SubprocessError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    sys.stdout.buffer.write(canonical_json_bytes(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
