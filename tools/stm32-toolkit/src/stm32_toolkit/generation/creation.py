"""Read-only, deterministic CubeMX project creation planning."""

from __future__ import annotations

import hashlib
import os
import re
import stat
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

from stm32_toolkit.generation.managed_files import canonical_json_bytes, sha256_hex
from stm32_toolkit.tool_support import ToolSupportProfile

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MCU = re.compile(r"^STM32[A-Z0-9]+$", re.IGNORECASE)
_SAFE_BOARD = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_MAX_IOC_BYTES = 4 * 1024 * 1024
_REPARSE = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)


class CreationInputError(ValueError):
    """A stable caller-input error safe to expose at the public boundary."""

    def __init__(self, code: str, field: str):
        super().__init__(f"{code}:{field}")
        self.code = code
        self.field = field


@dataclass(frozen=True, slots=True)
class CreationSource:
    kind: Literal["mcu", "board", "ioc"]
    value: str
    sha256: str | None = None

    def to_dict(self) -> dict[str, object]:
        result: dict[str, object] = {"kind": self.kind, "value": self.value}
        if self.sha256 is not None:
            result["sha256"] = self.sha256
        return result


@dataclass(frozen=True, slots=True)
class CreationRequest:
    source: CreationSource
    destination: str
    framework: Literal["hal", "ll"]
    language: Literal["c", "cpp"]
    overwrite: Literal["refuse"] = "refuse"

    def __post_init__(self) -> None:
        if self.source.kind not in ("mcu", "board", "ioc"):
            raise CreationInputError("CREATION_SOURCE_INVALID", "source")
        if self.source.kind == "mcu" and not _MCU.fullmatch(self.source.value):
            raise CreationInputError("CREATION_SOURCE_INVALID", "mcu")
        if self.source.kind == "board" and not _SAFE_BOARD.fullmatch(self.source.value):
            raise CreationInputError("CREATION_SOURCE_INVALID", "board")
        if self.source.kind == "ioc" and _portable_error(self.source.value):
            raise CreationInputError("CREATION_PATH_INVALID", "ioc")
        if _portable_error(self.destination):
            raise CreationInputError("CREATION_PATH_INVALID", "destination")
        if self.framework not in ("hal", "ll") or self.language not in ("c", "cpp"):
            raise CreationInputError("CREATION_OPTION_INVALID", "framework/language")
        if self.overwrite != "refuse":
            raise CreationInputError("CREATION_OVERWRITE_UNSUPPORTED", "overwrite")

    @classmethod
    def from_ioc(cls, ioc: str, destination: str, *, framework: str, language: str) -> "CreationRequest":
        return cls(CreationSource("ioc", _portable(ioc)), _portable(destination), framework, language)  # type: ignore[arg-type]

    @classmethod
    def from_mcu(cls, mcu: str, destination: str, *, framework: str, language: str) -> "CreationRequest":
        return cls(CreationSource("mcu", mcu.strip().upper()), _portable(destination), framework, language)  # type: ignore[arg-type]

    @classmethod
    def from_board(cls, board: str, destination: str, *, framework: str, language: str) -> "CreationRequest":
        return cls(CreationSource("board", board.strip()), _portable(destination), framework, language)  # type: ignore[arg-type]

    def to_dict(self) -> dict[str, object]:
        return {"source": self.source.to_dict(), "destination": self.destination, "framework": self.framework, "language": self.language, "overwrite": self.overwrite}


@dataclass(frozen=True, slots=True)
class CreationBlocker:
    code: str
    component: str
    remediation: str

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "component": self.component, "remediation": self.remediation}


@dataclass(frozen=True, slots=True)
class CreationPlan:
    schema_version: Literal[1]
    plan_id: str
    action_digest: str
    expires_at: str
    request: CreationRequest
    tool_profile_digest: str
    destination_inventory_digest: str
    blockers: tuple[CreationBlocker, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "schemaVersion": self.schema_version,
            "planId": self.plan_id,
            "actionDigest": self.action_digest,
            "expiresAt": self.expires_at,
            "request": self.request.to_dict(),
            "toolProfileDigest": self.tool_profile_digest,
            "destinationInventoryDigest": self.destination_inventory_digest,
            "blockers": [blocker.to_dict() for blocker in self.blockers],
        }


def _portable_error(value: object) -> str | None:
    if not isinstance(value, str) or not value:
        return "empty"
    if "\x00" in value or any(ord(char) < 32 for char in value):
        return "control"
    if value.startswith(("/", "\\", "//", "\\\\")) or re.match(r"^[A-Za-z]:", value):
        return "absolute"
    parts = value.replace("\\", "/").split("/")
    if any(part in ("", ".", "..") for part in parts):
        return "component"
    return None


def _portable(value: str) -> str:
    value = value.replace("\\", "/")
    if _portable_error(value):
        raise CreationInputError("CREATION_PATH_INVALID", "path")
    return value


def _regular(path: Path) -> bool:
    try:
        info = os.lstat(path)
        return stat.S_ISREG(info.st_mode) and not path.is_symlink() and not bool(getattr(info, "st_file_attributes", 0) & _REPARSE)
    except OSError:
        return False


def _directory(path: Path) -> bool:
    try:
        info = os.lstat(path)
        return stat.S_ISDIR(info.st_mode) and not path.is_symlink() and not bool(getattr(info, "st_file_attributes", 0) & _REPARSE)
    except OSError:
        return False


def _ioc_hash(path: Path) -> str:
    if not _regular(path) or path.suffix.casefold() != ".ioc":
        raise CreationInputError("CREATION_IOC_INVALID", "ioc")
    try:
        if path.stat().st_size > _MAX_IOC_BYTES:
            raise CreationInputError("CREATION_IOC_TOO_LARGE", "ioc")
        path.read_text(encoding="utf-8")
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except UnicodeError:
        raise CreationInputError("CREATION_IOC_INVALID", "ioc") from None
    except OSError:
        raise CreationInputError("CREATION_IOC_UNAVAILABLE", "ioc") from None


def _inventory(root: Path, destination: Path) -> tuple[str, bool]:
    if destination.exists() and not _directory(destination):
        return sha256_hex(canonical_json_bytes({"path": destination.name, "kind": "unsafe"})), True
    if not destination.exists():
        return sha256_hex(canonical_json_bytes({"state": "absent", "entries": []})), False
    entries: list[dict[str, object]] = []
    try:
        for child in sorted(destination.rglob("*"), key=lambda item: item.as_posix().casefold()):
            relative = child.relative_to(destination).as_posix()
            if child.is_symlink() or not (_directory(child) or _regular(child)):
                entries.append({"path": relative, "kind": "unsafe"})
            else:
                entries.append({"path": relative, "kind": "dir" if child.is_dir() else "file", "size": child.stat().st_size if child.is_file() else None})
    except OSError:
        entries.append({"path": "<unavailable>", "kind": "unsafe"})
    return sha256_hex(canonical_json_bytes({"state": "empty" if not entries else "populated", "entries": entries})), bool(entries)


def _validate_chain(root: Path, target: Path) -> None:
    try:
        relative = target.relative_to(root)
    except ValueError:
        raise CreationInputError("CREATION_PATH_INVALID", "path") from None
    current = root
    for part in relative.parts[:-1] if relative.parts else ():
        current = current / part
        if current.exists() and not _directory(current):
            raise CreationInputError("CREATION_PATH_INVALID", "path")


def _tool_digest(tools: ToolSupportProfile) -> str:
    return sha256_hex(canonical_json_bytes(tools.to_dict()))


def _expiry(now: datetime) -> str:
    instant = now.astimezone(timezone.utc) + timedelta(hours=1)
    return instant.replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def plan_project_creation(workspace_root: Path, request: CreationRequest, tools: ToolSupportProfile, *, now: datetime) -> CreationPlan:
    try:
        root = workspace_root.expanduser().resolve(strict=True)
    except (OSError, RuntimeError):
        raise CreationInputError("CREATION_WORKSPACE_INVALID", "workspaceRoot") from None
    if not root.is_dir():
        raise CreationInputError("CREATION_WORKSPACE_INVALID", "workspaceRoot")
    source = root / request.source.value if request.source.kind == "ioc" else None
    if source is not None:
        _validate_chain(root, source)
    source_hash = _ioc_hash(source) if source is not None else None
    normalized_source = CreationSource(request.source.kind, request.source.value, source_hash)
    normalized = CreationRequest(normalized_source, request.destination, request.framework, request.language, request.overwrite)
    destination = root / normalized.destination
    _validate_chain(root, destination)
    inventory_digest, has_inventory = _inventory(root, destination)
    blockers: list[CreationBlocker] = []
    issue_map = {issue.code: issue for issue in tools.issues}
    for code in ("CUBEMX_MISSING", "CUBEMX_UNSUPPORTED", "CUBECLT_MISSING", "GCC_MISSING", "CMAKE_MISSING", "NINJA_MISSING", "PYTHON_UNSUPPORTED"):
        issue = issue_map.get(code)
        if issue:
            blockers.append(CreationBlocker(issue.code, issue.component, issue.remediation))
    if tools.cubemx is None and not any(item.code == "CUBEMX_MISSING" for item in blockers):
        blockers.append(CreationBlocker("CUBEMX_MISSING", "cubeMx", "Install STM32CubeMX 6.18 and rerun discovery."))
    for fact, code, component in ((tools.cubeclt_root, "CUBECLT_MISSING", "cubeClt"), (tools.gcc, "GCC_MISSING", "gcc"), (tools.cmake, "CMAKE_MISSING", "cmake"), (tools.ninja, "NINJA_MISSING", "ninja")):
        if fact is None and not any(item.code == code for item in blockers):
            blockers.append(CreationBlocker(code, component, "Provide the supported STM32CubeCLT 1.22.0 tool."))
    if has_inventory:
        blockers.append(CreationBlocker("DESTINATION_NOT_EMPTY", "destination", "Choose an absent or empty destination; overwrite is refuse-only."))
    tool_digest = _tool_digest(tools)
    root_digest = sha256_hex(str(root).replace("\\", "/").casefold().encode("utf-8"))
    plan_inputs = {"schemaVersion": 1, "request": normalized.to_dict(), "toolProfileDigest": tool_digest, "destinationInventoryDigest": inventory_digest, "workspaceDigest": root_digest}
    plan_id = sha256_hex(canonical_json_bytes(plan_inputs))
    action_digest = sha256_hex(canonical_json_bytes({"operation": "project-create", "planId": plan_id}))
    return CreationPlan(1, plan_id, action_digest, _expiry(now), normalized, tool_digest, inventory_digest, tuple(blockers))
