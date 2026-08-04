"""Immutable project model with version-dispatched schema loading.

This module is the project-schema/model layer. It owns the frozen public model
types, deterministic schema dispatch for Schema v1 and v2, project-relative
path validation, and the stable manifest error contract shared with the
compatibility view in :mod:`stm32_toolkit.project`.
"""

from __future__ import annotations

import json
import os
import re
import stat
from dataclasses import dataclass
from importlib import resources
from pathlib import Path, PureWindowsPath
from uuid import UUID

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import ValidationError

from stm32_toolkit import __version__
from stm32_toolkit.identity import canonical_project_root

_MANIFEST_NAME = ".stm32-project.json"
_SCHEMA_V1_NAME = "stm32-project-v1.schema.json"
_SCHEMA_V2_NAME = "stm32-project.schema.json"

#: Exact v1 origin to v2 memory.source mapping; anything else maps to manual.
SOURCE_MAPPING = {"keil-migration": "keil", "cubemx": "cubemx"}

#: Windows drive-qualified forms: drive-absolute (``C:\\x``, ``C:/x``) and
#: drive-relative (``D:outside.c``) are never project-relative and are
#: rejected on every host, even where the host-native parser would treat the
#: foreign form as relative.
_WINDOWS_ABSOLUTE_RE = re.compile(r"^[A-Za-z]:")

#: Windows NTFS reparse-point attribute (FILE_ATTRIBUTE_REPARSE_POINT). NTFS
#: junctions and symlinks carry it; Python exposes it as ``st_file_attributes``
#: on Windows. The value is a stable public Windows constant and is spelled
#: here so detection also works on Python 3.10 where ``stat`` does not export
#: the named attribute.
_REPARSE_POINT_ATTRIBUTE = 0x400


class ProjectManifestError(Exception):
    """A deterministic manifest loading failure suitable for protocol responses."""

    def __init__(self, code: str, message: str, details: dict[str, object]) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = dict(details)


@dataclass(frozen=True)
class ProjectInfo:
    name: str
    origin: str


@dataclass(frozen=True)
class TargetSpec:
    device: str
    core: str
    fpu: str | None
    float_abi: str | None
    device_pack: str | None


@dataclass(frozen=True)
class FrameworkSpec:
    type: str
    version: str | None


@dataclass(frozen=True)
class BuildSpec:
    sources: tuple[str, ...]
    include_paths: tuple[str, ...]
    defines: tuple[str, ...]
    compile_options: tuple[str, ...]
    assembly_sources: tuple[str, ...]
    presets: tuple[str, ...]
    elf: str | None


@dataclass(frozen=True)
class MemoryRegion:
    name: str
    origin: int
    length: int
    attributes: str


@dataclass(frozen=True)
class MemorySpec:
    source: str
    regions: tuple[MemoryRegion, ...]


@dataclass(frozen=True)
class DebugSpec:
    backend: str | None
    target: str | None
    svd: str | None


@dataclass(frozen=True)
class GenerationSpec:
    tool: str
    version: str
    cube_mx_ioc: str | None
    managed_manifest: str
    generated_directories: tuple[str, ...]
    user_directories: tuple[str, ...]


@dataclass(frozen=True)
class ProjectModel:
    project_root: Path
    schema_version: int
    logical_project_id: UUID
    project: ProjectInfo
    target: TargetSpec
    framework: FrameworkSpec
    build: BuildSpec
    memory: MemorySpec
    debug: DebugSpec
    generation: GenerationSpec


def load_project_model(project_root: Path) -> ProjectModel:
    """Load a v1 or v2 manifest into a frozen model without writing project state.

    Schema v1 manifests produce a normalized compatibility model; schema v2
    manifests produce the exact model. All project-relative paths are validated
    for canonical-root containment but are never required to exist.
    """
    root = _canonical_root(project_root)
    payload = _load_manifest_json(root / _MANIFEST_NAME)
    version = _model_schema_version(payload)
    _validate_packaged_schema(payload, version)
    return _build_model(root, payload, version)


def _canonical_root(project_root: Path) -> Path:
    try:
        root = canonical_project_root(project_root)
    except OSError as error:
        raise ProjectManifestError(
            "PROJECT_NOT_CONFIGURED",
            "Project root is not available",
            {"path": str(project_root)},
        ) from error
    if not root.is_dir():
        raise ProjectManifestError(
            "PROJECT_NOT_CONFIGURED",
            "Project root is not a directory",
            {"path": str(project_root)},
        )
    return root


def _load_manifest_json(manifest_path: Path) -> object:
    if not manifest_path.is_file():
        raise ProjectManifestError(
            "PROJECT_NOT_CONFIGURED",
            "Project manifest is not configured",
            {"path": _MANIFEST_NAME},
        )
    try:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except UnicodeDecodeError as error:
        raise ProjectManifestError(
            "PROJECT_JSON_INVALID",
            "Project manifest is not valid JSON",
            {"path": "$", "reason": "invalid_utf8"},
        ) from error
    except json.JSONDecodeError as error:
        raise ProjectManifestError(
            "PROJECT_JSON_INVALID",
            "Project manifest is not valid JSON",
            {"path": "$", "line": error.lineno, "column": error.colno},
        ) from error
    except OSError as error:
        raise ProjectManifestError(
            "PROJECT_NOT_CONFIGURED",
            "Project manifest is not available",
            {"path": _MANIFEST_NAME},
        ) from error


def _load_schema(schema_path: Path | None, version: int | None = None) -> object:
    try:
        if schema_path is None:
            schema_name = _SCHEMA_V2_NAME if version == 2 else _SCHEMA_V1_NAME
            schema_text = (
                resources.files("stm32_toolkit")
                .joinpath("schemas", schema_name)
                .read_text(encoding="utf-8")
            )
        else:
            schema_text = schema_path.read_text(encoding="utf-8")
        return json.loads(schema_text)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ProjectManifestError(
            "PROJECT_SCHEMA_INVALID",
            "Project schema is not available",
            {"field": "$schema", "rule": "unavailable"},
        ) from error


_PACKAGED_VALIDATORS: dict[str, Draft202012Validator] = {}


def first_schema_error(payload: object, schema: object) -> tuple[str, str] | None:
    """Return ``(field, rule)`` for the first sorted validation error, if any.

    Used for caller-supplied explicit schemas, which are checked on every
    call because they are not trusted packaged resources.
    """
    try:
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        errors = sorted(validator.iter_errors(payload), key=_validation_sort_key)
    except Exception:
        return ("$schema", "invalidSchema")
    if not errors:
        return None
    error = errors[0]
    return (_validation_field(error), error.validator)


def _packaged_first_schema_error(payload: object, version: int) -> tuple[str, str] | None:
    """First sorted validation error against a cached packaged schema.

    Packaged schemas are static resources, so the recursive metaschema check
    runs once per schema name instead of once per validation call.
    """
    validator = _packaged_validator(version)
    try:
        errors = sorted(validator.iter_errors(payload), key=_validation_sort_key)
    except Exception:
        return ("$schema", "invalidSchema")
    if not errors:
        return None
    error = errors[0]
    return (_validation_field(error), error.validator)


def _packaged_validator(version: int) -> Draft202012Validator:
    schema_name = _SCHEMA_V2_NAME if version == 2 else _SCHEMA_V1_NAME
    validator = _PACKAGED_VALIDATORS.get(schema_name)
    if validator is None:
        schema = _load_schema(None, version)
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        _PACKAGED_VALIDATORS[schema_name] = validator
    return validator


def _validate_schema(payload: object, schema: object, version: int) -> None:
    """Validate against an explicit schema with stable error details."""
    first = first_schema_error(payload, schema)
    if first is None:
        return
    field, rule = first
    raise ProjectManifestError(
        "PROJECT_SCHEMA_INVALID",
        f"Project manifest does not satisfy schema version {version}",
        {"field": field, "rule": rule},
    )


def _validate_packaged_schema(payload: object, version: int) -> None:
    """Validate against the cached packaged schema for the manifest version."""
    first = _packaged_first_schema_error(payload, version)
    if first is None:
        return
    field, rule = first
    raise ProjectManifestError(
        "PROJECT_SCHEMA_INVALID",
        f"Project manifest does not satisfy schema version {version}",
        {"field": field, "rule": rule},
    )


def _model_schema_version(payload: object) -> int:
    payload = _require_manifest_object(payload)
    version = _require_schema_version(payload)
    if version not in (1, 2):
        raise ProjectManifestError(
            "PROJECT_SCHEMA_VERSION_UNSUPPORTED",
            "Project manifest schema version is not supported",
            {"schemaVersion": version, "supported": [1, 2]},
        )
    return int(version)


def _require_manifest_object(payload: object) -> dict:
    if not isinstance(payload, dict):
        raise ProjectManifestError(
            "PROJECT_SCHEMA_INVALID",
            "Project manifest is not an object",
            {"field": "$", "rule": "type"},
        )
    return payload


def _require_schema_version(payload: dict) -> object:
    if "schemaVersion" not in payload:
        raise ProjectManifestError(
            "PROJECT_SCHEMA_INVALID",
            "Project manifest schemaVersion is required",
            {"field": "schemaVersion", "rule": "required"},
        )
    version = payload["schemaVersion"]
    if isinstance(version, bool) or not isinstance(version, int):
        raise ProjectManifestError(
            "PROJECT_SCHEMA_INVALID",
            "Project manifest schemaVersion must be an integer",
            {"field": "schemaVersion", "rule": "type"},
        )
    return version


def validate_model_document(root: Path, payload: dict, version: int) -> None:
    """Post-schema model validations shared by loaders and the upgrade module.

    Checks canonical-root containment of every project-relative path field and
    memory-region name uniqueness. Never dereferences or requires target files.
    """
    cache: dict[Path, os.stat_result | None] = {}
    build = payload["build"]
    _validate_path_field(root, "build.sources", build.get("sources"), cache)
    _validate_path_field(root, "build.includePaths", build.get("includePaths"), cache)
    _validate_path_field(root, "build.assemblySources", build.get("assemblySources"), cache)
    _validate_path_field(root, "build.elf", build.get("elf"), cache)
    debug = payload.get("debug") or {}
    _validate_path_field(root, "debug.svd", debug.get("svd"), cache)
    if version == 2:
        generation = payload["generation"]
        _validate_path_field(
            root, "generation.cubeMxIoc", generation.get("cubeMxIoc"), cache
        )
        _validate_path_field(
            root, "generation.managedManifest", generation.get("managedManifest"), cache
        )
        _validate_path_field(
            root, "generation.generatedDirectories", generation.get("generatedDirectories"), cache
        )
        _validate_path_field(
            root, "generation.userDirectories", generation.get("userDirectories"), cache
        )
        _validate_unique_region_names(payload["memory"]["regions"])


def _validate_path_field(
    root: Path, field_prefix: str, value: object, cache: dict[Path, os.stat_result | None]
) -> None:
    if isinstance(value, str):
        _validate_path_value(root, value, field_prefix, cache)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _validate_path_value(root, item, f"{field_prefix}[{index}]", cache)

def _validate_path_value(
    root: Path, value: object, field: str, cache: dict[Path, os.stat_result | None]
) -> None:
    if not isinstance(value, str):
        return
    if "\x00" in value or _reject_foreign_absolute(value) or _has_traversal(value):
        raise _path_error(field)
    try:
        contained = _contained_in_root(root, value, cache)
    except (OSError, ValueError):
        # A path value that makes host path inspection raise (for example an
        # embedded NUL) is rejected with the same stable structured error.
        raise _path_error(field) from None
    if not contained:
        raise _path_error(field)


def _contained_in_root(
    root: Path, value: str, cache: dict[Path, os.stat_result | None]
) -> bool:
    """Canonical containment with a resolve-free fast path.

    A project-relative value without ``..`` components and without any
    existing link/reparse-point component is lexically inside the canonical
    root and needs no filesystem resolution. Only those cases, plus ``..``
    traversals, pay for a full ``resolve(strict=False)`` walk. Component
    lstat results are cached for the duration of one document validation.
    """
    parts = Path(value).parts
    if ".." in parts or _has_existing_link_component(root, parts, cache):
        return _resolved_within(root, value)
    return True


def _has_existing_link_component(
    root: Path, parts: tuple[str, ...], cache: dict[Path, os.stat_result | None]
) -> bool:
    """True when an existing component is a symlink or Windows reparse point.

    Windows NTFS junctions are directories with the reparse-point attribute
    and are not reported by ``stat.S_ISLNK``, so detection must also inspect
    ``st_file_attributes`` when the host provides it. Any ``..`` traversal or
    existing link component forces a full resolved containment check.
    """
    candidate = root
    for part in parts:
        candidate = candidate / part
        st = cache.get(candidate)
        if st is None:
            try:
                st = os.lstat(candidate)
            except FileNotFoundError:
                # A confirmed missing component cannot be a link; nothing
                # deeper can exist.
                st = None
            except NotADirectoryError:
                # A confirmed non-directory component cannot have children;
                # nothing deeper can exist.
                st = None
            except OSError:
                # PermissionError and every other inspection failure are
                # rejected conservatively by the caller; an uninspectable
                # component is never treated as safe or absent.
                raise
            cache[candidate] = st
        if st is None:
            return False
        if _is_link_or_reparse(st):
            return True
    return False


def _is_link_or_reparse(st: os.stat_result) -> bool:
    """A symlink or a Windows reparse point (for example an NTFS junction)."""
    if stat.S_ISLNK(st.st_mode):
        return True
    return bool(getattr(st, "st_file_attributes", 0) & _REPARSE_POINT_ATTRIBUTE)


def _resolved_within(root: Path, value: str) -> bool:
    try:
        (root / value).resolve(strict=False).relative_to(root)
        return True
    except (OSError, ValueError):
        return False


def _resolve_project_path(
    project_root: Path, value: str, field: str, cache: dict[Path, os.stat_result | None]
) -> Path:
    """Resolve a project-relative manifest path for the compatibility view."""
    if "\x00" in value or _reject_foreign_absolute(value) or _has_traversal(value):
        raise _path_error(field)
    try:
        parts = Path(value).parts
        if _has_traversal(value) or _has_existing_link_component(project_root, parts, cache):
            resolved = (project_root / value).resolve(strict=False)
            resolved.relative_to(project_root)
            return resolved
        return project_root / value
    except (OSError, ValueError) as error:
        raise _path_error(field) from error


def _reject_foreign_absolute(value: str) -> bool:
    """Reject POSIX-rooted, Windows drive, and UNC forms on every host."""
    if value.startswith("/") or value.startswith("\\"):
        return True
    return _WINDOWS_ABSOLUTE_RE.match(value) is not None


def _has_traversal(value: str) -> bool:
    """Detect ``..`` traversal under both ``/`` and ``\\`` conventions.

    On POSIX hosts the native parser treats ``..\\outside.c`` as a single
    component, so the Windows parser is consulted as well; a manifest
    accepted on Linux must not escape after relocation to Windows.
    """
    return ".." in PureWindowsPath(value).parts


def _path_error(field: str) -> ProjectManifestError:
    return ProjectManifestError(
        "PROJECT_SCHEMA_INVALID",
        "Project manifest path is outside the project root",
        {"field": field, "rule": "pathWithinProjectRoot"},
    )


def _validate_unique_region_names(regions: object) -> None:
    if not isinstance(regions, list):
        return
    names = [region.get("name") for region in regions if isinstance(region, dict)]
    if len(names) != len(set(names)):
        raise ProjectManifestError(
            "PROJECT_SCHEMA_INVALID",
            "Project manifest memory region names must be unique",
            {"field": "memory.regions", "rule": "uniqueRegionName"},
        )


def _build_model(root: Path, payload: dict, version: int) -> ProjectModel:
    validate_model_document(root, payload, version)

    project = ProjectInfo(
        name=payload["project"]["name"],
        origin=payload["project"]["origin"],
    )
    target_data = payload["target"]
    target = TargetSpec(
        device=target_data["device"],
        core=target_data["core"],
        fpu=target_data.get("fpu"),
        float_abi=target_data.get("floatAbi"),
        device_pack=target_data.get("devicePack"),
    )
    framework_data = payload["framework"]
    framework = FrameworkSpec(
        type=framework_data["type"],
        version=framework_data.get("version"),
    )
    build_data = payload["build"]
    build = BuildSpec(
        sources=tuple(build_data.get("sources", ())),
        include_paths=tuple(build_data.get("includePaths", ())),
        defines=tuple(build_data.get("defines", ())),
        compile_options=tuple(build_data.get("compileOptions", ())),
        assembly_sources=tuple(build_data.get("assemblySources", ())),
        presets=tuple(build_data.get("presets", ())) if version == 2 else (),
        elf=build_data.get("elf"),
    )
    debug_data = payload.get("debug") or {}
    debug = DebugSpec(
        backend=debug_data.get("backend"),
        target=debug_data.get("target"),
        svd=debug_data.get("svd"),
    )
    if version == 1:
        memory = MemorySpec(
            source=SOURCE_MAPPING.get(project.origin, "manual"),
            regions=(),
        )
        generation = GenerationSpec(
            tool="stm32-toolkit",
            version=__version__,
            cube_mx_ioc=None,
            managed_manifest=".stm32-toolkit/generated-files.json",
            generated_directories=(),
            user_directories=(),
        )
    else:
        memory_data = payload["memory"]
        memory = MemorySpec(
            source=memory_data["source"],
            regions=tuple(
                MemoryRegion(
                    name=region["name"],
                    origin=region["origin"],
                    length=region["length"],
                    attributes=region["attributes"],
                )
                for region in memory_data["regions"]
            ),
        )
        generation_data = payload["generation"]
        generated_by = payload["generatedBy"]
        generation = GenerationSpec(
            tool=generated_by["tool"],
            version=generated_by["version"],
            cube_mx_ioc=generation_data.get("cubeMxIoc"),
            managed_manifest=generation_data["managedManifest"],
            generated_directories=tuple(generation_data.get("generatedDirectories", ())),
            user_directories=tuple(generation_data.get("userDirectories", ())),
        )

    return ProjectModel(
        project_root=root,
        schema_version=version,
        logical_project_id=UUID(payload["logicalProjectId"]),
        project=project,
        target=target,
        framework=framework,
        build=build,
        memory=memory,
        debug=debug,
        generation=generation,
    )


def _validation_sort_key(error: ValidationError) -> tuple[str, str, str]:
    return (_validation_field(error), error.validator, str(error.validator_value))


def _validation_field(error: ValidationError) -> str:
    path = list(error.absolute_path)
    if error.validator == "required":
        required = error.validator_value
        if isinstance(required, list) and isinstance(error.instance, dict):
            missing = next((name for name in required if name not in error.instance), None)
            if isinstance(missing, str):
                path.append(missing)
    elif error.validator == "additionalProperties":
        properties = error.schema.get("properties", {})
        if isinstance(properties, dict) and isinstance(error.instance, dict):
            unexpected = sorted(set(error.instance) - set(properties))
            if unexpected:
                path.append(unexpected[0])
    return _format_field_path(path)


def _format_field_path(path: list[object]) -> str:
    value = ""
    for component in path:
        if isinstance(component, int):
            value += f"[{component}]"
        else:
            value += ("." if value else "") + str(component)
    return value or "$"
