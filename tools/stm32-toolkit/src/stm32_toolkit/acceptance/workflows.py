"""Project-bound adapters for immutable VS08-A acceptance records.

The adapter only authenticates records already produced by the Project, Test,
and Diagnostic workflows.  It never runs those workflows or creates a second
mutable acceptance lifecycle.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import cast
from uuid import UUID

from stm32_toolkit.diagnostic_workflows import (
    DiagnosticWorkflowContext,
    diagnostic_show,
    diagnostic_show_verification,
)
from stm32_toolkit.diagnostics import (
    DiagnosticSession,
    DiagnosticValidationError,
    FixVerification,
)
from stm32_toolkit.evidence import (
    EVIDENCE_CORRUPT,
    EvidenceEnvelope,
    EvidenceValidationError,
    get_root,
)
from stm32_toolkit.evidence.gc import RootRecord, put_root
from stm32_toolkit.evidence.model import MAX_ENVELOPE_BYTES, canonical_json_bytes
from stm32_toolkit.evidence.store import EvidenceStore
from stm32_toolkit.paths import WorkspacePaths, require_safe_session_id
from stm32_toolkit.project_model import ProjectManifestError, load_project_model
from stm32_toolkit.result import OperationResult
from stm32_toolkit.testing.publication import PublishedTestRun, TestRunRepository
from stm32_toolkit.testing_workflows import TestingWorkflowContext, test_show

from .model import (
    AcceptanceRecord,
    AcceptanceScenario,
    AcceptanceValidationError,
    RECORD_SCHEMA,
    REQUIRED_STAGES,
    describe_scenario,
)


_DESCRIBE_OPERATION = "acceptance.scenario.describe"
_RECORD_OPERATION = "acceptance.scenario.record"
_SHOW_OPERATION = "acceptance.scenario.show"
_UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
_HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_ACCEPTANCE_ENVELOPE_METADATA = frozenset(
    {
        "record",
        "record_sha256",
        "scenario_digest",
        "workspace_id",
        "logical_project_id",
    }
)
_ACCEPTANCE_ROOT_METADATA = frozenset(
    {
        "record_sha256",
        "scenario_digest",
        "workspace_id",
        "logical_project_id",
    }
)


_MESSAGES = {
    "ACCEPTANCE_INPUT_INVALID": "Acceptance scenario input is invalid.",
    "ACCEPTANCE_SCENARIO_UNKNOWN": "Acceptance scenario is not supported.",
    "ACCEPTANCE_SCENARIO_VERSION_UNSUPPORTED": "Acceptance scenario version is not supported.",
    "ACCEPTANCE_PROJECT_ORIGIN_MISMATCH": "Acceptance scenario project origin does not match.",
    "ACCEPTANCE_REFERENCE_INVALID": "Acceptance scenario reference is invalid.",
    "ACCEPTANCE_IDENTITY_MISMATCH": "Acceptance scenario identity does not match.",
    "ACCEPTANCE_PHYSICAL_EVIDENCE_FORBIDDEN": "Physical evidence is forbidden for software acceptance.",
    "ACCEPTANCE_NOT_COMPLETE": "Acceptance scenario workflow chain is not complete.",
    "ACCEPTANCE_RECORD_CONFLICT": "Acceptance record ID is already bound to different content.",
    "ACCEPTANCE_EVIDENCE_INTEGRITY_FAILED": "Acceptance evidence failed integrity validation.",
}


@dataclass(frozen=True)
class AcceptanceWorkflowContext:
    """The only caller-owned inputs for one acceptance operation."""

    project_root: Path
    data_root: Path
    session_id: str


# Narrow seams make the project-bound workflow deterministic in tests without
# replacing any public reader or Evidence publication primitive.
_load_project_model = load_project_model
_workspace_paths_factory = WorkspacePaths.from_roots
_evidence_store_factory = EvidenceStore
_utc_now = lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


class _AcceptanceFailure(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _failure(operation: str, code: str) -> OperationResult[None]:
    return OperationResult.failure(operation, code, _MESSAGES.get(code, _MESSAGES["ACCEPTANCE_REFERENCE_INVALID"]), {})


def _result(operation: str, action):
    try:
        return action()
    except AcceptanceValidationError as error:
        return _failure(operation, error.code)
    except _AcceptanceFailure as error:
        return _failure(operation, error.code)
    except (EvidenceValidationError, DiagnosticValidationError, ProjectManifestError, FileNotFoundError, OSError, TypeError, ValueError, KeyError, IndexError):
        return _failure(operation, "ACCEPTANCE_EVIDENCE_INTEGRITY_FAILED")


def _validate_context(context: AcceptanceWorkflowContext) -> None:
    if not isinstance(context, AcceptanceWorkflowContext):
        raise _AcceptanceFailure("ACCEPTANCE_INPUT_INVALID")
    if not isinstance(context.project_root, Path) or not isinstance(context.data_root, Path):
        raise _AcceptanceFailure("ACCEPTANCE_INPUT_INVALID")
    if not isinstance(context.session_id, str):
        raise _AcceptanceFailure("ACCEPTANCE_INPUT_INVALID")
    try:
        require_safe_session_id(context.session_id)
    except (TypeError, ValueError) as error:
        raise _AcceptanceFailure("ACCEPTANCE_INPUT_INVALID") from error


def _canonical_uuid(field: str, value: object) -> str:
    if not isinstance(value, str) or _UUID_PATTERN.fullmatch(value) is None:
        raise AcceptanceValidationError(f"{field} must be a canonical lowercase UUID")
    try:
        if str(UUID(value)) != value:
            raise ValueError
    except (TypeError, ValueError) as error:
        raise AcceptanceValidationError(f"{field} must be a canonical lowercase UUID") from error
    return value


def _typed_root_path(evidence: EvidenceStore, root_type: str, root_id: str) -> Path:
    root_name = hashlib.sha256(
        canonical_json_bytes({"root_type": root_type, "root_id": root_id})
    ).hexdigest() + ".json"
    return evidence.root / "roots" / root_type / root_name


def _root_failure_code(
    evidence: EvidenceStore, *, root_type: str, root_id: str
) -> str:
    """Classify a failed exact-key lookup without exposing Evidence details."""
    path = _typed_root_path(evidence, root_type, root_id)
    try:
        payload = evidence._read_file_bytes(path, maximum_bytes=MAX_ENVELOPE_BYTES)
    except FileNotFoundError:
        return "ACCEPTANCE_REFERENCE_INVALID"
    except (EvidenceValidationError, OSError, TypeError, ValueError):
        return "ACCEPTANCE_EVIDENCE_INTEGRITY_FAILED"
    try:
        document = json.loads(payload.decode("utf-8"))
        if canonical_json_bytes(document) != payload:
            return "ACCEPTANCE_EVIDENCE_INTEGRITY_FAILED"
        root = RootRecord.from_value(document)
    except (EvidenceValidationError, UnicodeError, json.JSONDecodeError, TypeError, ValueError):
        return "ACCEPTANCE_EVIDENCE_INTEGRITY_FAILED"
    if root.root_type != root_type or root.root_id != root_id:
        return "ACCEPTANCE_REFERENCE_INVALID"
    return "ACCEPTANCE_EVIDENCE_INTEGRITY_FAILED"


def _diagnostic_storage_id(value: str) -> str:
    """Map the canonical UUID wire spelling to Diagnostic's compact ID storage."""
    return value.replace("-", "")


def _hash_value(field: str, value: object) -> str:
    if not isinstance(value, str) or _HASH_PATTERN.fullmatch(value) is None:
        raise AcceptanceValidationError(f"{field} must be a lowercase SHA-256")
    return value


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise _AcceptanceFailure("ACCEPTANCE_REFERENCE_INVALID")
    return value


def _reader_failure_code(
    result: OperationResult[object],
    *,
    reader_kind: str,
    evidence: EvidenceStore | None = None,
    root_type: str | None = None,
    root_id: str | None = None,
) -> str:
    observed = result.code
    if reader_kind == "test":
        if observed == EVIDENCE_CORRUPT:
            if evidence is None or root_type is None or root_id is None:
                return "ACCEPTANCE_EVIDENCE_INTEGRITY_FAILED"
            return _root_failure_code(evidence, root_type=root_type, root_id=root_id)
        if observed.startswith("EVIDENCE_"):
            return "ACCEPTANCE_EVIDENCE_INTEGRITY_FAILED"
        return "ACCEPTANCE_REFERENCE_INVALID"
    if observed == "DIAGNOSTIC_NOT_FOUND":
        return "ACCEPTANCE_REFERENCE_INVALID"
    if observed == "DIAGNOSTIC_IDENTITY_MISMATCH":
        return "ACCEPTANCE_IDENTITY_MISMATCH"
    if observed.startswith("DIAGNOSTIC_"):
        return "ACCEPTANCE_EVIDENCE_INTEGRITY_FAILED"
    return "ACCEPTANCE_NOT_COMPLETE"


def _require_success(
    result: object,
    *,
    code: str = "ACCEPTANCE_REFERENCE_INVALID",
    reader_kind: str | None = None,
    evidence: EvidenceStore | None = None,
    root_type: str | None = None,
    root_id: str | None = None,
) -> Mapping[str, object]:
    if not isinstance(result, OperationResult) or result.ok is not True:
        if isinstance(result, OperationResult) and reader_kind is not None:
            raise _AcceptanceFailure(
                _reader_failure_code(
                    result,
                    reader_kind=reader_kind,
                    evidence=evidence,
                    root_type=root_type,
                    root_id=root_id,
                )
            )
        raise _AcceptanceFailure(code)
    # OperationResult intentionally freezes lists to tuples.  Public model
    # decoders are JSON boundaries and must receive the thawed canonical view.
    return _mapping(result.to_dict().get("data"), "workflow result")


def _load_project_and_workspace(
    context: AcceptanceWorkflowContext,
) -> tuple[object, WorkspacePaths, EvidenceStore]:
    _validate_context(context)
    try:
        model = _load_project_model(context.project_root)
    except ProjectManifestError as error:
        raise _AcceptanceFailure("ACCEPTANCE_REFERENCE_INVALID") from error
    if getattr(model, "schema_version", None) != 3:
        raise _AcceptanceFailure("ACCEPTANCE_REFERENCE_INVALID")
    try:
        workspace = _workspace_paths_factory(
            context.data_root,
            context.project_root,
            model.logical_project_id,
            context.session_id,
        )
    except (OSError, TypeError, ValueError) as error:
        raise _AcceptanceFailure("ACCEPTANCE_REFERENCE_INVALID") from error
    return model, workspace, _evidence_store_factory(workspace.workspace_root / "evidence")


def _project_origin(model: object) -> str:
    # v2/v3 manifests retain the migration label in ``project.origin``; the
    # normalized ``memory.source`` is the public project-origin vocabulary.
    origin = getattr(getattr(model, "memory", None), "source", None)
    if origin not in {"keil", "cubemx"}:
        raise _AcceptanceFailure("ACCEPTANCE_PROJECT_ORIGIN_MISMATCH")
    return cast(str, origin)


def _public_test_projection_matches(
    result: Mapping[str, object], published: PublishedTestRun, run_id: str
) -> None:
    if result.get("authoritative") is not True:
        raise _AcceptanceFailure("ACCEPTANCE_EVIDENCE_INTEGRITY_FAILED")
    run = _mapping(result.get("run"), "test run")
    if run.get("run_id") != run_id:
        raise _AcceptanceFailure("ACCEPTANCE_EVIDENCE_INTEGRITY_FAILED")
    if run.get("state") != published.manifest.state:
        raise _AcceptanceFailure("ACCEPTANCE_EVIDENCE_INTEGRITY_FAILED")
    if result.get("evidence_id") != str(published.envelope.evidence_id):
        raise _AcceptanceFailure("ACCEPTANCE_EVIDENCE_INTEGRITY_FAILED")
    if result.get("execution_source") != published.root.metadata.get("execution_source"):
        raise _AcceptanceFailure("ACCEPTANCE_EVIDENCE_INTEGRITY_FAILED")
    if result.get("physical_transport_evidence") != published.root.metadata.get("physical_transport_evidence"):
        raise _AcceptanceFailure("ACCEPTANCE_EVIDENCE_INTEGRITY_FAILED")
    if result.get("import_workspace_id") != published.root.metadata.get("import_workspace_id"):
        raise _AcceptanceFailure("ACCEPTANCE_EVIDENCE_INTEGRITY_FAILED")


def _validate_replay_run(
    published: PublishedTestRun,
    *,
    run_id: str,
    expected_state: str,
    workspace_id: str,
    project_id: str,
) -> None:
    manifest = published.manifest
    metadata = dict(published.envelope.metadata)
    root_metadata = dict(published.root.metadata)
    if manifest.run_id != run_id or manifest.mode != "target" or manifest.state != expected_state:
        raise _AcceptanceFailure("ACCEPTANCE_REFERENCE_INVALID")
    if manifest.transport != "replay":
        raise _AcceptanceFailure("ACCEPTANCE_PHYSICAL_EVIDENCE_FORBIDDEN")
    if (
        metadata.get("execution_source") != "replay"
        or metadata.get("physical_transport_evidence") is not False
        or root_metadata.get("execution_source") != "replay"
        or root_metadata.get("physical_transport_evidence") is not False
    ):
        raise _AcceptanceFailure("ACCEPTANCE_PHYSICAL_EVIDENCE_FORBIDDEN")
    if (
        metadata.get("import_workspace_id") != workspace_id
        or root_metadata.get("import_workspace_id") != workspace_id
        or manifest.identity.project_id != project_id
        or published.envelope.identity != manifest.identity
        or published.root.manifest_id != str(published.envelope.evidence_id)
    ):
        raise _AcceptanceFailure("ACCEPTANCE_IDENTITY_MISMATCH")


def _load_authoritative_runs(
    context: AcceptanceWorkflowContext,
    workspace: WorkspacePaths,
    evidence: EvidenceStore,
    *,
    failed_before_test_run_id: str,
    fixed_after_test_run_id: str,
) -> tuple[PublishedTestRun, PublishedTestRun]:
    testing_context = TestingWorkflowContext(
        context.project_root, context.data_root, context.session_id
    )
    before_result = _require_success(
        test_show(testing_context, run_id=failed_before_test_run_id),
        reader_kind="test",
        evidence=evidence,
        root_type="test-run",
        root_id=failed_before_test_run_id,
    )
    after_result = _require_success(
        test_show(testing_context, run_id=fixed_after_test_run_id),
        reader_kind="test",
        evidence=evidence,
        root_type="test-run",
        root_id=fixed_after_test_run_id,
    )
    repository = TestRunRepository(evidence)
    try:
        before = repository.load(failed_before_test_run_id)
        after = repository.load(fixed_after_test_run_id)
    except (EvidenceValidationError, OSError, ValueError, KeyError, TypeError) as error:
        raise _AcceptanceFailure("ACCEPTANCE_EVIDENCE_INTEGRITY_FAILED") from error
    _public_test_projection_matches(before_result, before, failed_before_test_run_id)
    _public_test_projection_matches(after_result, after, fixed_after_test_run_id)
    return before, after


def _load_diagnostic_chain(
    context: AcceptanceWorkflowContext,
    evidence: EvidenceStore,
    *,
    diagnostic_session_id: str,
    failed_before_test_run_id: str,
    fixed_after_test_run_id: str,
    before: PublishedTestRun,
    after: PublishedTestRun,
) -> tuple[DiagnosticSession, FixVerification, RootRecord]:
    diagnostic_storage_id = _diagnostic_storage_id(diagnostic_session_id)
    diagnostic_context = DiagnosticWorkflowContext(
        context.project_root, context.data_root, context.session_id
    )
    shown = _require_success(
        diagnostic_show(
            diagnostic_context, diagnostic_session_id=diagnostic_storage_id
        ),
        code="ACCEPTANCE_NOT_COMPLETE",
        reader_kind="diagnostic",
    )
    verification_shown = _require_success(
        diagnostic_show_verification(
            diagnostic_context, diagnostic_session_id=diagnostic_storage_id
        ),
        code="ACCEPTANCE_NOT_COMPLETE",
        reader_kind="diagnostic",
    )
    session_data = _mapping(shown.get("session"), "diagnostic session")
    verification_session_data = _mapping(verification_shown.get("session"), "diagnostic session")
    try:
        session = DiagnosticSession.from_value(session_data)
        verification_session = DiagnosticSession.from_value(verification_session_data)
    except (DiagnosticValidationError, TypeError, ValueError) as error:
        raise _AcceptanceFailure("ACCEPTANCE_EVIDENCE_INTEGRITY_FAILED") from error
    if session.to_dict() != verification_session.to_dict():
        raise _AcceptanceFailure("ACCEPTANCE_EVIDENCE_INTEGRITY_FAILED")
    if session.diagnostic_session_id != diagnostic_storage_id:
        raise _AcceptanceFailure("ACCEPTANCE_IDENTITY_MISMATCH")
    if session.state != "RESOLVED":
        raise _AcceptanceFailure("ACCEPTANCE_NOT_COMPLETE")
    if (
        session.failed_test_run_id != failed_before_test_run_id
        or session.failed_evidence_id != str(before.envelope.evidence_id)
        or session.identity.project_id != str(getattr(before.manifest.identity, "project_id", ""))
        or session.identity.project_id != str(getattr(after.manifest.identity, "project_id", ""))
        or session.identity.target_device != before.manifest.identity.target_device
        or session.identity.target_device != after.manifest.identity.target_device
        or session.identity.workspace_id != before.manifest.identity.workspace_id
        or session.identity.workspace_id != after.manifest.identity.workspace_id
    ):
        raise _AcceptanceFailure("ACCEPTANCE_IDENTITY_MISMATCH")
    if session.identity.project_id != str(getattr(after.manifest.identity, "project_id", "")):
        raise _AcceptanceFailure("ACCEPTANCE_IDENTITY_MISMATCH")
    if dict(session.identity.to_dict()).get("workspace_id") != before.manifest.identity.workspace_id:
        raise _AcceptanceFailure("ACCEPTANCE_IDENTITY_MISMATCH")

    try:
        selected = tuple(FixVerification.from_value(item) for item in session.fix_verifications)
    except (DiagnosticValidationError, TypeError, ValueError) as error:
        raise _AcceptanceFailure("ACCEPTANCE_EVIDENCE_INTEGRITY_FAILED") from error
    passing = tuple(item for item in selected if item.status == "PASSED")
    if not passing:
        raise _AcceptanceFailure("ACCEPTANCE_NOT_COMPLETE")
    if len(passing) != 1:
        raise _AcceptanceFailure("ACCEPTANCE_REFERENCE_INVALID")
    verification = passing[0]
    if (
        verification.diagnostic_session_id != diagnostic_storage_id
        or verification.failed_before_run_id != failed_before_test_run_id
        or verification.fixed_after_run_id != fixed_after_test_run_id
        or verification.failed_before_evidence_id != str(before.envelope.evidence_id)
        or verification.fixed_after_evidence_id != str(after.envelope.evidence_id)
    ):
        raise _AcceptanceFailure("ACCEPTANCE_REFERENCE_INVALID")
    shown_verifications = verification_shown.get("fix_verifications")
    if not isinstance(shown_verifications, list) or len(shown_verifications) != len(selected):
        raise _AcceptanceFailure("ACCEPTANCE_EVIDENCE_INTEGRITY_FAILED")
    try:
        if tuple(FixVerification.from_value(item) for item in shown_verifications) != selected:
            raise _AcceptanceFailure("ACCEPTANCE_EVIDENCE_INTEGRITY_FAILED")
    except (DiagnosticValidationError, TypeError, ValueError) as error:
        raise _AcceptanceFailure("ACCEPTANCE_EVIDENCE_INTEGRITY_FAILED") from error

    latest_root_id = f"{diagnostic_storage_id}.{session.revision:08d}"
    try:
        latest_root = get_root(evidence, "diagnostic-session", latest_root_id)
        latest_envelope = evidence.get_envelope(latest_root.manifest_id)
    except (EvidenceValidationError, OSError, ValueError, FileNotFoundError) as error:
        raise _AcceptanceFailure("ACCEPTANCE_EVIDENCE_INTEGRITY_FAILED") from error
    if (
        latest_root.manifest_id != str(latest_envelope.evidence_id)
        or latest_root.metadata.get("diagnostic_session_id") != diagnostic_storage_id
        or latest_root.metadata.get("revision") != session.revision
        or latest_envelope.identity != session.identity
    ):
        raise _AcceptanceFailure("ACCEPTANCE_EVIDENCE_INTEGRITY_FAILED")
    return session, verification, latest_root


def _record_digest(record: AcceptanceRecord) -> str:
    return hashlib.sha256(canonical_json_bytes(record.to_dict())).hexdigest()


def _acceptance_root_metadata(record: AcceptanceRecord) -> dict[str, object]:
    return {
        "record_sha256": _record_digest(record),
        "scenario_digest": record.scenario_digest,
        "workspace_id": record.workspace_id,
        "logical_project_id": record.logical_project_id,
    }


def _acceptance_envelope(
    record: AcceptanceRecord,
    *,
    identity: object,
    parents: tuple[str, ...],
) -> EvidenceEnvelope:
    return EvidenceEnvelope(
        identity=identity,
        operation="acceptance-scenario",
        produced_at_utc=record.produced_at_utc,
        parents=parents,
        artifacts=(),
        metadata={
            "record": record.to_dict(),
            **_acceptance_root_metadata(record),
        },
    )


def _read_acceptance(
    evidence: EvidenceStore, record_id: str
) -> tuple[AcceptanceRecord, RootRecord, EvidenceEnvelope]:
    try:
        root = get_root(evidence, "acceptance-scenario", record_id)
        envelope = evidence.get_envelope(root.manifest_id)
    except (EvidenceValidationError, OSError, FileNotFoundError, ValueError) as error:
        if isinstance(error, EvidenceValidationError) and error.code == EVIDENCE_CORRUPT:
            failure_code = _root_failure_code(
                evidence, root_type="acceptance-scenario", root_id=record_id
            )
            if failure_code == "ACCEPTANCE_REFERENCE_INVALID":
                raise _AcceptanceFailure(failure_code) from error
        raise _AcceptanceFailure("ACCEPTANCE_EVIDENCE_INTEGRITY_FAILED") from error
    if (
        root.root_type != "acceptance-scenario"
        or root.root_id != record_id
        or set(root.metadata) != _ACCEPTANCE_ROOT_METADATA
        or envelope.operation != "acceptance-scenario"
        or set(envelope.metadata) != _ACCEPTANCE_ENVELOPE_METADATA
        or envelope.identity.project_id != root.metadata.get("logical_project_id")
    ):
        raise _AcceptanceFailure("ACCEPTANCE_EVIDENCE_INTEGRITY_FAILED")
    try:
        record_data = json.loads(
            canonical_json_bytes(envelope.metadata["record"]).decode("utf-8")
        )
        record = AcceptanceRecord.from_value(record_data)
    except (AcceptanceValidationError, TypeError, ValueError) as error:
        raise _AcceptanceFailure("ACCEPTANCE_EVIDENCE_INTEGRITY_FAILED") from error
    if (
        record.record_id != record_id
        or envelope.produced_at_utc != record.produced_at_utc
        or root.manifest_id != str(envelope.evidence_id)
        or root.metadata != _acceptance_root_metadata(record)
        or canonical_json_bytes(envelope.metadata)
        != canonical_json_bytes({"record": record.to_dict(), **_acceptance_root_metadata(record)})
        or len(envelope.parents) != 3
        or len(set(envelope.parents)) != 3
        or envelope.parents[:2]
        != (record.failed_before_evidence_id, record.fixed_after_evidence_id)
    ):
        raise _AcceptanceFailure("ACCEPTANCE_EVIDENCE_INTEGRITY_FAILED")
    try:
        for parent_id in envelope.parents:
            evidence.get_envelope(parent_id)
    except (EvidenceValidationError, OSError, ValueError) as error:
        raise _AcceptanceFailure("ACCEPTANCE_EVIDENCE_INTEGRITY_FAILED") from error
    return record, root, envelope


def _check_existing_record(
    evidence: EvidenceStore,
    *,
    record_id: str,
    expected_values: Mapping[str, object],
) -> OperationResult[dict[str, object]] | None:
    root_path = _typed_root_path(evidence, "acceptance-scenario", record_id)
    try:
        root_exists = root_path.exists()
    except OSError:
        return _failure(_RECORD_OPERATION, "ACCEPTANCE_EVIDENCE_INTEGRITY_FAILED")
    if not root_exists:
        return None
    try:
        existing, _root, _envelope = _read_acceptance(evidence, record_id)
    except _AcceptanceFailure as error:
        if error.code == "ACCEPTANCE_EVIDENCE_INTEGRITY_FAILED":
            return _failure(_RECORD_OPERATION, "ACCEPTANCE_EVIDENCE_INTEGRITY_FAILED")
        return _failure(_RECORD_OPERATION, error.code)
    existing_values = existing.to_dict()
    if all(existing_values.get(key) == value for key, value in expected_values.items()):
        return OperationResult.success(_RECORD_OPERATION, {"record": existing.to_dict()})
    return _failure(_RECORD_OPERATION, "ACCEPTANCE_RECORD_CONFLICT")


def _record_acceptance(
    context: AcceptanceWorkflowContext,
    *,
    record_id: object,
    scenario_id: object,
    scenario_version: object,
    failed_before_test_run_id: object,
    fixed_after_test_run_id: object,
    diagnostic_session_id: object,
) -> OperationResult[dict[str, object]]:
    # Step 1: all caller syntax is closed before any project/store read.
    record_id = _canonical_uuid("recordId", record_id)
    failed_before_test_run_id = _canonical_uuid("failedBeforeTestRunId", failed_before_test_run_id)
    fixed_after_test_run_id = _canonical_uuid("fixedAfterTestRunId", fixed_after_test_run_id)
    diagnostic_session_id = _canonical_uuid("diagnosticSessionId", diagnostic_session_id)
    scenario = describe_scenario(cast(str, scenario_id), cast(str, scenario_version))
    if failed_before_test_run_id == fixed_after_test_run_id:
        raise AcceptanceValidationError("failed and fixed run IDs must differ")

    # Step 2: project origin and current import workspace are authoritative.
    model, workspace, evidence = _load_project_and_workspace(context)
    if _project_origin(model) != scenario.project_origin:
        raise _AcceptanceFailure("ACCEPTANCE_PROJECT_ORIGIN_MISMATCH")
    project_id = str(model.logical_project_id)

    # Steps 3-4: reload both existing public Target replay records.
    before, after = _load_authoritative_runs(
        context,
        workspace,
        evidence,
        failed_before_test_run_id=failed_before_test_run_id,
        fixed_after_test_run_id=fixed_after_test_run_id,
    )
    _validate_replay_run(
        before,
        run_id=failed_before_test_run_id,
        expected_state="failed",
        workspace_id=workspace.workspace_id,
        project_id=project_id,
    )
    _validate_replay_run(
        after,
        run_id=fixed_after_test_run_id,
        expected_state="passed",
        workspace_id=workspace.workspace_id,
        project_id=project_id,
    )
    if before.manifest.identity.target_device != after.manifest.identity.target_device:
        raise _AcceptanceFailure("ACCEPTANCE_IDENTITY_MISMATCH")

    # Step 5: reload the diagnostic session and exact passing verification.
    session, verification, diagnostic_root = _load_diagnostic_chain(
        context,
        evidence,
        diagnostic_session_id=diagnostic_session_id,
        failed_before_test_run_id=failed_before_test_run_id,
        fixed_after_test_run_id=fixed_after_test_run_id,
        before=before,
        after=after,
    )

    # Step 6: project stable references only; no Test/Diagnostic payloads are copied.
    stable_values = {
        "schema": RECORD_SCHEMA,
        "recordId": record_id,
        "scenarioId": scenario.scenario_id,
        "scenarioVersion": scenario.scenario_version,
        "scenarioDigest": scenario.scenario_digest,
        "workspaceId": workspace.workspace_id,
        "logicalProjectId": project_id,
        "projectOrigin": scenario.project_origin,
        "executionSource": "replay",
        "physicalTransportEvidence": False,
        "completedStages": list(REQUIRED_STAGES),
        "failedBeforeTestRunId": failed_before_test_run_id,
        "fixedAfterTestRunId": fixed_after_test_run_id,
        "diagnosticSessionId": diagnostic_session_id,
        "fixVerificationId": verification.fix_verification_id,
        "failedBeforeEvidenceId": str(before.envelope.evidence_id),
        "fixedAfterEvidenceId": str(after.envelope.evidence_id),
        "beforeBuildId": before.manifest.identity.build_id,
        "afterBuildId": after.manifest.identity.build_id,
        "beforeElfSha256": before.manifest.identity.elf_sha256,
        "afterElfSha256": after.manifest.identity.elf_sha256,
        "verdict": "SOFTWARE_PASSED",
    }
    existing = _check_existing_record(
        evidence,
        record_id=record_id,
        expected_values=stable_values,
    )
    if existing is not None:
        return existing
    record = AcceptanceRecord(
        schema=RECORD_SCHEMA,
        record_id=record_id,
        scenario_id=scenario.scenario_id,
        scenario_version=scenario.scenario_version,
        scenario_digest=scenario.scenario_digest,
        workspace_id=workspace.workspace_id,
        logical_project_id=project_id,
        project_origin=scenario.project_origin,
        execution_source="replay",
        physical_transport_evidence=False,
        completed_stages=REQUIRED_STAGES,
        failed_before_test_run_id=failed_before_test_run_id,
        fixed_after_test_run_id=fixed_after_test_run_id,
        diagnostic_session_id=diagnostic_session_id,
        fix_verification_id=verification.fix_verification_id,
        failed_before_evidence_id=str(before.envelope.evidence_id),
        fixed_after_evidence_id=str(after.envelope.evidence_id),
        before_build_id=before.manifest.identity.build_id,
        after_build_id=after.manifest.identity.build_id,
        before_elf_sha256=before.manifest.identity.elf_sha256,
        after_elf_sha256=after.manifest.identity.elf_sha256,
        verdict="SOFTWARE_PASSED",
        produced_at_utc=_utc_now(),
    )
    parent_values = (
        str(before.envelope.evidence_id),
        str(after.envelope.evidence_id),
        str(diagnostic_root.manifest_id),
    )
    parents = tuple(item for index, item in enumerate(parent_values) if item not in parent_values[:index])
    envelope = _acceptance_envelope(
        record,
        identity=after.manifest.identity,
        parents=parents,
    )
    # Step 7: existing immutable EvidenceStore primitives own publication.
    try:
        evidence.put_envelope(envelope)
        put_root(
            evidence,
            RootRecord(
                "acceptance-scenario",
                record.record_id,
                str(envelope.evidence_id),
                _acceptance_root_metadata(record),
            ),
        )
    except EvidenceValidationError as error:
        if error.code == EVIDENCE_CORRUPT:
            # An identical immutable retry is reusable; a different root is a conflict.
            existing = _check_existing_record(
                evidence,
                record_id=record.record_id,
                expected_values=stable_values,
            )
            if existing is not None:
                return existing
            return _failure(_RECORD_OPERATION, "ACCEPTANCE_RECORD_CONFLICT")
        raise _AcceptanceFailure("ACCEPTANCE_EVIDENCE_INTEGRITY_FAILED") from error
    # Step 8: reload every published byte through authoritative readers.
    stored, _root, _stored_envelope = _read_acceptance(evidence, record.record_id)
    if stored.to_dict() != record.to_dict():
        raise _AcceptanceFailure("ACCEPTANCE_EVIDENCE_INTEGRITY_FAILED")
    return OperationResult.success(_RECORD_OPERATION, {"record": stored.to_dict()})


def record_acceptance_scenario(
    context: AcceptanceWorkflowContext,
    *,
    record_id: object,
    scenario_id: object,
    scenario_version: object,
    failed_before_test_run_id: object,
    fixed_after_test_run_id: object,
    diagnostic_session_id: object,
) -> OperationResult[dict[str, object]]:
    return _result(
        _RECORD_OPERATION,
        lambda: _record_acceptance(
            context,
            record_id=record_id,
            scenario_id=scenario_id,
            scenario_version=scenario_version,
            failed_before_test_run_id=failed_before_test_run_id,
            fixed_after_test_run_id=fixed_after_test_run_id,
            diagnostic_session_id=diagnostic_session_id,
        ),
    )


def _show_acceptance(
    context: AcceptanceWorkflowContext, *, record_id: object
) -> OperationResult[dict[str, object]]:
    _validate_context(context)
    record_id = _canonical_uuid("recordId", record_id)
    model, workspace, evidence = _load_project_and_workspace(context)
    record, root, envelope = _read_acceptance(evidence, record_id)
    if (
        record.workspace_id != workspace.workspace_id
        or record.logical_project_id != str(model.logical_project_id)
        or record.project_origin != _project_origin(model)
        or envelope.identity.project_id != record.logical_project_id
        or envelope.identity.build_id != record.after_build_id
        or envelope.identity.elf_sha256 != record.after_elf_sha256
        or root.manifest_id != str(envelope.evidence_id)
    ):
        raise _AcceptanceFailure("ACCEPTANCE_IDENTITY_MISMATCH")
    return OperationResult.success(
        _SHOW_OPERATION,
        {"authoritative": True, "record": record.to_dict()},
    )


def show_acceptance_scenario(
    context: AcceptanceWorkflowContext, *, record_id: object
) -> OperationResult[dict[str, object]]:
    return _result(_SHOW_OPERATION, lambda: _show_acceptance(context, record_id=record_id))


def _describe_acceptance(
    context: AcceptanceWorkflowContext, *, scenario_id: object, scenario_version: object
) -> OperationResult[dict[str, object]]:
    _validate_context(context)
    scenario = describe_scenario(cast(str, scenario_id), cast(str, scenario_version))
    return OperationResult.success(_DESCRIBE_OPERATION, {"scenario": scenario.to_dict()})


def describe_acceptance_scenario(
    context: AcceptanceWorkflowContext, *, scenario_id: object, scenario_version: object
) -> OperationResult[dict[str, object]]:
    return _result(
        _DESCRIBE_OPERATION,
        lambda: _describe_acceptance(
            context, scenario_id=scenario_id, scenario_version=scenario_version
        ),
    )


__all__ = [
    "AcceptanceWorkflowContext",
    "describe_acceptance_scenario",
    "record_acceptance_scenario",
    "show_acceptance_scenario",
]
