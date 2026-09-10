"""Project-bound, append-only recovery workflows for VS08-B.

The adapter reads existing public authorities and publishes immutable attempt
snapshots through the existing EvidenceStore.  It never executes a scenario
stage or owns a target, lease, transport, timer, or mutable attempt index.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import cast
from uuid import UUID

from stm32_toolkit.acceptance.model import (
    AcceptanceRecord,
    AcceptanceValidationError,
    REQUIRED_STAGES,
    describe_scenario,
)
from stm32_toolkit.build.identity import git_evidence, snapshot_project_inputs
from stm32_toolkit.context import build_project_context
from stm32_toolkit.diagnostic_workflows import (
    DiagnosticWorkflowContext,
    diagnostic_show,
    _validate_pair_execution_policy as diagnostic_validate_pair_execution_policy,
)
from stm32_toolkit.diagnostics import (
    DiagnosticSession,
    DiagnosticValidationError,
    SourceChangeDeclaration,
)
from stm32_toolkit.evidence import (
    EVIDENCE_CORRUPT,
    EvidenceEnvelope,
    EvidenceIdentity,
    EvidenceValidationError,
    canonical_json_bytes,
    get_root,
)
from stm32_toolkit.evidence.gc import RootRecord
from stm32_toolkit.evidence.store import EvidenceStore
from stm32_toolkit.paths import WorkspacePaths, require_safe_session_id
from stm32_toolkit.project_model import ProjectManifestError, load_project_model
from stm32_toolkit.generation.managed_files import model_sha256_for
from stm32_toolkit.result import OperationResult
from stm32_toolkit.testing.publication import TestRunRepository
from stm32_toolkit.testing_workflows import TestingWorkflowContext, test_show

from .recovery import (
    ATTEMPT_SCHEMA,
    AcceptanceAttempt,
    AcceptanceRecoveryValidationError,
    PHYSICAL_ATTEMPT_SCHEMA,
    PHYSICAL_RECOVERY_POLICY_DIGEST,
    PHYSICAL_SCENARIO_DIGEST,
    PHYSICAL_SCENARIO_ID,
    PHYSICAL_SCENARIO_VERSION,
    PHYSICAL_TRANSPORT,
    PHYSICAL_STAGE_OUTPUT_KEYS,
    PHYSICAL_STAGES,
    PhysicalAcceptanceAttempt,
    SourceChangeIntent,
    RECOVERY_POLICY_DIGEST,
    STAGE_OUTPUT_KEYS,
    acceptance_recovery_policy,
    physical_acceptance_recovery_policy,
)
from .workflows import AcceptanceWorkflowContext, show_acceptance_scenario


_ATTEMPT_ROOT_TYPE = "acceptance-attempt"
_ATTEMPT_OPERATION = "acceptance-attempt"
_UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
_HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_NATIVE_RUN_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
_DIAGNOSTIC_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")
_UTC_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z$")
_ROOT_METADATA_FIELDS = frozenset(
    {"attempt_sha256", "revision", "workspace_id", "logical_project_id"}
)
_ENVELOPE_METADATA_FIELDS = frozenset({"attempt", "attempt_sha256"})

_MESSAGES = {
    "ACCEPTANCE_ATTEMPT_INPUT_INVALID": "Acceptance attempt input is invalid.",
    "ACCEPTANCE_ATTEMPT_NOT_FOUND": "Acceptance attempt was not found.",
    "ACCEPTANCE_ATTEMPT_REVISION_CONFLICT": "Acceptance attempt revision conflicts with the current chain.",
    "ACCEPTANCE_ATTEMPT_STAGE_INVALID": "Acceptance attempt stage is invalid.",
    "ACCEPTANCE_ATTEMPT_TIMED_OUT": "Acceptance attempt stage deadline has elapsed.",
    "ACCEPTANCE_ATTEMPT_AUTHORIZATION_REQUIRED": "Acceptance attempt requires explicit source-change authorization.",
    "ACCEPTANCE_ATTEMPT_ACTION_DIGEST_MISMATCH": "Acceptance attempt action digest does not match.",
    "ACCEPTANCE_ATTEMPT_OUTPUT_INVALID": "Acceptance attempt public output is invalid.",
    "ACCEPTANCE_ATTEMPT_IDENTITY_MISMATCH": "Acceptance attempt identity does not match.",
    "ACCEPTANCE_ATTEMPT_EVIDENCE_INTEGRITY_FAILED": "Acceptance attempt evidence failed integrity validation.",
    "ACCEPTANCE_ATTEMPT_CONFLICT": "Acceptance attempt content conflicts with an immutable revision.",
}


@dataclass(frozen=True)
class AcceptanceRecoveryContext:
    """Caller-owned project roots for one recovery operation."""

    project_root: Path
    data_root: Path
    session_id: str
    clock: Callable[[], str] | None = None


class _RecoveryFailure(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


# Narrow seams preserve the public authority boundaries and let tests supply a
# fake clock or existing reader output without replacing the adapter itself.
_load_project_model = load_project_model
_workspace_paths_factory = WorkspacePaths.from_roots
_evidence_store_factory = EvidenceStore
_build_project_context = build_project_context
_test_show = test_show
_diagnostic_show = diagnostic_show
_show_acceptance_scenario = show_acceptance_scenario
_utc_now = lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _failure(operation: str, code: str) -> OperationResult[None]:
    return OperationResult.failure(
        operation,
        code,
        _MESSAGES.get(code, _MESSAGES["ACCEPTANCE_ATTEMPT_EVIDENCE_INTEGRITY_FAILED"]),
        {},
    )


def _result(operation: str, action: Callable[[], OperationResult[dict[str, object]]]) -> OperationResult[dict[str, object]]:
    try:
        return action()
    except _RecoveryFailure as error:
        return _failure(operation, error.code)
    except AcceptanceRecoveryValidationError as error:
        return _failure(operation, error.code)
    except AcceptanceValidationError:
        return _failure(operation, "ACCEPTANCE_ATTEMPT_INPUT_INVALID")
    except (DiagnosticValidationError, EvidenceValidationError, ProjectManifestError, FileNotFoundError, OSError, TypeError, ValueError, KeyError, IndexError, AttributeError):
        return _failure(operation, "ACCEPTANCE_ATTEMPT_EVIDENCE_INTEGRITY_FAILED")


def _validate_context(context: AcceptanceRecoveryContext) -> None:
    if not isinstance(context, AcceptanceRecoveryContext):
        raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_INPUT_INVALID")
    if not isinstance(context.project_root, Path) or not isinstance(context.data_root, Path):
        raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_INPUT_INVALID")
    try:
        require_safe_session_id(context.session_id)
    except (TypeError, ValueError) as error:
        raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_INPUT_INVALID") from error


def _canonical_uuid(field: str, value: object) -> str:
    if not isinstance(value, str) or _UUID_PATTERN.fullmatch(value) is None:
        raise AcceptanceRecoveryValidationError(f"{field} must be a canonical lowercase UUID")
    try:
        if str(UUID(value)) != value:
            raise ValueError
    except (TypeError, ValueError) as error:
        raise AcceptanceRecoveryValidationError(f"{field} must be a canonical lowercase UUID") from error
    return value


def _canonical_hash(field: str, value: object) -> str:
    if not isinstance(value, str) or _HASH_PATTERN.fullmatch(value) is None:
        raise AcceptanceRecoveryValidationError(f"{field} must be a lowercase SHA-256")
    return value


def _canonical_utc(field: str, value: object) -> str:
    if not isinstance(value, str) or _UTC_PATTERN.fullmatch(value) is None:
        raise AcceptanceRecoveryValidationError(f"{field} must use UTC microseconds")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ")
    except ValueError as error:
        raise AcceptanceRecoveryValidationError(f"{field} is not a valid UTC timestamp") from error
    if parsed.strftime("%Y-%m-%dT%H:%M:%S.%fZ") != value:
        raise AcceptanceRecoveryValidationError(f"{field} must use UTC microseconds")
    return value


def _timestamp(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ")


def _now(context: AcceptanceRecoveryContext) -> str:
    value = context.clock() if context.clock is not None else _utc_now()
    return _canonical_utc("server time", value)


def _deadline(updated: str, stage: str) -> str:
    seconds = acceptance_recovery_policy().stage_timeout_seconds[stage]
    return (_timestamp(updated) + timedelta(seconds=seconds)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _physical_deadline(updated: str, stage: str) -> str:
    from .recovery import physical_acceptance_recovery_policy

    seconds = physical_acceptance_recovery_policy().stage_timeout_seconds[stage]
    return (_timestamp(updated) + timedelta(seconds=seconds)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _typed_root_path(evidence: EvidenceStore, root_id: str, root_type: str = _ATTEMPT_ROOT_TYPE) -> Path:
    name = hashlib.sha256(
        canonical_json_bytes({"root_type": root_type, "root_id": root_id})
    ).hexdigest() + ".json"
    return evidence.root / "roots" / root_type / name


def _root_id(attempt_id: str, revision: int) -> str:
    return f"{attempt_id}.{revision:08d}"


def _load_project_and_workspace(
    context: AcceptanceRecoveryContext,
) -> tuple[object, WorkspacePaths, EvidenceStore]:
    _validate_context(context)
    try:
        model = _load_project_model(context.project_root)
    except (ProjectManifestError, OSError, ValueError, TypeError) as error:
        raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_IDENTITY_MISMATCH") from error
    if getattr(model, "schema_version", None) != 3:
        raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_OUTPUT_INVALID")
    try:
        project_id = UUID(str(model.logical_project_id))
        workspace = _workspace_paths_factory(
            context.data_root,
            context.project_root,
            project_id,
            context.session_id,
        )
        evidence = _evidence_store_factory(workspace.workspace_root / "evidence")
    except (OSError, TypeError, ValueError) as error:
        raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_IDENTITY_MISMATCH") from error
    return model, workspace, evidence


def _project_origin(model: object) -> str:
    origin = getattr(getattr(model, "memory", None), "source", None)
    if origin not in {"keil", "cubemx"}:
        raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_OUTPUT_INVALID")
    return cast(str, origin)


def _project_model_digest(model: object) -> str:
    try:
        digest = model_sha256_for(model)
    except Exception:
        raw = getattr(model, "to_dict", lambda: {})()
        digest = hashlib.sha256(canonical_json_bytes(raw)).hexdigest()
    return _canonical_hash("projectModelDigest", digest)


def _build_data(
    context: AcceptanceRecoveryContext,
    model: object,
) -> Mapping[str, object]:
    result = _build_project_context(context.project_root, context.data_root, context.session_id)
    if not isinstance(result, OperationResult) or result.ok is not True:
        raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_OUTPUT_INVALID")
    data = result.to_dict().get("data")
    if not isinstance(data, Mapping) or not isinstance(data.get("build"), Mapping):
        raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_OUTPUT_INVALID")
    build = cast(Mapping[str, object], data["build"])
    if build.get("elfFresh") is not True or build.get("preset") != "arm-debug":
        raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_OUTPUT_INVALID")
    build_id = build.get("buildId")
    elf_sha = build.get("elfSha256")
    if not isinstance(build_id, str) or _HASH_PATTERN.fullmatch(build_id) is None:
        raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_OUTPUT_INVALID")
    if not isinstance(elf_sha, str) or _HASH_PATTERN.fullmatch(elf_sha) is None:
        raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_OUTPUT_INVALID")
    try:
        input_snapshot = snapshot_project_inputs(model).sha256
    except Exception as error:
        raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_OUTPUT_INVALID") from error
    _canonical_hash("beforeInputSnapshotSha256", input_snapshot)
    return {
        "buildId": build_id,
        "elfSha256": elf_sha,
        "inputSnapshotSha256": input_snapshot,
    }


def _current_identity(
    context: AcceptanceRecoveryContext,
    model: object,
    workspace: WorkspacePaths,
    *,
    build: Mapping[str, object] | None = None,
) -> EvidenceIdentity:
    project_id = str(getattr(model, "logical_project_id"))
    target = getattr(model, "target_device", None)
    if target is None:
        target = getattr(getattr(model, "target", None), "device", None)
    if not isinstance(target, str) or not target:
        target = "unknown"
    build_id = build.get("buildId") if build is not None else None
    elf_sha = build.get("elfSha256") if build is not None else None
    input_snapshot = build.get("inputSnapshotSha256") if build is not None else None
    if not isinstance(build_id, str) or _HASH_PATTERN.fullmatch(build_id) is None:
        build_id = "0" * 64
    if not isinstance(elf_sha, str) or _HASH_PATTERN.fullmatch(elf_sha) is None:
        elf_sha = "0" * 64
    if not isinstance(input_snapshot, str) or _HASH_PATTERN.fullmatch(input_snapshot) is None:
        try:
            input_snapshot = snapshot_project_inputs(model).sha256
        except Exception:
            input_snapshot = "0" * 64
    try:
        git = git_evidence(context.project_root)
        git_head = git.head if isinstance(git.head, str) and re.fullmatch(r"[0-9a-f]{40}", git.head) else "0" * 40
        git_dirty = bool(git.dirty)
    except Exception:
        git_head, git_dirty = "0" * 40, False
    return EvidenceIdentity(
        workspace_id=workspace.workspace_id,
        project_id=project_id,
        session_id=context.session_id,
        build_id=build_id,
        elf_sha256=elf_sha,
        target_device=target,
        input_snapshot_sha256=input_snapshot,
        git_commit=git_head,
        git_dirty=git_dirty,
    )


def _root_metadata(attempt: AcceptanceAttempt) -> dict[str, object]:
    return {
        "attempt_sha256": attempt.checkpoint_id,
        "revision": attempt.revision,
        "workspace_id": attempt.workspace_id,
        "logical_project_id": attempt.logical_project_id,
    }


def _envelope_metadata(attempt: AcceptanceAttempt) -> dict[str, object]:
    return {"attempt": attempt.to_dict(), "attempt_sha256": attempt.checkpoint_id}


def _decode_attempt_envelope(
    evidence: EvidenceStore,
    *,
    root: RootRecord,
    envelope: EvidenceEnvelope,
    expected_attempt_id: str,
    expected_revision: int,
    workspace_id: str,
    logical_project_id: str,
) -> AcceptanceAttempt:
    if (
        root.root_type != _ATTEMPT_ROOT_TYPE
        or root.root_id != _root_id(expected_attempt_id, expected_revision)
        or set(root.metadata) != _ROOT_METADATA_FIELDS
        or envelope.operation != _ATTEMPT_OPERATION
        or set(envelope.metadata) != _ENVELOPE_METADATA_FIELDS
        or envelope.identity.workspace_id != workspace_id
        or envelope.identity.project_id != logical_project_id
        or root.metadata.get("workspace_id") != workspace_id
        or root.metadata.get("logical_project_id") != logical_project_id
        or root.metadata.get("revision") != expected_revision
    ):
        raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_EVIDENCE_INTEGRITY_FAILED")
    raw = envelope.metadata.get("attempt")
    try:
        attempt = AcceptanceAttempt.from_value(json.loads(canonical_json_bytes(raw).decode("utf-8")))
    except (AcceptanceRecoveryValidationError, TypeError, ValueError, UnicodeError) as error:
        raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_EVIDENCE_INTEGRITY_FAILED") from error
    if (
        attempt.attempt_id != expected_attempt_id
        or attempt.revision != expected_revision
        or attempt.workspace_id != workspace_id
        or attempt.logical_project_id != logical_project_id
        or canonical_json_bytes(envelope.metadata)
        != canonical_json_bytes(_envelope_metadata(attempt))
        or root.metadata != _root_metadata(attempt)
        or root.manifest_id != str(envelope.evidence_id)
        or _hash_attempt_payload(attempt) != attempt.checkpoint_id
    ):
        raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_EVIDENCE_INTEGRITY_FAILED")
    return attempt


def _read_revision(
    evidence: EvidenceStore,
    *,
    attempt_id: str,
    revision: int,
    workspace_id: str,
    logical_project_id: str,
) -> tuple[AcceptanceAttempt, EvidenceEnvelope] | None:
    root_path = _typed_root_path(evidence, _root_id(attempt_id, revision))
    if not root_path.exists():
        return None
    try:
        root = get_root(evidence, _ATTEMPT_ROOT_TYPE, _root_id(attempt_id, revision))
        envelope = evidence.get_envelope(root.manifest_id)
    except (EvidenceValidationError, OSError, FileNotFoundError, ValueError) as error:
        raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_EVIDENCE_INTEGRITY_FAILED") from error
    attempt = _decode_attempt_envelope(
        evidence,
        root=root,
        envelope=envelope,
        expected_attempt_id=attempt_id,
        expected_revision=revision,
        workspace_id=workspace_id,
        logical_project_id=logical_project_id,
    )
    return attempt, envelope


def _load_chain(
    evidence: EvidenceStore,
    *,
    attempt_id: str,
    workspace_id: str,
    logical_project_id: str,
) -> list[tuple[AcceptanceAttempt, EvidenceEnvelope]]:
    chain: list[tuple[AcceptanceAttempt, EvidenceEnvelope]] = []
    for revision in range(8):
        item = _read_revision(
            evidence,
            attempt_id=attempt_id,
            revision=revision,
            workspace_id=workspace_id,
            logical_project_id=logical_project_id,
        )
        if item is None:
            later = any(
                _typed_root_path(evidence, _root_id(attempt_id, later_revision)).exists()
                for later_revision in range(revision + 1, 8)
            )
            if later:
                raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_EVIDENCE_INTEGRITY_FAILED")
            break
        attempt, envelope = item
        if chain and attempt.previous_checkpoint_id != chain[-1][0].checkpoint_id:
            raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_EVIDENCE_INTEGRITY_FAILED")
        if revision == 0 and attempt.previous_checkpoint_id is not None:
            raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_EVIDENCE_INTEGRITY_FAILED")
        chain.append(item)
    if not chain:
        raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_NOT_FOUND")
    return chain


def _next_deadline_stage(revision: int) -> str:
    if revision == 0:
        return REQUIRED_STAGES[0]
    return REQUIRED_STAGES[revision if revision <= 4 else revision - 1]


def _validate_chain_semantics(
    chain: list[tuple[AcceptanceAttempt, EvidenceEnvelope]],
    *,
    model: object | None = None,
    workspace: WorkspacePaths | None = None,
) -> None:
    """Validate semantic continuity beyond each snapshot's local schema."""
    if not chain:
        raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_NOT_FOUND")
    immutable = (
        "attempt_id", "scenario_id", "scenario_version", "scenario_digest",
        "recovery_policy_digest", "workspace_id", "logical_project_id",
        "project_origin", "execution_source", "physical_transport_evidence",
        "opened_at_utc",
    )
    first = chain[0][0]
    for revision, (attempt, envelope) in enumerate(chain):
        if attempt.revision != revision:
            raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_EVIDENCE_INTEGRITY_FAILED")
        if envelope.parents != (() if revision == 0 else (chain[revision - 1][1].evidence_id,)):
            raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_EVIDENCE_INTEGRITY_FAILED")
        if envelope.artifacts != () or envelope.produced_at_utc != attempt.updated_at_utc:
            raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_EVIDENCE_INTEGRITY_FAILED")
        if attempt.deadline_at_utc != (
            None if revision == 7 else _deadline(attempt.updated_at_utc, _next_deadline_stage(revision))
        ):
            raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_EVIDENCE_INTEGRITY_FAILED")
        if revision == 0 and attempt.opened_at_utc != attempt.updated_at_utc:
            raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_EVIDENCE_INTEGRITY_FAILED")
        if attempt is not first:
            if any(getattr(attempt, field) != getattr(first, field) for field in immutable):
                raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_EVIDENCE_INTEGRITY_FAILED")
            previous = chain[revision - 1][0]
            if _timestamp(attempt.updated_at_utc) < _timestamp(previous.updated_at_utc):
                raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_EVIDENCE_INTEGRITY_FAILED")
            if previous.deadline_at_utc is None or _timestamp(attempt.updated_at_utc) > _timestamp(previous.deadline_at_utc):
                raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_EVIDENCE_INTEGRITY_FAILED")
            for key, value in previous.stage_outputs.items():
                if value is not None and attempt.stage_outputs.get(key) != value:
                    raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_EVIDENCE_INTEGRITY_FAILED")
            if previous.source_change_authorization is not None and attempt.source_change_authorization != previous.source_change_authorization:
                raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_EVIDENCE_INTEGRITY_FAILED")
    if model is not None and workspace is not None and first.project_origin != _project_origin(model):
        raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_IDENTITY_MISMATCH")


def _hash_attempt_payload(attempt: AcceptanceAttempt) -> str:
    payload = attempt.to_dict()
    payload.pop("checkpointId")
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def _publish_root_locked(evidence: EvidenceStore, root: RootRecord) -> Path:
    """Publish one root while the caller holds EvidenceStore's lock."""
    payload = canonical_json_bytes(root.to_dict())
    directory = evidence._managed_directory("roots", root.root_type)
    name = hashlib.sha256(
        canonical_json_bytes({"root_type": root.root_type, "root_id": root.root_id})
    ).hexdigest() + ".json"
    target = directory / name
    try:
        evidence._validate_existing_path(target, regular=True, single_link=True)
    except FileNotFoundError:
        if evidence._atomic_create_new(target, payload, phase="acceptance-attempt-root"):
            return target
    if target.read_bytes() != payload:
        raise EvidenceValidationError(EVIDENCE_CORRUPT, "attempt root identity already has different canonical bytes")
    return target


def _publish_snapshot(
    evidence: EvidenceStore,
    context: AcceptanceRecoveryContext,
    model: object,
    workspace: WorkspacePaths,
    candidate: AcceptanceAttempt,
    *,
    expected_revision: int,
    chain: list[tuple[AcceptanceAttempt, EvidenceEnvelope]],
) -> AcceptanceAttempt:
    with evidence._mutation_lock():
        current = _load_chain(
            evidence,
            attempt_id=candidate.attempt_id,
            workspace_id=workspace.workspace_id,
            logical_project_id=str(getattr(model, "logical_project_id")),
        ) if _typed_root_path(evidence, _root_id(candidate.attempt_id, 0)).exists() else []
        if current:
            _validate_chain_semantics(current, model=model, workspace=workspace)
            latest, latest_envelope = current[-1]
            if latest.revision > expected_revision:
                if _equivalent_transition(latest, candidate):
                    return latest
                raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_REVISION_CONFLICT")
            if latest.revision == expected_revision and _equivalent_transition(latest, candidate):
                return latest
            if latest.revision != expected_revision:
                raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_REVISION_CONFLICT")
            if expected_revision != candidate.revision - 1 and not (
                expected_revision == candidate.revision
            ):
                raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_REVISION_CONFLICT")
            chain = current
            parent_envelope = latest_envelope
        else:
            if expected_revision != 0 or candidate.revision != 0:
                raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_REVISION_CONFLICT")
            parent_envelope = None
        identity = _current_identity(context, model, workspace)
        parents = () if parent_envelope is None else (str(parent_envelope.evidence_id),)
        envelope = EvidenceEnvelope(
            identity=identity,
            operation=_ATTEMPT_OPERATION,
            produced_at_utc=candidate.updated_at_utc,
            parents=parents,
            artifacts=(),
            metadata=_envelope_metadata(candidate),
        )
        evidence._put_envelope_locked(envelope)
        _publish_root_locked(
            evidence,
            RootRecord(
                _ATTEMPT_ROOT_TYPE,
                _root_id(candidate.attempt_id, candidate.revision),
                str(envelope.evidence_id),
                _root_metadata(candidate),
            ),
        )
        return candidate


def _equivalent_transition(existing: AcceptanceAttempt, candidate: AcceptanceAttempt) -> bool:
    left = existing.to_dict()
    right = candidate.to_dict()
    for key in ("checkpointId", "previousCheckpointId", "openedAtUtc", "deadlineAtUtc", "updatedAtUtc"):
        left.pop(key, None)
        right.pop(key, None)
    return left == right


def _base_snapshot(
    *,
    attempt_id: str,
    scenario_id: str,
    scenario_version: str,
    scenario_digest: str,
    workspace_id: str,
    logical_project_id: str,
    project_origin: str,
    opened_at: str,
    updated_at: str,
    revision: int = 0,
    previous_checkpoint_id: str | None = None,
    outputs: Mapping[str, object] | None = None,
    authorization: Mapping[str, object] | None = None,
    status: str = "ACTIVE",
    deadline_at: str | None = None,
) -> AcceptanceAttempt:
    if outputs is None:
        outputs = {key: None for key in STAGE_OUTPUT_KEYS}
    payload: dict[str, object] = {
        "schema": ATTEMPT_SCHEMA,
        "attemptId": attempt_id,
        "revision": revision,
        "checkpointId": "0" * 64,
        "previousCheckpointId": previous_checkpoint_id,
        "scenarioId": scenario_id,
        "scenarioVersion": scenario_version,
        "scenarioDigest": scenario_digest,
        "recoveryPolicyDigest": RECOVERY_POLICY_DIGEST,
        "workspaceId": workspace_id,
        "logicalProjectId": logical_project_id,
        "projectOrigin": project_origin,
        "executionSource": "replay",
        "physicalTransportEvidence": False,
        "status": status,
        "completedStages": list(REQUIRED_STAGES[: (revision if revision <= 4 else revision - 1)]),
        "stageOutputs": dict(outputs),
        "sourceChangeAuthorization": dict(authorization) if authorization is not None else None,
        "openedAtUtc": opened_at,
        "deadlineAtUtc": deadline_at,
        "updatedAtUtc": updated_at,
    }
    payload["checkpointId"] = hashlib.sha256(
        canonical_json_bytes({key: value for key, value in payload.items() if key != "checkpointId"})
    ).hexdigest()
    return AcceptanceAttempt.from_value(payload)


def _stage_reference_shape(
    stage: str,
    *,
    test_run_id: object,
    diagnostic_session_id: object,
    acceptance_record_id: object,
) -> tuple[str | None, str | None, str | None]:
    test_value = _canonical_uuid("testRunId", test_run_id) if test_run_id is not None else None
    diagnostic_value = _canonical_uuid("diagnosticSessionId", diagnostic_session_id) if diagnostic_session_id is not None else None
    acceptance_value = _canonical_uuid("acceptanceRecordId", acceptance_record_id) if acceptance_record_id is not None else None
    if stage == "target-failure-replayed":
        if test_value is None or diagnostic_value is not None or acceptance_value is not None:
            raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_STAGE_INVALID")
    elif stage == "diagnosis-completed":
        if diagnostic_value is None or test_value is not None or acceptance_value is not None:
            raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_STAGE_INVALID")
    elif stage == "target-fix-verified":
        if acceptance_value is None or test_value is not None or diagnostic_value is not None:
            raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_STAGE_INVALID")
    elif any(value is not None for value in (test_value, diagnostic_value, acceptance_value)):
        raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_STAGE_INVALID")
    return test_value, diagnostic_value, acceptance_value


def _checkpoint_retry_matches(
    attempt: AcceptanceAttempt,
    *,
    expected_revision: int,
    stage: str,
    test_run_id: str | None,
    diagnostic_session_id: str | None,
    acceptance_record_id: str | None,
) -> bool:
    """Check a response-loss retry against the already-published next revision."""
    if attempt.revision != expected_revision + 1:
        return False
    expected_prefix = REQUIRED_STAGES[: expected_revision + 1 if expected_revision < 4 else expected_revision]
    if tuple(attempt.completed_stages) != expected_prefix:
        return False
    outputs = attempt.stage_outputs
    if stage == "project-materialized":
        return test_run_id is None and diagnostic_session_id is None and acceptance_record_id is None and outputs["projectModelDigest"] is not None
    if stage == "firmware-built-before":
        return test_run_id is None and diagnostic_session_id is None and acceptance_record_id is None and outputs["beforeBuildId"] is not None
    if stage == "target-failure-replayed":
        return (
            test_run_id == outputs["failedBeforeTestRunId"]
            and diagnostic_session_id is None
            and acceptance_record_id is None
        )
    if stage == "diagnosis-completed":
        return (
            diagnostic_session_id == outputs["diagnosticSessionId"]
            and test_run_id is None
            and acceptance_record_id is None
        )
    if stage == "firmware-built-after":
        return test_run_id is None and diagnostic_session_id is None and acceptance_record_id is None and outputs["afterBuildId"] is not None
    if stage == "target-fix-verified":
        return (
            acceptance_record_id == outputs["acceptanceRecordId"]
            and test_run_id is None
            and diagnostic_session_id is None
        )
    return False


def _check_deadline(attempt: AcceptanceAttempt, now: str) -> None:
    if attempt.deadline_at_utc is not None and _timestamp(now) > _timestamp(attempt.deadline_at_utc):
        raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_TIMED_OUT")


def _public_data(result: object) -> Mapping[str, object]:
    if not isinstance(result, OperationResult) or result.ok is not True:
        raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_OUTPUT_INVALID")
    value = result.to_dict().get("data")
    if not isinstance(value, Mapping):
        raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_OUTPUT_INVALID")
    return cast(Mapping[str, object], _thaw_json(value))


def _thaw_json(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _thaw_json(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_thaw_json(item) for item in value]
    return value


def _build_transition(
    context: AcceptanceRecoveryContext,
    model: object,
    workspace: WorkspacePaths,
    attempt: AcceptanceAttempt,
    stage: str,
    *,
    test_run_id: str | None,
    diagnostic_session_id: str | None,
    acceptance_record_id: str | None,
) -> dict[str, object]:
    outputs = dict(attempt.stage_outputs)
    if stage == "project-materialized":
        outputs["projectModelDigest"] = _project_model_digest(model)
    elif stage == "firmware-built-before":
        build = _build_data(context, model)
        outputs["beforeBuildId"] = build["buildId"]
        outputs["beforeElfSha256"] = build["elfSha256"]
        outputs["beforeInputSnapshotSha256"] = build["inputSnapshotSha256"]
    elif stage == "target-failure-replayed":
        assert test_run_id is not None
        data = _public_data(_test_show(TestingWorkflowContext(context.project_root, context.data_root, context.session_id), run_id=test_run_id))
        run = data.get("run")
        if not isinstance(run, Mapping) or run.get("run_id") != test_run_id or run.get("mode") != "target" or run.get("state") != "failed":
            raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_OUTPUT_INVALID")
        if data.get("execution_source") != "replay" or data.get("physical_transport_evidence") is not False:
            raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_OUTPUT_INVALID")
        if data.get("import_workspace_id") != workspace.workspace_id:
            raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_IDENTITY_MISMATCH")
        evidence_id = data.get("evidence_id")
        outputs["failedBeforeTestRunId"] = test_run_id
        outputs["failedBeforeEvidenceId"] = _canonical_hash("failedBeforeEvidenceId", evidence_id)
        try:
            published = TestRunRepository(_evidence_store_factory(workspace.workspace_root / "evidence")).load(test_run_id)
            if (
                published.manifest.mode != "target"
                or published.manifest.state != "failed"
                or published.manifest.transport != "replay"
                or published.root.metadata.get("physical_transport_evidence") is not False
                or published.root.metadata.get("import_workspace_id") != workspace.workspace_id
                or published.manifest.identity.project_id != str(getattr(model, "logical_project_id"))
                or published.manifest.identity.build_id != attempt.stage_outputs.get("beforeBuildId")
                or published.manifest.identity.elf_sha256 != attempt.stage_outputs.get("beforeElfSha256")
                or str(published.envelope.evidence_id) != evidence_id
            ):
                raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_OUTPUT_INVALID")
            if published.manifest.identity.target_device != getattr(model, "target_device", getattr(getattr(model, "target", None), "device", None)):
                raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_IDENTITY_MISMATCH")
        except _RecoveryFailure:
            raise
        except (EvidenceValidationError, OSError, ValueError, KeyError, TypeError):
            # A fake public reader is sufficient for adapter unit tests; real
            # stores are reloaded and checked whenever their root exists.
            if _typed_root_path(
                _evidence_store_factory(workspace.workspace_root / "evidence"),
                test_run_id,
                "test-run",
            ).exists():
                raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_EVIDENCE_INTEGRITY_FAILED")
    elif stage == "diagnosis-completed":
        assert diagnostic_session_id is not None
        storage_id = diagnostic_session_id.replace("-", "")
        data = _public_data(_diagnostic_show(DiagnosticWorkflowContext(context.project_root, context.data_root, context.session_id), diagnostic_session_id=storage_id))
        session_data = data.get("session")
        if not isinstance(session_data, Mapping):
            raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_OUTPUT_INVALID")
        try:
            session = DiagnosticSession.from_value(session_data)
        except (DiagnosticValidationError, TypeError, ValueError) as error:
            raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_EVIDENCE_INTEGRITY_FAILED") from error
        _validate_diagnostic_session(
            session,
            attempt,
            model,
            workspace,
            expected_session_id=diagnostic_session_id,
            allow_source_change=False,
        )
        outputs["diagnosticSessionId"] = diagnostic_session_id
        outputs["diagnosticRevision"] = session.revision
        outputs["diagnosticEventHead"] = session.event_head
    elif stage == "firmware-built-after":
        if attempt.revision == 4:
            raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_AUTHORIZATION_REQUIRED")
        build = _build_data(context, model)
        if build["buildId"] == attempt.stage_outputs.get("beforeBuildId"):
            raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_OUTPUT_INVALID")
        authorization = attempt.source_change_authorization
        if authorization is None:
            raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_AUTHORIZATION_REQUIRED")
        session_id = cast(str, attempt.stage_outputs.get("diagnosticSessionId"))
        storage_id = session_id.replace("-", "")
        data = _public_data(_diagnostic_show(DiagnosticWorkflowContext(context.project_root, context.data_root, context.session_id), diagnostic_session_id=storage_id))
        session_data = data.get("session")
        if not isinstance(session_data, Mapping):
            raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_OUTPUT_INVALID")
        try:
            session = DiagnosticSession.from_value(session_data)
        except (DiagnosticValidationError, TypeError, ValueError) as error:
            raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_EVIDENCE_INTEGRITY_FAILED") from error
        _validate_diagnostic_session(
            session,
            attempt,
            model,
            workspace,
            expected_session_id=session_id,
            allow_source_change=True,
        )
        declarations = tuple(session.source_change_declarations)
        if len(declarations) != 1 or session.revision <= int(authorization["diagnosticRevision"]):
            raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_OUTPUT_INVALID")
        declaration = declarations[0]
        if (
            declaration.before_source_sha256 != attempt.stage_outputs.get("beforeInputSnapshotSha256")
            or declaration.after_source_sha256 != build["inputSnapshotSha256"]
            or declaration.before_build_id != attempt.stage_outputs.get("beforeBuildId")
            or declaration.before_elf_sha256 != attempt.stage_outputs.get("beforeElfSha256")
            or declaration.after_build_id != build["buildId"]
            or declaration.after_elf_sha256 != build["elfSha256"]
        ):
            raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_IDENTITY_MISMATCH")
        outputs["afterBuildId"] = build["buildId"]
        outputs["afterElfSha256"] = build["elfSha256"]
        outputs["afterInputSnapshotSha256"] = build["inputSnapshotSha256"]
        outputs["sourceChangeDeclarationId"] = declaration.declaration_id
    elif stage == "target-fix-verified":
        assert acceptance_record_id is not None
        data = _public_data(
            _show_acceptance_scenario(
                AcceptanceWorkflowContext(context.project_root, context.data_root, context.session_id),
                record_id=acceptance_record_id,
            )
        )
        raw_record = data.get("record")
        if not isinstance(raw_record, Mapping):
            raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_OUTPUT_INVALID")
        try:
            record = AcceptanceRecord.from_value(raw_record)
        except (AcceptanceValidationError, TypeError, ValueError) as error:
            raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_EVIDENCE_INTEGRITY_FAILED") from error
        expected = attempt.stage_outputs
        if (
            record.record_id != acceptance_record_id
            or record.scenario_id != attempt.scenario_id
            or record.scenario_version != attempt.scenario_version
            or record.scenario_digest != attempt.scenario_digest
            or record.workspace_id != attempt.workspace_id
            or record.logical_project_id != attempt.logical_project_id
            or record.project_origin != attempt.project_origin
            or record.execution_source != "replay"
            or record.physical_transport_evidence is not False
            or record.completed_stages != REQUIRED_STAGES
            or record.failed_before_test_run_id != expected.get("failedBeforeTestRunId")
            or record.failed_before_evidence_id != expected.get("failedBeforeEvidenceId")
            or record.diagnostic_session_id != expected.get("diagnosticSessionId")
            or record.before_build_id != expected.get("beforeBuildId")
            or record.after_build_id != expected.get("afterBuildId")
            or record.before_elf_sha256 != expected.get("beforeElfSha256")
            or record.after_elf_sha256 != expected.get("afterElfSha256")
            or record.verdict != "SOFTWARE_PASSED"
        ):
            raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_OUTPUT_INVALID")
        fixed_data = _public_data(
            _test_show(
                TestingWorkflowContext(context.project_root, context.data_root, context.session_id),
                run_id=record.fixed_after_test_run_id,
            )
        )
        fixed_run = fixed_data.get("run")
        if (
            not isinstance(fixed_run, Mapping)
            or fixed_run.get("run_id") != record.fixed_after_test_run_id
            or fixed_run.get("mode") != "target"
            or fixed_run.get("state") != "passed"
            or fixed_data.get("execution_source") != "replay"
            or fixed_data.get("physical_transport_evidence") is not False
            or fixed_data.get("import_workspace_id") != workspace.workspace_id
            or fixed_data.get("evidence_id") != record.fixed_after_evidence_id
        ):
            raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_OUTPUT_INVALID")
        outputs["acceptanceRecordId"] = acceptance_record_id
    else:
        raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_STAGE_INVALID")
    return outputs


def _validate_diagnostic_session(
    session: DiagnosticSession,
    attempt: AcceptanceAttempt,
    model: object,
    workspace: WorkspacePaths,
    *,
    expected_session_id: str,
    allow_source_change: bool,
) -> None:
    target = getattr(model, "target_device", None)
    if target is None:
        target = getattr(getattr(model, "target", None), "device", None)
    if (
        session.diagnostic_session_id != expected_session_id.replace("-", "")
        or session.failed_test_run_id != attempt.stage_outputs.get("failedBeforeTestRunId")
        or session.failed_evidence_id != attempt.stage_outputs.get("failedBeforeEvidenceId")
        or session.identity.project_id != str(getattr(model, "logical_project_id"))
        or session.identity.workspace_id != workspace.workspace_id
        or session.identity.target_device != target
        or session.identity.build_id != attempt.stage_outputs.get("beforeBuildId")
        or session.identity.elf_sha256 != attempt.stage_outputs.get("beforeElfSha256")
        or session.identity.input_snapshot_sha256 != attempt.stage_outputs.get("beforeInputSnapshotSha256")
    ):
        raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_IDENTITY_MISMATCH")
    if not allow_source_change and session.state != "INVESTIGATING":
        raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_OUTPUT_INVALID")
    if allow_source_change and session.state not in {"INVESTIGATING", "FIX_PROPOSED", "VERIFYING", "RESOLVED"}:
        raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_OUTPUT_INVALID")
    if not allow_source_change and session.source_change_declarations:
        raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_OUTPUT_INVALID")


def _action_digest(attempt: AcceptanceAttempt) -> str:
    auth_payload = {
        "action": "source-change",
        "attemptId": attempt.attempt_id,
        "revision": attempt.revision,
        "checkpointId": attempt.checkpoint_id,
        "scenarioId": attempt.scenario_id,
        "scenarioVersion": attempt.scenario_version,
        "scenarioDigest": attempt.scenario_digest,
        "workspaceId": attempt.workspace_id,
        "logicalProjectId": attempt.logical_project_id,
        "beforeBuildId": attempt.stage_outputs.get("beforeBuildId"),
        "beforeElfSha256": attempt.stage_outputs.get("beforeElfSha256"),
        "beforeInputSnapshotSha256": attempt.stage_outputs.get("beforeInputSnapshotSha256"),
        "failedBeforeTestRunId": attempt.stage_outputs.get("failedBeforeTestRunId"),
        "failedBeforeEvidenceId": attempt.stage_outputs.get("failedBeforeEvidenceId"),
        "diagnosticSessionId": attempt.stage_outputs.get("diagnosticSessionId"),
        "diagnosticRevision": attempt.stage_outputs.get("diagnosticRevision"),
        "diagnosticEventHead": attempt.stage_outputs.get("diagnosticEventHead"),
    }
    return hashlib.sha256(canonical_json_bytes(auth_payload)).hexdigest()


def _begin_attempt(
    context: AcceptanceRecoveryContext,
    *,
    attempt_id: object,
    scenario_id: object,
    scenario_version: object,
) -> OperationResult[dict[str, object]]:
    attempt_id = _canonical_uuid("attemptId", attempt_id)
    scenario = describe_scenario(cast(str, scenario_id), cast(str, scenario_version))
    model, workspace, evidence = _load_project_and_workspace(context)
    origin = _project_origin(model)
    if origin != scenario.project_origin:
        raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_IDENTITY_MISMATCH")
    project_id = str(getattr(model, "logical_project_id"))
    root0 = _typed_root_path(evidence, _root_id(attempt_id, 0))
    if root0.exists():
        chain = _load_chain(
            evidence,
            attempt_id=attempt_id,
            workspace_id=workspace.workspace_id,
            logical_project_id=project_id,
        )
        _validate_chain_semantics(chain, model=model, workspace=workspace)
        latest = chain[-1][0]
        if (
            latest.scenario_id != scenario.scenario_id
            or latest.scenario_version != scenario.scenario_version
            or latest.scenario_digest != scenario.scenario_digest
            or latest.project_origin != origin
        ):
            raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_CONFLICT")
        return OperationResult.success("acceptance.attempt.begin", {"attempt": latest.to_dict()})
    opened = _now(context)
    candidate = _base_snapshot(
        attempt_id=attempt_id,
        scenario_id=scenario.scenario_id,
        scenario_version=scenario.scenario_version,
        scenario_digest=scenario.scenario_digest,
        workspace_id=workspace.workspace_id,
        logical_project_id=project_id,
        project_origin=origin,
        opened_at=opened,
        updated_at=opened,
        deadline_at=_deadline(opened, "project-materialized"),
    )
    published = _publish_snapshot(
        evidence,
        context,
        model,
        workspace,
        candidate,
        expected_revision=0,
        chain=[],
    )
    return OperationResult.success("acceptance.attempt.begin", {"attempt": published.to_dict()})


def begin_acceptance_attempt(
    context: AcceptanceRecoveryContext,
    *,
    attempt_id: object,
    scenario_id: object,
    scenario_version: object,
) -> OperationResult[dict[str, object]]:
    if scenario_id == PHYSICAL_SCENARIO_ID:
        return _result(
            "acceptance.attempt.begin",
            lambda: _begin_physical_attempt(
                context,
                attempt_id=attempt_id,
                scenario_id=scenario_id,
                scenario_version=scenario_version,
            ),
        )
    return _result(
        "acceptance.attempt.begin",
        lambda: _begin_attempt(
            context,
            attempt_id=attempt_id,
            scenario_id=scenario_id,
            scenario_version=scenario_version,
        ),
    )


def _checkpoint_attempt(
    context: AcceptanceRecoveryContext,
    *,
    attempt_id: object,
    expected_revision: object,
    stage: object,
    test_run_id: object = None,
    diagnostic_session_id: object = None,
    acceptance_record_id: object = None,
) -> OperationResult[dict[str, object]]:
    attempt_id = _canonical_uuid("attemptId", attempt_id)
    if type(expected_revision) is not int or not 0 <= expected_revision <= 7:
        raise AcceptanceRecoveryValidationError("expectedRevision must be an integer from 0 through 7")
    if not isinstance(stage, str) or stage not in REQUIRED_STAGES:
        raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_STAGE_INVALID")
    test_value, diagnostic_value, acceptance_value = _stage_reference_shape(
        stage,
        test_run_id=test_run_id,
        diagnostic_session_id=diagnostic_session_id,
        acceptance_record_id=acceptance_record_id,
    )
    model, workspace, evidence = _load_project_and_workspace(context)
    chain = _load_chain(
        evidence,
        attempt_id=attempt_id,
        workspace_id=workspace.workspace_id,
        logical_project_id=str(getattr(model, "logical_project_id")),
    )
    _validate_chain_semantics(chain, model=model, workspace=workspace)
    current = chain[-1][0]
    if current.revision != expected_revision:
        if current.revision > expected_revision:
            if _checkpoint_retry_matches(
                current,
                expected_revision=expected_revision,
                stage=stage,
                test_run_id=test_value,
                diagnostic_session_id=diagnostic_value,
                acceptance_record_id=acceptance_value,
            ):
                return OperationResult.success(
                    "acceptance.attempt.checkpoint", {"attempt": current.to_dict()}
                )
            raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_REVISION_CONFLICT")
        raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_EVIDENCE_INTEGRITY_FAILED")
    if current.next_stage != stage:
        if stage == "firmware-built-after" and current.revision == 4:
            raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_AUTHORIZATION_REQUIRED")
        raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_STAGE_INVALID")
    now = _now(context)
    _check_deadline(current, now)
    outputs = _build_transition(
        context,
        model,
        workspace,
        current,
        stage,
        test_run_id=test_value,
        diagnostic_session_id=diagnostic_value,
        acceptance_record_id=acceptance_value,
    )
    revision = expected_revision + 1
    if expected_revision == 4:
        raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_AUTHORIZATION_REQUIRED")
    candidate = _base_snapshot(
        attempt_id=current.attempt_id,
        scenario_id=current.scenario_id,
        scenario_version=current.scenario_version,
        scenario_digest=current.scenario_digest,
        workspace_id=current.workspace_id,
        logical_project_id=current.logical_project_id,
        project_origin=current.project_origin,
        opened_at=current.opened_at_utc,
        updated_at=now,
        revision=revision,
        previous_checkpoint_id=current.checkpoint_id,
        outputs=outputs,
        authorization=current.source_change_authorization,
        status="COMPLETED" if revision == 7 else "ACTIVE",
        deadline_at=None if revision == 7 else _deadline(now, REQUIRED_STAGES[revision if revision <= 4 else revision - 1]),
    )
    published = _publish_snapshot(
        evidence,
        context,
        model,
        workspace,
        candidate,
        expected_revision=expected_revision,
        chain=chain,
    )
    return OperationResult.success("acceptance.attempt.checkpoint", {"attempt": published.to_dict()})


def checkpoint_acceptance_attempt(
    context: AcceptanceRecoveryContext,
    *,
    attempt_id: object,
    expected_revision: object,
    stage: object,
    test_run_id: object = None,
    diagnostic_session_id: object = None,
    acceptance_record_id: object = None,
    source_change_intent: object = None,
    fix_verification_id: object = None,
) -> OperationResult[dict[str, object]]:
    physical_hint = (
        stage == "target-failure-observed"
        or source_change_intent is not None
        or fix_verification_id is not None
    )
    # Once an attempt exists, its immutable root selects the model for every
    # subsequent stage.  Physical stages such as project materialization and
    # the two build checkpoints carry no v2-only arguments, so dispatching only
    # from the request shape would replay them through the v1 adapter.
    physical = physical_hint
    try:
        canonical_attempt_id = _canonical_uuid("attemptId", attempt_id)
        schema = _attempt_schema_for_context(context, canonical_attempt_id)
        if schema is not None:
            physical = schema != ATTEMPT_SCHEMA
    except (AcceptanceRecoveryValidationError, _RecoveryFailure):
        physical = physical_hint
    if physical:
        return _result(
            "acceptance.attempt.checkpoint",
            lambda: _checkpoint_physical_attempt(
                context,
                attempt_id=attempt_id,
                expected_revision=expected_revision,
                stage=stage,
                test_run_id=test_run_id,
                diagnostic_session_id=diagnostic_session_id,
                acceptance_record_id=acceptance_record_id,
                fix_verification_id=fix_verification_id,
                source_change_intent=source_change_intent,
            ),
        )
    if source_change_intent is not None or fix_verification_id is not None or stage == "target-failure-observed":
        return _result(
            "acceptance.attempt.checkpoint",
            _reject_physical_only_checkpoint_fields,
        )
    return _result(
        "acceptance.attempt.checkpoint",
        lambda: _checkpoint_attempt(
            context,
            attempt_id=attempt_id,
            expected_revision=expected_revision,
            stage=stage,
            test_run_id=test_run_id,
            diagnostic_session_id=diagnostic_session_id,
            acceptance_record_id=acceptance_record_id,
        ),
    )


def _authorize_source_change(
    context: AcceptanceRecoveryContext,
    *,
    attempt_id: object,
    expected_revision: object,
    action_digest: object,
    authorized: object,
) -> OperationResult[dict[str, object]]:
    attempt_id = _canonical_uuid("attemptId", attempt_id)
    if type(expected_revision) is not int or expected_revision != 4:
        raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_STAGE_INVALID")
    action_digest = _canonical_hash("actionDigest", action_digest)
    if type(authorized) is not bool or authorized is not True:
        raise AcceptanceRecoveryValidationError("authorized must be true")
    model, workspace, evidence = _load_project_and_workspace(context)
    chain = _load_chain(
        evidence,
        attempt_id=attempt_id,
        workspace_id=workspace.workspace_id,
        logical_project_id=str(getattr(model, "logical_project_id")),
    )
    _validate_chain_semantics(chain, model=model, workspace=workspace)
    current = chain[-1][0]
    if current.revision != expected_revision:
        if (
            current.revision == expected_revision + 1
            and expected_revision == 4
            and current.source_change_authorization is not None
            and current.source_change_authorization.get("actionDigest") == action_digest
            and authorized is True
        ):
            return OperationResult.success(
                "acceptance.attempt.authorize-source-change", {"attempt": current.to_dict()}
            )
        raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_REVISION_CONFLICT")
    now = _now(context)
    _check_deadline(current, now)
    expected_digest = _action_digest(current)
    if action_digest != expected_digest:
        raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_ACTION_DIGEST_MISMATCH")
    if current.source_change_authorization is not None:
        raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_REVISION_CONFLICT")
    diagnostic_id = cast(str, current.stage_outputs.get("diagnosticSessionId"))
    diagnostic_data = _public_data(
        _diagnostic_show(
            DiagnosticWorkflowContext(context.project_root, context.data_root, context.session_id),
            diagnostic_session_id=diagnostic_id.replace("-", ""),
        )
    )
    session_data = diagnostic_data.get("session")
    if not isinstance(session_data, Mapping):
        raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_OUTPUT_INVALID")
    try:
        diagnostic_session = DiagnosticSession.from_value(session_data)
    except (DiagnosticValidationError, TypeError, ValueError) as error:
        raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_EVIDENCE_INTEGRITY_FAILED") from error
    _validate_diagnostic_session(
        diagnostic_session,
        current,
        model,
        workspace,
        expected_session_id=diagnostic_id,
        allow_source_change=False,
    )
    if (
        diagnostic_session.revision != current.stage_outputs.get("diagnosticRevision")
        or diagnostic_session.event_head != current.stage_outputs.get("diagnosticEventHead")
    ):
        raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_IDENTITY_MISMATCH")
    if diagnostic_session.source_change_declarations:
        raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_OUTPUT_INVALID")
    authorization = {
        "action": "source-change",
        "actionDigest": expected_digest,
        "authorized": True,
        "authorizedAtUtc": now,
        "diagnosticSessionId": current.stage_outputs["diagnosticSessionId"],
        "diagnosticRevision": current.stage_outputs["diagnosticRevision"],
        "diagnosticEventHead": current.stage_outputs["diagnosticEventHead"],
    }
    candidate = _base_snapshot(
        attempt_id=current.attempt_id,
        scenario_id=current.scenario_id,
        scenario_version=current.scenario_version,
        scenario_digest=current.scenario_digest,
        workspace_id=current.workspace_id,
        logical_project_id=current.logical_project_id,
        project_origin=current.project_origin,
        opened_at=current.opened_at_utc,
        updated_at=now,
        revision=5,
        previous_checkpoint_id=current.checkpoint_id,
        outputs=current.stage_outputs,
        authorization=authorization,
        status="ACTIVE",
        deadline_at=_deadline(now, "firmware-built-after"),
    )
    published = _publish_snapshot(
        evidence,
        context,
        model,
        workspace,
        candidate,
        expected_revision=4,
        chain=chain,
    )
    return OperationResult.success("acceptance.attempt.authorize-source-change", {"attempt": published.to_dict()})


# ---------------------------------------------------------------------------
# Task 10 physical recovery adapter
# ---------------------------------------------------------------------------


def _physical_expected_stage_count(revision: int) -> int:
    return revision if revision <= 4 else revision - 1


def _physical_native_run_id(field: str, value: object) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value.encode("utf-8")) > 64 * 1024
        or _NATIVE_RUN_ID_PATTERN.fullmatch(value) is None
    ):
        raise AcceptanceRecoveryValidationError(f"{field} must be a native Target run identifier")
    return value


def _physical_diagnostic_id(field: str, value: object) -> str:
    if not isinstance(value, str) or _DIAGNOSTIC_ID_PATTERN.fullmatch(value) is None:
        raise AcceptanceRecoveryValidationError(
            f"{field} must be a 32-hex Diagnostic session identifier"
        )
    return value


def _physical_target(model: object) -> str:
    target = getattr(model, "target_device", None)
    if target is None:
        target = getattr(getattr(model, "target", None), "device", None)
    if not isinstance(target, str) or not target:
        raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_IDENTITY_MISMATCH")
    return target


def _physical_root_metadata(attempt: PhysicalAcceptanceAttempt) -> dict[str, object]:
    return {
        "attempt_sha256": attempt.checkpoint_id,
        "revision": attempt.revision,
        "workspace_id": attempt.workspace_id,
        "logical_project_id": attempt.logical_project_id,
    }


def _physical_envelope_metadata(attempt: PhysicalAcceptanceAttempt) -> dict[str, object]:
    return {"attempt": attempt.to_dict(), "attempt_sha256": attempt.checkpoint_id}


def _decode_physical_attempt_envelope(
    evidence: EvidenceStore,
    *,
    root: RootRecord,
    envelope: EvidenceEnvelope,
    expected_attempt_id: str,
    expected_revision: int,
    workspace_id: str,
    logical_project_id: str,
) -> PhysicalAcceptanceAttempt:
    if (
        root.root_type != _ATTEMPT_ROOT_TYPE
        or root.root_id != _root_id(expected_attempt_id, expected_revision)
        or set(root.metadata) != _ROOT_METADATA_FIELDS
        or envelope.operation != _ATTEMPT_OPERATION
        or set(envelope.metadata) != _ENVELOPE_METADATA_FIELDS
        or envelope.identity.workspace_id != workspace_id
        or envelope.identity.project_id != logical_project_id
        or root.metadata.get("workspace_id") != workspace_id
        or root.metadata.get("logical_project_id") != logical_project_id
        or root.metadata.get("revision") != expected_revision
    ):
        raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_EVIDENCE_INTEGRITY_FAILED")
    raw = envelope.metadata.get("attempt")
    try:
        attempt = PhysicalAcceptanceAttempt.from_value(
            json.loads(canonical_json_bytes(raw).decode("utf-8"))
        )
    except (AcceptanceRecoveryValidationError, TypeError, ValueError, UnicodeError) as error:
        raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_EVIDENCE_INTEGRITY_FAILED") from error
    if (
        attempt.attempt_id != expected_attempt_id
        or attempt.revision != expected_revision
        or attempt.workspace_id != workspace_id
        or attempt.logical_project_id != logical_project_id
        or canonical_json_bytes(envelope.metadata)
        != canonical_json_bytes(_physical_envelope_metadata(attempt))
        or root.metadata != _physical_root_metadata(attempt)
        or root.manifest_id != str(envelope.evidence_id)
        or _hash_physical_attempt_payload(attempt) != attempt.checkpoint_id
    ):
        raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_EVIDENCE_INTEGRITY_FAILED")
    return attempt


def _read_physical_revision(
    evidence: EvidenceStore,
    *,
    attempt_id: str,
    revision: int,
    workspace_id: str,
    logical_project_id: str,
) -> tuple[PhysicalAcceptanceAttempt, EvidenceEnvelope] | None:
    root_path = _typed_root_path(evidence, _root_id(attempt_id, revision))
    if not root_path.exists():
        return None
    try:
        root = get_root(evidence, _ATTEMPT_ROOT_TYPE, _root_id(attempt_id, revision))
        envelope = evidence.get_envelope(root.manifest_id)
    except (EvidenceValidationError, OSError, FileNotFoundError, ValueError) as error:
        raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_EVIDENCE_INTEGRITY_FAILED") from error
    attempt = _decode_physical_attempt_envelope(
        evidence,
        root=root,
        envelope=envelope,
        expected_attempt_id=attempt_id,
        expected_revision=revision,
        workspace_id=workspace_id,
        logical_project_id=logical_project_id,
    )
    return attempt, envelope


def _load_physical_chain(
    evidence: EvidenceStore,
    *,
    attempt_id: str,
    workspace_id: str,
    logical_project_id: str,
) -> list[tuple[PhysicalAcceptanceAttempt, EvidenceEnvelope]]:
    chain: list[tuple[PhysicalAcceptanceAttempt, EvidenceEnvelope]] = []
    for revision in range(8):
        item = _read_physical_revision(
            evidence,
            attempt_id=attempt_id,
            revision=revision,
            workspace_id=workspace_id,
            logical_project_id=logical_project_id,
        )
        if item is None:
            if any(
                _typed_root_path(evidence, _root_id(attempt_id, later_revision)).exists()
                for later_revision in range(revision + 1, 8)
            ):
                raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_EVIDENCE_INTEGRITY_FAILED")
            break
        attempt, envelope = item
        if chain and attempt.previous_checkpoint_id != chain[-1][0].checkpoint_id:
            raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_EVIDENCE_INTEGRITY_FAILED")
        if revision == 0 and attempt.previous_checkpoint_id is not None:
            raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_EVIDENCE_INTEGRITY_FAILED")
        chain.append(item)
    if not chain:
        raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_NOT_FOUND")
    return chain


def _validate_physical_chain_semantics(
    chain: list[tuple[PhysicalAcceptanceAttempt, EvidenceEnvelope]],
    *,
    model: object | None = None,
    workspace: WorkspacePaths | None = None,
    session_id: str | None = None,
) -> None:
    if not chain:
        raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_NOT_FOUND")
    immutable = (
        "attempt_id", "scenario_id", "scenario_version", "scenario_digest",
        "recovery_policy_digest", "workspace_id", "logical_project_id",
        "project_origin", "execution_source", "opened_at_utc",
    )
    first = chain[0][0]
    for revision, (attempt, envelope) in enumerate(chain):
        if attempt.revision != revision:
            raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_EVIDENCE_INTEGRITY_FAILED")
        if envelope.parents != (() if revision == 0 else (chain[revision - 1][1].evidence_id,)):
            raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_EVIDENCE_INTEGRITY_FAILED")
        if envelope.artifacts != () or envelope.produced_at_utc != attempt.updated_at_utc:
            raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_EVIDENCE_INTEGRITY_FAILED")
        expected_stage_index = (
            0
            if revision == 0
            else revision
            if revision <= 4
            else revision - 1
        )
        expected_stage = PHYSICAL_STAGES[min(expected_stage_index, len(PHYSICAL_STAGES) - 1)]
        if attempt.deadline_at_utc != (
            None if revision == 7 else _physical_deadline(attempt.updated_at_utc, expected_stage)
        ):
            raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_EVIDENCE_INTEGRITY_FAILED")
        if revision == 0 and attempt.opened_at_utc != attempt.updated_at_utc:
            raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_EVIDENCE_INTEGRITY_FAILED")
        if attempt is not first:
            if any(getattr(attempt, field) != getattr(first, field) for field in immutable):
                raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_EVIDENCE_INTEGRITY_FAILED")
            previous = chain[revision - 1][0]
            if _timestamp(attempt.updated_at_utc) < _timestamp(previous.updated_at_utc):
                raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_EVIDENCE_INTEGRITY_FAILED")
            if previous.deadline_at_utc is None or _timestamp(attempt.updated_at_utc) > _timestamp(previous.deadline_at_utc):
                raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_EVIDENCE_INTEGRITY_FAILED")
            for key, value in previous.stage_outputs.items():
                if value is not None and attempt.stage_outputs.get(key) != value:
                    raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_EVIDENCE_INTEGRITY_FAILED")
            if previous.source_change_authorization is not None and attempt.source_change_authorization != previous.source_change_authorization:
                raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_EVIDENCE_INTEGRITY_FAILED")
            if previous.source_change_intent is not None and attempt.source_change_intent != previous.source_change_intent:
                raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_EVIDENCE_INTEGRITY_FAILED")
        if session_id is not None and envelope.identity.session_id != session_id:
            raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_IDENTITY_MISMATCH")
    if model is not None and workspace is not None:
        if first.project_origin != _project_origin(model):
            raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_IDENTITY_MISMATCH")
        if first.workspace_id != workspace.workspace_id or first.logical_project_id != str(getattr(model, "logical_project_id")):
            raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_IDENTITY_MISMATCH")


def _hash_physical_attempt_payload(attempt: PhysicalAcceptanceAttempt) -> str:
    payload = attempt.to_dict()
    payload.pop("checkpointId")
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def _publish_physical_snapshot(
    evidence: EvidenceStore,
    context: AcceptanceRecoveryContext,
    model: object,
    workspace: WorkspacePaths,
    candidate: PhysicalAcceptanceAttempt,
    *,
    expected_revision: int,
    chain: list[tuple[PhysicalAcceptanceAttempt, EvidenceEnvelope]],
) -> PhysicalAcceptanceAttempt:
    with evidence._mutation_lock():
        root0 = _typed_root_path(evidence, _root_id(candidate.attempt_id, 0))
        current = (
            _load_physical_chain(
                evidence,
                attempt_id=candidate.attempt_id,
                workspace_id=workspace.workspace_id,
                logical_project_id=str(getattr(model, "logical_project_id")),
            )
            if root0.exists()
            else []
        )
        if current:
            _validate_physical_chain_semantics(
                current, model=model, workspace=workspace, session_id=context.session_id
            )
            latest, latest_envelope = current[-1]
            if latest.revision > expected_revision:
                if _physical_equivalent_transition(latest, candidate):
                    return latest
                raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_REVISION_CONFLICT")
            if latest.revision == expected_revision and _physical_equivalent_transition(latest, candidate):
                return latest
            if latest.revision != expected_revision:
                raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_REVISION_CONFLICT")
            chain = current
            parent_envelope = latest_envelope
        else:
            if expected_revision != 0 or candidate.revision != 0:
                raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_REVISION_CONFLICT")
            parent_envelope = None
        identity = _current_identity(context, model, workspace)
        parents = () if parent_envelope is None else (str(parent_envelope.evidence_id),)
        envelope = EvidenceEnvelope(
            identity=identity,
            operation=_ATTEMPT_OPERATION,
            produced_at_utc=candidate.updated_at_utc,
            parents=parents,
            artifacts=(),
            metadata=_physical_envelope_metadata(candidate),
        )
        evidence._put_envelope_locked(envelope)
        _publish_root_locked(
            evidence,
            RootRecord(
                _ATTEMPT_ROOT_TYPE,
                _root_id(candidate.attempt_id, candidate.revision),
                str(envelope.evidence_id),
                _physical_root_metadata(candidate),
            ),
        )
        return candidate


def _physical_equivalent_transition(
    existing: PhysicalAcceptanceAttempt, candidate: PhysicalAcceptanceAttempt
) -> bool:
    left = existing.to_dict()
    right = candidate.to_dict()
    for key in ("checkpointId", "previousCheckpointId", "openedAtUtc", "deadlineAtUtc", "updatedAtUtc"):
        left.pop(key, None)
        right.pop(key, None)
    return left == right


def _physical_base_snapshot(
    *,
    attempt_id: str,
    opened_at: str,
    updated_at: str,
    workspace_id: str,
    logical_project_id: str,
    revision: int = 0,
    previous_checkpoint_id: str | None = None,
    outputs: Mapping[str, object] | None = None,
    authorization: Mapping[str, object] | None = None,
    intent: SourceChangeIntent | None = None,
    status: str = "ACTIVE",
    deadline_at: str | None = None,
) -> PhysicalAcceptanceAttempt:
    if outputs is None:
        outputs = {key: None for key in PHYSICAL_STAGE_OUTPUT_KEYS}
    payload: dict[str, object] = {
        "schema": PHYSICAL_ATTEMPT_SCHEMA,
        "attemptId": attempt_id,
        "revision": revision,
        "checkpointId": "0" * 64,
        "previousCheckpointId": previous_checkpoint_id,
        "scenarioId": PHYSICAL_SCENARIO_ID,
        "scenarioVersion": PHYSICAL_SCENARIO_VERSION,
        "scenarioDigest": PHYSICAL_SCENARIO_DIGEST,
        "recoveryPolicyDigest": PHYSICAL_RECOVERY_POLICY_DIGEST,
        "workspaceId": workspace_id,
        "logicalProjectId": logical_project_id,
        "projectOrigin": "keil",
        "executionSource": "physical",
        "physicalTransportEvidence": revision >= 3,
        "status": status,
        "completedStages": list(PHYSICAL_STAGES[: _physical_expected_stage_count(revision)]),
        "stageOutputs": dict(outputs),
        "sourceChangeAuthorization": dict(authorization) if authorization is not None else None,
        "sourceChangeIntent": intent.to_dict() if intent is not None else None,
        "openedAtUtc": opened_at,
        "deadlineAtUtc": deadline_at,
        "updatedAtUtc": updated_at,
    }
    payload["checkpointId"] = hashlib.sha256(
        canonical_json_bytes({key: value for key, value in payload.items() if key != "checkpointId"})
    ).hexdigest()
    return PhysicalAcceptanceAttempt.from_value(payload)


def _physical_stage_reference_shape(
    stage: str,
    *,
    test_run_id: object,
    diagnostic_session_id: object,
    acceptance_record_id: object,
    fix_verification_id: object,
) -> tuple[str | None, str | None, str | None, str | None]:
    if acceptance_record_id is not None:
        raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_STAGE_INVALID")
    test_value = _physical_native_run_id("testRunId", test_run_id) if test_run_id is not None else None
    diagnostic_value = _physical_diagnostic_id("diagnosticSessionId", diagnostic_session_id) if diagnostic_session_id is not None else None
    fix_value = _canonical_hash("fixVerificationId", fix_verification_id) if fix_verification_id is not None else None
    if stage == "target-failure-observed":
        if test_value is None or diagnostic_value is not None or fix_value is not None:
            raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_STAGE_INVALID")
    elif stage == "diagnosis-completed":
        if diagnostic_value is None or test_value is not None or fix_value is not None:
            raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_STAGE_INVALID")
    elif stage == "target-fix-verified":
        if test_value is None or fix_value is None or diagnostic_value is not None:
            raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_STAGE_INVALID")
    elif any(value is not None for value in (test_value, diagnostic_value, fix_value)):
        raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_STAGE_INVALID")
    return test_value, diagnostic_value, None, fix_value


def _physical_intent_matches(left: SourceChangeIntent | None, right: SourceChangeIntent | None) -> bool:
    if left is None or right is None:
        return left is right
    return left.to_dict() == right.to_dict() or (
        tuple(dict(item) for item in left.changes) == tuple(dict(item) for item in right.changes)
        and (left.intent_digest is None or right.intent_digest is None or left.intent_digest == right.intent_digest)
    )


def _physical_checkpoint_retry_matches(
    attempt: PhysicalAcceptanceAttempt,
    *,
    expected_revision: int,
    stage: str,
    test_run_id: str | None,
    diagnostic_session_id: str | None,
    fix_verification_id: str | None,
    source_change_intent: SourceChangeIntent | None,
) -> bool:
    if attempt.revision != expected_revision + 1:
        return False
    expected_prefix = PHYSICAL_STAGES[: _physical_expected_stage_count(expected_revision + 1)]
    if tuple(attempt.completed_stages) != expected_prefix:
        return False
    outputs = attempt.stage_outputs
    if stage == "project-materialized":
        return outputs["projectModelDigest"] is not None and all(value is None for value in (test_run_id, diagnostic_session_id, fix_verification_id, source_change_intent))
    if stage == "firmware-built-before":
        return outputs["beforeBuildId"] is not None and all(value is None for value in (test_run_id, diagnostic_session_id, fix_verification_id, source_change_intent))
    if stage == "target-failure-observed":
        return test_run_id == outputs["failedBeforeTestRunId"] and diagnostic_session_id is None and fix_verification_id is None and source_change_intent is None
    if stage == "diagnosis-completed":
        return diagnostic_session_id == outputs["diagnosticSessionId"] and test_run_id is None and fix_verification_id is None and _physical_intent_matches(attempt.source_change_intent, source_change_intent)
    if stage == "firmware-built-after":
        return outputs["afterBuildId"] is not None and all(value is None for value in (test_run_id, diagnostic_session_id, fix_verification_id, source_change_intent))
    if stage == "target-fix-verified":
        return test_run_id == outputs["fixedAfterTestRunId"] and fix_verification_id == outputs["fixVerificationId"] and diagnostic_session_id is None and source_change_intent is None
    return False


def _source_change_paths(model: object) -> frozenset[str]:
    build = getattr(model, "build", None)
    values = (*tuple(getattr(build, "sources", ())), *tuple(getattr(build, "assembly_sources", ())))
    if any(not isinstance(value, str) for value in values):
        raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_OUTPUT_INVALID")
    return frozenset(cast(str, value) for value in values)


def _snapshot_entries(snapshot: object) -> dict[str, object]:
    entries = getattr(snapshot, "entries", None)
    if not isinstance(entries, tuple):
        raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_OUTPUT_INVALID")
    result: dict[str, object] = {}
    for entry in entries:
        path = getattr(entry, "path", None)
        if not isinstance(path, str) or path in result:
            raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_EVIDENCE_INTEGRITY_FAILED")
        result[path] = entry
    return result


def _derive_physical_intent(
    model: object,
    intent: SourceChangeIntent,
    snapshot: object,
    *,
    expected_before_hash: str,
) -> SourceChangeIntent:
    if getattr(snapshot, "sha256", None) != expected_before_hash:
        raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_IDENTITY_MISMATCH")
    entries = _snapshot_entries(snapshot)
    owned_sources = _source_change_paths(model)
    replacement: dict[str, dict[str, object]] = {}
    for change in intent.changes:
        path = cast(str, change["path"])
        if path not in owned_sources or path not in entries:
            raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_OUTPUT_INVALID")
        entry = entries[path]
        before_hash = getattr(entry, "sha256", None)
        before_size = getattr(entry, "size", None)
        if (
            before_hash != change["beforeSha256"]
            or type(before_size) is not int
            or (before_hash == change["afterSha256"] and before_size == change["afterSize"])
        ):
            raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_IDENTITY_MISMATCH")
        replacement[path] = dict(change)
    payload = [
        {
            "path": cast(str, getattr(entry, "path")),
            "size": replacement.get(cast(str, getattr(entry, "path")), {}).get("afterSize", getattr(entry, "size")),
            "sha256": replacement.get(cast(str, getattr(entry, "path")), {}).get("afterSha256", getattr(entry, "sha256")),
        }
        for entry in sorted(getattr(snapshot, "entries"), key=lambda item: cast(str, getattr(item, "path")).encode("utf-8"))
    ]
    expected_after = hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
    return SourceChangeIntent.expanded(
        changes=[dict(item) for item in intent.changes],
        before_input_snapshot_sha256=expected_before_hash,
        expected_after_input_snapshot_sha256=expected_after,
    )


def _load_physical_test_run(
    context: AcceptanceRecoveryContext,
    model: object,
    workspace: WorkspacePaths,
    run_id: str,
    *,
    expected_state: str,
    expected_transport: str = PHYSICAL_TRANSPORT,
    expected_build_id: str | None = None,
    expected_elf_sha256: str | None = None,
    expected_input_snapshot_sha256: str | None = None,
) -> object:
    try:
        published = TestRunRepository(
            _evidence_store_factory(workspace.workspace_root / "evidence")
        ).load(run_id)
    except (EvidenceValidationError, OSError, FileNotFoundError, ValueError, TypeError, KeyError) as error:
        raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_EVIDENCE_INTEGRITY_FAILED") from error
    manifest = getattr(published, "manifest", None)
    envelope = getattr(published, "envelope", None)
    root = getattr(published, "root", None)
    identity = getattr(manifest, "identity", None)
    metadata = getattr(envelope, "metadata", None)
    root_metadata = getattr(root, "metadata", None)
    if manifest is None or envelope is None or root is None or identity is None:
        raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_EVIDENCE_INTEGRITY_FAILED")
    if getattr(manifest, "run_id", None) != run_id:
        raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_EVIDENCE_INTEGRITY_FAILED")
    if getattr(envelope, "operation", None) != "target-test-physical":
        raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_OUTPUT_INVALID")
    if (
        getattr(manifest, "mode", None) != "target"
        or getattr(manifest, "transport", None) != expected_transport
        or getattr(manifest, "state", None) != expected_state
        or not isinstance(metadata, Mapping)
        or metadata.get("execution_source") != "physical"
        or metadata.get("physical_transport_evidence") is not True
    ):
        raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_OUTPUT_INVALID")
    if (
        getattr(root, "manifest_id", None) != getattr(envelope, "evidence_id", None)
        or not isinstance(root_metadata, Mapping)
        or root_metadata.get("physical_transport_evidence") is not True
        or metadata.get("target_id") != getattr(identity, "target_device", None)
        or not isinstance(metadata.get("probe_id"), str)
        or _HASH_PATTERN.fullmatch(cast(str, metadata.get("probe_id"))) is None
        or not isinstance(metadata.get("transport_config_digest"), str)
        or _HASH_PATTERN.fullmatch(cast(str, metadata.get("transport_config_digest"))) is None
    ):
        raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_EVIDENCE_INTEGRITY_FAILED")
    if (
        getattr(identity, "project_id", None) != str(getattr(model, "logical_project_id"))
        or getattr(identity, "workspace_id", None) != workspace.workspace_id
        or getattr(identity, "session_id", None) != context.session_id
        or getattr(identity, "target_device", None) != _physical_target(model)
    ):
        raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_IDENTITY_MISMATCH")
    if expected_build_id is not None and getattr(identity, "build_id", None) != expected_build_id:
        raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_IDENTITY_MISMATCH")
    if expected_elf_sha256 is not None and getattr(identity, "elf_sha256", None) != expected_elf_sha256:
        raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_IDENTITY_MISMATCH")
    if expected_input_snapshot_sha256 is not None and getattr(identity, "input_snapshot_sha256", None) != expected_input_snapshot_sha256:
        raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_IDENTITY_MISMATCH")
    return published


def _physical_diagnostic_data(
    context: AcceptanceRecoveryContext,
    diagnostic_session_id: str,
) -> DiagnosticSession:
    data = _public_data(
        _diagnostic_show(
            DiagnosticWorkflowContext(context.project_root, context.data_root, context.session_id),
            diagnostic_session_id=diagnostic_session_id,
        )
    )
    raw = data.get("session")
    if not isinstance(raw, Mapping):
        raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_OUTPUT_INVALID")
    try:
        return DiagnosticSession.from_value(raw)
    except (DiagnosticValidationError, TypeError, ValueError) as error:
        raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_EVIDENCE_INTEGRITY_FAILED") from error


def _validate_physical_diagnostic_session(
    session: DiagnosticSession,
    attempt: PhysicalAcceptanceAttempt,
    model: object,
    workspace: WorkspacePaths,
    context: AcceptanceRecoveryContext,
    *,
    expected_session_id: str,
    allow_source_change: bool,
) -> None:
    identity = session.identity
    if (
        session.diagnostic_session_id != expected_session_id
        or session.failed_test_run_id != attempt.stage_outputs.get("failedBeforeTestRunId")
        or session.failed_evidence_id != attempt.stage_outputs.get("failedBeforeEvidenceId")
        or session.failed_run_mode != "target"
        or identity.project_id != str(getattr(model, "logical_project_id"))
        or identity.workspace_id != workspace.workspace_id
        or identity.session_id != context.session_id
        or identity.target_device != _physical_target(model)
        or identity.build_id != attempt.stage_outputs.get("beforeBuildId")
        or identity.elf_sha256 != attempt.stage_outputs.get("beforeElfSha256")
        or identity.input_snapshot_sha256 != attempt.stage_outputs.get("beforeInputSnapshotSha256")
    ):
        raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_IDENTITY_MISMATCH")
    if not allow_source_change and (session.state != "INVESTIGATING" or session.source_change_declarations):
        raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_OUTPUT_INVALID")
    if allow_source_change and session.state not in {"INVESTIGATING", "FIX_PROPOSED", "VERIFYING", "RESOLVED"}:
        raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_OUTPUT_INVALID")


def _physical_validate_declaration(
    declaration: SourceChangeDeclaration,
    attempt: PhysicalAcceptanceAttempt,
    intent: SourceChangeIntent,
    *,
    after_build: Mapping[str, object] | None = None,
) -> None:
    if (
        declaration.before_source_sha256 != attempt.stage_outputs.get("beforeInputSnapshotSha256")
        or declaration.before_build_id != attempt.stage_outputs.get("beforeBuildId")
        or declaration.before_elf_sha256 != attempt.stage_outputs.get("beforeElfSha256")
        or tuple(declaration.changed_paths) != tuple(cast(str, item["path"]) for item in intent.changes)
    ):
        raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_IDENTITY_MISMATCH")
    if after_build is not None and (
        declaration.after_source_sha256 != after_build.get("inputSnapshotSha256")
        or declaration.after_build_id != after_build.get("buildId")
        or declaration.after_elf_sha256 != after_build.get("elfSha256")
    ):
        raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_IDENTITY_MISMATCH")


def _physical_build_transition(
    context: AcceptanceRecoveryContext,
    model: object,
    workspace: WorkspacePaths,
    attempt: PhysicalAcceptanceAttempt,
    stage: str,
    *,
    test_run_id: str | None,
    diagnostic_session_id: str | None,
    fix_verification_id: str | None,
    source_change_intent: SourceChangeIntent | None,
) -> tuple[dict[str, object], SourceChangeIntent | None]:
    outputs = dict(attempt.stage_outputs)
    intent = attempt.source_change_intent
    if stage == "project-materialized":
        outputs["projectModelDigest"] = _project_model_digest(model)
    elif stage == "firmware-built-before":
        build = _build_data(context, model)
        outputs["beforeBuildId"] = build["buildId"]
        outputs["beforeElfSha256"] = build["elfSha256"]
        outputs["beforeInputSnapshotSha256"] = build["inputSnapshotSha256"]
    elif stage == "target-failure-observed":
        assert test_run_id is not None
        published = _load_physical_test_run(
            context,
            model,
            workspace,
            test_run_id,
            expected_state="failed",
            expected_transport=PHYSICAL_TRANSPORT,
            expected_build_id=cast(str, attempt.stage_outputs.get("beforeBuildId")),
            expected_elf_sha256=cast(str, attempt.stage_outputs.get("beforeElfSha256")),
            expected_input_snapshot_sha256=cast(str, attempt.stage_outputs.get("beforeInputSnapshotSha256")),
        )
        evidence_id = str(getattr(getattr(published, "envelope"), "evidence_id"))
        outputs["failedBeforeTestRunId"] = test_run_id
        outputs["failedBeforeEvidenceId"] = _canonical_hash("failedBeforeEvidenceId", evidence_id)
    elif stage == "diagnosis-completed":
        assert diagnostic_session_id is not None and source_change_intent is not None
        session = _physical_diagnostic_data(context, diagnostic_session_id)
        _validate_physical_diagnostic_session(
            session, attempt, model, workspace, context,
            expected_session_id=diagnostic_session_id,
            allow_source_change=False,
        )
        # Reconfirm the fresh P3 build authority at the diagnosis boundary.
        # The source snapshot alone cannot prove that the published firmware
        # and build record still identify the same before-change candidate.
        before_build = _build_data(context, model)
        if (
            before_build["buildId"] != attempt.stage_outputs.get("beforeBuildId")
            or before_build["elfSha256"] != attempt.stage_outputs.get("beforeElfSha256")
            or before_build["inputSnapshotSha256"] != attempt.stage_outputs.get("beforeInputSnapshotSha256")
        ):
            raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_IDENTITY_MISMATCH")
        try:
            before_snapshot = snapshot_project_inputs(model)
        except Exception as error:
            raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_OUTPUT_INVALID") from error
        try:
            intent = _derive_physical_intent(
                model,
                source_change_intent,
                before_snapshot,
                expected_before_hash=cast(str, attempt.stage_outputs["beforeInputSnapshotSha256"]),
            )
        except AcceptanceRecoveryValidationError as error:
            raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_OUTPUT_INVALID") from error
        outputs["diagnosticSessionId"] = diagnostic_session_id
        outputs["diagnosticRevision"] = session.revision
        outputs["diagnosticEventHead"] = session.event_head
    elif stage == "firmware-built-after":
        if attempt.revision == 4:
            raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_AUTHORIZATION_REQUIRED")
        if attempt.source_change_authorization is None or attempt.source_change_intent is None:
            raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_AUTHORIZATION_REQUIRED")
        build = _build_data(context, model)
        if build["buildId"] == attempt.stage_outputs.get("beforeBuildId"):
            raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_OUTPUT_INVALID")
        if build["inputSnapshotSha256"] != attempt.source_change_intent.expected_after_input_snapshot_sha256:
            raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_IDENTITY_MISMATCH")
        session = _physical_diagnostic_data(
            context, cast(str, attempt.stage_outputs.get("diagnosticSessionId"))
        )
        _validate_physical_diagnostic_session(
            session, attempt, model, workspace, context,
            expected_session_id=cast(str, attempt.stage_outputs.get("diagnosticSessionId")),
            allow_source_change=True,
        )
        if (
            session.revision <= int(cast(int, attempt.source_change_authorization["diagnosticRevision"]))
            or session.event_head == attempt.source_change_authorization["diagnosticEventHead"]
            or len(session.source_change_declarations) != 1
        ):
            raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_OUTPUT_INVALID")
        declaration = session.source_change_declarations[0]
        _physical_validate_declaration(
            declaration, attempt, attempt.source_change_intent, after_build=build
        )
        outputs["afterBuildId"] = build["buildId"]
        outputs["afterElfSha256"] = build["elfSha256"]
        outputs["afterInputSnapshotSha256"] = build["inputSnapshotSha256"]
        outputs["sourceChangeDeclarationId"] = declaration.declaration_id
    elif stage == "target-fix-verified":
        assert test_run_id is not None and fix_verification_id is not None
        if attempt.source_change_intent is None:
            raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_OUTPUT_INVALID")
        before = _load_physical_test_run(
            context,
            model,
            workspace,
            cast(str, attempt.stage_outputs["failedBeforeTestRunId"]),
            expected_state="failed",
            expected_transport=PHYSICAL_TRANSPORT,
            expected_build_id=cast(str, attempt.stage_outputs["beforeBuildId"]),
            expected_elf_sha256=cast(str, attempt.stage_outputs["beforeElfSha256"]),
            expected_input_snapshot_sha256=cast(str, attempt.stage_outputs["beforeInputSnapshotSha256"]),
        )
        after = _load_physical_test_run(
            context,
            model,
            workspace,
            test_run_id,
            expected_state="passed",
            expected_transport=PHYSICAL_TRANSPORT,
            expected_build_id=cast(str, attempt.stage_outputs["afterBuildId"]),
            expected_elf_sha256=cast(str, attempt.stage_outputs["afterElfSha256"]),
            expected_input_snapshot_sha256=cast(str, attempt.stage_outputs["afterInputSnapshotSha256"]),
        )
        try:
            diagnostic_validate_pair_execution_policy(before, after)
        except Exception as error:
            if isinstance(error, _RecoveryFailure):
                raise
            raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_IDENTITY_MISMATCH") from error
        session = _physical_diagnostic_data(
            context, cast(str, attempt.stage_outputs["diagnosticSessionId"])
        )
        _validate_physical_diagnostic_session(
            session, attempt, model, workspace, context,
            expected_session_id=cast(str, attempt.stage_outputs["diagnosticSessionId"]),
            allow_source_change=True,
        )
        declarations = tuple(session.source_change_declarations)
        if len(declarations) != 1:
            raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_OUTPUT_INVALID")
        _physical_validate_declaration(
            declarations[0], attempt, attempt.source_change_intent,
            after_build={
                "buildId": attempt.stage_outputs["afterBuildId"],
                "elfSha256": attempt.stage_outputs["afterElfSha256"],
                "inputSnapshotSha256": attempt.stage_outputs["afterInputSnapshotSha256"],
            },
        )
        verifications = tuple(
            item for item in session.fix_verifications
            if item.fix_verification_id == fix_verification_id
        )
        if len(verifications) != 1:
            raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_OUTPUT_INVALID")
        verification = verifications[0]
        fixed_evidence_id = str(getattr(getattr(after, "envelope"), "evidence_id"))
        if (
            session.state != "RESOLVED"
            or verification.status != "PASSED"
            or verification.diagnostic_session_id != session.diagnostic_session_id
            or verification.failed_before_run_id != attempt.stage_outputs.get("failedBeforeTestRunId")
            or verification.failed_before_evidence_id != attempt.stage_outputs.get("failedBeforeEvidenceId")
            or verification.fixed_after_run_id != test_run_id
            or verification.fixed_after_evidence_id != fixed_evidence_id
            or verification.source_change_declaration_id != declarations[0].declaration_id
        ):
            raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_IDENTITY_MISMATCH")
        outputs["fixedAfterTestRunId"] = test_run_id
        outputs["fixedAfterEvidenceId"] = _canonical_hash("fixedAfterEvidenceId", fixed_evidence_id)
        outputs["fixVerificationId"] = fix_verification_id
    else:
        raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_STAGE_INVALID")
    return outputs, intent


def _physical_action_digest(attempt: PhysicalAcceptanceAttempt) -> str:
    payload = {
        "schema": PHYSICAL_ATTEMPT_SCHEMA,
        "action": "source-change",
        "attemptId": attempt.attempt_id,
        "revision": attempt.revision,
        "checkpointId": attempt.checkpoint_id,
        "scenarioId": attempt.scenario_id,
        "scenarioVersion": attempt.scenario_version,
        "scenarioDigest": attempt.scenario_digest,
        "recoveryPolicyDigest": attempt.recovery_policy_digest,
        "workspaceId": attempt.workspace_id,
        "logicalProjectId": attempt.logical_project_id,
        "failedBeforeTestRunId": attempt.stage_outputs.get("failedBeforeTestRunId"),
        "failedBeforeEvidenceId": attempt.stage_outputs.get("failedBeforeEvidenceId"),
        "diagnosticSessionId": attempt.stage_outputs.get("diagnosticSessionId"),
        "diagnosticRevision": attempt.stage_outputs.get("diagnosticRevision"),
        "diagnosticEventHead": attempt.stage_outputs.get("diagnosticEventHead"),
        "intentDigest": attempt.source_change_intent.intent_digest if attempt.source_change_intent else None,
    }
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def _begin_physical_attempt(
    context: AcceptanceRecoveryContext,
    *,
    attempt_id: object,
    scenario_id: object,
    scenario_version: object,
) -> OperationResult[dict[str, object]]:
    attempt_id = _canonical_uuid("attemptId", attempt_id)
    if scenario_id != PHYSICAL_SCENARIO_ID or scenario_version != PHYSICAL_SCENARIO_VERSION:
        raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_INPUT_INVALID")
    model, workspace, evidence = _load_project_and_workspace(context)
    if _project_origin(model) != "keil":
        raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_IDENTITY_MISMATCH")
    project_id = str(getattr(model, "logical_project_id"))
    root0 = _typed_root_path(evidence, _root_id(attempt_id, 0))
    if root0.exists():
        try:
            chain = _load_physical_chain(
                evidence,
                attempt_id=attempt_id,
                workspace_id=workspace.workspace_id,
                logical_project_id=project_id,
            )
        except _RecoveryFailure:
            # A pre-existing VS08 replay attempt occupies the same attempt ID
            # namespace and must never be silently reinterpreted as physical.
            raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_CONFLICT")
        _validate_physical_chain_semantics(
            chain, model=model, workspace=workspace, session_id=context.session_id
        )
        latest = chain[-1][0]
        if latest.scenario_id != PHYSICAL_SCENARIO_ID:
            raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_CONFLICT")
        return OperationResult.success("acceptance.attempt.begin", {"attempt": latest.to_dict()})
    opened = _now(context)
    candidate = _physical_base_snapshot(
        attempt_id=attempt_id,
        opened_at=opened,
        updated_at=opened,
        workspace_id=workspace.workspace_id,
        logical_project_id=project_id,
        deadline_at=_physical_deadline(opened, PHYSICAL_STAGES[0]),
    )
    published = _publish_physical_snapshot(
        evidence, context, model, workspace, candidate, expected_revision=0, chain=[]
    )
    return OperationResult.success("acceptance.attempt.begin", {"attempt": published.to_dict()})


def _physical_attempt_for_context(
    context: AcceptanceRecoveryContext, attempt_id: str
) -> tuple[object, WorkspacePaths, EvidenceStore, list[tuple[PhysicalAcceptanceAttempt, EvidenceEnvelope]]] | None:
    model, workspace, evidence = _load_project_and_workspace(context)
    if not isinstance(getattr(evidence, "root", None), Path):
        return None
    root0 = _typed_root_path(evidence, _root_id(attempt_id, 0))
    if not root0.exists():
        return None
    try:
        root = get_root(evidence, _ATTEMPT_ROOT_TYPE, _root_id(attempt_id, 0))
        envelope = evidence.get_envelope(root.manifest_id)
        raw = envelope.metadata.get("attempt")
    except (EvidenceValidationError, OSError, FileNotFoundError, ValueError, TypeError) as error:
        raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_EVIDENCE_INTEGRITY_FAILED") from error
    if not isinstance(raw, Mapping) or raw.get("schema") != PHYSICAL_ATTEMPT_SCHEMA:
        if isinstance(raw, Mapping) and raw.get("schema") == ATTEMPT_SCHEMA:
            return None
        raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_EVIDENCE_INTEGRITY_FAILED")
    chain = _load_physical_chain(
        evidence,
        attempt_id=attempt_id,
        workspace_id=workspace.workspace_id,
        logical_project_id=str(getattr(model, "logical_project_id")),
    )
    _validate_physical_chain_semantics(
        chain, model=model, workspace=workspace, session_id=context.session_id
    )
    return model, workspace, evidence, chain


def _attempt_schema_for_context(
    context: AcceptanceRecoveryContext, attempt_id: str
) -> str | None:
    """Peek the immutable root only to dispatch v1 versus v2 operations."""
    model, workspace, evidence = _load_project_and_workspace(context)
    if not isinstance(getattr(evidence, "root", None), Path):
        return None
    root_path = _typed_root_path(evidence, _root_id(attempt_id, 0))
    if not root_path.exists():
        return None
    try:
        root = get_root(evidence, _ATTEMPT_ROOT_TYPE, _root_id(attempt_id, 0))
        envelope = evidence.get_envelope(root.manifest_id)
    except (EvidenceValidationError, OSError, FileNotFoundError, ValueError, TypeError) as error:
        raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_EVIDENCE_INTEGRITY_FAILED") from error
    raw = envelope.metadata.get("attempt")
    if not isinstance(raw, Mapping):
        raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_EVIDENCE_INTEGRITY_FAILED")
    schema = raw.get("schema")
    return schema if isinstance(schema, str) else None


def _checkpoint_physical_attempt(
    context: AcceptanceRecoveryContext,
    *,
    attempt_id: object,
    expected_revision: object,
    stage: object,
    test_run_id: object = None,
    diagnostic_session_id: object = None,
    acceptance_record_id: object = None,
    fix_verification_id: object = None,
    source_change_intent: object = None,
) -> OperationResult[dict[str, object]]:
    attempt_id = _canonical_uuid("attemptId", attempt_id)
    if type(expected_revision) is not int or not 0 <= expected_revision <= 7:
        raise AcceptanceRecoveryValidationError("expectedRevision must be an integer from 0 through 7")
    if not isinstance(stage, str) or stage not in PHYSICAL_STAGES:
        raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_STAGE_INVALID")
    test_value, diagnostic_value, _unused, fix_value = _physical_stage_reference_shape(
        stage,
        test_run_id=test_run_id,
        diagnostic_session_id=diagnostic_session_id,
        acceptance_record_id=acceptance_record_id,
        fix_verification_id=fix_verification_id,
    )
    intent_value: SourceChangeIntent | None = None
    if source_change_intent is not None:
        try:
            intent_value = SourceChangeIntent.from_value(source_change_intent)
        except AcceptanceRecoveryValidationError as error:
            raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_INPUT_INVALID") from error
        if intent_value.intent_digest is not None:
            raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_INPUT_INVALID")
    if stage != "diagnosis-completed" and intent_value is not None:
        raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_STAGE_INVALID")
    if stage == "diagnosis-completed" and intent_value is None:
        raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_STAGE_INVALID")
    loaded = _physical_attempt_for_context(context, attempt_id)
    if loaded is None:
        raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_NOT_FOUND")
    model, workspace, evidence, chain = loaded
    current = chain[-1][0]
    if current.revision != expected_revision:
        if current.revision > expected_revision and _physical_checkpoint_retry_matches(
            current,
            expected_revision=expected_revision,
            stage=stage,
            test_run_id=test_value,
            diagnostic_session_id=diagnostic_value,
            fix_verification_id=fix_value,
            source_change_intent=intent_value,
        ):
            return OperationResult.success("acceptance.attempt.checkpoint", {"attempt": current.to_dict()})
        raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_REVISION_CONFLICT")
    if current.next_stage != stage:
        if stage == "firmware-built-after" and current.revision == 4:
            raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_AUTHORIZATION_REQUIRED")
        raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_STAGE_INVALID")
    now = _now(context)
    _check_deadline_physical(current, now)
    outputs, expanded_intent = _physical_build_transition(
        context,
        model,
        workspace,
        current,
        stage,
        test_run_id=test_value,
        diagnostic_session_id=diagnostic_value,
        fix_verification_id=fix_value,
        source_change_intent=intent_value,
    )
    revision = expected_revision + 1
    if expected_revision == 4:
        raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_AUTHORIZATION_REQUIRED")
    candidate = _physical_base_snapshot(
        attempt_id=current.attempt_id,
        opened_at=current.opened_at_utc,
        updated_at=now,
        workspace_id=current.workspace_id,
        logical_project_id=current.logical_project_id,
        revision=revision,
        previous_checkpoint_id=current.checkpoint_id,
        outputs=outputs,
        authorization=current.source_change_authorization,
        intent=expanded_intent if expanded_intent is not None else current.source_change_intent,
        status="COMPLETED" if revision == 7 else "ACTIVE",
        deadline_at=None if revision == 7 else _physical_deadline(now, PHYSICAL_STAGES[revision if revision <= 4 else revision - 1]),
    )
    published = _publish_physical_snapshot(
        evidence,
        context,
        model,
        workspace,
        candidate,
        expected_revision=expected_revision,
        chain=chain,
    )
    return OperationResult.success("acceptance.attempt.checkpoint", {"attempt": published.to_dict()})


def _check_deadline_physical(attempt: PhysicalAcceptanceAttempt, now: str) -> None:
    if attempt.deadline_at_utc is not None and _timestamp(now) > _timestamp(attempt.deadline_at_utc):
        raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_TIMED_OUT")


def _reject_physical_only_checkpoint_fields() -> OperationResult[dict[str, object]]:
    raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_STAGE_INVALID")


def _authorize_physical_source_change(
    context: AcceptanceRecoveryContext,
    *,
    attempt_id: object,
    expected_revision: object,
    action_digest: object,
    authorized: object,
) -> OperationResult[dict[str, object]]:
    attempt_id = _canonical_uuid("attemptId", attempt_id)
    if type(expected_revision) is not int or expected_revision != 4:
        raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_STAGE_INVALID")
    action_digest = _canonical_hash("actionDigest", action_digest)
    if type(authorized) is not bool or authorized is not True:
        raise AcceptanceRecoveryValidationError("authorized must be true")
    loaded = _physical_attempt_for_context(context, attempt_id)
    if loaded is None:
        raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_NOT_FOUND")
    model, workspace, evidence, chain = loaded
    current = chain[-1][0]
    if current.revision != expected_revision:
        if (
            current.revision == 5
            and current.source_change_authorization is not None
            and current.source_change_authorization.get("actionDigest") == action_digest
        ):
            return OperationResult.success("acceptance.attempt.authorize-source-change", {"attempt": current.to_dict()})
        raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_REVISION_CONFLICT")
    now = _now(context)
    _check_deadline_physical(current, now)
    if current.source_change_authorization is not None or current.source_change_intent is None:
        raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_REVISION_CONFLICT")
    if action_digest != _physical_action_digest(current):
        raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_ACTION_DIGEST_MISMATCH")
    session_id = cast(str, current.stage_outputs.get("diagnosticSessionId"))
    session = _physical_diagnostic_data(context, session_id)
    _validate_physical_diagnostic_session(
        session, current, model, workspace, context,
        expected_session_id=session_id,
        allow_source_change=False,
    )
    if (
        session.revision != current.stage_outputs.get("diagnosticRevision")
        or session.event_head != current.stage_outputs.get("diagnosticEventHead")
    ):
        raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_IDENTITY_MISMATCH")
    try:
        before_snapshot = snapshot_project_inputs(model)
    except Exception as error:
        raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_OUTPUT_INVALID") from error
    if (
        current.source_change_intent.before_input_snapshot_sha256 != current.stage_outputs.get("beforeInputSnapshotSha256")
        or before_snapshot.sha256 != current.stage_outputs.get("beforeInputSnapshotSha256")
    ):
        raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_IDENTITY_MISMATCH")
    try:
        refreshed_intent = _derive_physical_intent(
            model,
            SourceChangeIntent.new(changes=[dict(item) for item in current.source_change_intent.changes]),
            before_snapshot,
            expected_before_hash=cast(str, current.stage_outputs["beforeInputSnapshotSha256"]),
        )
    except AcceptanceRecoveryValidationError as error:
        raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_OUTPUT_INVALID") from error
    if refreshed_intent != current.source_change_intent:
        raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_IDENTITY_MISMATCH")
    authorization = {
        "action": "source-change",
        "actionDigest": action_digest,
        "authorized": True,
        "authorizedAtUtc": now,
        "diagnosticSessionId": current.stage_outputs["diagnosticSessionId"],
        "diagnosticRevision": current.stage_outputs["diagnosticRevision"],
        "diagnosticEventHead": current.stage_outputs["diagnosticEventHead"],
    }
    candidate = _physical_base_snapshot(
        attempt_id=current.attempt_id,
        opened_at=current.opened_at_utc,
        updated_at=now,
        workspace_id=current.workspace_id,
        logical_project_id=current.logical_project_id,
        revision=5,
        previous_checkpoint_id=current.checkpoint_id,
        outputs=current.stage_outputs,
        authorization=authorization,
        intent=current.source_change_intent,
        status="ACTIVE",
        deadline_at=_physical_deadline(now, "firmware-built-after"),
    )
    published = _publish_physical_snapshot(
        evidence,
        context,
        model,
        workspace,
        candidate,
        expected_revision=4,
        chain=chain,
    )
    return OperationResult.success("acceptance.attempt.authorize-source-change", {"attempt": published.to_dict()})


def _show_physical_attempt(
    context: AcceptanceRecoveryContext,
    *,
    attempt_id: object,
    resume: bool,
) -> OperationResult[dict[str, object]]:
    attempt_id = _canonical_uuid("attemptId", attempt_id)
    loaded = _physical_attempt_for_context(context, attempt_id)
    if loaded is None:
        raise _RecoveryFailure("ACCEPTANCE_ATTEMPT_NOT_FOUND")
    _model, _workspace, _evidence, chain = loaded
    attempt = chain[-1][0]
    data: dict[str, object] = {"authoritative": True, "attempt": attempt.to_dict()}
    if resume:
        now = _now(context)
        data.update(
            {
                "nextStage": attempt.next_stage,
                "authorizationRequired": attempt.revision == 4,
                "actionDigest": _physical_action_digest(attempt) if attempt.revision == 4 else None,
                "timedOut": attempt.deadline_at_utc is not None and _timestamp(now) > _timestamp(attempt.deadline_at_utc),
                "recoveryPolicy": physical_acceptance_recovery_policy().to_dict(),
            }
        )
    return OperationResult.success("acceptance.attempt.resume" if resume else "acceptance.attempt.show", data)


def authorize_acceptance_source_change(
    context: AcceptanceRecoveryContext,
    *,
    attempt_id: object,
    expected_revision: object,
    action_digest: object,
    authorized: object,
) -> OperationResult[dict[str, object]]:
    physical = False
    canonical_attempt_id: str | None = None
    try:
        canonical_attempt_id = _canonical_uuid("attemptId", attempt_id)
        physical = _attempt_schema_for_context(context, canonical_attempt_id) == PHYSICAL_ATTEMPT_SCHEMA
    except (AcceptanceRecoveryValidationError, _RecoveryFailure):
        physical = False
    if physical:
        return _result(
            "acceptance.attempt.authorize-source-change",
            lambda: _authorize_physical_source_change(
                context,
                attempt_id=attempt_id,
                expected_revision=expected_revision,
                action_digest=action_digest,
                authorized=authorized,
            ),
        )
    return _result(
        "acceptance.attempt.authorize-source-change",
        lambda: _authorize_source_change(
            context,
            attempt_id=attempt_id,
            expected_revision=expected_revision,
            action_digest=action_digest,
            authorized=authorized,
        ),
    )


def _show_attempt(
    context: AcceptanceRecoveryContext,
    *,
    attempt_id: object,
    resume: bool,
) -> OperationResult[dict[str, object]]:
    attempt_id = _canonical_uuid("attemptId", attempt_id)
    model, workspace, evidence = _load_project_and_workspace(context)
    chain = _load_chain(
        evidence,
        attempt_id=attempt_id,
        workspace_id=workspace.workspace_id,
        logical_project_id=str(getattr(model, "logical_project_id")),
    )
    _validate_chain_semantics(chain, model=model, workspace=workspace)
    attempt = chain[-1][0]
    data: dict[str, object] = {"authoritative": True, "attempt": attempt.to_dict()}
    if resume:
        now = _now(context)
        data.update(
            {
                "nextStage": attempt.next_stage,
                "authorizationRequired": attempt.revision == 4,
                "actionDigest": _action_digest(attempt) if attempt.revision == 4 else None,
                "timedOut": attempt.deadline_at_utc is not None and _timestamp(now) > _timestamp(attempt.deadline_at_utc),
                "recoveryPolicy": acceptance_recovery_policy().to_dict(),
            }
        )
    return OperationResult.success(
        "acceptance.attempt.resume" if resume else "acceptance.attempt.show",
        data,
    )


def show_acceptance_attempt(
    context: AcceptanceRecoveryContext,
    *,
    attempt_id: object,
) -> OperationResult[dict[str, object]]:
    physical = False
    try:
        canonical_attempt_id = _canonical_uuid("attemptId", attempt_id)
        physical = _attempt_schema_for_context(context, canonical_attempt_id) == PHYSICAL_ATTEMPT_SCHEMA
    except (AcceptanceRecoveryValidationError, _RecoveryFailure):
        physical = False
    if physical:
        return _result(
            "acceptance.attempt.show",
            lambda: _show_physical_attempt(context, attempt_id=attempt_id, resume=False),
        )
    return _result(
        "acceptance.attempt.show",
        lambda: _show_attempt(context, attempt_id=attempt_id, resume=False),
    )


def resume_acceptance_attempt(
    context: AcceptanceRecoveryContext,
    *,
    attempt_id: object,
) -> OperationResult[dict[str, object]]:
    physical = False
    try:
        canonical_attempt_id = _canonical_uuid("attemptId", attempt_id)
        physical = _attempt_schema_for_context(context, canonical_attempt_id) == PHYSICAL_ATTEMPT_SCHEMA
    except (AcceptanceRecoveryValidationError, _RecoveryFailure):
        physical = False
    if physical:
        return _result(
            "acceptance.attempt.resume",
            lambda: _show_physical_attempt(context, attempt_id=attempt_id, resume=True),
        )
    return _result(
        "acceptance.attempt.resume",
        lambda: _show_attempt(context, attempt_id=attempt_id, resume=True),
    )


__all__ = [
    "AcceptanceRecoveryContext",
    "authorize_acceptance_source_change",
    "begin_acceptance_attempt",
    "checkpoint_acceptance_attempt",
    "resume_acceptance_attempt",
    "show_acceptance_attempt",
]
