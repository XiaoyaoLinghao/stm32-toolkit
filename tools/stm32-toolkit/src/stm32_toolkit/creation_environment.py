"""Closed execution-environment facts for authorized CubeMX creation.

The VS07-A support profile describes discovered tools.  This module adds the
creation-only facts that are deliberately absent from that profile: CubeMX's
safe sibling Java runtime and one trusted, offline Cube firmware package.  All
paths are inspected without following redirects and the resulting immutable
fact set is bound by one deterministic digest.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from stm32_toolkit.generation.creation import CreationRequest
from stm32_toolkit.generation.managed_files import canonical_json_bytes, sha256_hex
from stm32_toolkit.tool_support import ToolFact, ToolSupportProfile

_REPARSE = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
_PACKAGE_RE = re.compile(r"^STM32Cube_FW_([A-Z0-9]+)_V([0-9][A-Za-z0-9_.-]*)$", re.IGNORECASE)
_MAX_PACKAGE_METADATA_BYTES = 256 * 1024
_MAX_PACKAGE_FILES = 200_000
# The official F4 package contains Projects/*/Examples/*/STM32CubeIDE/Example
# trees 13 components deep; retain a finite bound above that observed shape.
_MAX_REPOSITORY_DEPTH = 16
_MAX_MCU_DESCRIPTORS = 10_000
_MAX_MCU_DESCRIPTOR_BYTES = 2 * 1024 * 1024


class CreationEnvironmentError(ValueError):
    """A bounded, typed creation-environment failure."""

    def __init__(self, code: str, message: str, details: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = dict(details or {})


def _safe_regular(path: Path) -> Path | None:
    try:
        lexical = path.absolute()
        resolved = lexical.resolve(strict=True)
        current = lexical
        while True:
            info = os.lstat(current)
            if stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & _REPARSE):
                return None
            if current == current.parent:
                break
            current = current.parent
        info = os.lstat(resolved)
        if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & _REPARSE):
            return None
        return resolved
    except (OSError, RuntimeError, ValueError):
        return None


def _safe_directory(path: Path) -> Path | None:
    try:
        lexical = path.absolute()
        resolved = lexical.resolve(strict=True)
        current = lexical
        while True:
            info = os.lstat(current)
            if stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & _REPARSE):
                return None
            if current == current.parent:
                break
            current = current.parent
        info = os.lstat(resolved)
        if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & _REPARSE):
            return None
        return resolved
    except (OSError, RuntimeError, ValueError):
        return None


def _digest_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _display_path(path: Path) -> str:
    """Return a portable internal path spelling (never used in public errors)."""
    return path.as_posix()


def _family_for_request(request: CreationRequest, project_root: Path | None = None) -> str | None:
    value = request.source.value.upper()
    if request.source.kind == "ioc":
        try:
            ioc_path = Path(request.source.value)
            if project_root is not None:
                ioc_path = project_root / ioc_path
            text = ioc_path.read_text(encoding="utf-8", errors="strict")
        except (OSError, UnicodeError):
            return None
        match = re.search(r"(?im)^\s*Mcu\.Name\s*=\s*(STM32[A-Za-z0-9]+)", text)
        value = match.group(1).upper() if match else value
    # Cube package families use the series letter plus its first number
    # (F4/G4/H7/etc.); the MCU suffix continues after that family token.
    match = re.match(r"^STM32([A-Z]+[0-9])", value)
    return match.group(1) if match else None


def _default_repository() -> Path:
    # This is the canonical updater location observed by VS07-A.  It is only
    # read; the creation flow never creates or repairs it.
    return Path.home() / "STM32Cube" / "Repository"


def _package_metadata(package: Path) -> tuple[str, str]:
    name = package.name
    version = ""
    metadata_candidates = (package / "package.xml", package / ".pack", package / "package.json")
    for metadata in metadata_candidates:
        try:
            info = os.lstat(metadata)
            if not stat.S_ISREG(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & _REPARSE):
                continue
            if info.st_size > _MAX_PACKAGE_METADATA_BYTES:
                raise CreationEnvironmentError("CUBEMX_PACKAGE_INVALID", "firmware package metadata is oversized")
            data = metadata.read_bytes()
            if metadata.suffix.casefold() == ".json":
                payload = json.loads(data.decode("utf-8"))
                if isinstance(payload, dict):
                    name = str(payload.get("name", name))
                    version = str(payload.get("version", ""))
            else:
                root = ET.fromstring(data.decode("utf-8"))
                name = str(root.attrib.get("name", name))
                version = str(root.attrib.get("version", ""))
            break
        except CreationEnvironmentError:
            raise
        except (OSError, UnicodeError, ET.ParseError, ValueError, TypeError):
            raise CreationEnvironmentError("CUBEMX_PACKAGE_INVALID", "firmware package metadata is invalid") from None
    match = _PACKAGE_RE.match(package.name)
    if match and not version:
        version = match.group(2)
    if not name or not version:
        raise CreationEnvironmentError("CUBEMX_PACKAGE_INVALID", "firmware package metadata is incomplete")
    return name, version


def _package_digest(package: Path) -> str:
    entries: list[dict[str, object]] = []
    try:
        count = 0
        for path in sorted(package.rglob("*"), key=lambda item: item.as_posix().casefold()):
            count += 1
            if count > _MAX_PACKAGE_FILES:
                raise CreationEnvironmentError("CUBEMX_PACKAGE_INVALID", "firmware package inventory is oversized")
            relative = path.relative_to(package)
            depth = len(relative.parts)
            if depth > _MAX_REPOSITORY_DEPTH:
                raise CreationEnvironmentError("CUBEMX_PACKAGE_INVALID", "firmware package path is too deep")
            info = os.lstat(path)
            if stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & _REPARSE):
                raise CreationEnvironmentError("CUBEMX_PACKAGE_INVALID", "firmware package contains a redirect")
            if stat.S_ISREG(info.st_mode):
                entries.append({"path": relative.as_posix(), "kind": "file", "size": info.st_size, "sha256": _digest_file(path)})
            elif stat.S_ISDIR(info.st_mode):
                entries.append({"path": relative.as_posix(), "kind": "dir"})
            else:
                raise CreationEnvironmentError("CUBEMX_PACKAGE_INVALID", "firmware package contains a special file")
    except CreationEnvironmentError:
        raise
    except OSError:
        raise CreationEnvironmentError("CUBEMX_PACKAGE_INVALID", "firmware package cannot be inspected") from None
    return sha256_hex(canonical_json_bytes(entries))


def _mcu_descriptor_facts(install: Path, request: CreationRequest) -> tuple[str | None, str | None, str | None]:
    if request.source.kind != "mcu":
        return None, None, None
    root = _safe_directory(install / "db" / "mcu")
    if root is None:
        raise CreationEnvironmentError("CUBEMX_MCU_DESCRIPTOR_INVALID", "CubeMX MCU descriptor database is unavailable")
    expected = f"{request.source.value.casefold()}.xml"
    matches: list[Path] = []
    inspected = 0
    pending = [root]
    try:
        while pending:
            current = pending.pop()
            children = sorted(current.iterdir(), key=lambda path: path.name.casefold())
            for child in children:
                inspected += 1
                if inspected > _MAX_MCU_DESCRIPTORS:
                    raise CreationEnvironmentError("CUBEMX_MCU_DESCRIPTOR_INVALID", "CubeMX MCU descriptor inventory is oversized")
                info = os.lstat(child)
                if stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & _REPARSE):
                    raise CreationEnvironmentError("CUBEMX_MCU_DESCRIPTOR_INVALID", "CubeMX MCU descriptor database contains a redirect")
                if stat.S_ISDIR(info.st_mode):
                    pending.append(child)
                elif stat.S_ISREG(info.st_mode) and child.name.casefold() == expected:
                    safe = _safe_regular(child)
                    if safe is None:
                        raise CreationEnvironmentError("CUBEMX_MCU_DESCRIPTOR_INVALID", "CubeMX MCU descriptor is unsafe")
                    matches.append(safe)
    except CreationEnvironmentError:
        raise
    except OSError:
        raise CreationEnvironmentError("CUBEMX_MCU_DESCRIPTOR_INVALID", "CubeMX MCU descriptors cannot be inspected") from None
    if len(matches) != 1:
        raise CreationEnvironmentError("CUBEMX_MCU_DESCRIPTOR_INVALID", "CubeMX MCU descriptor is missing or ambiguous")
    descriptor = matches[0]
    try:
        info = os.lstat(descriptor)
        if info.st_size > _MAX_MCU_DESCRIPTOR_BYTES:
            raise CreationEnvironmentError("CUBEMX_MCU_DESCRIPTOR_INVALID", "CubeMX MCU descriptor is oversized")
        data = descriptor.read_bytes()
        root_node = ET.fromstring(data.decode("utf-8"))
    except CreationEnvironmentError:
        raise
    except (OSError, UnicodeError, ET.ParseError):
        raise CreationEnvironmentError("CUBEMX_MCU_DESCRIPTOR_INVALID", "CubeMX MCU descriptor is malformed") from None
    token = root_node.attrib.get("RefName")
    if not isinstance(token, str) or not token or token.casefold() != request.source.value.casefold():
        raise CreationEnvironmentError("CUBEMX_MCU_DESCRIPTOR_INVALID", "CubeMX MCU descriptor RefName disagrees with the request")
    return token, descriptor.relative_to(install).as_posix(), hashlib.sha256(data).hexdigest()


@dataclass(frozen=True, slots=True)
class CreationExecutionEnvironment:
    """Immutable execution facts bound to one authorized creation."""

    cubemx_executable: Path
    cubemx_version: str
    cubemx_sha256: str
    java_executable: Path
    java_sha256: str
    repository: Path
    package: Path
    package_name: str
    package_version: str
    package_sha256: str
    native_source_token: str | None = None
    native_descriptor_path: str | None = None
    native_descriptor_sha256: str | None = None
    cubeclt_root: Path | None = None
    gcc: ToolFact | None = None
    cmake: ToolFact | None = None
    ninja: ToolFact | None = None
    protocol: tuple[str, ...] = (
        "source",
        "project name",
        "project path",
        "project toolchain",
        "project compiler",
        "SetStructure",
        "project generate",
        "exit",
    )
    digest: str = field(init=False)

    def __post_init__(self) -> None:
        payload = {
            "cubeMx": {"path": _display_path(self.cubemx_executable), "version": self.cubemx_version, "sha256": self.cubemx_sha256},
            "java": {"path": _display_path(self.java_executable), "sha256": self.java_sha256},
            "repository": _display_path(self.repository),
            "package": {"path": _display_path(self.package), "name": self.package_name, "version": self.package_version, "sha256": self.package_sha256},
            "native": {
                "sourceToken": self.native_source_token,
                "descriptorPath": self.native_descriptor_path,
                "descriptorSha256": self.native_descriptor_sha256,
            },
            "cubeCltRoot": _display_path(self.cubeclt_root) if self.cubeclt_root else None,
            "gcc": self.gcc.to_dict() if self.gcc else None,
            "cmake": self.cmake.to_dict() if self.cmake else None,
            "ninja": self.ninja.to_dict() if self.ninja else None,
            "protocol": list(self.protocol),
        }
        object.__setattr__(self, "digest", sha256_hex(canonical_json_bytes(payload)))

    @property
    def cubemx_path(self) -> Path:
        return self.cubemx_executable

    @property
    def cube_mx(self) -> Path:
        return self.cubemx_executable

    @property
    def java_path(self) -> Path:
        return self.java_executable

    @property
    def java(self) -> Path:
        return self.java_executable

    @property
    def repository_digest(self) -> str:
        return sha256_hex(canonical_json_bytes({"repository": _display_path(self.repository), "package": self.package_sha256}))

    @property
    def package_digest(self) -> str:
        return self.package_sha256

    def to_dict(self) -> dict[str, object]:
        """Return sanitized facts suitable for internal evidence/public filtering."""
        return {
            "cubeMxVersion": self.cubemx_version,
            "cubeMxSha256": self.cubemx_sha256,
            "javaSha256": self.java_sha256,
            "packageName": self.package_name,
            "packageVersion": self.package_version,
            "packageSha256": self.package_sha256,
            "nativeSourceToken": self.native_source_token,
            "nativeDescriptorPath": self.native_descriptor_path,
            "nativeDescriptorSha256": self.native_descriptor_sha256,
            "repositoryDigest": self.repository_digest,
            "cubeCltRoot": _display_path(self.cubeclt_root) if self.cubeclt_root else None,
            "digest": self.digest,
            "protocol": list(self.protocol),
        }


def discover_creation_environment(
    support: ToolSupportProfile,
    request: CreationRequest,
    *,
    repository: Path | None = None,
    project_root: Path | None = None,
) -> CreationExecutionEnvironment:
    """Resolve and validate the closed creation environment.

    ``repository`` is an internal trusted configuration selected by the CLI or
    runtime.  Callers cannot override CubeMX, Java, process, timeout, or script
    facts through the public apply APIs.
    """
    if not isinstance(support, ToolSupportProfile) or support.cubemx is None:
        raise CreationEnvironmentError("CUBEMX_MISSING", "STM32CubeMX is unavailable")
    cubemx = _safe_regular(support.cubemx.path)
    if cubemx is None:
        raise CreationEnvironmentError("CUBEMX_INVALID", "STM32CubeMX executable is invalid")
    install = cubemx.parent
    sibling = _safe_regular(install / "jre" / "bin" / "java.exe")
    if sibling is None:
        raise CreationEnvironmentError("CUBEMX_JAVA_MISSING", "CubeMX sibling Java runtime is unavailable")
    expected_root = install.resolve(strict=True)
    try:
        sibling.relative_to(expected_root)
    except ValueError:
        raise CreationEnvironmentError("CUBEMX_JAVA_INVALID", "CubeMX Java runtime is outside its installation") from None

    repository_candidate = repository or _default_repository()
    repository_path = _safe_directory(repository_candidate)
    if repository_path is None:
        try:
            exists = os.path.lexists(repository_candidate)
        except OSError:
            exists = True
        code = "CUBEMX_REPOSITORY_INVALID" if exists else "CUBEMX_REPOSITORY_MISSING"
        raise CreationEnvironmentError(code, "Cube firmware repository is unavailable")
    family = _family_for_request(request, project_root)
    candidates: list[Path] = []
    try:
        for item in sorted(repository_path.iterdir(), key=lambda path: path.name.casefold()):
            if not _PACKAGE_RE.fullmatch(item.name):
                continue
            if item.suffix.casefold() == ".zip":
                continue
            safe_item = _safe_directory(item)
            if safe_item is None:
                raise CreationEnvironmentError("CUBEMX_REPOSITORY_INVALID", "Cube firmware repository contains an unsafe package")
            if family is None or item.name.upper().startswith(f"STM32CUBE_FW_{family.upper()}_"):
                candidates.append(safe_item)
    except OSError:
        raise CreationEnvironmentError("CUBEMX_REPOSITORY_INVALID", "Cube firmware repository cannot be inspected") from None
    if not candidates:
        raise CreationEnvironmentError("CUBEMX_PACKAGE_MISSING", "required Cube firmware package is unavailable")
    if len(candidates) != 1:
        raise CreationEnvironmentError("CUBEMX_PACKAGE_AMBIGUOUS", "required Cube firmware package is ambiguous")
    package = candidates[0]
    name, version = _package_metadata(package)
    package_hash = _package_digest(package)
    native_token, descriptor_path, descriptor_hash = _mcu_descriptor_facts(install, request)
    try:
        cubemx_hash = _digest_file(cubemx)
        java_hash = _digest_file(sibling)
    except OSError:
        raise CreationEnvironmentError("CUBEMX_EXECUTION_ENVIRONMENT_INVALID", "CubeMX execution facts cannot be hashed") from None
    return CreationExecutionEnvironment(
        cubemx_executable=cubemx,
        cubemx_version=support.cubemx.version,
        cubemx_sha256=cubemx_hash,
        java_executable=sibling,
        java_sha256=java_hash,
        repository=repository_path,
        package=package,
        package_name=name,
        package_version=version,
        package_sha256=package_hash,
        native_source_token=native_token,
        native_descriptor_path=descriptor_path,
        native_descriptor_sha256=descriptor_hash,
        cubeclt_root=support.cubeclt_root,
        gcc=support.gcc,
        cmake=support.cmake,
        ninja=support.ninja,
    )


# Explicit aliases make the internal seam easy to discover without widening
# the public CLI/MCP request schema.
build_creation_environment = discover_creation_environment
resolve_creation_environment = discover_creation_environment
