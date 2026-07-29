from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import ValidationError

from stm32_toolkit.identity import canonical_project_root


_MANIFEST_NAME = ".stm32-project.json"
_SCHEMA_NAME = "stm32-project.schema.json"


class ProjectManifestError(Exception):
    """A deterministic manifest loading failure suitable for protocol responses."""

    def __init__(self, code: str, message: str, details: dict[str, object]) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = dict(details)


@dataclass(frozen=True)
class ProjectManifest:
    project_root: Path
    logical_project_id: UUID
    target_device: str
    framework_type: str
    source_paths: tuple[Path, ...]
    elf_path: Path | None

    @classmethod
    def load(
        cls,
        project_root: Path,
        schema_path: Path | None = None,
    ) -> "ProjectManifest":
        root = _canonical_root(project_root)
        payload = _load_manifest_json(root / _MANIFEST_NAME)
        schema = _load_schema(schema_path)
        _validate_schema(payload, schema)

        build = payload["build"]
        sources = tuple(
            _resolve_project_path(root, path, f"build.sources[{index}]")
            for index, path in enumerate(build["sources"])
        )
        elf_value = build.get("elf")
        elf_path = (
            _resolve_project_path(root, elf_value, "build.elf")
            if elf_value is not None
            else None
        )

        return cls(
            project_root=root,
            logical_project_id=UUID(payload["logicalProjectId"]),
            target_device=payload["target"]["device"],
            framework_type=payload["framework"]["type"],
            source_paths=sources,
            elf_path=elf_path,
        )


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


def _load_schema(schema_path: Path | None) -> object:
    path = schema_path if schema_path is not None else _default_schema_path()
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ProjectManifestError(
            "PROJECT_SCHEMA_INVALID",
            "Project schema is not available",
            {"field": "$schema", "rule": "unavailable"},
        ) from error


def _default_schema_path() -> Path:
    package_path = Path(__file__).resolve()
    for ancestor in package_path.parents:
        candidate = ancestor / "schemas" / _SCHEMA_NAME
        if candidate.is_file():
            return candidate
    return package_path.parent / "schemas" / _SCHEMA_NAME


def _validate_schema(payload: object, schema: object) -> None:
    try:
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
    except Exception as error:
        raise ProjectManifestError(
            "PROJECT_SCHEMA_INVALID",
            "Project schema is not available",
            {"field": "$schema", "rule": "invalidSchema"},
        ) from error

    errors = sorted(validator.iter_errors(payload), key=_validation_sort_key)
    if errors:
        error = errors[0]
        raise ProjectManifestError(
            "PROJECT_SCHEMA_INVALID",
            "Project manifest does not satisfy schema version 1",
            {"field": _validation_field(error), "rule": error.validator},
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


def _resolve_project_path(project_root: Path, value: str, field: str) -> Path:
    candidate = project_root / value
    resolved = candidate.resolve(strict=False)
    try:
        resolved.relative_to(project_root)
    except ValueError as error:
        raise ProjectManifestError(
            "PROJECT_SCHEMA_INVALID",
            "Project manifest path is outside the project root",
            {"field": field, "rule": "pathWithinProjectRoot"},
        ) from error
    return resolved
