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
_CPU_FLAG_RE = re.compile(r"(?i)(?:^|\s)-mcpu=([A-Za-z0-9_.+-]+)")
_FPU_FLAG_RE = re.compile(r"(?i)(?:^|\s)-mfpu=([A-Za-z0-9_.+-]+)")
_FLOAT_ABI_FLAG_RE = re.compile(r"(?i)(?:^|\s)-mfloat-abi=([A-Za-z0-9_.+-]+)")
_IOC_RE = re.compile(r"(?im)^\s*Mcu\.Name\s*=\s*([^\r\n]+)")
_PKG_RE = re.compile(r"(?im)^\s*ProjectManager\.FirmwarePackage\s*=\s*([^\r\n]+)")
_LANG_RE = re.compile(r"(?im)^\s*ProjectManager\.Language\s*=\s*([^\r\n]+)")
_MEM_RE = re.compile(r"(?im)\b([A-Za-z_][A-Za-z0-9_]*)\s*\(([^)]*)\)\s*:\s*ORIGIN\s*=\s*(0x[0-9A-Fa-f]+|[0-9]+)\s*,\s*LENGTH\s*=\s*([0-9A-Za-z]+)")
_PROJECT_RE = re.compile(r"(?im)^\s*project\s*\(\s*([A-Za-z0-9_.+-]+)")
_ADD_SUBDIRECTORY_RE = re.compile(r"(?im)^\s*add_subdirectory\s*\(\s*([A-Za-z0-9_./+-]+)")
_TOOLCHAIN_RE = re.compile(r'(?im)^\s*set\s*\(\s*CMAKE_TOOLCHAIN_FILE\s+(?:"([^"]+)"|([^\s)]+))')


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


def _set_values(text: str, name: str) -> list[str]:
    match = re.search(rf"(?is)\bset\s*\(\s*{re.escape(name)}\s+([^)]*)\)", text)
    if not match:
        return []
    body = re.sub(r"#[^\n]*", "", match.group(1)).replace("\\\n", " ")
    return [first or second for first, second in re.findall(r'(?:"([^"]+)"|([^\s()]+))', body)]


def _cmake_files(staging_dir: Path, top: str) -> tuple[tuple[Path, str], ...]:
    files: list[tuple[Path, str]] = [(staging_dir, top)]
    pending = [staging_dir / item / "CMakeLists.txt" for item in _ADD_SUBDIRECTORY_RE.findall(top)]
    seen = {staging_dir / "CMakeLists.txt"}
    while pending:
        path = pending.pop(0)
        if path in seen:
            continue
        try:
            relative = path.parent.relative_to(staging_dir)
        except ValueError:
            raise _invalid("native CMake subdirectory is unsafe") from None
        if any(part in {"", ".", ".."} for part in relative.parts):
            raise _invalid("native CMake subdirectory is unsafe")
        text = _read_text(staging_dir, path.relative_to(staging_dir).as_posix())
        assert text is not None
        seen.add(path)
        files.append((path.parent, text))
        pending.extend(path.parent / item / "CMakeLists.txt" for item in _ADD_SUBDIRECTORY_RE.findall(text))
        if len(files) > 32:
            raise _invalid("native CMake graph exceeds its bound")
    return tuple(files)


def _expand_cmake_path(value: str, base: Path, staging_dir: Path) -> str:
    value = value.replace("\\", "/")
    if value.startswith("${CMAKE_SOURCE_DIR}/") or value.startswith("${PROJECT_SOURCE_DIR}/"):
        value = value.split("}/", 1)[1]
        path = staging_dir / value
    elif value.startswith("${CMAKE_CURRENT_LIST_DIR}/"):
        value = value.split("}/", 1)[1]
        path = base / value
    elif value.startswith("${"):
        raise _invalid("native CMake variable is unresolved")
    elif value.startswith("/") or value.startswith("\\") or re.match(r"^[A-Za-z]:", value):
        raise _invalid("native CMake path is unsafe")
    else:
        path = base / value
    try:
        relative = path.resolve(strict=False).relative_to(staging_dir.resolve(strict=True)).as_posix()
    except (OSError, RuntimeError, ValueError):
        raise _invalid("native CMake path escapes staging") from None
    if relative in {"", "."} or any(part in {"", ".", ".."} for part in Path(relative).parts):
        raise _invalid("native CMake path is unsafe")
    if not _SAFE_REL.fullmatch(relative):
        raise _invalid("native CMake path is unsafe")
    return relative


def _declared_paths(cmake_files: tuple[tuple[Path, str], ...], names: tuple[str, ...], staging_dir: Path) -> list[str]:
    values: list[str] = []
    for base, text in cmake_files:
        for name in names:
            values.extend(_set_values(text, name))
    result: list[str] = []
    for value in values:
        if value.upper() in {"PRIVATE", "PUBLIC", "INTERFACE"}:
            continue
        result.append(_expand_cmake_path(value, base, staging_dir))
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
    fpu: str
    float_abi: str
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
            "target": {"device": self.target_device, "core": self.core, "fpu": self.fpu, "floatAbi": self.float_abi},
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
    cmake_files = _cmake_files(staging_dir, cmake)
    if any(re.search(r"(?i)\b(?:add_custom_command|add_custom_target|execute_process|ExternalProject|FetchContent)\b|\bfile\s*\(\s*(?:download|upload)\b|\binclude\s*\(", text) for _, text in cmake_files):
        raise _invalid("native CMake contains an unsafe construct")
    toolchain_files: list[tuple[Path, str]] = []
    for quoted, bare in _TOOLCHAIN_RE.findall(cmake):
        value = quoted or bare
        relative = _expand_cmake_path(value, staging_dir, staging_dir)
        toolchain_path = staging_dir / relative
        toolchain_text = _read_text(staging_dir, relative)
        assert toolchain_text is not None
        toolchain_files.append((toolchain_path.parent, toolchain_text))
    all_cmake = "\n".join(text for _, text in (*cmake_files, *toolchain_files))
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
    core_match = _CPU_FLAG_RE.search(all_cmake) or _CPU_RE.search(all_cmake)
    core = core_match.group(1).lower() if core_match else ""
    if not core.startswith("cortex-"):
        raise _invalid("native CPU identity is invalid")
    fpu_match = _FPU_FLAG_RE.search(all_cmake)
    float_abi_match = _FLOAT_ABI_FLAG_RE.search(all_cmake)
    if fpu_match is None or float_abi_match is None:
        raise _invalid("native CPU floating-point facts are incomplete")
    fpu = fpu_match.group(1).lower()
    float_abi = float_abi_match.group(1).lower()
    source_tokens: list[str] = _declared_paths(cmake_files, ("MX_Application_Src", "STM32_Drivers_Src"), staging_dir)
    for _, text in cmake_files:
        source_tokens.extend(_tokens(text, r"(?:set\s*\(\s*[A-Za-z0-9_]*SOURCES|target_sources\s*\([^)]*)\s+([^)]*)\)"))
    source_paths = tuple(sorted({item for item in source_tokens if item.casefold().endswith((".c", ".cpp"))}))
    assembly = tuple(sorted({item for item in source_tokens if item.casefold().endswith((".s", ".asm", ".spp"))}))
    if not source_paths and not assembly:
        raise _invalid("native source inventory is empty")
    for relative in (*source_paths, *assembly):
        if not _safe_file(staging_dir.joinpath(*relative.split("/"))):
            raise _invalid("native source inventory references a missing file")
    include_tokens = _declared_paths(cmake_files, ("MX_Include_Dirs",), staging_dir)
    for _, text in cmake_files:
        include_tokens.extend(_tokens(text, r"target_include_directories\s*\([^)]*?\s((?:[^()]|\([^)]*\))*)\)"))
    include_paths = tuple(sorted(set(include_tokens)))
    for relative in include_paths:
        if not (staging_dir.joinpath(*relative.split("/"))).is_dir():
            raise _invalid("native include inventory references a missing directory")
    define_tokens: list[str] = []
    for _, text in cmake_files:
        define_tokens.extend(value for value in _set_values(text, "MX_Defines_Syms") if _SAFE_REL.fullmatch(value))
        define_tokens.extend(_tokens(text, r"target_compile_definitions\s*\([^)]*?\s((?:[^()]|\([^)]*\))*)\)"))
    defines = tuple(sorted(set(define_tokens)))
    option_tokens: list[str] = []
    for _, text in cmake_files:
        option_tokens.extend(_tokens(text, r"target_compile_options\s*\([^)]*?\s((?:[^()]|\([^)]*\))*)\)"))
    option_tokens.extend(re.findall(r"(?i)-(?:mcpu|mthumb|mfpu|mfloat-abi)(?:=[A-Za-z0-9_.+-]+)?", all_cmake))
    options = tuple(sorted(set(option_tokens)))
    linker_match = re.search(r'(?im)-T\s*"?(?:\$\{CMAKE_SOURCE_DIR\}/)?([A-Za-z0-9_.+-]+\.ld)', all_cmake)
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
        flags = attrs.lower()
        attributes = "rwx" if "x" in flags and "w" in flags else ("r-x" if "x" in flags else ("rw-" if "w" in flags else "r--"))
        memory.append(
            {
                "name": name,
                "origin": int(origin, 0),
                "length": _length(length),
                "attributes": attributes,
            }
        )
    if not memory:
        raise _invalid("native linker memory regions are missing")
    project_match = _PROJECT_RE.search(cmake)
    if project_match is None:
        raise _invalid("native project name is missing")
    project_name = project_match.group(1)
    logical = uuid5(NAMESPACE_URL, f"stm32-toolkit/project/{plan_id}")
    return NativeProjectModel(
        project_root=staging_dir,
        logical_project_id=logical,
        project_name=project_name,
        target_device=device,
        core=core,
        fpu=fpu,
        float_abi=float_abi,
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
