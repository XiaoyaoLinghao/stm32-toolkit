"""Bounded parsing of the two verified STM32CubeMX 6.18 CMake dialects."""

from __future__ import annotations

import json
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid5

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
_SAFE_TOKEN = re.compile(r"^[A-Za-z0-9_+@=.-]+$")
_IOC_RE = re.compile(r"(?im)^\s*Mcu\.Name\s*=\s*([^\r\n]+)")
_PKG_RE = re.compile(r"(?im)^\s*ProjectManager\.FirmwarePackage\s*=\s*([^\r\n]+)")
_LANG_RE = re.compile(r"(?im)^\s*ProjectManager\.Language\s*=\s*([^\r\n]+)")
_MEM_RE = re.compile(
    r"(?im)\b([A-Za-z_][A-Za-z0-9_]*)\s*\(([^)]*)\)\s*:\s*ORIGIN\s*=\s*(0x[0-9A-Fa-f]+|[0-9]+)\s*,\s*LENGTH\s*=\s*([0-9A-Za-z]+)"
)
_SET_RE = re.compile(r"(?im)^\s*set\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\b([^)]*)\)")
_PROJECT_BINDING_RE = re.compile(r"(?im)^\s*set\s*\(\s*CMAKE_PROJECT_NAME\s+([A-Za-z][A-Za-z0-9_.-]*)\s*\)\s*$")
_PROJECT_REF_RE = re.compile(r"(?im)^\s*project\s*\(\s*\$\{CMAKE_PROJECT_NAME\}\s*\)\s*$")
_ADD_SUBDIRECTORY_RE = re.compile(r"(?im)^\s*add_subdirectory\s*\(\s*([^)]*?)\s*\)\s*$")
_INCLUDE_RE = re.compile(r"(?im)^\s*include\s*\(\s*([^)]*?)\s*\)\s*$")
_UNSAFE_CMAKE_RE = re.compile(
    r"(?i)\b(?:add_custom_command|add_custom_target|execute_process|ExternalProject|FetchContent)\b|"
    r"\bfile\s*\(\s*(?:download|upload)\b"
)
_DEBUG_DEFINE = "$<$<CONFIG:Debug>:DEBUG>"


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


def _read_text(
    root: Path,
    relative: str,
    *,
    required: bool = True,
    inventory: tuple[tuple[str, int, str], ...] | None = None,
) -> str | None:
    if inventory is not None and relative not in {item[0] for item in inventory}:
        if required:
            raise _invalid("required native file is unavailable")
        return None
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


def _set_body(text: str, name: str) -> str:
    matches = []
    for match in _SET_RE.finditer(text):
        variable = match.group(1)
        if variable.casefold() == name.casefold():
            matches.append(match.group(2))
    if len(matches) != 1:
        raise _invalid(f"native CMake fact {name} is missing or ambiguous")
    return matches[0]


def _values(body: str) -> list[str]:
    body = re.sub(r"#[^\n]*", "", body).replace("\\\n", " ").strip()
    values: list[str] = []
    for quoted, bare in re.findall(r'"([^"]*)"|([^\s()]+)', body):
        value = quoted or bare
        if value:
            values.append(value.replace("\\", "/"))
    return values


def _scalar_set(text: str, name: str) -> str:
    values = _values(_set_body(text, name))
    if len(values) != 1 or not values[0]:
        raise _invalid(f"native CMake fact {name} is missing or ambiguous")
    return values[0]


def _resolve_path(value: str, declared_dir: Path, staging_dir: Path) -> str:
    if not isinstance(value, str) or not value or any(ord(char) < 32 for char in value):
        raise _invalid("native CMake path is unsafe")
    normalized = value.replace("\\", "/")
    if normalized.startswith("${sourceDir}/"):
        path = staging_dir / normalized[len("${sourceDir}/") :]
    elif normalized.startswith("${CMAKE_SOURCE_DIR}/"):
        path = staging_dir / normalized[len("${CMAKE_SOURCE_DIR}/") :]
    elif normalized.startswith("${CMAKE_CURRENT_SOURCE_DIR}/"):
        path = declared_dir / normalized[len("${CMAKE_CURRENT_SOURCE_DIR}/") :]
    elif normalized.startswith("${CMAKE_CURRENT_LIST_DIR}/"):
        path = declared_dir / normalized[len("${CMAKE_CURRENT_LIST_DIR}/") :]
    elif normalized.startswith("${"):
        raise _invalid("native CMake variable is unresolved")
    elif normalized.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", normalized):
        raise _invalid("native CMake path is unsafe")
    else:
        path = declared_dir / normalized
    try:
        relative = path.resolve(strict=False).relative_to(staging_dir.resolve(strict=True)).as_posix()
    except (OSError, RuntimeError, ValueError):
        raise _invalid("native CMake path escapes staging") from None
    if relative in {"", "."} or not _SAFE_REL.fullmatch(relative) or any(part in {"", ".", ".."} for part in Path(relative).parts):
        raise _invalid("native CMake path is unsafe")
    return relative


def _path_list(text: str, name: str, declared_dir: Path, staging_dir: Path) -> list[str]:
    return [_resolve_path(value, declared_dir, staging_dir) for value in _values(_set_body(text, name))]


def _define_list(text: str, name: str) -> tuple[list[str], list[str]]:
    values = _values(_set_body(text, name))
    common: list[str] = []
    configuration: list[str] = []
    for value in values:
        if value == _DEBUG_DEFINE:
            configuration.append(value)
        elif _SAFE_TOKEN.fullmatch(value):
            common.append(value)
        else:
            raise _invalid("native CMake define is unsafe")
    return common, configuration


def _package_fact(value: str, fallback_version: str) -> tuple[str | None, str | None]:
    """Canonicalize CubeMX package family/version across IOC and directory spellings."""
    normalized = value.strip().replace("_", " ")
    match = re.fullmatch(r"(?i)STM32Cube\s+FW\s*([A-Z0-9]+)(?:\s+V?([0-9][A-Za-z0-9_.-]*))?", normalized)
    if match is None:
        return None, None
    version = match.group(2) or fallback_version.strip().lstrip("Vv")
    if not version:
        return match.group(1).casefold(), None
    return match.group(1).casefold(), version.casefold()


def _project_name(cmake: str) -> str:
    bindings = _PROJECT_BINDING_RE.findall(cmake)
    projects = _PROJECT_REF_RE.findall(cmake)
    all_projects = re.findall(r"(?im)^\s*project\s*\(", cmake)
    if len(bindings) != 1 or len(projects) != 1 or len(all_projects) != 1:
        raise _invalid("native project name binding is missing or ambiguous")
    return bindings[0]


def _parse_target_flags(flags: str) -> tuple[str, str, str, tuple[str, ...]]:
    if any(char in flags for char in ('"', "'", "${")):
        raise _invalid("native CPU flags are not literal")
    cpu = re.findall(r"(?i)(?:^|\s)-mcpu=([A-Za-z0-9_.+-]+)(?=\s|$)", flags)
    fpu = re.findall(r"(?i)(?:^|\s)-mfpu=([A-Za-z0-9_.+-]+)(?=\s|$)", flags)
    abi = re.findall(r"(?i)(?:^|\s)-mfloat-abi=([A-Za-z0-9_.+-]+)(?=\s|$)", flags)
    if len(cpu) != 1 or len(fpu) != 1 or len(abi) != 1 or not cpu[0].lower().startswith("cortex-"):
        raise _invalid("native CPU floating-point facts are incomplete")
    options = tuple(sorted(set(re.findall(r"(?i)-(?:mcpu|mthumb|mfpu|mfloat-abi)(?:=[A-Za-z0-9_.+-]+)?", flags))))
    return cpu[0].lower(), fpu[0].lower(), abi[0].lower(), options


def _linker_from_flags(text: str) -> str:
    matches = re.findall(
        r'(?i)-T\s*\\?["\']?(?:\$\{CMAKE_SOURCE_DIR\}/)?([A-Za-z0-9_.+-]+\.ld)',
        text,
    )
    if len(matches) != 1:
        raise _invalid("native linker script reference is missing or ambiguous")
    return matches[0]


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


def _check_unsafe(text: str) -> None:
    if _UNSAFE_CMAKE_RE.search(text):
        raise _invalid("native CMake contains an unsafe construct")


def _global_toolchain(staging_dir: Path, inventory: tuple[tuple[str, int, str], ...]) -> tuple[str, str]:
    preset_text = _read_text(staging_dir, "CMakePresets.json", inventory=inventory)
    assert preset_text is not None
    try:
        payload = json.loads(preset_text)
    except (TypeError, ValueError, UnicodeError):
        raise _invalid("native CMake presets are invalid") from None
    if not isinstance(payload, dict) or payload.get("version") != 3 or not isinstance(payload.get("configurePresets"), list):
        raise _invalid("native CMake presets are invalid")
    defaults = [item for item in payload["configurePresets"] if isinstance(item, dict) and item.get("name") == "default"]
    if len(defaults) != 1 or not isinstance(defaults[0].get("toolchainFile"), str):
        raise _invalid("native CMake default toolchain is missing or ambiguous")
    toolchain_value = defaults[0]["toolchainFile"]
    if not toolchain_value.startswith("${sourceDir}/"):
        raise _invalid("native CMake toolchain path is not source-rooted")
    toolchain_relative = _resolve_path(toolchain_value, staging_dir, staging_dir)
    toolchain = _read_text(staging_dir, toolchain_relative, inventory=inventory)
    assert toolchain is not None
    _check_unsafe(toolchain)
    return _scalar_set(toolchain, "TARGET_FLAGS"), toolchain


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
    configuration_defines: tuple[str, ...] = ()

    def to_manifest(self) -> dict[str, object]:
        elf_name = re.sub(r"[^A-Za-z0-9_.-]", "_", self.project_name).strip(".") or "firmware"
        return {
            "schemaVersion": 3,
            "logicalProjectId": str(self.logical_project_id),
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
                "nativeLinkerScript": self.linker_script,
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
    cmake = _read_text(staging_dir, "CMakeLists.txt", inventory=files)
    assert cmake is not None
    project_name = _project_name(cmake)
    add_matches = _ADD_SUBDIRECTORY_RE.findall(cmake)
    include_matches = _INCLUDE_RE.findall(cmake)
    exact_global = [value.replace("\\", "/") for value in add_matches if value.replace("\\", "/") == "cmake/stm32cubemx"]
    exact_context = [value.strip() for value in include_matches if value.strip() == '"mx-generated.cmake"']
    if add_matches and include_matches:
        raise _invalid("native CMake mixes CubeMX dialects")
    if add_matches:
        if len(add_matches) != 1 or len(exact_global) != 1:
            raise _invalid("native global CubeMX subdirectory is missing or unsafe")
        dialect = "global"
    elif include_matches:
        if len(include_matches) != 1 or len(exact_context) != 1:
            raise _invalid("native context CubeMX include is missing or unsafe")
        dialect = "context"
    else:
        raise _invalid("native CubeMX CMake dialect is missing")
    _check_unsafe(cmake)

    if dialect == "global":
        flags, toolchain = _global_toolchain(staging_dir, files)
        core, fpu, float_abi, compile_options = _parse_target_flags(flags)
        linker = _linker_from_flags(toolchain)
        generated_root = staging_dir / "cmake" / "stm32cubemx"
        generated_text = _read_text(staging_dir, "cmake/stm32cubemx/CMakeLists.txt", inventory=files)
        assert generated_text is not None
        generated_base = generated_root
    else:
        flags = _scalar_set(cmake, "STM32_MCU_FLAGS")
        core, fpu, float_abi, compile_options = _parse_target_flags(flags)
        linker = _scalar_set(cmake, "STM32_LINKER_SCRIPT")
        generated_root = staging_dir
        generated_text = _read_text(staging_dir, "mx-generated.cmake", inventory=files)
        assert generated_text is not None
        generated_base = staging_dir
        _check_unsafe(generated_text)
    del generated_root
    linker = _resolve_path(linker, staging_dir, staging_dir)
    linker_rows = [row for row in files if row[0] == linker]
    if len(linker_rows) != 1:
        raise _invalid("native linker script is not present exactly once in the native inventory")

    source_values = _path_list(generated_text, "MX_Application_Src", generated_base, staging_dir)
    source_values.extend(_path_list(generated_text, "STM32_Drivers_Src", generated_base, staging_dir))
    include_values = _path_list(generated_text, "MX_Include_Dirs", generated_base, staging_dir)
    define_values, configuration_defines = _define_list(generated_text, "MX_Defines_Syms")
    source_paths = tuple(sorted({item for item in source_values if item.casefold().endswith((".c", ".cpp"))}))
    assembly = tuple(sorted({item for item in source_values if item.casefold().endswith((".s", ".asm", ".spp"))}))
    if not source_paths and not assembly:
        raise _invalid("native source inventory is empty")
    for relative in (*source_paths, *assembly):
        if not _safe_file(staging_dir.joinpath(*relative.split("/"))):
            raise _invalid("native source inventory references a missing file")
    include_paths = tuple(sorted(set(include_values)))
    for relative in include_paths:
        if not staging_dir.joinpath(*relative.split("/")).is_dir():
            raise _invalid("native include inventory references a missing directory")

    linker_text = _read_text(staging_dir, linker, inventory=files)
    assert linker_text is not None
    memory: list[dict[str, object]] = []
    for name, attrs, origin, length in _MEM_RE.findall(linker_text):
        flags_text = attrs.lower()
        attributes = "rwx" if "x" in flags_text and "w" in flags_text else ("r-x" if "x" in flags_text else ("rw-" if "w" in flags_text else "r--"))
        memory.append({"name": name, "origin": int(origin, 0), "length": _length(length), "attributes": attributes})
    if not memory:
        raise _invalid("native linker memory regions are missing")

    ioc_candidates = [name for name, _, _ in files if name.casefold().endswith(".ioc")]
    if len(ioc_candidates) > 1:
        raise _invalid("native IOC inventory is ambiguous")
    ioc_path = ioc_candidates[0] if ioc_candidates else None
    if request.source.kind == "ioc" and ioc_path is None:
        raise _invalid("native IOC source is missing")
    ioc = _read_text(staging_dir, ioc_path, required=False, inventory=files) if ioc_path else None
    native_device = _IOC_RE.search(ioc or "")
    device = native_device.group(1).strip() if native_device else request.source.value
    if not device or not re.fullmatch(r"STM32[A-Za-z0-9]+", device, re.IGNORECASE):
        raise _invalid("native MCU identity is missing")
    if request.source.kind == "mcu" and device.upper() != request.source.value.upper():
        raise _invalid("native MCU identity disagrees with the request")
    package = _PKG_RE.search(ioc or "")
    if package is None:
        raise _invalid("native IOC package fact is missing")
    actual_family, actual_version = _package_fact(package.group(1).strip(), "")
    expected_family, expected_version = _package_fact(
        str(getattr(environment, "package_name", "")),
        str(getattr(environment, "package_version", "")),
    )
    if actual_family is None or expected_family is None or actual_family != expected_family:
        raise _invalid("native IOC package disagrees with the environment")
    if actual_version is not None and actual_version != expected_version:
        raise _invalid("native IOC package disagrees with the environment")
    native_language_match = _LANG_RE.search(ioc or "")
    native_language = native_language_match.group(1).strip().casefold() if native_language_match else "c"
    if request.language == "cpp" and native_language not in {"c++", "cpp"}:
        raise _invalid("native language does not satisfy the C++ request")
    if request.framework == "ll" and not re.search(r"(?im)\bLL_[A-Za-z0-9_]+", ioc or ""):
        raise _invalid("native IOC does not explicitly select LL")
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
        defines=tuple(sorted(set(define_values))),
        compile_options=compile_options,
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
        configuration_defines=tuple(configuration_defines),
    )


def write_native_project_manifests(staging_dir: Path, model: NativeProjectModel) -> Path:
    """Write the schema-3 project and literal CubeMX ownership manifests."""
    try:
        manifest_path = staging_dir / ".stm32-project.json"
        manifest_path.write_bytes(json.dumps(model.to_manifest(), indent=2, ensure_ascii=False).encode("utf-8") + b"\n")
        ownership = {
            "schemaVersion": 1,
            "tool": "stm32-toolkit",
            "generator": {"tool": "stm32-cubemx", "version": model.cubemx_version, "executableSha256": model.cubemx_sha256},
            "source": {"packageName": model.package_name, "packageVersion": model.package_version, "packageSha256": model.package_sha256},
            "planId": model.plan_id,
            "actionDigest": model.action_digest,
            "executionEnvironmentDigest": model.environment_digest,
            "files": [
                {"path": path, "size": size, "sha256": digest}
                for path, size, digest in model.files
                if not path.startswith(".stm32-toolkit/") and path != ".stm32-project.json"
            ],
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
