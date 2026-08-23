"""Bounded declarative parsing of CubeMX native CMake output."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID, NAMESPACE_URL, uuid5

from stm32_toolkit import __version__
from stm32_toolkit.creation_environment import CreationExecutionEnvironment
from stm32_toolkit.generation.creation import CreationRequest
from stm32_toolkit.generation.managed_files import canonical_json_bytes, sha256_hex

_REPARSE = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
_MAX_FILES = 200_000
_MAX_TOTAL_BYTES = 256 * 1024 * 1024
_MAX_FILE_BYTES = 32 * 1024 * 1024
_MAX_PATH_DEPTH = 32
_MAX_RELATIVE_BYTES = 4096
_SAFE_REL = re.compile(r"^[A-Za-z0-9_./+@=-]+$")
_CPU_RE = re.compile(r"(?im)^\s*(?:set\s*\(\s*CMAKE_SYSTEM_PROCESSOR\s+|CMAKE_SYSTEM_PROCESSOR\s*=\s*)([A-Za-z0-9_.+-]+)", re.MULTILINE)
_IOC_RE = re.compile(r"(?im)^\s*Mcu\.Name\s*=\s*([^\r\n]+)")
_PKG_RE = re.compile(r"(?im)^\s*ProjectManager\.FirmwarePackage\s*=\s*([^\r\n]+)")
_LANG_RE = re.compile(r"(?im)^\s*ProjectManager\.Language\s*=\s*([^\r\n]+)")
_MEM_RE = re.compile(r"(?im)\b([A-Za-z_][A-Za-z0-9_]*)\s*\(([^)]*)\)\s*:\s*ORIGIN\s*=\s*(0x[0-9A-Fa-f]+|[0-9]+)\s*,\s*LENGTH\s*=\s*([0-9A-Za-z]+)")
_PROJECT_RE = re.compile(r"(?im)^\s*project\s*\(\s*([A-Za-z0-9_.+-]+)")


class CubeMXNativeProjectError(ValueError):
    """A closed native-output validation/parsing failure."""

    def __init__(self, code: str, message: str, details: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = dict(details or {})


def _invalid(message: str, **details: object) -> CubeMXNativeProjectError:
    return CubeMXNativeProjectError("CUBEMX_NATIVE_OUTPUT_INVALID", message, details)


def _safe_file(path: Path) -> bool:
    try:
        info = os.lstat(path)
        return stat.S_ISREG(info.st_mode) and not path.is_symlink() and not bool(getattr(info, "st_file_attributes", 0) & _REPARSE)
    except OSError:
        return False


def _safe_inventory(root: Path) -> tuple[tuple[str, int, str], ...]:
    try:
        if not root.is_dir() or root.is_symlink():
            raise _invalid("native staging is not a directory")
        rows: list[tuple[str, int, str]] = []
        total = 0
        for path in sorted(root.rglob("*"), key=lambda item: item.as_posix().casefold()):
            relative = path.relative_to(root).as_posix()
            if len(relative.encode("utf-8")) > _MAX_RELATIVE_BYTES or len(Path(relative).parts) > _MAX_PATH_DEPTH:
                raise _invalid("native path exceeds its bound")
            info = os.lstat(path)
            if stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & _REPARSE):
                raise _invalid("native output contains a redirect")
            if stat.S_ISDIR(info.st_mode):
                continue
            if not stat.S_ISREG(info.st_mode):
                raise _invalid("native output contains a special file")
            if info.st_size > _MAX_FILE_BYTES:
                raise _invalid("native file exceeds its bound")
            total += info.st_size
            if total > _MAX_TOTAL_BYTES:
                raise _invalid("native output exceeds its aggregate bound")
            rows.append((relative, info.st_size, sha256_hex(path.read_bytes())))
            if len(rows) > _MAX_FILES:
                raise _invalid("native output contains too many files")
        return tuple(rows)
    except CubeMXNativeProjectError:
        raise
    except (OSError, UnicodeError):
        raise _invalid("native output cannot be inspected") from None


def _read_text(root: Path, relative: str, *, required: bool = True) -> str | None:
    path = root.joinpath(*relative.split("/"))
    if not _safe_file(path):
        if required:
            raise _invalid("required native file is unavailable")
        return None
    try:
        data = path.read_bytes()
        if len(data) > _MAX_FILE_BYTES:
            raise _invalid("native metadata file exceeds its bound")
        return data.decode("utf-8")
    except CubeMXNativeProjectError:
        raise
    except (OSError, UnicodeDecodeError):
        raise _invalid("native metadata is not valid UTF-8") from None


def _tokens(text: str, pattern: str) -> list[str]:
    result: list[str] = []
    for match in re.finditer(pattern, text, flags=re.IGNORECASE | re.DOTALL):
        body = match.group(1)
        body = re.sub(r"#[^\n]*", "", body)
        for token in re.findall(r"(?:\"([^\"]+)\"|([^\s()]+))", body):
            value = token[0] or token[1]
            if value.upper() in {"PRIVATE", "PUBLIC", "INTERFACE", "APP_SOURCES", "SOURCES"}:
                continue
            if value.startswith("${") or value.startswith("-") and not value.startswith("-m"):
                continue
            if value.startswith("/") or value.startswith("\\") or ".." in Path(value).parts or ":" in value:
                raise _invalid("native CMake path is unsafe")
            if not _SAFE_REL.fullmatch(value):
                raise _invalid("native CMake token is unsafe")
            result.append(value.replace("\\", "/"))
    return result


def _length(value: str) -> int:
    match = re.fullmatch(r"(?i)(0x[0-9a-f]+|[0-9]+)([km]?)", value)
    if not match:
        raise _invalid("linker memory length is invalid")
    amount = int(match.group(1), 0)
    suffix = match.group(2).lower()
    if suffix == "k":
        amount *= 1024
    elif suffix == "m":
        amount *= 1024 * 1024
    return amount


@dataclass(frozen=True, slots=True)
class NativeProjectModel:
    project_root: Path
    logical_project_id: UUID
    project_name: str
    target_device: str
    core: str
    framework: str
    language: str
    sources: tuple[str, ...]
    assembly_sources: tuple[str, ...]
    include_paths: tuple[str, ...]
    defines: tuple[str, ...]
    compile_options: tuple[str, ...]
    linker_script: str
    memory_regions: tuple[dict[str, object], ...]
    ioc_path: str | None
    plan_id: str
    action_digest: str
    environment_digest: str
    cubemx_version: str
    cubemx_sha256: str
    package_name: str
    package_version: str
    package_sha256: str
    files: tuple[tuple[str, int, str], ...]

    def to_manifest(self) -> dict[str, object]:
        elf_name = re.sub(r"[^A-Za-z0-9_.-]", "_", self.project_name).strip(".") or "firmware"
        return {
            "schemaVersion": 3,
            "logicalProjectId": str(self.logical_project_id),
            # `.stm32-project.json` remains the Toolkit schema-3 model.  The
            # CubeMX source/tool binding is recorded separately in the
            # ownership manifest; configure/build require this generatedBy
            # identity to remain the Toolkit version.
            "generatedBy": {"tool": "stm32-toolkit", "version": __version__},
            "project": {"name": self.project_name, "origin": "cubemx"},
            "target": {"device": self.target_device, "core": self.core},
            "framework": {"type": self.framework, "version": None},
            "build": {
                "sources": list(self.sources),
                "includePaths": list(self.include_paths),
                "defines": list(self.defines),
                "compileOptions": list(self.compile_options),
                "assemblySources": list(self.assembly_sources),
                "presets": ["arm-debug", "arm-release"],
                "elf": f"build/arm-debug/{elf_name}.elf",
            },
            "memory": {"source": "cubemx", "regions": list(self.memory_regions)},
            "debug": {},
            "generation": {
                "cubeMxIoc": self.ioc_path,
                "managedManifest": ".stm32-toolkit/generated-files.json",
                "generatedDirectories": ["Core", "Drivers"],
                "userDirectories": ["App", "Tests"],
            },
        }


def parse_native_project(
    staging_dir: Path,
    *,
    request: CreationRequest,
    plan_id: str,
    action_digest: str,
    environment: CreationExecutionEnvironment | object,
) -> NativeProjectModel:
    if not isinstance(staging_dir, Path) or not staging_dir.is_dir():
        raise _invalid("native staging is unavailable")
    if not isinstance(request, CreationRequest) or not re.fullmatch(r"[0-9a-f]{64}", plan_id) or not re.fullmatch(r"[0-9a-f]{64}", action_digest):
        raise _invalid("native binding is invalid")
    files = _safe_inventory(staging_dir)
    cmake = _read_text(staging_dir, "CMakeLists.txt")
    assert cmake is not None
    if re.search(r"(?i)\b(?:add_custom_command|add_custom_target|execute_process|ExternalProject|FetchContent)\b|\bfile\s*\(\s*(?:download|upload)\b|\binclude\s*\(", cmake):
        raise _invalid("native CMake contains an unsafe construct")
    ioc_candidates = [name for name, _, _ in files if name.casefold().endswith(".ioc")]
    if len(ioc_candidates) > 1:
        raise _invalid("native IOC inventory is ambiguous")
    ioc_path = ioc_candidates[0] if ioc_candidates else None
    if request.source.kind == "ioc" and ioc_path is None:
        raise _invalid("native IOC source is missing")
    ioc = _read_text(staging_dir, ioc_path, required=False) if ioc_path else None
    native_device = _IOC_RE.search(ioc or "")
    device = (native_device.group(1).strip() if native_device else (request.source.value if request.source.kind == "mcu" else ""))
    if not device or not re.fullmatch(r"STM32[A-Za-z0-9]+", device, re.IGNORECASE):
        raise _invalid("native MCU identity is missing")
    if request.source.kind == "mcu" and device.upper() != request.source.value.upper():
        raise _invalid("native MCU identity disagrees with the request")
    package = _PKG_RE.search(ioc or "")
    expected_package = str(getattr(environment, "package_name", ""))
    if package and expected_package and package.group(1).strip().casefold() not in expected_package.casefold():
        raise _invalid("native IOC package disagrees with the environment")
    native_language = (_LANG_RE.search(ioc or "").group(1).strip().casefold() if _LANG_RE.search(ioc or "") else "c")
    if request.language == "cpp" and native_language not in {"c++", "cpp"}:
        raise _invalid("native language does not satisfy the C++ request")
    if request.framework == "ll" and not re.search(r"(?im)\bLL_[A-Za-z0-9_]+", ioc or ""):
        raise _invalid("native IOC does not explicitly select LL")
    core_match = _CPU_RE.search(cmake)
    core = core_match.group(1).lower() if core_match else "cortex-m4"
    if not core.startswith("cortex-"):
        raise _invalid("native CPU identity is invalid")
    source_tokens = _tokens(cmake, r"(?:set\s*\(\s*[A-Za-z0-9_]*SOURCES|target_sources\s*\([^)]*)\s+([^)]*)\)")
    if not source_tokens:
        source_tokens = [name for name, _, _ in files if name.casefold().endswith((".c", ".cpp"))]
    source_paths = tuple(sorted({item for item in source_tokens if item.casefold().endswith((".c", ".cpp"))}))
    assembly = tuple(sorted({item for item in source_tokens if item.casefold().endswith((".s", ".asm", ".spp"))}))
    if not source_paths and not assembly:
        raise _invalid("native source inventory is empty")
    for relative in (*source_paths, *assembly):
        if not _safe_file(staging_dir.joinpath(*relative.split("/"))):
            raise _invalid("native source inventory references a missing file")
    include_paths = tuple(sorted(set(_tokens(cmake, r"target_include_directories\s*\([^)]*?\s((?:[^()]|\([^)]*\))*)\)"))))
    for relative in include_paths:
        if not (staging_dir.joinpath(*relative.split("/"))).is_dir():
            raise _invalid("native include inventory references a missing directory")
    defines = tuple(sorted(set(_tokens(cmake, r"target_compile_definitions\s*\([^)]*?\s((?:[^()]|\([^)]*\))*)\)"))))
    options = tuple(sorted(set(_tokens(cmake, r"target_compile_options\s*\([^)]*?\s((?:[^()]|\([^)]*\))*)\)"))))
    linker_match = re.search(r"(?im)(?:LINKER_SCRIPT|CMAKE_EXE_LINKER_FLAGS[^\n]*-T)\s*(?:=\s*)?(?:\$\{CMAKE_SOURCE_DIR\}/)?([A-Za-z0-9_.+-]+\.ld)", cmake)
    if linker_match:
        linker = linker_match.group(1)
    else:
        candidates = [name for name, _, _ in files if name.casefold().endswith(".ld")]
        if len(candidates) != 1:
            raise _invalid("native linker script is missing or ambiguous")
        linker = candidates[0]
    linker_text = _read_text(staging_dir, linker)
    assert linker_text is not None
    memory: list[dict[str, object]] = []
    for name, attrs, origin, length in _MEM_RE.findall(linker_text):
        memory.append({"name": name, "origin": int(origin, 0), "length": _length(length), "attributes": "r-x" if "x" in attrs.lower() else "rw-"})
    if not memory:
        raise _invalid("native linker memory regions are missing")
    project_match = _PROJECT_RE.search(cmake)
    project_name = project_match.group(1) if project_match else staging_dir.name
    logical = uuid5(NAMESPACE_URL, f"stm32-toolkit/project/{plan_id}")
    return NativeProjectModel(
        project_root=staging_dir,
        logical_project_id=logical,
        project_name=project_name,
        target_device=device,
        core=core,
        framework=request.framework,
        language=request.language,
        sources=source_paths,
        assembly_sources=assembly,
        include_paths=include_paths,
        defines=defines,
        compile_options=options,
        linker_script=linker,
        memory_regions=tuple(memory),
        ioc_path=ioc_path,
        plan_id=plan_id,
        action_digest=action_digest,
        environment_digest=str(getattr(environment, "digest", "")),
        cubemx_version=str(getattr(environment, "cubemx_version", "")),
        cubemx_sha256=str(getattr(environment, "cubemx_sha256", "")),
        package_name=str(getattr(environment, "package_name", "")),
        package_version=str(getattr(environment, "package_version", "")),
        package_sha256=str(getattr(environment, "package_sha256", "")),
        files=files,
    )


def write_native_project_manifests(staging_dir: Path, model: NativeProjectModel) -> Path:
    """Write schema-3 project and literal CubeMX ownership manifests."""
    try:
        manifest_path = staging_dir / ".stm32-project.json"
        manifest_path.write_bytes(json.dumps(model.to_manifest(), indent=2, ensure_ascii=False).encode("utf-8") + b"\n")
        ownership = {
            "schemaVersion": 1,
            "tool": "stm32-toolkit",
            "generator": {"tool": "stm32-cubemx", "version": model.cubemx_version, "executableSha256": model.cubemx_sha256},
            "source": {
                "packageName": model.package_name,
                "packageVersion": model.package_version,
                "packageSha256": model.package_sha256,
            },
            "planId": model.plan_id,
            "actionDigest": model.action_digest,
            "executionEnvironmentDigest": model.environment_digest,
            "files": [{"path": path, "size": size, "sha256": digest} for path, size, digest in model.files if not path.startswith(".stm32-toolkit/") and path != ".stm32-project.json"],
        }
        ownership_path = staging_dir / ".stm32-toolkit" / "cubemx-ownership.json"
        ownership_path.parent.mkdir(parents=True, exist_ok=True)
        ownership_path.write_bytes(json.dumps(ownership, indent=2, ensure_ascii=False).encode("utf-8") + b"\n")
        return ownership_path
    except OSError:
        raise CubeMXNativeProjectError("CUBEMX_NATIVE_OUTPUT_INVALID", "native project manifests cannot be written") from None


validate_native_project = parse_native_project
build_native_project_model = parse_native_project


__all__ = ["CubeMXNativeProjectError", "NativeProjectModel", "parse_native_project", "validate_native_project", "write_native_project_manifests"]
