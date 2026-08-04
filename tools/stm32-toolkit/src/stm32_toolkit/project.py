from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from stm32_toolkit.project_model import (
    ProjectManifestError,
    _MANIFEST_NAME,
    _canonical_root,
    _load_manifest_json,
    _load_schema,
    _model_schema_version,
    _require_schema_version,
    _resolve_project_path,
    _validate_packaged_schema,
    _validate_schema,
    validate_model_document,
)


@dataclass(frozen=True)
class ProjectManifest:
    project_root: Path
    logical_project_id: UUID
    target_device: str
    framework_type: str
    source_paths: tuple[Path, ...]
    assembly_source_paths: tuple[Path, ...]
    elf_path: Path | None

    @classmethod
    def load(
        cls,
        project_root: Path,
        schema_path: Path | None = None,
    ) -> "ProjectManifest":
        """Load the resolved-path compatibility view for a v1 or v2 manifest.

        With no explicit schema, v1 and v2 manifests are dispatched to their
        packaged schemas. With an explicit schema path, the supplied schema
        alone governs schema validation and the payload's integer
        ``schemaVersion`` (exactly 1 or 2, booleans rejected) selects the
        supported model. Every project-relative path field is validated for
        canonical-root containment after schema validation in both modes.
        """
        root = _canonical_root(project_root)
        payload = _load_manifest_json(root / _MANIFEST_NAME)
        if schema_path is None:
            version = _compat_dispatch_version(payload)
            _validate_packaged_schema(payload, version)
        else:
            version = _model_schema_version(payload)
            schema = _load_schema(schema_path, None)
            _validate_schema(payload, schema, version)
        validate_model_document(root, payload, version)

        cache: dict[Path, os.stat_result | None] = {}
        build = payload["build"]
        sources = tuple(
            _resolve_project_path(root, path, f"build.sources[{index}]", cache)
            for index, path in enumerate(build["sources"])
        )
        assembly_sources = tuple(
            _resolve_project_path(root, path, f"build.assemblySources[{index}]", cache)
            for index, path in enumerate(build["assemblySources"])
        )
        elf_value = build.get("elf")
        elf_path = (
            _resolve_project_path(root, elf_value, "build.elf", cache)
            if elf_value is not None
            else None
        )

        return cls(
            project_root=root,
            logical_project_id=UUID(payload["logicalProjectId"]),
            target_device=payload["target"]["device"],
            framework_type=payload["framework"]["type"],
            source_paths=sources,
            assembly_source_paths=assembly_sources,
            elf_path=elf_path,
        )


def _compat_dispatch_version(payload: dict) -> int:
    """Default compatibility dispatch: exact integer 2 selects v2, else v1.

    The stable required/type checks from the model loader still apply, so
    missing, boolean, float, or string ``schemaVersion`` values are rejected.
    An unsupported integer (for example 99) keeps the pre-existing stable
    v1-schema error contract of the compatibility loader instead of the model
    loader's unsupported-version error.
    """
    version = _require_schema_version(payload)
    return 2 if version == 2 else 1
