"""Application workflows for the VS-02 failed-run diagnostic boundary."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import re
import secrets
from typing import Callable

from stm32_toolkit.diagnostics import (
    ACTORS,
    DIAGNOSTIC_EVIDENCE_MISSING,
    DIAGNOSTIC_IDENTITY_MISMATCH,
    DIAGNOSTIC_INVALID_EVENT,
    DIAGNOSTIC_REVISION_CONFLICT,
    DiagnosticSession,
    DiagnosticStore,
    DiagnosticValidationError,
    create_event,
)
from stm32_toolkit.evidence import EvidenceValidationError
from stm32_toolkit.evidence.store import EvidenceStore
from stm32_toolkit.paths import WorkspacePaths, require_safe_session_id
from stm32_toolkit.project_model import ProjectManifestError, load_project_model
from stm32_toolkit.result import OperationResult
from stm32_toolkit.testing.model import TestProtocolError
from stm32_toolkit.testing.publication import TestRunRepository


_START_OPERATION = "diagnostic.start"
_SHOW_OPERATION = "diagnostic.show"
_BEGIN_OPERATION = "diagnostic.begin"
_OPERATION_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
_RUN_ID = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
_DIAGNOSTIC_SESSION_ID = re.compile(r"^[0-9a-f]{32}$")
_UTC = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z$")


@dataclass(frozen=True)
class DiagnosticWorkflowContext:
    """Caller context; storage roots are derived from the loaded Project v3 model."""

    project_root: Path
    data_root: Path
    session_id: str


@dataclass(frozen=True)
class _WorkflowState:
    model: object
    workspace: WorkspacePaths
    evidence_store: EvidenceStore
    diagnostic_store: DiagnosticStore
    repository: TestRunRepository


class _WorkflowFailure(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


# These are deliberately narrow seams for deterministic application tests.
_load_project_model = load_project_model
_workspace_paths_factory: Callable[..., WorkspacePaths] = WorkspacePaths.from_roots
_evidence_store_factory = EvidenceStore
_diagnostic_store_factory = DiagnosticStore
_repository_factory = TestRunRepository
_session_id_factory = lambda: secrets.token_hex(16)
_utc_now = lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _failure(operation: str, code: str) -> OperationResult[None]:
    error = DiagnosticValidationError(code)
    return OperationResult.failure(operation, error.code, error.message, {})


def _result(operation: str, action: Callable[[], OperationResult[object]]) -> OperationResult[object]:
    try:
        return action()
    except DiagnosticValidationError as error:
        return OperationResult.failure(operation, error.code, error.message, {})
    except _WorkflowFailure as error:
        return _failure(operation, error.code)


def _validate_context(context: DiagnosticWorkflowContext) -> None:
    if not isinstance(context, DiagnosticWorkflowContext):
        raise _WorkflowFailure(DIAGNOSTIC_IDENTITY_MISMATCH)
    if not isinstance(context.project_root, Path) or not isinstance(context.data_root, Path):
        raise _WorkflowFailure(DIAGNOSTIC_IDENTITY_MISMATCH)
    if not isinstance(context.session_id, str):
        raise _WorkflowFailure(DIAGNOSTIC_IDENTITY_MISMATCH)
    try:
        require_safe_session_id(context.session_id)
    except (TypeError, ValueError):
        raise _WorkflowFailure(DIAGNOSTIC_IDENTITY_MISMATCH) from None


def _validate_operation_id(operation_id: object) -> str:
    if not isinstance(operation_id, str) or _OPERATION_ID.fullmatch(operation_id) is None:
        raise _WorkflowFailure(DIAGNOSTIC_INVALID_EVENT)
    return operation_id


def _validate_run_id(run_id: object) -> str:
    if not isinstance(run_id, str) or _RUN_ID.fullmatch(run_id) is None:
        raise _WorkflowFailure(DIAGNOSTIC_INVALID_EVENT)
    return run_id


def _validate_actor(actor: object) -> str:
    if not isinstance(actor, str) or actor not in ACTORS:
        raise _WorkflowFailure(DIAGNOSTIC_INVALID_EVENT)
    return actor


def _validate_session_id(session_id: object) -> str:
    if not isinstance(session_id, str) or _DIAGNOSTIC_SESSION_ID.fullmatch(session_id) is None:
        raise _WorkflowFailure(DIAGNOSTIC_INVALID_EVENT)
    return session_id


def _validate_revision(expected_revision: object) -> int:
    if type(expected_revision) is not int or expected_revision < 0:
        raise _WorkflowFailure(DIAGNOSTIC_REVISION_CONFLICT)
    return expected_revision


def _make_state(context: DiagnosticWorkflowContext) -> _WorkflowState:
    _validate_context(context)
    try:
        model = _load_project_model(context.project_root)
        if getattr(model, "schema_version", None) != 3:
            raise _WorkflowFailure(DIAGNOSTIC_IDENTITY_MISMATCH)
        logical_project_id = getattr(model, "logical_project_id")
        workspace = _workspace_paths_factory(
            context.data_root,
            context.project_root,
            logical_project_id,
            context.session_id,
        )
    except _WorkflowFailure:
        raise
    except ProjectManifestError as error:
        raise _WorkflowFailure(DIAGNOSTIC_IDENTITY_MISMATCH) from error
    except (OSError, TypeError, ValueError, AttributeError) as error:
        raise _WorkflowFailure(DIAGNOSTIC_IDENTITY_MISMATCH) from error
    evidence_store = _evidence_store_factory(workspace.workspace_root / "evidence")
    diagnostic_store = _diagnostic_store_factory(workspace.diagnostics_root, evidence_store)
    repository = _repository_factory(evidence_store)
    return _WorkflowState(model, workspace, evidence_store, diagnostic_store, repository)


def _require_identity(state: _WorkflowState, identity: object) -> None:
    if (
        getattr(identity, "project_id", None) != str(state.model.logical_project_id)
        or getattr(identity, "workspace_id", None) != state.workspace.workspace_id
    ):
        raise DiagnosticValidationError(DIAGNOSTIC_IDENTITY_MISMATCH)


def _load_failed_run(state: _WorkflowState, failed_test_run_id: str) -> object:
    try:
        return state.repository.load(failed_test_run_id)
    except (EvidenceValidationError, TestProtocolError, OSError, TypeError, ValueError, KeyError, IndexError) as error:
        raise _WorkflowFailure(DIAGNOSTIC_EVIDENCE_MISSING) from error


def _session_data(session: DiagnosticSession, *, authoritative: bool = False) -> dict[str, object]:
    data: dict[str, object] = {"session": session.to_dict()}
    if authoritative:
        data["authoritative"] = True
    return data


def _diagnostic_start(
    context: DiagnosticWorkflowContext,
    *,
    operation_id: object,
    failed_test_run_id: object,
    actor: object,
) -> OperationResult[object]:
    operation_id = _validate_operation_id(operation_id)
    failed_test_run_id = _validate_run_id(failed_test_run_id)
    actor = _validate_actor(actor)
    state = _make_state(context)
    published = _load_failed_run(state, failed_test_run_id)
    manifest = getattr(published, "manifest")
    if getattr(manifest, "mode", None) != "host" or getattr(manifest, "state", None) != "failed":
        raise DiagnosticValidationError(DIAGNOSTIC_INVALID_EVENT)
    identity = getattr(manifest, "identity")
    _require_identity(state, identity)
    envelope = getattr(published, "envelope")
    event = create_event(
        diagnostic_session_id=_new_session_id(),
        operation_id=operation_id,
        sequence=0,
        revision_before=0,
        event_type="session.created",
        occurred_at_utc=_new_timestamp(),
        actor=actor,
        previous_digest=None,
        payload={
            "request": {"failed_test_run_id": failed_test_run_id},
            "result": {
                "failed_evidence_id": str(envelope.evidence_id),
                "identity": identity.to_dict(),
            },
        },
    )
    accepted = state.diagnostic_store.create(event)
    return OperationResult.success(_START_OPERATION, {"session": accepted.session.to_dict()})


def _new_session_id() -> str:
    value = _session_id_factory()
    if not isinstance(value, str) or _DIAGNOSTIC_SESSION_ID.fullmatch(value) is None:
        raise DiagnosticValidationError(DIAGNOSTIC_INVALID_EVENT)
    return value


def _new_timestamp() -> str:
    value = _utc_now()
    if not isinstance(value, str) or _UTC.fullmatch(value) is None:
        raise DiagnosticValidationError(DIAGNOSTIC_INVALID_EVENT)
    return value


def _load_bound_session(state: _WorkflowState, diagnostic_session_id: str) -> DiagnosticSession:
    session = state.diagnostic_store.load(diagnostic_session_id)
    _require_identity(state, session.identity)
    return session


def _diagnostic_show(
    context: DiagnosticWorkflowContext,
    *,
    diagnostic_session_id: object,
) -> OperationResult[object]:
    diagnostic_session_id = _validate_session_id(diagnostic_session_id)
    state = _make_state(context)
    session = _load_bound_session(state, diagnostic_session_id)
    return OperationResult.success(_SHOW_OPERATION, _session_data(session, authoritative=True))


def _diagnostic_begin(
    context: DiagnosticWorkflowContext,
    *,
    operation_id: object,
    diagnostic_session_id: object,
    expected_revision: object,
    actor: object,
) -> OperationResult[object]:
    operation_id = _validate_operation_id(operation_id)
    diagnostic_session_id = _validate_session_id(diagnostic_session_id)
    expected_revision = _validate_revision(expected_revision)
    actor = _validate_actor(actor)
    state = _make_state(context)
    session = _load_bound_session(state, diagnostic_session_id)
    event = create_event(
        diagnostic_session_id=session.diagnostic_session_id,
        operation_id=operation_id,
        sequence=session.revision,
        revision_before=session.revision,
        event_type="investigation.started",
        occurred_at_utc=_new_timestamp(),
        actor=actor,
        previous_digest=session.event_head,
        payload={"request": {}, "result": {}},
    )
    accepted = state.diagnostic_store.append(
        diagnostic_session_id,
        event,
        expected_revision=expected_revision,
    )
    return OperationResult.success(_BEGIN_OPERATION, {"session": accepted.session.to_dict()})


def diagnostic_start(
    context: DiagnosticWorkflowContext,
    *,
    operation_id: str,
    failed_test_run_id: str,
    actor: str = "user",
) -> OperationResult[object]:
    return _result(
        _START_OPERATION,
        lambda: _diagnostic_start(
            context,
            operation_id=operation_id,
            failed_test_run_id=failed_test_run_id,
            actor=actor,
        ),
    )


def diagnostic_show(
    context: DiagnosticWorkflowContext,
    *,
    diagnostic_session_id: str,
) -> OperationResult[object]:
    return _result(
        _SHOW_OPERATION,
        lambda: _diagnostic_show(context, diagnostic_session_id=diagnostic_session_id),
    )


def diagnostic_begin(
    context: DiagnosticWorkflowContext,
    *,
    operation_id: str,
    diagnostic_session_id: str,
    expected_revision: int,
    actor: str = "user",
) -> OperationResult[object]:
    return _result(
        _BEGIN_OPERATION,
        lambda: _diagnostic_begin(
            context,
            operation_id=operation_id,
            diagnostic_session_id=diagnostic_session_id,
            expected_revision=expected_revision,
            actor=actor,
        ),
    )


__all__ = [
    "DiagnosticWorkflowContext",
    "diagnostic_start",
    "diagnostic_show",
    "diagnostic_begin",
]
