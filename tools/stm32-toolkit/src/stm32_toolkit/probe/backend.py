"""Backend contract shared by PyOCD, FakeProbe, and the Probe Service."""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from types import MappingProxyType
from collections.abc import Iterable
from typing import Mapping, Protocol, runtime_checkable

from .selector import (
    probe_fingerprint as calculate_probe_fingerprint,
    public_probe_selector,
    valid_hardware_probe_id,
)

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")

PROGRAM_DIAGNOSTIC_STAGES = frozenset(
    {"driver-acquire", "programmer-create", "program-call"}
)
_PROGRAM_EXCEPTION_FIELDS = frozenset(
    {"type", "message", "errno", "winerror", "address", "resultCode"}
)
_PROGRAM_EXCEPTION_TYPE = re.compile(
    r"^(?:builtins|pyocd|usb)(?:\.[A-Za-z_][A-Za-z0-9_]*)+$"
)
_PROGRAM_MESSAGE_LIMIT = 256
_PROGRAM_TEXT_SCAN_LIMIT = 2048
_PROGRAM_INT_MIN = -(1 << 63)
_PROGRAM_INT_MAX = (1 << 63) - 1
_PROGRAM_SECRET = re.compile(
    r"(?i)\b(?:password|passwd|token|secret|credential|api[_-]?key|"
    r"authorization|access[_-]?token)\b\s*[:=]\s*(?:\"[^\"]*\"|'[^']*'|"
    r"(?:[^\s,;]+\s+)?[^\s,;]+)"
)
_PROGRAM_QUOTED = re.compile(r"\"[^\"\r\n]{0,2048}\"|'[^'\r\n]{0,2048}'")
_PROGRAM_UNTERMINATED_QUOTE = re.compile(r'''"[^"\r\n]*$|'[^'\r\n]*$''')
_PROGRAM_URL = re.compile(r"(?i)\b[a-z][a-z0-9+.-]{1,31}://[^\s\"'<>]+")
_PROGRAM_WINDOWS_PATH = re.compile(
    r"(?<![A-Za-z0-9])(?:[A-Za-z]:[\\/]|\\\\)[^\s\"'<>]+"
)
_PROGRAM_POSIX_PATH = re.compile(r"(?<![A-Za-z0-9])/(?:[^\s\"'<>]+)")
_PROGRAM_PROBE_SELECTOR = re.compile(r"(?i)\b(?:pyocd|cmsis-dap):[^\s,;]+")


def _program_redaction_tokens(redactions: Iterable[object] | object) -> tuple[str, ...]:
    if isinstance(redactions, str):
        redactions = (redactions,)
    try:
        iterator = iter(redactions)  # type: ignore[arg-type]
    except BaseException:
        return ()
    result: list[str] = []
    for _ in range(8):
        try:
            token = next(iterator)
        except StopIteration:
            break
        except BaseException:
            break
        if type(token) is str and token and len(token) <= _PROGRAM_TEXT_SCAN_LIMIT:
            if token not in result:
                result.append(token)
    return tuple(result)


def _sanitize_program_message(
    value: object, *, redactions: Iterable[object] | object = ()
) -> str:
    try:
        text = str(value)
    except BaseException:
        return "[unavailable]"
    if not isinstance(text, str):
        return "[unavailable]"
    text = text[:_PROGRAM_TEXT_SCAN_LIMIT]
    text = "".join(
        character
        if (
            0x20 <= ord(character) < 0x7F
            or ord(character) >= 0xA0
            and not 0xD800 <= ord(character) <= 0xDFFF
        )
        else " "
        for character in text
    )
    for token in _program_redaction_tokens(redactions):
        text = text.replace(token, "[redacted]")
    text = _PROGRAM_SECRET.sub("[redacted]", text)
    text = _PROGRAM_QUOTED.sub("[redacted]", text)
    text = _PROGRAM_UNTERMINATED_QUOTE.sub("[redacted]", text)
    text = _PROGRAM_URL.sub("[redacted]", text)
    text = _PROGRAM_PROBE_SELECTOR.sub("[redacted]", text)
    text = _PROGRAM_WINDOWS_PATH.sub("[redacted]", text)
    text = _PROGRAM_POSIX_PATH.sub("[redacted]", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:_PROGRAM_MESSAGE_LIMIT] or "[unavailable]"


def _program_exception_type(error: BaseException) -> str:
    try:
        error_type = type(error)
        module = error_type.__module__
        qualified_name = error_type.__qualname__
    except BaseException:
        return "unknown"
    if (
        type(module) is not str
        or type(qualified_name) is not str
        or (module != "builtins" and not module.startswith(("pyocd.", "usb.")))
    ):
        return "unknown"
    value = f"{module}.{qualified_name}"
    return (
        value
        if len(value) <= 128 and _PROGRAM_EXCEPTION_TYPE.fullmatch(value)
        else "unknown"
    )


def _program_exception_integer(error: BaseException, *names: str) -> int | None:
    for name in names:
        try:
            value = getattr(error, name)
        except BaseException:
            continue
        if (
            type(value) is int
            and _PROGRAM_INT_MIN <= value <= _PROGRAM_INT_MAX
        ):
            return value
    return None


def _program_next_exception(error: BaseException) -> BaseException | None:
    try:
        cause = error.__cause__
    except BaseException:
        cause = None
    if isinstance(cause, BaseException):
        return cause
    try:
        suppressed = error.__suppress_context__
    except BaseException:
        suppressed = True
    if suppressed:
        return None
    try:
        context = error.__context__
    except BaseException:
        context = None
    return context if isinstance(context, BaseException) else None


def _program_exception_entry(
    error: BaseException, *, redactions: tuple[str, ...]
) -> dict[str, object]:
    return {
        "type": _program_exception_type(error),
        "message": _sanitize_program_message(error, redactions=redactions),
        "errno": _program_exception_integer(error, "errno"),
        "winerror": _program_exception_integer(error, "winerror"),
        "address": _program_exception_integer(error, "address", "fault_address"),
        "resultCode": _program_exception_integer(error, "resultCode", "result_code"),
    }


def _program_message_is_safe(value: object) -> bool:
    return (
        type(value) is str
        and len(value) <= _PROGRAM_MESSAGE_LIMIT
        and _sanitize_program_message(value) == value
    )


def validate_program_diagnostic(value: object) -> dict[str, object] | None:
    """Return a detached copy of one closed, wire-safe program diagnostic."""

    if type(value) is not dict or set(value) != {
        "schemaVersion", "stage", "exceptions"
    }:
        return None
    if (
        type(value["schemaVersion"]) is not int
        or value["schemaVersion"] != 1
        or type(value["stage"]) is not str
        or value["stage"] not in PROGRAM_DIAGNOSTIC_STAGES
        or type(value["exceptions"]) is not list
        or not 1 <= len(value["exceptions"]) <= 3
    ):
        return None
    exceptions: list[dict[str, object]] = []
    for entry in value["exceptions"]:
        if type(entry) is not dict or set(entry) != _PROGRAM_EXCEPTION_FIELDS:
            return None
        exception_type = entry["type"]
        if (
            type(exception_type) is not str
            or exception_type != "unknown"
            and (
                len(exception_type) > 128
                or _PROGRAM_EXCEPTION_TYPE.fullmatch(exception_type) is None
            )
            or not _program_message_is_safe(entry["message"])
        ):
            return None
        for field_name in ("errno", "winerror", "address", "resultCode"):
            field_value = entry[field_name]
            if field_value is not None and (
                type(field_value) is not int
                or not _PROGRAM_INT_MIN <= field_value <= _PROGRAM_INT_MAX
            ):
                return None
        exceptions.append(dict(entry))
    return {
        "schemaVersion": 1,
        "stage": value["stage"],
        "exceptions": exceptions,
    }


def make_program_diagnostic(
    stage: str,
    error: BaseException,
    *,
    redactions: Iterable[object] | object = (),
) -> dict[str, object]:
    """Construct one bounded diagnostic from an exception and its cause chain."""

    if type(stage) is not str or stage not in PROGRAM_DIAGNOSTIC_STAGES:
        raise ValueError("program diagnostic stage is invalid")
    if not isinstance(error, BaseException):
        raise TypeError("program diagnostic exception is invalid")
    tokens = _program_redaction_tokens(redactions)
    exceptions: list[dict[str, object]] = []
    current: BaseException | None = error
    seen: set[int] = set()
    while current is not None and len(exceptions) < 3:
        identity = id(current)
        if identity in seen:
            break
        seen.add(identity)
        exceptions.append(_program_exception_entry(current, redactions=tokens))
        current = _program_next_exception(current)
    value = {"schemaVersion": 1, "stage": stage, "exceptions": exceptions}
    validated = validate_program_diagnostic(value)
    if validated is None:
        raise RuntimeError("program diagnostic construction failed")
    return validated


def extract_program_diagnostic(details: object) -> dict[str, object] | None:
    """Extract only a valid program diagnostic from a frozen or wire mapping."""

    if type(details) not in {dict, MappingProxyType}:
        return None
    candidate = details.get("programDiagnostic")
    if candidate is None:
        return None

    def thaw(value: object, active: frozenset[int] = frozenset(), depth: int = 0) -> object:
        if type(value) in {dict, MappingProxyType}:
            if depth > 4 or len(value) > 6 or id(value) in active:
                raise ValueError("recursive program diagnostic")
            next_active = active | {id(value)}
            return {
                key: thaw(member, next_active, depth + 1)
                for key, member in value.items()
            }
        if type(value) in {list, tuple}:
            if depth > 4 or len(value) > 3 or id(value) in active:
                raise ValueError("recursive program diagnostic")
            next_active = active | {id(value)}
            return [thaw(member, next_active, depth + 1) for member in value]
        return value

    try:
        return validate_program_diagnostic(thaw(candidate))
    except (RecursionError, TypeError, ValueError):
        return None


def program_diagnostic_details(
    stage: str,
    error: BaseException,
    *,
    redactions: Iterable[object] | object = (),
) -> dict[str, object]:
    return {"programDiagnostic": make_program_diagnostic(stage, error, redactions=redactions)}


class ProbeBackendError(Exception):
    def __init__(
        self, code: str, message: str, details: Mapping[str, object] | None = None
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = dict(details or {})


@dataclass(frozen=True)
class ProbeDescriptor:
    probe_id: str
    vendor: str
    product: str
    board_name: str | None
    hardware_id: str | None = None
    probe_fingerprint: str | None = None

    def __post_init__(self) -> None:
        hardware_id = self.hardware_id if self.hardware_id is not None else self.probe_id
        if not valid_hardware_probe_id(hardware_id):
            raise ValueError("probe descriptor hardware identifier is invalid")
        expected_selector = public_probe_selector(hardware_id)
        if self.probe_id != expected_selector:
            raise ValueError("probe descriptor selector is invalid")
        expected_fingerprint = calculate_probe_fingerprint(hardware_id)
        if (
            self.probe_fingerprint is not None
            and self.probe_fingerprint != expected_fingerprint
        ):
            raise ValueError("probe descriptor fingerprint is invalid")
        object.__setattr__(self, "hardware_id", hardware_id)
        object.__setattr__(self, "probe_fingerprint", expected_fingerprint)

    def to_dict(self) -> dict[str, object]:
        return {
            "probeId": self.probe_id,
            "hardwareId": self.hardware_id,
            "probeFingerprint": self.probe_fingerprint,
            "vendor": self.vendor,
            "product": self.product,
            "boardName": self.board_name,
        }


@dataclass(frozen=True)
class FlashBackendReport:
    bytes_programmed: int | None
    sectors_programmed: int | None

    def to_dict(self) -> dict[str, object]:
        return {
            "bytesProgrammed": self.bytes_programmed,
            "sectorsProgrammed": self.sectors_programmed,
        }


@dataclass(frozen=True)
class ProbeAttachmentEvidence:
    probe_id: str
    requested_target: str
    resolved_part_number: str
    core_count: int

    def to_dict(self) -> dict[str, object]:
        return {
            "probeId": self.probe_id,
            "requestedTarget": self.requested_target,
            "resolvedPartNumber": self.resolved_part_number,
            "coreCount": self.core_count,
        }


@dataclass(frozen=True)
class DebugHandoffMetadata:
    """Identity captured by one successful attachment for external handoff."""

    probe_id: str
    target: str
    board_id: str = field(repr=False)

    def __post_init__(self) -> None:
        if (
            not isinstance(self.probe_id, str)
            or not isinstance(self.target, str)
            or _IDENTIFIER.fullmatch(self.probe_id) is None
            or _IDENTIFIER.fullmatch(self.target) is None
            or not valid_hardware_probe_id(self.board_id)
            or public_probe_selector(self.board_id) != self.probe_id
        ):
            raise ValueError("debug handoff metadata is invalid")

    def to_dict(self) -> dict[str, str]:
        return {
            "probeId": self.probe_id,
            "target": self.target,
            "boardId": self.board_id,
        }

    @classmethod
    def from_value(cls, value: object) -> "DebugHandoffMetadata":
        if isinstance(value, cls):
            return cls(value.probe_id, value.target, value.board_id)
        if not isinstance(value, Mapping) or set(value) != {"probeId", "target", "boardId"}:
            raise ValueError("debug handoff metadata is invalid")
        probe_id = value.get("probeId")
        target = value.get("target")
        board_id = value.get("boardId")
        if not all(isinstance(item, str) for item in (probe_id, target, board_id)):
            raise ValueError("debug handoff metadata is invalid")
        return cls(probe_id, target, board_id)


@runtime_checkable
class DebugHandoffMetadataBackend(Protocol):
    """Private additive capability for the authenticated handoff path."""

    def debug_handoff_metadata(
        self, *, deadline: float | None = None
    ) -> DebugHandoffMetadata: ...


@runtime_checkable
class ProbeBackend(Protocol):
    def preflight_target_capabilities(self, probe_id: str, operation_level: object) -> None: ...

    def list_probes(self) -> tuple[ProbeDescriptor, ...]: ...

    def open_attach(
        self, probe_id: str, target: str, *, halt_on_connect: bool = False
    ) -> ProbeAttachmentEvidence: ...

    def read_memory(self, address: int, length: int) -> bytes: ...

    def read_core_registers(self, names: tuple[str, ...]) -> Mapping[str, int]: ...

    def halt(self) -> None: ...

    def resume(self) -> None: ...

    def step(self) -> None: ...

    def reset(self) -> None: ...

    def flash_elf(self, image: bytes) -> FlashBackendReport: ...

    def close(self) -> None: ...


@runtime_checkable
class TargetProbeBackend(ProbeBackend, Protocol):
    """Additive v2 target capabilities without invalidating existing Probe fakes."""

    def target_observation_policy(self) -> Mapping[str, object]: ...
    def target_read_memory(self, address: int, length: int) -> bytes: ...
    def target_read_core_registers(self, names: tuple[str, ...]) -> Mapping[str, int]: ...
    def target_identity(self) -> Mapping[str, object]: ...
    def target_state(self) -> Mapping[str, object]: ...
    def set_temporary_breakpoint(self, address: int, size: int) -> Mapping[str, object]: ...
    def clear_temporary_breakpoint(self, breakpoint_id: str) -> Mapping[str, object]: ...
    def capture_fault(self, max_stack_bytes: int) -> Mapping[str, object]: ...
    def capture_logs(self, channel: str, max_bytes: int, duration_ms: int) -> Mapping[str, object]: ...
    def open_target_transport(self, transport: str, config: Mapping[str, object], deadline_ms: int) -> Mapping[str, object]: ...
    def read_target_transport(self, transport_id: str, max_bytes: int, deadline_ms: int) -> Mapping[str, object]: ...
    def close_target_transport(self, transport_id: str) -> Mapping[str, object]: ...
