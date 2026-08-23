"""Authorized CubeMX staging, configure/build reuse, and activation."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import shutil
import stat
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator

from stm32_toolkit.creation_authorization import (
    ConsumedCreationAuthorization,
    CreationAuthorizationError,
    CreationAuthorizationStore,
    _durable_lock,
)
from stm32_toolkit.cubemx_adapter import CubeMXAdapter, CubeMXAdapterError, CubeMXStagingContext
from stm32_toolkit.cubemx_project import (
    CubeMXNativeProjectError,
    parse_native_project,
    write_native_project_manifests,
)
from stm32_toolkit.creation_environment import CreationEnvironmentError
from stm32_toolkit.generation.configure import apply_project_configuration, plan_project_configuration
from stm32_toolkit.generation.creation import _inventory_state
from stm32_toolkit.project_model import ProjectManifestError, load_project_model
from stm32_toolkit.result import OperationResult
from stm32_toolkit.workflows import build_firmware_workflow

_DESTINATION_LOCKS: dict[Path, threading.Lock] = {}
_DESTINATION_LOCKS_GUARD = threading.Lock()


def _lock_for(path: Path) -> threading.Lock:
    with _DESTINATION_LOCKS_GUARD:
        return _DESTINATION_LOCKS.setdefault(path, threading.Lock())


@contextmanager
def _acquire_activation_lock(data_root: Path, destination: Path) -> Iterator[None]:
    """Claim a destination activation slot across independent processes."""
    try:
        canonical = destination.expanduser().resolve(strict=False).as_posix().encode("utf-8")
        lock_name = hashlib.sha256(canonical).hexdigest()
        lock_path = data_root.expanduser().resolve(strict=False) / "creation" / "activation-locks" / f"{lock_name}.lock"
        with _durable_lock(lock_path):
            yield
    except CreationAuthorizationError:
        raise CreationApplyError("CREATION_ACTIVATION_FAILED", "creation activation lock is unavailable") from None


class CreationApplyError(ValueError):
    def __init__(self, code: str, message: str, details: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = dict(details or {})


@dataclass(frozen=True, slots=True)
class CreationApplyRequest:
    project_root: Path
    data_root: Path
    authorization_digest: str
    authorized: bool
    expected_plan_id: str | None = None
    expected_action_digest: str | None = None


@dataclass(frozen=True, slots=True)
class CreationApplyEvidence:
    attempt_id: str
    ownership_manifest_path: str | None
    ownership_manifest_sha256: str | None
    debug: object
    release: object

    def to_dict(self) -> dict[str, object]:
        return {
            "attemptId": self.attempt_id,
            "ownershipManifestPath": self.ownership_manifest_path,
            "ownershipManifestSha256": self.ownership_manifest_sha256,
            "debug": _json_value(self.debug),
            "release": _json_value(self.release),
        }


def _json_value(value: object) -> object:
    if isinstance(value, OperationResult):
        return value.to_dict()
    if hasattr(value, "to_dict"):
        try:
            return value.to_dict()
        except Exception:
            return None
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return None


def _failure(operation: str, code: str, message: str, details: dict[str, object] | None = None) -> OperationResult[None]:
    return OperationResult.failure(operation, code, message, details or {})


def _destination(root: Path, capability: ConsumedCreationAuthorization) -> Path:
    try:
        candidate = root / capability.request.destination
        resolved_parent = candidate.parent.resolve(strict=True)
        resolved_parent.relative_to(root)
        return candidate
    except (OSError, RuntimeError, ValueError):
        raise CreationApplyError("CREATION_DESTINATION_CHANGED", "creation destination is unavailable") from None


def _state(root: Path, destination: Path) -> tuple[str, str]:
    try:
        return _inventory_state(root, destination)
    except (OSError, ValueError, RuntimeError):
        raise CreationApplyError("CREATION_DESTINATION_CHANGED", "creation destination cannot be inspected") from None


def _write_attempt(data_root: Path, attempt_id: str, payload: dict[str, object]) -> None:
    try:
        path = data_root / "creation" / "attempts" / attempt_id
        path.mkdir(parents=True, exist_ok=True)
        (path / "failure.json").write_bytes(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
    except OSError:
        # Failure evidence is bounded best-effort and never changes the typed
        # product outcome or leaks raw host process output.
        return


def _cleanup(path: Path | None) -> bool:
    if path is None or not path.exists():
        return True
    try:
        shutil.rmtree(path)
        return not path.exists()
    except OSError:
        return False


def _assert_public_paths_are_portable(staging: Path, root: Path) -> None:
    """Reject native output that embeds host-controlled absolute project paths."""
    markers = {
        str(staging.resolve(strict=True)).encode("utf-8"),
        staging.resolve(strict=True).as_posix().encode("utf-8"),
        str(root.resolve(strict=True)).encode("utf-8"),
        root.resolve(strict=True).as_posix().encode("utf-8"),
    }
    try:
        for path in staging.rglob("*"):
            if not path.is_file() or path.is_symlink():
                continue
            data = path.read_bytes()
            if any(marker and marker in data for marker in markers):
                raise CreationApplyError("CUBEMX_NATIVE_OUTPUT_INVALID", "native output contains an absolute host path")
    except CreationApplyError:
        raise
    except OSError:
        raise CreationApplyError("CUBEMX_NATIVE_OUTPUT_INVALID", "native output cannot be inspected") from None


def _result_ok(value: object) -> bool:
    return isinstance(value, OperationResult) and value.ok


def _default_validate(staging: Path, *, capability: ConsumedCreationAuthorization, environment: object) -> object:
    model = parse_native_project(
        staging,
        request=capability.request,
        plan_id=capability.plan_id,
        action_digest=capability.action_digest,
        environment=environment,
    )
    ownership_path = write_native_project_manifests(staging, model)
    digest = hashlib.sha256(ownership_path.read_bytes()).hexdigest()
    return type("NativeValidation", (), {"model": model, "ownership_manifest_path": ownership_path.relative_to(staging).as_posix(), "ownership_manifest_sha256": digest})()


def _default_configure(staging: Path) -> OperationResult[object]:
    try:
        model = load_project_model(staging)
        plan = plan_project_configuration(model)
        if plan.blockers:
            return _failure("project-configuration-apply", "CREATION_CONFIGURATION_FAILED", "Project configuration is blocked", {"blockers": [item.to_dict() for item in plan.blockers]})
        return apply_project_configuration(plan)
    except (ProjectManifestError, OSError, ValueError):
        return _failure("project-configuration-apply", "CREATION_CONFIGURATION_FAILED", "Project configuration failed")


def _default_build(staging: Path, preset: str) -> OperationResult[object]:
    return build_firmware_workflow(staging, preset=preset, clean=False, timeout_seconds=300, authorized=True)


def _activate_absent(staging: Path, destination: Path) -> None:
    try:
        os.replace(staging, destination)
    except OSError:
        raise CreationApplyError("CREATION_ACTIVATION_FAILED", "creation destination activation failed") from None


def _activate_empty(staging: Path, destination: Path, backup: Path) -> None:
    destination_backed_up = False
    staging_activated = False

    def restore_exact_empty() -> None:
        try:
            if staging_activated and destination.exists():
                os.replace(destination, staging)
            if destination_backed_up and backup.exists():
                os.replace(backup, destination)
            if not destination.exists():
                destination.mkdir()
            if any(destination.iterdir()):
                raise OSError
        except OSError:
            raise CreationApplyError("CREATION_ACTIVATION_ROLLBACK_FAILED", "creation activation rollback failed") from None

    try:
        os.replace(destination, backup)
        destination_backed_up = True
        os.replace(staging, destination)
        staging_activated = True
        try:
            shutil.rmtree(backup)
        except OSError:
            restore_exact_empty()
            raise CreationApplyError("CREATION_ACTIVATION_FAILED", "creation backup cleanup failed") from None
    except CreationApplyError:
        raise
    except OSError:
        if destination_backed_up and not staging_activated:
            restore_exact_empty()
        raise CreationApplyError("CREATION_ACTIVATION_FAILED", "creation destination activation failed") from None


def apply_creation(
    request: CreationApplyRequest,
    *,
    store: CreationAuthorizationStore | None = None,
    adapter: object | None = None,
    environment: object | None = None,
    environment_factory: Callable[[ConsumedCreationAuthorization], object] | None = None,
    adapter_factory: Callable[[ConsumedCreationAuthorization, object], object] | None = None,
    revalidate_plan: Callable[..., None] | None = None,
    validate_native: Callable[..., object] | None = None,
    configure: Callable[[Path], object] | None = None,
    build: Callable[[Path, str], object] | None = None,
    on_activate: Callable[[], None] | None = None,
    attempt_id_factory: Callable[[], str] | None = None,
) -> OperationResult[dict[str, object]]:
    """Consume one capability, build in sibling staging, and activate once."""
    operation = "project-create-apply"
    if type(request.authorized) is not bool or request.authorized is not True:
        raise CreationAuthorizationError("CREATION_AUTHORIZATION_REQUIRED", "authorization must be the JSON boolean true")
    authorization_store = store or CreationAuthorizationStore(request.data_root)
    try:
        capability = authorization_store.consume(request.authorization_digest, authorized=request.authorized)
    except CreationAuthorizationError as error:
        return _failure(operation, error.code, error.message, error.details)
    try:
        root = request.project_root.expanduser().resolve(strict=True)
        if root != capability.project_root:
            raise CreationApplyError("CREATION_PLAN_CHANGED", "authorization project root changed")
        if request.expected_plan_id is not None and request.expected_plan_id != capability.plan_id:
            raise CreationApplyError("CREATION_PLAN_CHANGED", "creation plan changed")
        if request.expected_action_digest is not None and request.expected_action_digest != capability.action_digest:
            raise CreationApplyError("CREATION_PLAN_CHANGED", "creation action changed")
        destination = _destination(root, capability)
        original_digest, original_state = _state(root, destination)
        if original_state == "unsafe" or original_state == "populated":
            raise CreationApplyError("CREATION_DESTINATION_CHANGED", "destination must be absent or empty")
        if revalidate_plan is not None:
            try:
                revalidate_plan(capability, root, destination, original_digest, original_state)
            except CreationApplyError:
                raise
            except Exception:
                raise CreationApplyError("CREATION_PLAN_CHANGED", "creation plan could not be revalidated") from None
        if environment is None and environment_factory is not None:
            try:
                environment = environment_factory(capability)
            except CreationEnvironmentError:
                raise
            except Exception:
                raise CreationApplyError(
                    "CREATION_EXECUTION_ENVIRONMENT_CHANGED",
                    "creation execution environment is unavailable",
                ) from None
        if environment is not None and getattr(environment, "digest", capability.environment_digest) != capability.environment_digest:
            raise CreationApplyError("CREATION_EXECUTION_ENVIRONMENT_CHANGED", "creation execution environment changed")
        if adapter is None and adapter_factory is not None:
            try:
                adapter = adapter_factory(capability, environment)
            except CubeMXAdapterError:
                raise
            except Exception:
                raise CreationApplyError("CUBEMX_EXECUTION_ENVIRONMENT_CHANGED", "CubeMX adapter is unavailable") from None
        if adapter is None:
            raise CreationApplyError("CUBEMX_EXECUTION_ENVIRONMENT_CHANGED", "CubeMX adapter is unavailable")
        attempt_id = attempt_id_factory() if attempt_id_factory else secrets.token_hex(12)
        staging = destination.parent / f".stm32tk-creation-{attempt_id}"
        staging.mkdir()
        execution = adapter.generate(capability, CubeMXStagingContext(staging))
        control_root = getattr(execution, "control_root", None)
        if isinstance(control_root, Path):
            try:
                control_root.resolve(strict=False).relative_to(staging.resolve(strict=True))
            except ValueError:
                pass
            else:
                raise CreationApplyError("CUBEMX_NATIVE_OUTPUT_INVALID", "CubeMX control files overlap project staging")
            if not _cleanup(control_root):
                raise CreationApplyError("CREATION_ACTIVATION_FAILED", "CubeMX control files could not be cleaned")
        _assert_public_paths_are_portable(staging, root)
        validation = (validate_native or _default_validate)(staging, capability=capability, environment=environment)
        configured = (configure or _default_configure)(staging)
        if not _result_ok(configured):
            raise CreationApplyError("CREATION_CONFIGURATION_FAILED", "Project configuration failed", {"result": _json_value(configured)})
        debug = (build or _default_build)(staging, "arm-debug")
        if not _result_ok(debug):
            raise CreationApplyError("CREATION_DEBUG_BUILD_FAILED", "Debug build failed", {"result": _json_value(debug)})
        release = (build or _default_build)(staging, "arm-release")
        if not _result_ok(release):
            raise CreationApplyError("CREATION_RELEASE_BUILD_FAILED", "Release build failed", {"result": _json_value(release)})
        with _acquire_activation_lock(request.data_root, destination):
            current_digest, current_state = _state(root, destination)
            if current_digest != original_digest or current_state != original_state:
                raise CreationApplyError("CREATION_DESTINATION_CHANGED", "destination changed while creation was staged")
            backup = destination.parent / f".{destination.name}.backup-{attempt_id}"
            if original_state == "absent":
                _activate_absent(staging, destination)
            else:
                _activate_empty(staging, destination, backup)
            if on_activate is not None:
                on_activate()
        evidence = CreationApplyEvidence(
            attempt_id=attempt_id,
            ownership_manifest_path=getattr(validation, "ownership_manifest_path", None),
            ownership_manifest_sha256=getattr(validation, "ownership_manifest_sha256", None),
            debug=debug,
            release=release,
        )
        return OperationResult.success(
            operation,
            {
                "planId": capability.plan_id,
                "authorizationDigest": capability.authorization_digest,
                "destination": capability.request.destination,
                "ownershipManifestPath": evidence.ownership_manifest_path,
                "ownershipManifestSha256": evidence.ownership_manifest_sha256,
                "configurationPlanId": capability.plan_id,
                "debug": _json_value(debug),
                "release": _json_value(release),
                "attemptId": attempt_id,
                "mutated": True,
            },
        )
    except CreationApplyError as error:
        attempt = locals().get("attempt_id", "unknown")
        _write_attempt(request.data_root, str(attempt), {"code": error.code, "phase": "apply"})
        staging_path = locals().get("staging")
        if isinstance(staging_path, Path) and staging_path.exists():
            if not _cleanup(staging_path) and error.code not in {"CREATION_ACTIVATION_ROLLBACK_FAILED"}:
                return _failure(operation, "CREATION_ACTIVATION_ROLLBACK_FAILED", "creation staging cleanup failed", {"attemptId": str(attempt)})
        return _failure(operation, error.code, error.message, {**error.details, "attemptId": str(attempt)})
    except CubeMXAdapterError as error:
        attempt = str(locals().get("attempt_id", "unknown"))
        staging_path = locals().get("staging")
        if isinstance(staging_path, Path) and staging_path.exists() and not _cleanup(staging_path):
            return _failure(operation, "CREATION_ACTIVATION_ROLLBACK_FAILED", "creation staging cleanup failed", {"attemptId": attempt})
        _write_attempt(request.data_root, attempt, {"code": error.code, "phase": "cubemx"})
        return _failure(operation, error.code, error.message, {"attemptId": attempt})
    except CreationEnvironmentError as error:
        attempt = str(locals().get("attempt_id", "unknown"))
        staging_path = locals().get("staging")
        if isinstance(staging_path, Path) and staging_path.exists() and not _cleanup(staging_path):
            return _failure(operation, "CREATION_ACTIVATION_ROLLBACK_FAILED", "creation staging cleanup failed", {"attemptId": attempt})
        _write_attempt(request.data_root, attempt, {"code": error.code, "phase": "environment"})
        return _failure(operation, error.code, error.message, {"attemptId": attempt})
    except CubeMXNativeProjectError as error:
        attempt = str(locals().get("attempt_id", "unknown"))
        staging_path = locals().get("staging")
        if isinstance(staging_path, Path) and staging_path.exists() and not _cleanup(staging_path):
            return _failure(operation, "CREATION_ACTIVATION_ROLLBACK_FAILED", "creation staging cleanup failed", {"attemptId": attempt})
        _write_attempt(request.data_root, attempt, {"code": error.code, "phase": "validation"})
        return _failure(operation, error.code, error.message, {"attemptId": attempt})
    except OSError:
        staging_path = locals().get("staging")
        if isinstance(staging_path, Path) and staging_path.exists() and not _cleanup(staging_path):
            return _failure(operation, "CREATION_ACTIVATION_ROLLBACK_FAILED", "creation staging cleanup failed", {"attemptId": str(locals().get("attempt_id", "unknown"))})
        return _failure(operation, "CREATION_ACTIVATION_FAILED", "creation staging failed", {"attemptId": str(locals().get("attempt_id", "unknown"))})


apply_creation_workflow = apply_creation
run_creation_apply = apply_creation

__all__ = ["CreationApplyError", "CreationApplyRequest", "CreationApplyEvidence", "apply_creation", "apply_creation_workflow"]
