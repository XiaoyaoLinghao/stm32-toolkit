"""Authorized CubeMX regeneration preview/apply orchestration.

All public entry points return :class:`OperationResult` and are intentionally
neutral about their host (CLI, MCP, or a direct caller).  The transaction
uses the accepted VS07-B generation-container/activation-staging ordering;
CubeMX is invoked at most once for prepare and once for apply.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import shutil
import stat
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Mapping

from stm32_toolkit.creation_apply import (
    _acquire_activation_lock,
    _assert_public_paths_are_portable,
    _cleanup,
    _create_owned_root,
    _owned_root_absent,
    _remove_empty_container,
)
from stm32_toolkit.creation_apply import CreationApplyError
from stm32_toolkit.creation_authorization import (
    CreationAuthorizationStore,
    CreationPrepareRequest,
    _durable_lock,
    _issued_claim,
)
from stm32_toolkit.cubemx_adapter import CubeMXAdapter, CubeMXAdapterError, CubeMXExecutionResult, CubeMXStagingContext, _control_root
from stm32_toolkit.cubemx_project import (
    CubeMXNativeProjectError,
    NativeProjectModel,
    parse_native_project,
    write_native_project_manifests,
)
from stm32_toolkit.creation_environment import CreationEnvironmentError
from stm32_toolkit.generation.creation import CreationRequest
from stm32_toolkit.generation.managed_files import GeneratedFile, build_managed_manifest_bytes, model_sha256_for, portable_sort_key
from stm32_toolkit.generation.configure import apply_project_configuration, plan_project_configuration
from stm32_toolkit.project_model import ProjectManifestError, load_project_model
from stm32_toolkit.result import OperationResult
from stm32_toolkit.tool_support import ToolSupportProfile
from stm32_toolkit.workflows import build_firmware_workflow
from stm32_toolkit.regeneration import (
    MAX_FILE_BYTES,
    MAX_FILES,
    MAX_TOTAL_BYTES,
    InventoryEntry,
    OwnershipSnapshot,
    RegenerationBlocker,
    RegenerationError,
    RegenerationInputError,
    RegenerationPlan,
    RegenerationPreview,
    RegenerationWorkflowRequest,
    _USER_ROOTS,
    _canonical_root,
    _creation_request,
    _digest,
    _expiry,
    _load_snapshot,
    _read_file,
    _relative_path,
    _scan,
    _safe_lstat,
    build_regeneration_plan,
    build_regeneration_preview,
)


def plan_regeneration_workflow(
    request: RegenerationWorkflowRequest,
    *,
    support_profile: ToolSupportProfile | None = None,
    repository: Path | None = None,
    environment: object | None = None,
) -> OperationResult[dict[str, object]]:
    """Neutral read-only plan adapter shared by CLI/MCP/direct callers."""
    from stm32_toolkit.regeneration import plan_regeneration

    return plan_regeneration(request, support_profile=support_profile, repository=repository, environment=environment)


class RegenerationAuthorizationError(ValueError):
    """Typed single-use regeneration capability failure."""

    def __init__(self, code: str, message: str, details: Mapping[str, object] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = dict(details or {})


@dataclass(frozen=True, slots=True)
class RegenerationAuthorization:
    authorization_digest: str
    plan_id: str
    action_digest: str
    preview_digest: str
    execution_environment_digest: str
    project_state_digest: str
    ownership_manifest_digest: str
    managed_manifest_digest: str
    current_ioc_sha256: str
    workspace_root: Path
    data_root: Path
    destination: str
    expires_at: str
    record_path: Path
    _claim: object | None = None

    def _is_store_issued(self) -> bool:
        return self._claim is not None

    def to_dict(self) -> dict[str, object]:
        return {
            "authorizationDigest": self.authorization_digest,
            "planId": self.plan_id,
            "actionDigest": self.action_digest,
            "previewDigest": self.preview_digest,
            "executionEnvironmentDigest": self.execution_environment_digest,
            "projectStateDigest": self.project_state_digest,
            "expiresAt": self.expires_at,
            "mutated": False,
        }


def _auth_digest(payload: Mapping[str, object]) -> str:
    canonical = {key: value for key, value in payload.items() if key not in {"authorizationDigest", "state"}}
    canonical["state"] = "prepared"
    from stm32_toolkit.generation.managed_files import canonical_json_bytes, sha256_hex

    return sha256_hex(canonical_json_bytes(canonical))


def _json_no_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


class RegenerationAuthorizationStore:
    """File-backed, atomic, single-use preview-bound capabilities."""

    def __init__(self, data_root: Path, *, now: Callable[[], datetime] | None = None, nonce_factory: Callable[[], str] | None = None) -> None:
        if not isinstance(data_root, Path) or not data_root.is_absolute():
            raise RegenerationAuthorizationError("REGENERATION_AUTHORIZATION_INVALID", "authorization data root is invalid")
        self.data_root = data_root.expanduser().resolve(strict=False)
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._nonce = nonce_factory or (lambda: secrets.token_urlsafe(24))

    @property
    def authorization_root(self) -> Path:
        return self.data_root / "regeneration" / "authorizations"

    @property
    def locks_root(self) -> Path:
        return self.authorization_root / ".locks"

    def _path(self, digest: str) -> Path:
        return self.authorization_root / f"{digest}.json"

    def _lock_path(self, digest: str) -> Path:
        return self.locks_root / f"{digest}.lock"

    def prepare(self, *, plan: RegenerationPlan, preview: RegenerationPreview) -> RegenerationAuthorization:
        if not isinstance(plan, RegenerationPlan) or not isinstance(preview, RegenerationPreview):
            raise RegenerationAuthorizationError("REGENERATION_AUTHORIZATION_INVALID", "authorization payload is invalid")
        if not all(_digest(item) for item in (plan.plan_id, plan.action_digest, preview.preview_digest, plan.execution_environment_digest, plan.project_state_digest, plan.ownership_manifest_digest, plan.managed_manifest_digest, plan.current_ioc_sha256)):
            raise RegenerationAuthorizationError("REGENERATION_AUTHORIZATION_INVALID", "authorization digest is invalid")
        expires = plan.expires_at
        try:
            expiry = datetime.strptime(expires, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            raise RegenerationAuthorizationError("REGENERATION_AUTHORIZATION_INVALID", "authorization expiry is invalid") from None
        if self._now().astimezone(timezone.utc).replace(microsecond=0) >= expiry:
            raise RegenerationAuthorizationError("REGENERATION_AUTHORIZATION_EXPIRED", "authorization has expired")
        payload: dict[str, object] = {
            "schemaVersion": 1,
            "nonce": str(self._nonce()),
            "issuedAt": self._now().astimezone(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "expiresAt": expires,
            "state": "prepared",
            "planId": plan.plan_id,
            "actionDigest": plan.action_digest,
            "previewDigest": preview.preview_digest,
            "executionEnvironmentDigest": plan.execution_environment_digest,
            "projectStateDigest": plan.project_state_digest,
            "ownershipManifestDigest": plan.ownership_manifest_digest,
            "managedManifestDigest": plan.managed_manifest_digest,
            "currentIocSha256": plan.current_ioc_sha256,
            "workspaceRoot": plan.request.workspace_root.as_posix(),
            "dataRoot": plan.request.data_root.as_posix(),
            "destination": plan.request.destination,
        }
        digest = _auth_digest(payload)
        payload["authorizationDigest"] = digest
        data = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        if len(data) > 64 * 1024:
            raise RegenerationAuthorizationError("REGENERATION_AUTHORIZATION_INVALID", "authorization record is oversized")
        try:
            self.authorization_root.mkdir(parents=True, exist_ok=True)
            path = self._path(digest)
            with _durable_lock(self._lock_path(digest)):
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                try:
                    os.write(fd, data)
                finally:
                    os.close(fd)
        except FileExistsError:
            raise RegenerationAuthorizationError("REGENERATION_AUTHORIZATION_INVALID", "authorization nonce collision") from None
        except (OSError, ValueError):
            raise RegenerationAuthorizationError("REGENERATION_AUTHORIZATION_INVALID", "authorization record cannot be written") from None
        return RegenerationAuthorization(digest, plan.plan_id, plan.action_digest, preview.preview_digest, plan.execution_environment_digest, plan.project_state_digest, plan.ownership_manifest_digest, plan.managed_manifest_digest, plan.current_ioc_sha256, plan.request.workspace_root, plan.request.data_root, plan.request.destination, expires, path)

    def _decode(self, digest: str, *, require_prepared: bool) -> tuple[dict[str, object], Path]:
        if not _digest(digest):
            raise RegenerationAuthorizationError("REGENERATION_AUTHORIZATION_INVALID", "authorization digest is invalid")
        path = self._path(digest)
        try:
            data, _ = _read_file(path, limit=64 * 1024)
            payload = json.loads(data.decode("utf-8"), object_pairs_hook=_json_no_duplicates)
        except (RegenerationError, OSError, UnicodeError, ValueError, TypeError):
            raise RegenerationAuthorizationError("REGENERATION_AUTHORIZATION_INVALID", "authorization record is malformed") from None
        required = {"schemaVersion", "nonce", "issuedAt", "expiresAt", "state", "planId", "actionDigest", "previewDigest", "executionEnvironmentDigest", "projectStateDigest", "ownershipManifestDigest", "managedManifestDigest", "currentIocSha256", "workspaceRoot", "dataRoot", "destination", "authorizationDigest"}
        if not isinstance(payload, dict) or set(payload) != required or payload.get("schemaVersion") != 1 or payload.get("authorizationDigest") != digest or _auth_digest(payload) != digest:
            raise RegenerationAuthorizationError("REGENERATION_AUTHORIZATION_INVALID", "authorization record is malformed")
        if not isinstance(payload.get("nonce"), str) or not payload["nonce"] or payload.get("state") not in {"prepared", "consumed"}:
            raise RegenerationAuthorizationError("REGENERATION_AUTHORIZATION_INVALID", "authorization record is malformed")
        if not all(_digest(payload.get(item)) for item in ("planId", "actionDigest", "previewDigest", "executionEnvironmentDigest", "projectStateDigest", "ownershipManifestDigest", "managedManifestDigest", "currentIocSha256")):
            raise RegenerationAuthorizationError("REGENERATION_AUTHORIZATION_INVALID", "authorization record is malformed")
        if not isinstance(payload.get("workspaceRoot"), str) or not isinstance(payload.get("dataRoot"), str) or not isinstance(payload.get("destination"), str):
            raise RegenerationAuthorizationError("REGENERATION_AUTHORIZATION_INVALID", "authorization record is malformed")
        try:
            workspace = Path(payload["workspaceRoot"])
            data_root = Path(payload["dataRoot"])
            if not workspace.is_absolute() or workspace != workspace.resolve(strict=False) or not data_root.is_absolute() or data_root != data_root.resolve(strict=False):
                raise ValueError
            if data_root != self.data_root:
                raise ValueError
            expires = datetime.strptime(str(payload["expiresAt"]), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            if require_prepared and payload.get("state") == "consumed":
                raise RegenerationAuthorizationError("REGENERATION_AUTHORIZATION_CONSUMED", "authorization has already been consumed")
            if self._now().astimezone(timezone.utc).replace(microsecond=0) >= expires:
                raise RegenerationAuthorizationError("REGENERATION_AUTHORIZATION_EXPIRED", "authorization has expired")
        except RegenerationAuthorizationError:
            raise
        except (OSError, ValueError, TypeError):
            raise RegenerationAuthorizationError("REGENERATION_AUTHORIZATION_INVALID", "authorization record is malformed") from None
        return payload, path

    def peek(self, digest: str) -> RegenerationAuthorization:
        payload, path = self._decode(digest, require_prepared=True)
        return self._value(payload, path, claim=None)

    def consume(self, digest: str, *, authorized: bool) -> RegenerationAuthorization:
        if type(authorized) is not bool or authorized is not True:
            raise RegenerationAuthorizationError("REGENERATION_AUTHORIZATION_REQUIRED", "authorization must be the JSON boolean true")
        if not _digest(digest):
            raise RegenerationAuthorizationError("REGENERATION_AUTHORIZATION_INVALID", "authorization digest is invalid")
        with _durable_lock(self._lock_path(digest)):
            payload, path = self._decode(digest, require_prepared=True)
            payload["state"] = "consumed"
            data = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
            temp = path.with_name(f".{path.name}.{self._nonce()}.tmp")
            try:
                temp.write_bytes(data)
                os.replace(temp, path)
            except OSError:
                try:
                    temp.unlink(missing_ok=True)
                except OSError:
                    pass
                raise RegenerationAuthorizationError("REGENERATION_AUTHORIZATION_INVALID", "authorization state cannot be consumed") from None
            return self._value(payload, path, claim=_issued_claim())

    def _value(self, payload: Mapping[str, object], path: Path, *, claim: object | None) -> RegenerationAuthorization:
        return RegenerationAuthorization(str(payload["authorizationDigest"]), str(payload["planId"]), str(payload["actionDigest"]), str(payload["previewDigest"]), str(payload["executionEnvironmentDigest"]), str(payload["projectStateDigest"]), str(payload["ownershipManifestDigest"]), str(payload["managedManifestDigest"]), str(payload["currentIocSha256"]), Path(str(payload["workspaceRoot"])), Path(str(payload["dataRoot"])), str(payload["destination"]), str(payload["expiresAt"]), path, claim)


def _failure(operation: str, code: str, message: str, details: Mapping[str, object] | None = None) -> OperationResult[None]:
    return OperationResult.failure(operation, code, message, details or {})


def _json_value(value: object) -> object:
    if isinstance(value, OperationResult):
        return value.to_dict()
    if hasattr(value, "to_dict"):
        try:
            return value.to_dict()
        except Exception:
            return None
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return None


@dataclass(frozen=True, slots=True)
class _Candidate:
    root: Path
    model: object
    snapshot: OwnershipSnapshot
    preview: RegenerationPreview


def _capability_for(plan: RegenerationPlan, attempt: str, *, now: datetime | None = None) -> tuple[object, Path]:
    """Create and consume one private CreationAuthorizationStore record."""
    if plan.model is None:
        raise RegenerationError("REGENERATION_PROJECT_INVALID", "CubeMX regeneration inputs are unavailable")
    request = _creation_request(plan.model, plan.request.project_root, plan.ioc_path, plan.current_ioc_sha256)
    ephemeral_root = plan.request.data_root / "regeneration" / f".ephemeral-{attempt}"
    try:
        store = CreationAuthorizationStore(
            ephemeral_root,
            now=(lambda: now) if now is not None else None,
        )
        issued = store.prepare(
            CreationPrepareRequest(
                request=request,
                project_root=plan.request.project_root,
                plan_id=plan.plan_id,
                action_digest=plan.action_digest,
                environment_digest=plan.execution_environment_digest,
                expires_at=plan.expires_at,
            )
        )
        return store.consume(issued.authorization_digest, authorized=True), ephemeral_root
    except Exception:
        if not _cleanup(ephemeral_root):
            raise RegenerationError(
                "REGENERATION_CLEANUP_REQUIRED",
                "internal preview authorization cleanup failed",
                {"recovery": ephemeral_root.name},
            ) from None
        raise RegenerationError("REGENERATION_AUTHORIZATION_INVALID", "internal preview authorization could not be issued") from None


def _native_child(container: Path, expected_name: str, execution: object) -> Path:
    candidate = getattr(execution, "project_root", execution)
    if not isinstance(candidate, Path):
        raise RegenerationError("REGENERATION_PREVIEW_FAILED", "CubeMX did not return a project root")
    try:
        container_resolved = container.resolve(strict=True)
        lexical = candidate.absolute()
        lexical_info = _safe_lstat(lexical)
        if not stat.S_ISDIR(lexical_info.st_mode):
            raise OSError
        path = lexical.resolve(strict=True)
        path.relative_to(container_resolved)
        info = _safe_lstat(path)
        entries = sorted(container.iterdir(), key=lambda item: item.name.casefold())
        if path.parent != container_resolved or path.name != expected_name or not stat.S_ISDIR(info.st_mode) or len(entries) != 1:
            raise OSError
    except (OSError, RuntimeError, ValueError, RegenerationError):
        raise RegenerationError("REGENERATION_PREVIEW_FAILED", "CubeMX output root is invalid") from None
    return path


def _copy_tree(source: Path, target: Path) -> None:
    """Copy a declared App/Tests tree with no redirect following."""
    if not os.path.lexists(source):
        return
    info = _safe_lstat(source)
    if not stat.S_ISDIR(info.st_mode):
        raise RegenerationError("REGENERATION_PATH_UNSAFE", "user ownership root is not a directory")
    target.mkdir(parents=True, exist_ok=True)
    pending = [(source, target)]
    while pending:
        current, out = pending.pop()
        try:
            children = sorted(current.iterdir(), key=lambda item: portable_sort_key(item.name))
        except OSError:
            raise RegenerationError("REGENERATION_USER_DRIFT", "user-owned files cannot be copied") from None
        for child in children:
            child_info = _safe_lstat(child)
            destination = out / child.name
            if stat.S_ISDIR(child_info.st_mode):
                destination.mkdir(parents=True, exist_ok=False)
                pending.append((child, destination))
            elif stat.S_ISREG(child_info.st_mode):
                data, _ = _read_file(child)
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(data)
            else:
                raise RegenerationError("REGENERATION_PATH_UNSAFE", "user-owned files contain a special path")


def _discard_derived(candidate: Path) -> None:
    """Drop generated build/artifact state before candidate activation."""
    for name in ("build", "artifacts"):
        path = candidate / name
        if not os.path.lexists(path):
            continue
        try:
            info = _safe_lstat(path)
            if not stat.S_ISDIR(info.st_mode):
                raise OSError
            shutil.rmtree(path)
        except (OSError, RuntimeError, ValueError):
            raise RegenerationError("REGENERATION_PATH_UNSAFE", "derived output root is unsafe") from None
    lock = candidate / ".stm32-toolkit" / "build.lock"
    if os.path.lexists(lock):
        try:
            info = _safe_lstat(lock)
            if not stat.S_ISREG(info.st_mode):
                raise OSError
            lock.unlink()
        except (OSError, RuntimeError, ValueError):
            raise RegenerationError("REGENERATION_PATH_UNSAFE", "derived build lock is unsafe") from None


def _seed_candidate_manifests(candidate: Path, model: object) -> None:
    if not isinstance(model, NativeProjectModel):
        # Test doubles may already provide the accepted schema-3 manifests.
        if not (candidate / ".stm32-project.json").is_file() or not (candidate / ".stm32-toolkit" / "cubemx-ownership.json").is_file():
            raise RegenerationError("REGENERATION_PREVIEW_FAILED", "CubeMX candidate metadata is unavailable")
        return
    ownership = write_native_project_manifests(candidate, model)
    project_model = load_project_model(candidate)
    rows = {path: (size, digest) for path, size, digest in model.files}
    generated: list[GeneratedFile] = []
    for target in __import__("stm32_toolkit.generation.managed_files", fromlist=["GENERATED_TARGETS"]).GENERATED_TARGETS:
        row = rows.get(target)
        if row is None:
            continue
        size, digest = row
        data = (candidate / target).read_bytes()
        generated.append(GeneratedFile(target, "unchanged", "", 1, digest, digest, size, size, "", data, data))
    generated.sort(key=lambda item: portable_sort_key(item.path))
    manifest = candidate / ".stm32-toolkit" / "generated-files.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_bytes(build_managed_manifest_bytes(tuple(generated), model_sha256_for(project_model)))


def _assert_candidate_compatible(plan: RegenerationPlan, model: object) -> None:
    """Keep target/toolchain identity fixed across one IOC regeneration."""
    if not isinstance(model, NativeProjectModel) or plan.model is None:
        return
    if model.target_device.casefold() != plan.model.target.device.casefold():
        raise RegenerationError("REGENERATION_PREVIEW_FAILED", "CubeMX candidate target differs from the project")
    if model.framework.casefold() != plan.model.framework.type.casefold():
        raise RegenerationError("REGENERATION_PREVIEW_FAILED", "CubeMX candidate framework differs from the project")
    expected_language = _creation_request(plan.model, plan.request.project_root, plan.ioc_path, plan.current_ioc_sha256).language
    if model.language.casefold() != expected_language.casefold():
        raise RegenerationError("REGENERATION_PREVIEW_FAILED", "CubeMX candidate language differs from the project")
    if plan.model.generation.native_linker_script and model.linker_script != plan.model.generation.native_linker_script:
        raise RegenerationError("REGENERATION_PREVIEW_FAILED", "CubeMX candidate linker differs from the project")


def _candidate_snapshot(candidate: Path) -> OwnershipSnapshot:
    return _load_snapshot(RegenerationWorkflowRequest(candidate.parent, candidate.parent / ".regeneration-data", "candidate", candidate.name))


def _prepare_candidate(
    plan: RegenerationPlan,
    container: Path,
    *,
    adapter: object | None,
    environment: object | None,
    validate_native: Callable[..., object] | None,
    copy_user: bool,
    now: datetime | None = None,
) -> OwnershipSnapshot:
    if plan.model is None:
        raise RegenerationError("REGENERATION_PROJECT_INVALID", "CubeMX project model is unavailable")
    resolved_environment = environment or plan.environment
    if resolved_environment is None:
        raise RegenerationError("REGENERATION_GENERATOR_DRIFT", "CubeMX execution facts are unavailable")
    # Keep the private capability-store path short.  The generation container
    # name is intentionally descriptive, but reusing it below the data root
    # can exceed Windows' component/path limits once the store appends its
    # own ``creation/authorizations`` and lock names.
    cap, ephemeral_root = _capability_for(plan, secrets.token_hex(12), now=now)
    runner = adapter or CubeMXAdapter(resolved_environment)
    try:
        execution = runner.generate(cap, CubeMXStagingContext(container))
    except CubeMXAdapterError as error:
        raise RegenerationError(error.code if error.code.startswith("CUBEMX_") else "REGENERATION_PREVIEW_FAILED", error.message, error.details) from None
    finally:
        if not _cleanup(ephemeral_root):
            raise RegenerationError(
                "REGENERATION_CLEANUP_REQUIRED",
                "internal preview authorization cleanup failed",
                {"recovery": ephemeral_root.name},
            )
    child = _native_child(container, plan.request.project_root.name, execution)
    try:
        _assert_public_paths_are_portable(child, plan.request.project_root)
    except CreationApplyError as error:
        raise RegenerationError(error.code, error.message, error.details) from None
    _discard_derived(child)
    try:
        if validate_native is None:
            model = parse_native_project(child, request=cap.request, plan_id=plan.plan_id, action_digest=plan.action_digest, environment=resolved_environment)
        else:
            model = validate_native(child, request=cap.request, plan_id=plan.plan_id, action_digest=plan.action_digest, environment=resolved_environment)
    except CubeMXNativeProjectError as error:
        raise RegenerationError(error.code, error.message, error.details) from None
    except RegenerationError:
        raise
    except Exception:
        raise RegenerationError("REGENERATION_PREVIEW_FAILED", "CubeMX candidate validation failed") from None
    actual_model = getattr(model, "model", model)
    _assert_candidate_compatible(plan, actual_model)
    _seed_candidate_manifests(child, actual_model)
    if copy_user:
        for root_name in ("App", "Tests"):
            _copy_tree(plan.request.project_root / root_name, child / root_name)
    try:
        snapshot = _load_snapshot_for_candidate(child, resolved_environment)
        _reject_candidate_blockers(snapshot)
        return snapshot
    except RegenerationError:
        raise


def _load_snapshot_for_candidate(candidate: Path, environment: object | None) -> OwnershipSnapshot:
    # The generic loader only needs the project model and local manifests; its
    # request is an internal read-only value and never reaches a public result.
    try:
        model = load_project_model(candidate)
        ownership_bytes, ownership_rows = __import__("stm32_toolkit.regeneration", fromlist=["_validate_ownership_manifest"])._validate_ownership_manifest(candidate)
        model_sha = __import__("stm32_toolkit.regeneration", fromlist=["_model_hash"])._model_hash(model)
        managed_bytes, managed_digest, _ = __import__("stm32_toolkit.regeneration", fromlist=["_managed_facts"])._managed_facts(candidate, model_sha)
        toolkit = {".stm32-project.json", ".stm32-toolkit/generated-files.json", ".stm32-toolkit/cubemx-ownership.json"} | {row.path for row in __import__("stm32_toolkit.generation.managed_files", fromlist=["parse_managed_manifest"]).parse_managed_manifest(managed_bytes)}
        cube = {str(row["path"]) for row in ownership_rows}
        inventory, data = _scan(candidate, toolkit, cube)
        return __import__("stm32_toolkit.regeneration", fromlist=["_classify_snapshot"])._classify_snapshot(model, inventory, data, ownership_rows, ownership_bytes, managed_bytes, managed_digest, model_sha)
    except RegenerationError:
        raise
    except (ProjectManifestError, OSError, ValueError):
        raise RegenerationError("REGENERATION_PREVIEW_FAILED", "CubeMX candidate metadata is invalid") from None


def _user_inventory_from_entries(inventory: tuple[InventoryEntry, ...]) -> tuple[tuple[str, str, int, str | None], ...]:
    return tuple(
        (entry.path, entry.kind, entry.size, entry.sha256)
        for entry in inventory
        if entry.ownership == "user"
    )


def _user_inventory(root: Path) -> tuple[tuple[str, str, int, str | None], ...]:
    """Rehash only the closed App/Tests roots without widening ownership."""
    records: list[InventoryEntry] = []
    total = 0
    files = 0
    for root_name in _USER_ROOTS:
        user_root = root / root_name
        if not os.path.lexists(user_root):
            continue
        info = _safe_lstat(user_root)
        if not stat.S_ISDIR(info.st_mode):
            raise RegenerationError("REGENERATION_USER_DRIFT", "user ownership root is not a directory", {"root": root_name})
        records.append(InventoryEntry(root_name, "dir", 0, None, "user"))
        pending = [user_root]
        while pending:
            current = pending.pop()
            try:
                children = sorted(current.iterdir(), key=lambda item: portable_sort_key(item.name))
            except OSError:
                raise RegenerationError("REGENERATION_USER_DRIFT", "user-owned files cannot be inspected", {"root": root_name}) from None
            for child in children:
                relative = _relative_path(root, child)
                child_info = _safe_lstat(child)
                if stat.S_ISDIR(child_info.st_mode):
                    records.append(InventoryEntry(relative, "dir", 0, None, "user"))
                    pending.append(child)
                    continue
                if not stat.S_ISREG(child_info.st_mode):
                    raise RegenerationError("REGENERATION_PATH_UNSAFE", "user-owned files contain a special path", {"root": root_name})
                files += 1
                if files > MAX_FILES:
                    raise RegenerationError("REGENERATION_PATH_UNSAFE", "user-owned file count exceeds its bound")
                data, size = _read_file(child)
                total += size
                if total > MAX_TOTAL_BYTES:
                    raise RegenerationError("REGENERATION_PATH_UNSAFE", "user-owned aggregate size exceeds its bound")
                records.append(InventoryEntry(relative, "file", size, hashlib.sha256(data).hexdigest(), "user"))
    records.sort(key=lambda item: portable_sort_key(item.path))
    return tuple((entry.path, entry.kind, entry.size, entry.sha256) for entry in records)


def _reject_candidate_blockers(snapshot: OwnershipSnapshot) -> None:
    if snapshot.blockers:
        blocker = snapshot.blockers[0]
        raise RegenerationError(
            blocker.code,
            "CubeMX candidate ownership state is invalid",
            {"blockers": [item.to_dict() for item in snapshot.blockers]},
        )


def _clean_roots(*roots: tuple[Path | None, bool]) -> bool:
    okay = True
    for path, owned in roots:
        if path is not None and owned:
            okay = _cleanup(path) and okay
    return okay


def _clean_preview_roots(container: Path | None, owned: bool) -> bool:
    """Remove the generation container and its CubeMX control sibling."""
    if container is None or not owned:
        return True
    control = container.parent / f".stm32tk-cubemx-control-{hashlib.sha256(str(container.resolve(strict=False)).encode('utf-8')).hexdigest()[:16]}"
    return _clean_roots((container, True), (control, True))


def _plan_for_request(
    request: RegenerationWorkflowRequest,
    *,
    support_profile: ToolSupportProfile | None,
    repository: Path | None,
    environment: object | None,
    now: datetime | None = None,
) -> RegenerationPlan:
    return build_regeneration_plan(
        request,
        support_profile=support_profile,
        repository=repository,
        environment=environment,
        now=now,
    )


def prepare_regeneration_workflow(
    request: RegenerationWorkflowRequest,
    *,
    plan_id: str,
    action_digest: str,
    authorized: bool = False,
    support_profile: ToolSupportProfile | None = None,
    repository: Path | None = None,
    store: RegenerationAuthorizationStore | None = None,
    adapter: object | None = None,
    environment: object | None = None,
    validate_native: Callable[..., object] | None = None,
    now: datetime | None = None,
) -> OperationResult[dict[str, object]]:
    operation = "project-regenerate-prepare"
    try:
        plan = _plan_for_request(request, support_profile=support_profile, repository=repository, environment=environment, now=now)
    except RegenerationInputError as error:
        return _failure(operation, error.code, error.message, {"field": error.field})
    except RegenerationError as error:
        return _failure(operation, error.code, error.message, error.details)
    if type(plan_id) is not str or type(action_digest) is not str or plan_id != plan.plan_id or action_digest != plan.action_digest:
        return _failure(operation, "REGENERATION_PLAN_CHANGED", "the regeneration plan changed since planning", {"currentPlanId": plan.plan_id, "currentActionDigest": plan.action_digest})
    if type(authorized) is not bool or authorized is not True:
        return _failure(operation, "REGENERATION_AUTHORIZATION_REQUIRED", "authorization must be the JSON boolean true", {})
    if plan.blockers:
        blocker = plan.blockers[0]
        return _failure(operation, blocker.code, "regeneration prerequisites are unavailable", {"blockers": [item.to_dict() for item in plan.blockers]})
    env = environment or plan.environment
    if env is None:
        return _failure(operation, "REGENERATION_GENERATOR_DRIFT", "CubeMX execution facts are unavailable", {})
    attempt = secrets.token_hex(12)
    container = plan.request.project_root.parent / f".stm32tk-regeneration-preview-{attempt}"
    owned = False
    try:
        _create_owned_root(container)
        owned = True
        candidate_snapshot = _prepare_candidate(
            plan,
            container,
            adapter=adapter,
            environment=env,
            validate_native=validate_native,
            copy_user=True,
            now=now,
        )
        preview = build_regeneration_preview(_load_snapshot(plan.request), candidate_snapshot)
        current_plan = _plan_for_request(request, support_profile=support_profile, repository=repository, environment=env, now=now)
        if current_plan.plan_id != plan.plan_id or current_plan.project_state_digest != plan.project_state_digest:
            raise RegenerationError("REGENERATION_STATE_CHANGED", "project state changed during preview")
        if not _clean_preview_roots(container, owned):
            return _failure(operation, "REGENERATION_CLEANUP_REQUIRED", "regeneration preview cleanup failed", {"recovery": container.name})
        owned = False
        auth_store = store or RegenerationAuthorizationStore(
            plan.request.data_root,
            now=(lambda: now) if now is not None else None,
        )
        authorization = auth_store.prepare(plan=plan, preview=preview)
        data = {**plan.to_dict(), **preview.to_dict(), **authorization.to_dict(), "mutated": False}
        return OperationResult.success(operation, data)
    except RegenerationAuthorizationError as error:
        if not _clean_preview_roots(container, owned):
            return _failure(operation, "REGENERATION_CLEANUP_REQUIRED", "regeneration preview cleanup failed", {"recovery": container.name})
        return _failure(operation, error.code, error.message, error.details)
    except RegenerationError as error:
        cleaned = _clean_preview_roots(container, owned)
        details = dict(error.details)
        if not cleaned:
            return _failure(operation, "REGENERATION_CLEANUP_REQUIRED", "regeneration preview cleanup failed", {"recovery": container.name})
        return _failure(operation, error.code, error.message, details)
    except (OSError, ValueError, RuntimeError):
        cleaned = _clean_preview_roots(container, owned)
        if not cleaned:
            return _failure(operation, "REGENERATION_CLEANUP_REQUIRED", "regeneration preview cleanup failed", {"recovery": container.name})
        return _failure(operation, "REGENERATION_PREVIEW_FAILED", "CubeMX preview failed", {})


def _activation_replace(staging: Path, destination: Path, attempt: str) -> tuple[bool, str | None]:
    backup = destination.parent / f".{destination.name}.regen-backup-{attempt}"
    _owned_root_absent(backup)
    backed_up = False
    activated = False
    try:
        os.replace(destination, backup)
        backed_up = True
        os.replace(staging, destination)
        activated = True
    except OSError:
        try:
            if activated and destination.exists():
                os.replace(destination, staging)
            if backed_up and backup.exists():
                os.replace(backup, destination)
        except OSError:
            raise RegenerationError("REGENERATION_ROLLBACK_FAILED", "regeneration activation rollback failed") from None
        raise RegenerationError("REGENERATION_ACTIVATION_FAILED", "regeneration activation failed") from None
    try:
        shutil.rmtree(backup)
    except OSError:
        # The new project is active, but the old tree remains as an owned,
        # bounded recovery name.  Never delete a collision here.
        return True, backup.name
    return True, None


def apply_regeneration_workflow(
    request: RegenerationWorkflowRequest,
    *,
    authorization_digest: str,
    authorized: bool,
    support_profile: ToolSupportProfile | None = None,
    repository: Path | None = None,
    store: RegenerationAuthorizationStore | None = None,
    adapter: object | None = None,
    environment: object | None = None,
    validate_native: Callable[..., object] | None = None,
    configure: Callable[[Path], object] | None = None,
    build: Callable[[Path, str], object] | None = None,
    now: datetime | None = None,
) -> OperationResult[dict[str, object]]:
    operation = "project-regenerate-apply"
    if type(authorized) is not bool or authorized is not True:
        return _failure(operation, "REGENERATION_AUTHORIZATION_REQUIRED", "authorization must be the JSON boolean true", {})
    auth_store = store or RegenerationAuthorizationStore(
        request.data_root,
        now=(lambda: now) if now is not None else None,
    )
    try:
        authorization = auth_store.consume(authorization_digest, authorized=True)
    except RegenerationAuthorizationError as error:
        return _failure(operation, error.code, error.message, error.details)
    try:
        if authorization.workspace_root != request.workspace_root or authorization.data_root != request.data_root or authorization.destination != request.destination:
            raise RegenerationError("REGENERATION_AUTHORIZATION_INVALID", "authorization is bound to a different project")
        plan = _plan_for_request(request, support_profile=support_profile, repository=repository, environment=environment, now=now)
        if plan.current_ioc_sha256 != authorization.current_ioc_sha256:
            raise RegenerationError("REGENERATION_STATE_CHANGED", "the authorized IOC changed")
        if plan.ownership_manifest_digest != authorization.ownership_manifest_digest:
            raise RegenerationError("REGENERATION_STATE_CHANGED", "the authorized ownership manifest changed")
        if plan.managed_manifest_digest != authorization.managed_manifest_digest:
            raise RegenerationError("REGENERATION_TOOLKIT_DRIFT", "the authorized Toolkit manifest changed")
        if plan.project_state_digest != authorization.project_state_digest:
            raise RegenerationError("REGENERATION_USER_DRIFT", "the authorized user-owned state changed")
        if plan.execution_environment_digest != authorization.execution_environment_digest:
            raise RegenerationError("REGENERATION_GENERATOR_DRIFT", "the authorized execution environment changed")
        if plan.plan_id != authorization.plan_id or plan.action_digest != authorization.action_digest:
            raise RegenerationError("REGENERATION_PLAN_CHANGED", "the authorized regeneration plan changed")
        if plan.blockers:
            blocker = plan.blockers[0]
            raise RegenerationError(blocker.code, "regeneration prerequisites are unavailable", {"blockers": [item.to_dict() for item in plan.blockers]})
        env = environment or plan.environment
        if env is None:
            raise RegenerationError("REGENERATION_GENERATOR_DRIFT", "CubeMX execution facts are unavailable")
        attempt = secrets.token_hex(12)
        container = plan.request.project_root.parent / f".stm32tk-regeneration-{attempt}"
        staging = plan.request.project_root.parent / f".stm32tk-regeneration-activation-{attempt}"
        generation_owned = activation_owned = False
        try:
            _create_owned_root(container)
            generation_owned = True
            candidate_snapshot = _prepare_candidate(
                plan,
                container,
                adapter=adapter,
                environment=env,
                validate_native=validate_native,
                copy_user=True,
                now=now,
            )
            preview = build_regeneration_preview(_load_snapshot(plan.request), candidate_snapshot)
            if preview.preview_digest != authorization.preview_digest:
                raise RegenerationError("REGENERATION_PREVIEW_CHANGED", "CubeMX preview differs from the authorized preview")
            child = container / plan.request.project_root.name
            _owned_root_absent(staging)
            os.replace(child, staging)
            activation_owned = True
            _remove_empty_container(container)
            generation_owned = False
            configured = configure(staging) if configure is not None else _default_configure(staging)
            if not isinstance(configured, OperationResult) or not configured.ok:
                raise RegenerationError("REGENERATION_CONFIGURATION_FAILED", "project configuration failed", {"result": _json_value(configured)})
            debug = build(staging, "arm-debug") if build is not None else _default_build(staging, "arm-debug")
            if not isinstance(debug, OperationResult) or not debug.ok:
                raise RegenerationError("REGENERATION_DEBUG_BUILD_FAILED", "Debug build failed", {"result": _json_value(debug)})
            release = build(staging, "arm-release") if build is not None else _default_build(staging, "arm-release")
            if not isinstance(release, OperationResult) or not release.ok:
                raise RegenerationError("REGENERATION_RELEASE_BUILD_FAILED", "Release build failed", {"result": _json_value(release)})
            with _acquire_activation_lock(request.data_root, plan.request.project_root):
                current = _load_snapshot(plan.request)
                current_plan = _plan_for_request(request, support_profile=support_profile, repository=repository, environment=environment, now=now)
                if current_plan.plan_id != plan.plan_id:
                    raise RegenerationError("REGENERATION_STATE_CHANGED", "project state changed while staged")
                expected_user = _user_inventory_from_entries(plan.inventory)
                current_user = _user_inventory_from_entries(current.inventory)
                if current_user != expected_user:
                    raise RegenerationError("REGENERATION_USER_DRIFT", "user-owned state changed while staged")
                candidate_user = _user_inventory(staging)
                if candidate_user != current_user:
                    raise RegenerationError("REGENERATION_USER_DRIFT", "candidate user-owned state changed before activation")
                # The activation lock serializes destination replacement; only
                # the exact validated candidate can cross it.
                _, recovery = _activation_replace(staging, plan.request.project_root, attempt)
                activation_owned = False
            if recovery is not None:
                return _failure(operation, "REGENERATION_CLEANUP_REQUIRED", "old project backup requires bounded recovery", {"recovery": recovery, "attemptId": attempt})
            return OperationResult.success(operation, {
                "planId": plan.plan_id,
                "authorizationDigest": authorization.authorization_digest,
                "previewDigest": preview.preview_digest,
                "destination": request.destination,
                "ownershipManifestSha256": candidate_snapshot.ownership_manifest_digest,
                "debug": _json_value(debug),
                "release": _json_value(release),
                "attemptId": attempt,
                "mutated": True,
            })
        finally:
            if not _clean_preview_roots(container, generation_owned) or not _clean_roots((staging, activation_owned)):
                raise RegenerationError(
                    "REGENERATION_CLEANUP_REQUIRED",
                    "regeneration transaction cleanup failed",
                    {"recovery": container.name},
                )
    except RegenerationError as error:
        return _failure(operation, error.code, error.message, error.details)
    except CubeMXAdapterError as error:
        return _failure(operation, error.code, error.message, error.details)
    except (OSError, RuntimeError, ValueError):
        return _failure(operation, "REGENERATION_ACTIVATION_FAILED", "regeneration activation failed", {})


def _default_configure(staging: Path) -> OperationResult[object]:
    try:
        model = load_project_model(staging)
        plan = plan_project_configuration(model)
        if plan.blockers:
            return OperationResult.failure("project-configuration-apply", "REGENERATION_CONFIGURATION_FAILED", "project configuration is blocked", {"blockers": [item.to_dict() for item in plan.blockers]})
        return apply_project_configuration(plan)
    except (ProjectManifestError, OSError, ValueError):
        return OperationResult.failure("project-configuration-apply", "REGENERATION_CONFIGURATION_FAILED", "project configuration failed", {})


def _default_build(staging: Path, preset: str) -> OperationResult[object]:
    return build_firmware_workflow(staging, preset=preset, clean=False, timeout_seconds=300, authorized=True)


# Concise aliases used by direct callers and older internal adapters.
prepare_regeneration = prepare_regeneration_workflow
apply_regeneration = apply_regeneration_workflow


__all__ = [
    "RegenerationAuthorization",
    "RegenerationAuthorizationError",
    "RegenerationAuthorizationStore",
    "apply_regeneration",
    "apply_regeneration_workflow",
    "prepare_regeneration",
    "prepare_regeneration_workflow",
    "plan_regeneration_workflow",
]
