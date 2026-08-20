"""Application workflows for the managed Host testing evidence boundary."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import re

from stm32_toolkit.build.identity import (
    GitEvidence,
    InputSnapshot,
    git_evidence,
    snapshot_project_inputs,
)
from stm32_toolkit.build.model import BuildError
from stm32_toolkit.evidence import (
    EVIDENCE_CORRUPT,
    EVIDENCE_INVALID,
    EVIDENCE_LIMIT_EXCEEDED,
    EVIDENCE_PATH_UNSAFE,
    EvidenceIdentityContext,
    EvidenceValidationError,
)
from stm32_toolkit.evidence.store import EvidenceStore
from stm32_toolkit.paths import WorkspacePaths
from stm32_toolkit.project_model import ProjectManifestError, load_project_model
from stm32_toolkit.result import OperationResult
from stm32_toolkit.testing.host import HostTestRunner
from stm32_toolkit.testing.model import (
    TestProtocolError,
    host_target_device,
)
from stm32_toolkit.testing.publication import TestRunPublisher, TestRunRepository


_DISCOVER_OPERATION = "test.host.discover"
_RUN_OPERATION = "test.host.run"
_SHOW_OPERATION = "test.show"
_DIGEST = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class TestingWorkflowContext:
    project_root: Path
    data_root: Path
    session_id: str


@dataclass(frozen=True)
class _WorkflowState:
    model: object
    host_config: object
    workspace: WorkspacePaths
    identity: EvidenceIdentityContext | None
    evidence_store: EvidenceStore
    results_root: Path


class _WorkflowFailure(Exception):
    """Internal typed failure used for context construction boundaries."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


# These are deliberately narrow seams for the fixed construction/read points
# of this module.  They are not a general dependency-injection facility.
_load_project_model = load_project_model
_snapshot_project_inputs = snapshot_project_inputs
_git_evidence = git_evidence
_host_runner_factory = HostTestRunner
_evidence_store_factory = EvidenceStore
_publisher_factory = TestRunPublisher
_repository_factory = TestRunRepository


_PUBLIC_MESSAGES = {
    EVIDENCE_INVALID: "Evidence is invalid.",
    EVIDENCE_CORRUPT: "Evidence is corrupt.",
    EVIDENCE_PATH_UNSAFE: "Evidence path is unsafe.",
    EVIDENCE_LIMIT_EXCEEDED: "Evidence limit exceeded.",
    "PROJECT_NOT_CONFIGURED": "Project is not configured.",
    "PROJECT_JSON_INVALID": "Project manifest JSON is invalid.",
    "PROJECT_SCHEMA_INVALID": "Project manifest schema is invalid.",
    "PROJECT_SCHEMA_VERSION_UNSUPPORTED": "Project manifest schema version is unsupported.",
    "TEST_NO_CASES": "No test cases were discovered.",
    "TEST_CASE_NOT_FOUND": "A requested test case was not discovered.",
    "TEST_INVENTORY_CHANGED": "The test inventory changed.",
    "TEST_PROTOCOL_INVALID": "Test protocol is invalid.",
    "TEST_TIMEOUT": "Test operation timed out.",
    "TEST_TRANSPORT_UNAVAILABLE": "Target test transport is unavailable.",
    "TEST_AUTHORIZATION_INVALID": "Target test authorization is invalid.",
    "TEST_IDENTITY_MISMATCH": "Test identity does not match.",
    "TEST_EXECUTION_FAILED": "Test execution failed.",
}

_TEST_CODE_MAP = {
    "TEST_PROCESS_TIMEOUT": "TEST_TIMEOUT",
    "TEST_PROCESS_ERROR": "TEST_EXECUTION_FAILED",
    "TEST_PROCESS_FAILED": "TEST_EXECUTION_FAILED",
    "TEST_FLASH_FAILED": "TEST_EXECUTION_FAILED",
    "TEST_DUPLICATE_CASE": "TEST_PROTOCOL_INVALID",
    "TEST_ENVIRONMENT_INVALID": "TEST_PROTOCOL_INVALID",
    "TEST_DISCOVERY_INVALID": "TEST_PROTOCOL_INVALID",
    "TEST_EVENT_PAYLOAD_INVALID": "TEST_PROTOCOL_INVALID",
    "TEST_EVENT_SEQUENCE_INVALID": "TEST_PROTOCOL_INVALID",
    "TEST_EXIT_MISMATCH": "TEST_PROTOCOL_INVALID",
    "TEST_NATIVE_RESULT_INVALID": "TEST_PROTOCOL_INVALID",
    "TEST_FRAME_CRC_INVALID": "TEST_PROTOCOL_INVALID",
    "TEST_FRAME_VERSION_INVALID": "TEST_PROTOCOL_INVALID",
    "TEST_STREAM_INCOMPLETE": "TEST_PROTOCOL_INVALID",
    "TEST_FRAME_TOO_LARGE": EVIDENCE_LIMIT_EXCEEDED,
    "TEST_FRAME_RECOVERY_LIMIT": EVIDENCE_LIMIT_EXCEEDED,
    "TEST_STREAM_TOO_LARGE": EVIDENCE_LIMIT_EXCEEDED,
    "TEST_PROCESS_OUTPUT_LIMIT": EVIDENCE_LIMIT_EXCEEDED,
    "TEST_RESULTS_UNSAFE": EVIDENCE_PATH_UNSAFE,
}


def _failure(operation: str, code: str) -> OperationResult[None]:
    public_code = code if code in _PUBLIC_MESSAGES else "TEST_PROTOCOL_INVALID"
    return OperationResult.failure(
        operation,
        public_code,
        _PUBLIC_MESSAGES[public_code],
        {},
    )


def _project_failure(operation: str, error: BaseException) -> OperationResult[None]:
    code = getattr(error, "code", "PROJECT_NOT_CONFIGURED")
    if code not in {
        "PROJECT_NOT_CONFIGURED",
        "PROJECT_JSON_INVALID",
        "PROJECT_SCHEMA_INVALID",
        "PROJECT_SCHEMA_VERSION_UNSUPPORTED",
    }:
        code = "PROJECT_NOT_CONFIGURED"
    return _failure(operation, code)


def _test_failure(operation: str, error: TestProtocolError) -> OperationResult[None]:
    code = _TEST_CODE_MAP.get(error.code, error.code)
    return _failure(operation, code)


def _evidence_failure(operation: str, error: EvidenceValidationError) -> OperationResult[None]:
    return _failure(operation, error.code)


def _exception_result(operation: str, error: BaseException) -> OperationResult[None]:
    if isinstance(error, _WorkflowFailure):
        return _failure(operation, error.code)
    if isinstance(error, EvidenceValidationError):
        return _evidence_failure(operation, error)
    if isinstance(error, TestProtocolError):
        return _test_failure(operation, error)
    if isinstance(error, ProjectManifestError):
        return _project_failure(operation, error)
    if isinstance(error, BuildError):
        # Input/Git identity cannot be established for this application
        # context; the public boundary intentionally does not expose build
        # domain details or their paths.
        return _failure(operation, "TEST_IDENTITY_MISMATCH")
    if isinstance(error, (OSError, ValueError, TypeError)):
        return _failure(operation, "PROJECT_NOT_CONFIGURED")
    if isinstance(error, RuntimeError):
        # A native execution failure without a lower-level typed reason is
        # still a stable public test execution failure.
        return _failure(operation, "TEST_EXECUTION_FAILED")
    raise error


def _configured_workspace(context: TestingWorkflowContext) -> tuple[object, WorkspacePaths]:
    if not isinstance(context, TestingWorkflowContext):
        raise _WorkflowFailure("PROJECT_NOT_CONFIGURED")
    try:
        model = _load_project_model(context.project_root)
    except ProjectManifestError:
        raise
    except (AttributeError, OSError, TypeError, ValueError) as error:
        raise _WorkflowFailure("PROJECT_NOT_CONFIGURED") from error
    if (
        getattr(model, "schema_version", None) != 3
        or getattr(model, "testing", None) is None
        or getattr(model.testing, "host", None) is None
    ):
        raise _WorkflowFailure("PROJECT_NOT_CONFIGURED")
    try:
        workspace = WorkspacePaths.from_roots(
            context.data_root,
            context.project_root,
            model.logical_project_id,
            context.session_id,
        )
        workspace.ensure()
    except (AttributeError, OSError, TypeError, ValueError) as error:
        raise _WorkflowFailure("PROJECT_NOT_CONFIGURED") from error
    return model, workspace


def _make_state(
    context: TestingWorkflowContext,
    *,
    with_identity: bool,
) -> _WorkflowState:
    model, workspace = _configured_workspace(context)
    identity: EvidenceIdentityContext | None = None
    if with_identity:
        try:
            snapshot: InputSnapshot = _snapshot_project_inputs(model)
            git: GitEvidence = _git_evidence(context.project_root)
            identity = EvidenceIdentityContext(
                workspace_id=_workspace_identity_id(workspace, model.logical_project_id),
                project_id=str(model.logical_project_id),
                session_id=workspace.session_id,
                target_device=host_target_device(),
                input_snapshot_sha256=snapshot.sha256,
                git_commit=git.head,
                git_dirty=git.dirty,
            )
        except (EvidenceValidationError, TestProtocolError, BuildError):
            raise
        except (AttributeError, OSError, TypeError, ValueError) as error:
            raise _WorkflowFailure("PROJECT_NOT_CONFIGURED") from error
    evidence_store = _evidence_store_factory(workspace.workspace_root / "evidence")
    return _WorkflowState(
        model=model,
        host_config=model.testing.host,
        workspace=workspace,
        identity=identity,
        evidence_store=evidence_store,
        results_root=workspace.session_root / "test-results",
    )


def _workspace_identity_id(workspace: WorkspacePaths, logical_project_id: object) -> str:
    """Return the complete identity digest for a managed workspace.

    The existing path allocator retains a 24-character directory key.  The
    Evidence identity schema uses complete SHA-256 identifiers, so recover the
    same allocator input without changing the managed directory name.  A
    complete workspace ID supplied by a future path implementation is retained
    verbatim.
    """
    workspace_id = workspace.workspace_id
    if _DIGEST.fullmatch(workspace_id) is not None:
        return workspace_id
    canonical = str(workspace.project_root).replace("\\", "/").casefold()
    return sha256(f"{logical_project_id}\0{canonical}".encode("utf-8")).hexdigest()


def _runner(state: _WorkflowState) -> object:
    return _host_runner_factory(
        project_root=state.workspace.project_root,
        evidence_store=state.evidence_store,
        results_root=state.results_root,
    )


def host_test_discover(context: TestingWorkflowContext) -> OperationResult[dict[str, object]]:
    """Discover Host tests and return the complete inventory plus its artifact."""
    try:
        state = _make_state(context, with_identity=True)
        runner = _runner(state)
        if state.identity is None:
            raise _WorkflowFailure("PROJECT_NOT_CONFIGURED")
        inventory = runner.discover(state.host_config, state.identity)
        artifact = getattr(runner, "discovery_artifact", None)
        if artifact is None:
            raise TestProtocolError("TEST_PROTOCOL_INVALID", "Host discovery artifact is missing")
        return OperationResult.success(
            _DISCOVER_OPERATION,
            {
                "inventory": inventory.to_dict(),
                "discovery_artifact": artifact.to_dict(),
            },
        )
    except Exception as error:
        return _exception_result(_DISCOVER_OPERATION, error)


def _valid_digest(value: object) -> bool:
    return isinstance(value, str) and _DIGEST.fullmatch(value) is not None


def _valid_case_ids(case_ids: object) -> bool:
    if not isinstance(case_ids, tuple):
        return False
    if not all(isinstance(case_id, str) and bool(case_id) for case_id in case_ids):
        return False
    return len(case_ids) == len(set(case_ids))


def host_test_run(
    context: TestingWorkflowContext,
    *,
    inventory_digest: str,
    case_ids: tuple[str, ...],
) -> OperationResult[dict[str, object]]:
    """Freshly discover, bind the supplied inventory digest, run, and publish."""
    try:
        if not _valid_digest(inventory_digest):
            raise TestProtocolError("TEST_PROTOCOL_INVALID", "inventory digest is invalid")
        if not _valid_case_ids(case_ids):
            raise TestProtocolError("TEST_CASE_NOT_FOUND", "requested case IDs are invalid")
        state = _make_state(context, with_identity=True)
        runner = _runner(state)
        if state.identity is None:
            raise _WorkflowFailure("PROJECT_NOT_CONFIGURED")
        inventory = runner.discover(state.host_config, state.identity)
        if inventory.inventory_digest != inventory_digest:
            raise TestProtocolError("TEST_INVENTORY_CHANGED", "inventory digest changed")
        requested = inventory.case_ids if not case_ids else case_ids
        if any(case_id not in inventory.case_ids for case_id in requested):
            raise TestProtocolError("TEST_CASE_NOT_FOUND", "requested test case was not discovered")
        manifest = runner.run(inventory, case_ids)
        publisher = _publisher_factory(
            state.evidence_store,
            state.workspace.project_root,
            state.results_root,
        )
        published = publisher.publish_host(
            manifest,
            inventory_digest=inventory_digest,
        )
        return OperationResult.success(_RUN_OPERATION, published.public_data())
    except Exception as error:
        return _exception_result(_RUN_OPERATION, error)


def test_show(
    context: TestingWorkflowContext,
    *,
    run_id: str,
) -> OperationResult[dict[str, object]]:
    """Reload exactly one authoritative Host run through the repository."""
    try:
        state = _make_state(context, with_identity=False)
        repository = _repository_factory(state.evidence_store)
        published = repository.load(run_id)
        return OperationResult.success(_SHOW_OPERATION, published.public_data(authoritative=True))
    except Exception as error:
        return _exception_result(_SHOW_OPERATION, error)


__all__ = [
    "TestingWorkflowContext",
    "host_test_discover",
    "host_test_run",
    "test_show",
]
