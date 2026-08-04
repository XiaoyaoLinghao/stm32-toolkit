from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from stm32_toolkit.project_model import (
    ProjectManifestError,
    _MANIFEST_NAME,
    _canonical_root,
    _load_manifest_json,
    _load_schema,
    _resolve_project_path,
    _validate_packaged_schema,
    _validate_schema,
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

        With no explicit schema, v2 manifests validate against the packaged v2
        schema and everything else keeps the historical single-schema v1
        behavior and stable error details. With an explicit schema path, the
        supplied schema alone governs validation.
        """
        root = _canonical_root(project_root)
        payload = _load_manifest_json(root / _MANIFEST_NAME)
        if schema_path is None:
            version = (
                2 if isinstance(payload, dict) and payload.get("schemaVersion") == 2 else 1
            )
            _validate_packaged_schema(payload, version)
        else:
            version = 1
            schema = _load_schema(schema_path, None)
            _validate_schema(payload, schema, version)

        cache: dict[Path, int] = {}
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
