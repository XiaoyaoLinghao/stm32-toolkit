"""Immutable models shared by Host and Target test runners."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import platform
import re
import unicodedata
from typing import Iterable, Literal, Mapping, Sequence, cast

from stm32_toolkit.evidence import ArtifactRef, EvidenceIdentity, canonical_json_bytes


TEST_SCHEMA = "stm32-test/1"
RUN_STATES = ("discovered", "running", "passed", "failed", "error", "cancelled")
CASE_STATES = ("passed", "failed", "skipped", "error", "timeout")
EVENT_KINDS = {
    1: "inventory",
    2: "run_start",
    3: "case_start",
    4: "case_result",
    5: "run_end",
    6: "log",
}
MAX_FRAME_PAYLOAD_BYTES = 16 * 1024
MAX_RUN_STREAM_BYTES = 64 * 1024 * 1024
MAX_CASES = 100_000
MAX_STRING_BYTES = 64 * 1024
MAX_DURATION_MS = 2**63 - 1
_HASH = re.compile(r"^[0-9a-f]{64}$")
_RUN_ID = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


class TestProtocolError(ValueError):
    """Stable common-test failure with a machine-readable code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def protocol_error(code: str, message: str) -> TestProtocolError:
    return TestProtocolError(code, message)


def _string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value or unicodedata.normalize("NFC", value) != value:
        raise protocol_error("TEST_PROTOCOL_INVALID", f"{field} must be a non-empty NFC string")
    if len(value.encode("utf-8")) > MAX_STRING_BYTES:
        raise protocol_error("TEST_PROTOCOL_INVALID", f"{field} exceeds the UTF-8 limit")
    return value


def _utc(value: object, field: str) -> str:
    text = _string(value, field)
    try:
        parsed = datetime.strptime(text, "%Y-%m-%dT%H:%M:%S.%fZ")
    except ValueError as exc:
        raise protocol_error("TEST_PROTOCOL_INVALID", f"{field} must be canonical UTC") from exc
    if parsed.strftime("%Y-%m-%dT%H:%M:%S.%fZ") != text:
        raise protocol_error("TEST_PROTOCOL_INVALID", f"{field} must be canonical UTC")
    return text


def _duration(value: object, field: str = "duration_ms") -> int:
    if type(value) is not int or not 0 <= value <= MAX_DURATION_MS:
        raise protocol_error("TEST_PROTOCOL_INVALID", f"{field} must be an unsigned bounded integer")
    return value


def _hash(value: object, field: str) -> str:
    if not isinstance(value, str) or _HASH.fullmatch(value) is None:
        raise protocol_error("TEST_PROTOCOL_INVALID", f"{field} must be a lowercase SHA-256")
    return value


def _artifact(value: object, field: str, *, nullable: bool = True) -> ArtifactRef | None:
    if value is None and nullable:
        return None
    if not isinstance(value, ArtifactRef):
        raise protocol_error("TEST_PROTOCOL_INVALID", f"{field} must be an ArtifactRef")
    return value


def _sorted_case_ids(case_ids: object, *, allow_empty: bool = False) -> tuple[str, ...]:
    if not isinstance(case_ids, tuple):
        raise protocol_error("TEST_PROTOCOL_INVALID", "case_ids must be a tuple")
    if (not case_ids and not allow_empty) or len(case_ids) > MAX_CASES:
        code = "TEST_NO_CASES" if not case_ids else "TEST_PROTOCOL_INVALID"
        raise protocol_error(code, "test inventory is empty" if not case_ids else "too many test cases")
    normalized = tuple(_string(item, "case_id") for item in case_ids)
    if len(set(normalized)) != len(normalized):
        raise protocol_error("TEST_DUPLICATE_CASE", "case IDs must be unique")
    if normalized != tuple(sorted(normalized, key=lambda item: item.encode("utf-8"))):
        raise protocol_error("TEST_PROTOCOL_INVALID", "case IDs must use UTF-8 byte order")
    return normalized


def calculate_inventory_digest(
    mode: str,
    identity: EvidenceIdentity,
    case_ids: Sequence[str],
    *,
    executable_inventory: Sequence[Mapping[str, object]] = (),
) -> str:
    """Digest canonical identity, sorted IDs, and Host executable commands."""
    if mode not in {"host", "target"} or not isinstance(identity, EvidenceIdentity):
        raise protocol_error("TEST_PROTOCOL_INVALID", "inventory mode or identity is invalid")
    ordered = tuple(sorted((_string(item, "case_id") for item in case_ids), key=lambda item: item.encode("utf-8")))
    if len(ordered) != len(set(ordered)) or not ordered:
        raise protocol_error("TEST_NO_CASES", "test inventory is empty or duplicated")
    executables: list[dict[str, object]] = []
    for item in executable_inventory:
        if not isinstance(item, Mapping) or set(item) != {"case_id", "command"}:
            raise protocol_error("TEST_PROTOCOL_INVALID", "executable inventory item is invalid")
        case_id = _string(item["case_id"], "executable case_id")
        command = item["command"]
        if not isinstance(command, (list, tuple)) or not command:
            raise protocol_error("TEST_PROTOCOL_INVALID", "executable command is invalid")
        members = [_string(member, "executable command member") for member in command]
        executables.append({"case_id": case_id, "command": members})
    executables.sort(key=lambda item: cast(str, item["case_id"]).encode("utf-8"))
    if executables and [item["case_id"] for item in executables] != list(ordered):
        raise protocol_error("TEST_PROTOCOL_INVALID", "executable inventory differs from case IDs")
    payload = {
        "case_ids": list(ordered),
        "executables": executables,
        "identity": identity.to_dict(),
        "mode": mode,
    }
    return sha256(canonical_json_bytes(payload)).hexdigest()


def _canonical_host_executables(
    executable_inventory: Iterable[Mapping[str, object]],
) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for item in executable_inventory:
        if not isinstance(item, Mapping) or set(item) != {"case_id", "command"}:
            raise protocol_error("TEST_PROTOCOL_INVALID", "Host executable inventory item is invalid")
        case_id = _string(item["case_id"], "Host executable case_id")
        command = item["command"]
        if not isinstance(command, (list, tuple)) or not command:
            raise protocol_error("TEST_PROTOCOL_INVALID", "Host executable command is invalid")
        result.append({
            "case_id": case_id,
            "command": [_string(member, "Host executable command member") for member in command],
        })
    result.sort(key=lambda item: cast(str, item["case_id"]).encode("utf-8"))
    if not result or len({item["case_id"] for item in result}) != len(result):
        raise protocol_error("TEST_NO_CASES", "Host executable inventory is empty or duplicated")
    return result


def calculate_host_build_inventory_digest(
    build_preset: str,
    ctest_preset: str,
    labels: Sequence[str],
    executable_inventory: Iterable[Mapping[str, object]],
) -> str:
    """Canonical Host ``build_id`` for the CMake build/test inventory."""
    normalized_labels = tuple(
        sorted((_string(label, "Host test label") for label in labels), key=lambda item: item.encode("utf-8"))
    )
    if len(set(normalized_labels)) != len(normalized_labels):
        raise protocol_error("TEST_PROTOCOL_INVALID", "Host test labels are duplicated")
    payload = {
        "build_preset": _string(build_preset, "build_preset"),
        "ctest_preset": _string(ctest_preset, "ctest_preset"),
        "labels": list(normalized_labels),
        "tests": _canonical_host_executables(executable_inventory),
    }
    return sha256(canonical_json_bytes(payload)).hexdigest()


def calculate_host_test_executable_inventory_digest(
    executable_inventory: Iterable[Mapping[str, object]],
) -> str:
    """Canonical Host ``elf_sha256`` for the ordered test executable inventory."""
    executables = [
        {"case_id": item["case_id"], "executable": cast(list[str], item["command"])[0]}
        for item in _canonical_host_executables(executable_inventory)
    ]
    return sha256(canonical_json_bytes(executables)).hexdigest()


@dataclass(frozen=True)
class TestCaseResult:
    case_id: str
    state: Literal["passed", "failed", "skipped", "error", "timeout"]
    started_at_utc: str
    ended_at_utc: str
    duration_ms: int
    message: str | None
    stdout: ArtifactRef | None
    stderr: ArtifactRef | None

    def __post_init__(self) -> None:
        _string(self.case_id, "case_id")
        if self.state not in CASE_STATES:
            raise protocol_error("TEST_PROTOCOL_INVALID", "case state is invalid")
        started = _utc(self.started_at_utc, "started_at_utc")
        ended = _utc(self.ended_at_utc, "ended_at_utc")
        if ended < started:
            raise protocol_error("TEST_PROTOCOL_INVALID", "case end precedes its start")
        _duration(self.duration_ms)
        if self.message is not None:
            _string(self.message, "message")
        _artifact(self.stdout, "stdout")
        _artifact(self.stderr, "stderr")

    def to_dict(self) -> dict[str, object]:
        return {
            "case_id": self.case_id,
            "state": self.state,
            "started_at_utc": self.started_at_utc,
            "ended_at_utc": self.ended_at_utc,
            "duration_ms": self.duration_ms,
            "message": self.message,
            "stdout": None if self.stdout is None else self.stdout.to_dict(),
            "stderr": None if self.stderr is None else self.stderr.to_dict(),
        }


@dataclass(frozen=True)
class TestInventory:
    mode: Literal["host", "target"]
    identity: EvidenceIdentity
    case_ids: tuple[str, ...]
    inventory_digest: str
    discovered_at_utc: str

    def __post_init__(self) -> None:
        if self.mode not in {"host", "target"} or not isinstance(self.identity, EvidenceIdentity):
            raise protocol_error("TEST_PROTOCOL_INVALID", "inventory mode or identity is invalid")
        _sorted_case_ids(self.case_ids)
        _hash(self.inventory_digest, "inventory_digest")
        _utc(self.discovered_at_utc, "discovered_at_utc")

    def to_dict(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "identity": self.identity.to_dict(),
            "case_ids": list(self.case_ids),
            "inventory_digest": self.inventory_digest,
            "discovered_at_utc": self.discovered_at_utc,
        }


def create_inventory(
    mode: Literal["host", "target"],
    identity: EvidenceIdentity,
    case_ids: Sequence[str],
    discovered_at_utc: str,
    *,
    executable_inventory: Sequence[Mapping[str, object]] = (),
) -> TestInventory:
    ordered = tuple(
        sorted((_string(item, "case_id") for item in case_ids), key=lambda item: item.encode("utf-8"))
    )
    digest = calculate_inventory_digest(
        mode, identity, ordered, executable_inventory=executable_inventory
    )
    return TestInventory(mode, identity, ordered, digest, discovered_at_utc)


@dataclass(frozen=True)
class TestRunManifest:
    schema: Literal["stm32-test/1"]
    run_id: str
    mode: Literal["host", "target"]
    state: Literal["discovered", "running", "passed", "failed", "error", "cancelled"]
    identity: EvidenceIdentity
    transport: str | None
    cases: tuple[TestCaseResult, ...]
    started_at_utc: str
    ended_at_utc: str
    duration_ms: int
    stdout: ArtifactRef | None
    stderr: ArtifactRef | None
    raw_events: ArtifactRef

    def __post_init__(self) -> None:
        if self.schema != TEST_SCHEMA:
            raise protocol_error("TEST_PROTOCOL_INVALID", "schema must be stm32-test/1")
        run_id = _string(self.run_id, "run_id")
        if _RUN_ID.fullmatch(run_id) is None:
            raise protocol_error("TEST_PROTOCOL_INVALID", "run_id is invalid")
        if self.mode not in {"host", "target"} or self.state not in RUN_STATES:
            raise protocol_error("TEST_PROTOCOL_INVALID", "run mode or state is invalid")
        if not isinstance(self.identity, EvidenceIdentity):
            raise protocol_error("TEST_PROTOCOL_INVALID", "identity must be EvidenceIdentity")
        if self.transport is not None:
            _string(self.transport, "transport")
        if not isinstance(self.cases, tuple) or not self.cases or len(self.cases) > MAX_CASES:
            raise protocol_error("TEST_PROTOCOL_INVALID", "cases must be a bounded tuple")
        if not all(isinstance(case, TestCaseResult) for case in self.cases):
            raise protocol_error("TEST_PROTOCOL_INVALID", "cases must contain TestCaseResult")
        ids = [case.case_id for case in self.cases]
        if len(ids) != len(set(ids)):
            raise protocol_error("TEST_DUPLICATE_CASE", "manifest case IDs must be unique")
        started = _utc(self.started_at_utc, "started_at_utc")
        ended = _utc(self.ended_at_utc, "ended_at_utc")
        if ended < started:
            raise protocol_error("TEST_PROTOCOL_INVALID", "run end precedes its start")
        _duration(self.duration_ms)
        _artifact(self.stdout, "stdout")
        _artifact(self.stderr, "stderr")
        raw = _artifact(self.raw_events, "raw_events", nullable=False)
        assert raw is not None
        if raw.size_bytes > MAX_RUN_STREAM_BYTES:
            raise protocol_error("TEST_STREAM_TOO_LARGE", "raw event stream exceeds 64 MiB")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "run_id": self.run_id,
            "mode": self.mode,
            "state": self.state,
            "identity": self.identity.to_dict(),
            "transport": self.transport,
            "cases": [case.to_dict() for case in self.cases],
            "started_at_utc": self.started_at_utc,
            "ended_at_utc": self.ended_at_utc,
            "duration_ms": self.duration_ms,
            "stdout": None if self.stdout is None else self.stdout.to_dict(),
            "stderr": None if self.stderr is None else self.stderr.to_dict(),
            "raw_events": self.raw_events.to_dict(),
        }


def host_target_device(*, system: str | None = None, architecture: str | None = None) -> str:
    os_name = (platform.system() if system is None else system).casefold()
    machine = (platform.machine() if architecture is None else architecture).casefold()
    os_name = {"darwin": "macos"}.get(os_name, os_name)
    machine = {
        "x86_64": "amd64", "amd64": "amd64", "aarch64": "arm64",
        "arm64": "arm64", "i386": "x86", "i686": "x86", "x86": "x86",
    }.get(machine, machine)
    _string(os_name, "host operating system")
    _string(machine, "host architecture")
    return f"host:{os_name}/{machine}"


def validate_host_identity(
    identity: EvidenceIdentity,
    *,
    system: str | None = None,
    architecture: str | None = None,
) -> None:
    if not isinstance(identity, EvidenceIdentity):
        raise protocol_error("TEST_IDENTITY_MISMATCH", "host identity is invalid")
    expected = host_target_device(system=system, architecture=architecture)
    if (
        identity.target_device != expected
        or identity.build_id == "0" * 64
        or identity.elf_sha256 == "0" * 64
    ):
        raise protocol_error(
            "TEST_IDENTITY_MISMATCH",
            "host identity must bind the exact host and canonical build/executable inventories",
        )
