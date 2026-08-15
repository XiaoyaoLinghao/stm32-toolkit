"""Exact, authorized Schema v2-to-v3 project upgrade planning and apply."""

from __future__ import annotations

import json
import os
import re
import threading
from collections.abc import Mapping as MappingABC
from dataclasses import dataclass
from difflib import unified_diff
from hashlib import sha256
from pathlib import Path
from types import MappingProxyType
from typing import Mapping, cast
from uuid import uuid4

from stm32_toolkit.identity import canonical_project_root
from stm32_toolkit.project_model import (
    ProjectManifestError,
    _MANIFEST_NAME,
    _canonical_root,
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
    candidate: str
    diff: str
    plan_digest: str
    action_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "proposed", cast(Mapping[str, object], _freeze(self.proposed)))


class _StageError(Exception):
    def __init__(self, stage: str) -> None:
        super().__init__(stage)
        self.stage = stage


@dataclass
class _PreparedUpgrade:
    plan: UpgradePlan
    signature: tuple[object, ...]
    consumed: bool
    lock: threading.Lock


_PREPARED: dict[str, _PreparedUpgrade] = {}
_PREPARED_LOCK = threading.Lock()


def plan_project_upgrade(project_root: Path) -> UpgradePlan:
    """Build and register an immutable v2-to-v3 MODIFY plan without writes."""
    root = _canonical_root(project_root)
    manifest_path = root / _MANIFEST_NAME
    raw_bytes = _read_manifest_bytes(manifest_path)
    payload = _parse_manifest_bytes(raw_bytes)
    version = _plan_schema_version(payload)
    _validate_packaged_schema(payload, version)

    candidate = _build_candidate(raw_bytes)
    proposed = _parse_manifest_bytes(candidate.encode("utf-8"))
    invalid = _proposed_validation_error(proposed, root)
    if invalid is not None:
        field, rule = invalid
        raise ProjectUpgradeError(
            "PROJECT_UPGRADE_PLAN_INVALID",
            "Proposed project manifest is not valid schema version 3",
            {"field": field, "rule": rule},
        )

    source_sha256 = sha256(raw_bytes).hexdigest()
    diff = _build_diff(raw_bytes.decode("utf-8"), candidate)
    plan_digest = _digest(
        {
            "manifestPath": str(manifest_path),
            "sourceSha256": source_sha256,
            "fromVersion": 2,
            "toVersion": 3,
            "candidate": candidate,
            "diff": diff,
        }
    )
    action_digest = _digest(
        {
            "operation": "project.upgrade.apply",
            "planDigest": plan_digest,
            "sourceSha256": source_sha256,
        }
    )
    plan = UpgradePlan(
        manifest_path=manifest_path,
        source_sha256=source_sha256,
        from_version=2,
        to_version=3,
        proposed=proposed,
        candidate=candidate,
        diff=diff,
        plan_digest=plan_digest,
        action_digest=action_digest,
    )
    prepared = _PreparedUpgrade(plan, _plan_signature(plan), False, threading.Lock())
    with _PREPARED_LOCK:
        _PREPARED[action_digest] = prepared
    return plan


def upgrade_project_v2_to_v3(project_root: Path) -> UpgradePlan:
    """Named read-only route for preparing the Schema v2-to-v3 upgrade."""
    return plan_project_upgrade(project_root)


def apply_project_upgrade(
    plan: UpgradePlan, authorized: object, expected_plan_digest: object
) -> OperationResult[Mapping[str, object]]:
    """Consume one exact MODIFY token and atomically apply its v3 candidate."""
    if not isinstance(plan, UpgradePlan):
        return _invalid_plan("plan", "type")
    with _PREPARED_LOCK:
        prepared = _PREPARED.get(plan.action_digest)
    if prepared is None or prepared.plan is not plan:
        return _invalid_plan("plan", "registeredPreparedAction")
    if authorized != plan.action_digest or not isinstance(authorized, str):
        return OperationResult.failure(
            "project.upgrade",
            "PROJECT_UPGRADE_AUTHORIZATION_REQUIRED",
            "Exact project upgrade authorization is required",
            {"field": "authorized", "rule": "exactActionDigest"},
        )
    if expected_plan_digest != plan.plan_digest or not isinstance(
        expected_plan_digest, str
    ):
        return OperationResult.failure(
            "project.upgrade",
            "PROJECT_UPGRADE_PLAN_DIGEST_MISMATCH",
            "Project upgrade plan digest does not match",
            {
                "expectedPlanDigest": plan.plan_digest,
                "observedPlanDigest": expected_plan_digest,
            },
        )
    with prepared.lock:
        if prepared.consumed:
            return OperationResult.failure(
                "project.upgrade",
                "PROJECT_UPGRADE_AUTHORIZATION_CONSUMED",
                "Project upgrade authorization was already consumed",
                {"actionDigest": plan.action_digest},
            )
        prepared.consumed = True
        if prepared.signature != _plan_signature(plan):
            return _invalid_plan("plan", "immutablePreparedAction")
        if type(plan.from_version) is not int or plan.from_version != 2:
            return _invalid_plan_versions(plan)
        if type(plan.to_version) is not int or plan.to_version != 3:
            return _invalid_plan_versions(plan)
        manifest_path = plan.manifest_path
        if not _is_canonical_manifest_path(manifest_path):
            return _invalid_plan("manifestPath", "canonicalProjectManifest")
        try:
            current_bytes = manifest_path.read_bytes()
        except OSError:
            return _changed_since_plan(manifest_path, plan.source_sha256, None)
        observed = sha256(current_bytes).hexdigest()
        if observed != plan.source_sha256:
            return _changed_since_plan(manifest_path, plan.source_sha256, observed)
        try:
            current_payload = _parse_manifest_bytes(current_bytes)
            if _require_schema_version(current_payload) != 2:
                raise ProjectManifestError("invalid", "invalid", {})
            _validate_packaged_schema(current_payload, 2)
            validate_model_document(manifest_path.parent, current_payload, 2)
            expected_candidate = _build_candidate(current_bytes)
            proposed = _parse_manifest_bytes(expected_candidate.encode("utf-8"))
            invalid = _proposed_validation_error(proposed, manifest_path.parent)
            if invalid is not None:
                raise ProjectManifestError("invalid", "invalid", {})
        except ProjectManifestError:
            return _invalid_plan("source", "validSchemaVersion2")
        if (
            expected_candidate != plan.candidate
            or proposed != _thaw(plan.proposed)
            or _build_diff(current_bytes.decode("utf-8"), expected_candidate) != plan.diff
        ):
            return _invalid_plan("proposed", "deterministicUpgrade")
        result_sha256 = sha256(plan.candidate.encode("utf-8")).hexdigest()
        try:
            _write_temp_and_replace(manifest_path, plan.candidate)
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
                "fromVersion": 2,
                "toVersion": 3,
                "sourceSha256": plan.source_sha256,
                "resultSha256": result_sha256,
                "planDigest": plan.plan_digest,
                "actionDigest": plan.action_digest,
            },
        )


def _invalid_plan(field: str, rule: str) -> OperationResult[None]:
    return OperationResult.failure(
        "project.upgrade",
        "PROJECT_UPGRADE_PLAN_INVALID",
        "Project upgrade plan is invalid",
        {"field": field, "rule": rule},
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
    if version == 1:
        raise ProjectUpgradeError(
            "PROJECT_UPGRADE_V1_ROUTE_REQUIRED",
            "Schema version 1 requires the explicit legacy upgrade route",
            {"schemaVersion": 1, "route": "v1-to-v2"},
        )
    if version == 3:
        raise ProjectUpgradeError(
            "PROJECT_UPGRADE_NOT_REQUIRED",
            "Project is already schema version 3",
            {"schemaVersion": 3},
        )
    if version not in (1, 2, 3):
        raise ProjectUpgradeError(
            "PROJECT_SCHEMA_VERSION_UNSUPPORTED",
            "Project schema version is not supported",
            {"schemaVersion": version, "supported": [1, 2, 3]},
        )
    return int(version)


def _build_candidate(raw_bytes: bytes) -> str:
    source = raw_bytes.decode("utf-8")
    candidate, count = re.subn(
        r'("schemaVersion"\s*:\s*)2(?=\s*[,}])', r"\g<1>3", source, count=1
    )
    if count != 1:
        raise ProjectUpgradeError(
            "PROJECT_UPGRADE_PLAN_INVALID",
            "Schema version could not be upgraded deterministically",
            {"field": "schemaVersion", "rule": "deterministicUpgrade"},
        )
    return candidate


def _build_diff(source: str, candidate: str) -> str:
    return "".join(
        unified_diff(
            source.splitlines(keepends=True),
            candidate.splitlines(keepends=True),
            fromfile=f"{_MANIFEST_NAME} (v2)",
            tofile=f"{_MANIFEST_NAME} (v3)",
        )
    )


def _proposed_validation_error(
    proposed: Mapping[str, object], root: Path
) -> tuple[str, str] | None:
    field_rule = _packaged_first_schema_error(proposed, 3)
    if field_rule is not None:
        return field_rule
    try:
        validate_model_document(root, cast(dict, proposed), 3)
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


def _digest(value: Mapping[str, object]) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def _plan_signature(plan: UpgradePlan) -> tuple[object, ...]:
    return (
        plan.manifest_path,
        plan.source_sha256,
        plan.from_version,
        plan.to_version,
        _thaw(plan.proposed),
        plan.candidate,
        plan.diff,
        plan.plan_digest,
        plan.action_digest,
    )


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
