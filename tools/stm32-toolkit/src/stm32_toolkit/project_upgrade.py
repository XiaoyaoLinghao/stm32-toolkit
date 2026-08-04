"""Read-only v1-to-v2 upgrade planning and atomic digest-guarded application.

The plan is a recursively immutable snapshot of the proposed v2 document plus
the source manifest SHA-256. Applying re-reads the manifest, verifies the
digest still matches, revalidates the proposed v2 document, and replaces the
manifest through a same-directory temporary file so a failure never leaves a
partial or corrupt manifest.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping as MappingABC
from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from types import MappingProxyType
from typing import Mapping, cast
from uuid import uuid4

from stm32_toolkit import __version__
from stm32_toolkit.identity import canonical_project_root
from stm32_toolkit.project_model import (
    SOURCE_MAPPING,
    ProjectManifestError,
    _MANIFEST_NAME,
    _canonical_root,
    _model_schema_version,
    _packaged_first_schema_error,
    _require_manifest_object,
    _require_schema_version,
    _validate_packaged_schema,
    validate_model_document,
)
from stm32_toolkit.result import OperationResult


class ProjectUpgradeError(Exception):
    """A deterministic upgrade failure suitable for protocol responses."""

    def __init__(self, code: str, message: str, details: Mapping[str, object]) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = dict(details)


@dataclass(frozen=True)
class UpgradePlan:
    manifest_path: Path
    source_sha256: str
    from_version: int
    to_version: int
    proposed: Mapping[str, object]

    def __post_init__(self) -> None:
        object.__setattr__(self, "proposed", cast(Mapping[str, object], _freeze(self.proposed)))


class _StageError(Exception):
    def __init__(self, stage: str) -> None:
        super().__init__(stage)
        self.stage = stage


def plan_project_upgrade(project_root: Path) -> UpgradePlan:
    """Build an immutable 1-to-2 upgrade plan without writing any project state."""
    root = _canonical_root(project_root)
    manifest_path = root / _MANIFEST_NAME
    raw_bytes = _read_manifest_bytes(manifest_path)
    payload = _parse_manifest_bytes(raw_bytes)
    version = _plan_schema_version(payload)
    _validate_packaged_schema(payload, version)

    proposed = _build_proposed(payload)
    invalid = _proposed_validation_error(proposed, root)
    if invalid is not None:
        field, rule = invalid
        raise ProjectUpgradeError(
            "PROJECT_UPGRADE_PLAN_INVALID",
            "Proposed project manifest is not valid schema version 2",
            {"field": field, "rule": rule},
        )

    return UpgradePlan(
        manifest_path=manifest_path,
        source_sha256=sha256(raw_bytes).hexdigest(),
        from_version=1,
        to_version=2,
        proposed=proposed,
    )


def apply_project_upgrade(plan: UpgradePlan) -> OperationResult[Mapping[str, object]]:
    """Atomically apply a validated 1-to-2 plan when the source digest matches.

    A public ``UpgradePlan`` constructor is not a write capability: the target
    path must be the canonical project-root manifest, the digest-matching
    current bytes must be a valid Schema v1 manifest, the proposed payload
    must be valid Schema v2, and it must be exactly the deterministic v1-to-v2
    mapping of the digest-matching bytes. Only then is a same-directory
    temporary file atomically replaced into place.
    """
    if type(plan.from_version) is not int or plan.from_version != 1:
        return _invalid_plan_versions(plan)
    if type(plan.to_version) is not int or plan.to_version != 2:
        return _invalid_plan_versions(plan)

    manifest_path = plan.manifest_path
    if not _is_canonical_manifest_path(manifest_path):
        return OperationResult.failure(
            "project.upgrade",
            "PROJECT_UPGRADE_PLAN_INVALID",
            "Project upgrade plan is invalid",
            {"field": "manifestPath", "rule": "canonicalProjectManifest"},
        )

    try:
        current_bytes = manifest_path.read_bytes()
    except OSError:
        return _changed_since_plan(manifest_path, plan.source_sha256, None)
    observed = sha256(current_bytes).hexdigest()
    if observed != plan.source_sha256:
        return _changed_since_plan(manifest_path, plan.source_sha256, observed)

    try:
        current_payload = _parse_manifest_bytes(current_bytes)
        if _model_schema_version(current_payload) != 1:
            raise ProjectManifestError(
                "PROJECT_UPGRADE_PLAN_INVALID",
                "Current project manifest is not schema version 1",
                {"schemaVersion": current_payload.get("schemaVersion")},
            )
        _validate_packaged_schema(current_payload, 1)
        validate_model_document(manifest_path.parent, current_payload, 1)
    except ProjectManifestError:
        return OperationResult.failure(
            "project.upgrade",
            "PROJECT_UPGRADE_PLAN_INVALID",
            "Project upgrade plan is invalid",
            {"field": "source", "rule": "validSchemaVersion1"},
        )

    proposed = cast(Mapping[str, object], _thaw(plan.proposed))
    invalid = _proposed_validation_error(proposed, manifest_path.parent)
    if invalid is not None:
        field, rule = invalid
        return OperationResult.failure(
            "project.upgrade",
            "PROJECT_UPGRADE_PLAN_INVALID",
            "Project upgrade plan is invalid",
            {"field": field, "rule": rule},
        )

    expected = _build_proposed(current_payload)
    if proposed != expected:
        return OperationResult.failure(
            "project.upgrade",
            "PROJECT_UPGRADE_PLAN_INVALID",
            "Project upgrade plan is invalid",
            {"field": "proposed", "rule": "deterministicUpgrade"},
        )

    content = _serialize(proposed)
    result_sha256 = sha256(content.encode("utf-8")).hexdigest()
    try:
        _write_temp_and_replace(manifest_path, content)
    except _StageError as error:
        return OperationResult.failure(
            "project.upgrade",
            "PROJECT_UPGRADE_IO_ERROR",
            "Project upgrade I/O error",
            {"path": str(manifest_path), "stage": error.stage},
        )

    return OperationResult.success(
        "project.upgrade",
        {
            "path": str(manifest_path),
            "fromVersion": 1,
            "toVersion": 2,
            "sourceSha256": plan.source_sha256,
            "resultSha256": result_sha256,
        },
    )


def _invalid_plan_versions(plan: UpgradePlan) -> OperationResult[None]:
    """Reject plan versions that are not built-in integers exactly 1 and 2.

    Booleans, floats, strings, and int subclasses are invalid even when they
    compare equal to 1 or 2 (``True == 1`` and ``1.0 == 1`` in Python).
    """
    return OperationResult.failure(
        "project.upgrade",
        "PROJECT_UPGRADE_PLAN_INVALID",
        "Project upgrade plan is invalid",
        {"fromVersion": plan.from_version, "toVersion": plan.to_version},
    )


def _is_canonical_manifest_path(manifest_path: Path) -> bool:
    """The only writable apply target is the canonical project-root manifest.

    A non-``Path`` target (for example a string) is rejected here without
    ever touching ``.name`` or other ``Path`` attributes, so no raw
    ``AttributeError`` can leak from a forged plan.
    """
    if (
        not isinstance(manifest_path, Path)
        or manifest_path.name != _MANIFEST_NAME
        or not manifest_path.is_absolute()
    ):
        return False
    try:
        canonical_parent = canonical_project_root(manifest_path.parent)
    except OSError:
        return False
    return canonical_parent == manifest_path.parent


def _read_manifest_bytes(manifest_path: Path) -> bytes:
    try:
        return manifest_path.read_bytes()
    except FileNotFoundError as error:
        raise ProjectManifestError(
            "PROJECT_NOT_CONFIGURED",
            "Project manifest is not configured",
            {"path": _MANIFEST_NAME},
        ) from error
    except OSError as error:
        raise ProjectManifestError(
            "PROJECT_NOT_CONFIGURED",
            "Project manifest is not available",
            {"path": _MANIFEST_NAME},
        ) from error


def _parse_manifest_bytes(raw_bytes: bytes) -> dict:
    try:
        text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ProjectManifestError(
            "PROJECT_JSON_INVALID",
            "Project manifest is not valid JSON",
            {"path": "$", "reason": "invalid_utf8"},
        ) from error
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as error:
        raise ProjectManifestError(
            "PROJECT_JSON_INVALID",
            "Project manifest is not valid JSON",
            {"path": "$", "line": error.lineno, "column": error.colno},
        ) from error
    return _require_manifest_object(payload)


def _plan_schema_version(payload: dict) -> int:
    version = _require_schema_version(payload)
    if version == 2:
        raise ProjectUpgradeError(
            "PROJECT_UPGRADE_NOT_REQUIRED",
            "Project is already schema version 2",
            {"schemaVersion": 2},
        )
    if version not in (1, 2):
        raise ProjectUpgradeError(
            "PROJECT_SCHEMA_VERSION_UNSUPPORTED",
            "Project schema version is not supported",
            {"schemaVersion": version, "supported": [1, 2]},
        )
    return int(version)


def _build_proposed(payload: dict) -> dict:
    """Map a validated v1 document to the exact proposed v2 document."""
    proposed = deepcopy(payload)
    proposed["schemaVersion"] = 2
    proposed["generatedBy"] = {"tool": "stm32-toolkit", "version": __version__}
    framework = proposed.get("framework")
    if isinstance(framework, dict) and "version" not in framework:
        framework["version"] = None
    build = proposed.get("build")
    if isinstance(build, dict):
        build["presets"] = []
    project = proposed.get("project")
    origin = project.get("origin") if isinstance(project, dict) else None
    origin = origin if isinstance(origin, str) else ""
    proposed["memory"] = {
        "source": SOURCE_MAPPING.get(origin, "manual"),
        "regions": [],
    }
    proposed["generation"] = {
        "cubeMxIoc": None,
        "managedManifest": ".stm32-toolkit/generated-files.json",
        "generatedDirectories": [],
        "userDirectories": [],
    }
    return proposed


def _proposed_validation_error(
    proposed: Mapping[str, object], root: Path
) -> tuple[str, str] | None:
    field_rule = _packaged_first_schema_error(proposed, 2)
    if field_rule is not None:
        return field_rule
    try:
        validate_model_document(root, cast(dict, proposed), 2)
    except ProjectManifestError as error:
        return (
            cast(str, error.details["field"]),
            cast(str, error.details["rule"]),
        )
    return None


def _changed_since_plan(
    manifest_path: Path, expected_sha256: str, observed_sha256: str | None
) -> OperationResult[None]:
    return OperationResult.failure(
        "project.upgrade",
        "PROJECT_CHANGED_SINCE_PLAN",
        "Project manifest changed since the upgrade plan was created",
        {
            "path": str(manifest_path),
            "expectedSha256": expected_sha256,
            "observedSha256": observed_sha256,
        },
    )


def _serialize(proposed: Mapping[str, object]) -> str:
    return json.dumps(proposed, indent=2, ensure_ascii=False) + "\n"


def _write_temp_and_replace(manifest_path: Path, content: str) -> None:
    directory = manifest_path.parent
    temp_path = directory / f".{manifest_path.name}.{uuid4().hex}.tmp"
    try:
        try:
            fd = os.open(temp_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except OSError as error:
            raise _StageError("write") from error
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
                try:
                    handle.write(content)
                except OSError as error:
                    raise _StageError("write") from error
                try:
                    handle.flush()
                    os.fsync(handle.fileno())
                except OSError as error:
                    raise _StageError("flush") from error
        except _StageError:
            raise
        except OSError as error:
            raise _StageError("write") from error
    except _StageError as error:
        _remove_temp(temp_path)
        raise
    try:
        os.replace(temp_path, manifest_path)
    except OSError as error:
        _remove_temp(temp_path)
        raise _StageError("replace") from error
    _fsync_directory(directory)


def _remove_temp(temp_path: Path) -> None:
    try:
        os.unlink(temp_path)
    except FileNotFoundError:
        return
    except OSError as error:
        raise _StageError("cleanup") from error


def _fsync_directory(directory: Path) -> None:
    """Best-effort directory fsync; unsupported filesystems are skipped."""
    try:
        fd = os.open(directory, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def _freeze(value: object) -> object:
    if isinstance(value, MappingABC):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


def _thaw(value: object) -> object:
    if isinstance(value, MappingABC):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value
