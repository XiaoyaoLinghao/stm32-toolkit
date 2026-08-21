"""Public History/Evidence workflow for bounded replay analysis publication."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
import json
from hashlib import sha256
from pathlib import Path
import re
import tempfile
from typing import cast
from uuid import UUID

from stm32_toolkit.diagnostics import DiagnosticMarkerRef, SourceChangeDeclaration
from stm32_toolkit.evidence import (
    ArtifactRef,
    EvidenceEnvelope,
    EvidenceIdentity,
    EvidenceValidationError,
)
from stm32_toolkit.evidence.gc import RootRecord, get_root, put_root
from stm32_toolkit.evidence.store import EvidenceStore, MAX_EVIDENCE_READ_BYTES
from stm32_toolkit.paths import WorkspacePaths
from stm32_toolkit.testing.publication import TestRunRepository

from .analysis import (
    AnalysisError,
    AnalysisEvidenceRef,
    AnalysisLineage,
    AnalysisRequest,
    AnalysisResult,
    DiagnosticMarker,
    analyze_monitor_windows,
)
from .history import (
    MAX_HISTORY_VALUES,
    HistoryBatchSlice,
    HistoryPage,
    HistoryQuery,
    HistoryStore,
)
from .models import ObservationBinding, SampleBatch, unix_ns_to_utc
from .protocol import ProtocolResult
from .replay import (
    MONITOR_RUN_REF_ARTIFACT_KIND,
    MONITOR_RUN_REF_OPERATION,
    MONITOR_RUN_REF_ROOT_TYPE,
    MONITOR_RUN_REF_SCHEMA,
    MONITOR_REPLAY_EXECUTION_SOURCE,
    MONITOR_REPLAY_IMPORT_OPERATION,
    MonitorReplayDocument,
    MonitorReplayError,
    MonitorRunRef,
    canonical_replay_json_bytes,
)


ANALYSIS_WORKFLOW_INVALID = "ANALYSIS_WORKFLOW_INVALID"
INCOMPATIBLE_IDENTITY = "INCOMPATIBLE_IDENTITY"
EVIDENCE_INTEGRITY_FAILURE = "EVIDENCE_INTEGRITY_FAILURE"
OPERATION_CONFLICT = "OPERATION_CONFLICT"
ENVIRONMENT_FAILURE = "ENVIRONMENT_FAILURE"

_ERROR_CODES = frozenset(
    {
        ANALYSIS_WORKFLOW_INVALID,
        INCOMPATIBLE_IDENTITY,
        EVIDENCE_INTEGRITY_FAILURE,
        OPERATION_CONFLICT,
        ENVIRONMENT_FAILURE,
    }
)
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_DIAGNOSTIC_HASH = re.compile(r"[0-9a-f]{32}\Z")
_MONITOR_ANALYSIS_OPERATION = "monitor-analysis"
_DIAGNOSTIC_MARKER_OPERATION = "diagnostic-marker"
_MONITOR_ANALYSIS_ROOT = "monitor-analysis"
_DIAGNOSTIC_MARKER_ROOT = "diagnostic-marker"
_ANALYSIS_BUNDLE_OPERATION = "monitor-analysis-bundle"
_ANALYSIS_BUNDLE_ROOT = "monitor-analysis-bundle"
_ANALYSIS_BUNDLE_SCHEMA = "stm32-monitor-analysis-bundle/1"
_ANALYSIS_BUNDLE_REF_SCHEMA = "stm32-monitor-analysis-bundle-ref/1"
_REPLAY_ROLES = {"failed-before", "fixed-after"}

class AnalysisWorkflowError(ValueError):
    """One stable, bounded error at the analysis publication boundary."""

    def __init__(self, code: str, message: str) -> None:
        if type(code) is not str or code not in _ERROR_CODES:
            raise ValueError("unknown analysis workflow error code")
        if type(message) is not str or not message or len(message) > 256:
            raise ValueError("analysis workflow error message is invalid")
        super().__init__(message)
        self._code = code
        self._message = message

    @property
    def code(self) -> str:
        return self._code

    @property
    def message(self) -> str:
        return self._message


@dataclass(frozen=True, slots=True)
class AnalysisPublication:
    analysis_result: AnalysisResult
    analysis_evidence_ref: AnalysisEvidenceRef
    diagnostic_marker: DiagnosticMarker
    diagnostic_marker_ref: DiagnosticMarkerRef

    def to_dict(self) -> dict[str, object]:
        """Return the one closed wire projection owned by Monitor analysis."""

        return {
            "analysis_result": self.analysis_result.to_dict(),
            "analysis_evidence_ref": self.analysis_evidence_ref.to_dict(),
            "diagnostic_marker": self.diagnostic_marker.to_dict(),
            "diagnostic_marker_ref": self.diagnostic_marker_ref.to_dict(),
        }

    @classmethod
    def from_value(cls, value: object) -> "AnalysisPublication":
        if type(value) is cls:
            return value
        if type(value) is not dict or set(value) != {
            "analysis_result",
            "analysis_evidence_ref",
            "diagnostic_marker",
            "diagnostic_marker_ref",
        }:
            _fail(ANALYSIS_WORKFLOW_INVALID, "analysis publication is invalid")
        try:
            publication = cls(
                analysis_result=AnalysisResult.from_value(value["analysis_result"]),
                analysis_evidence_ref=AnalysisEvidenceRef.from_value(
                    value["analysis_evidence_ref"]
                ),
                diagnostic_marker=DiagnosticMarker.from_value(value["diagnostic_marker"]),
                diagnostic_marker_ref=DiagnosticMarkerRef.from_value(
                    value["diagnostic_marker_ref"]
                ),
            )
        except AnalysisWorkflowError:
            raise
        except Exception as error:
            _fail(ANALYSIS_WORKFLOW_INVALID, "analysis publication is invalid")
            raise AssertionError from error
        return publication

    def __post_init__(self) -> None:
        if type(self.analysis_result) is not AnalysisResult:
            _fail(ANALYSIS_WORKFLOW_INVALID, "analysis result is invalid")
        if type(self.analysis_evidence_ref) is not AnalysisEvidenceRef:
            _fail(ANALYSIS_WORKFLOW_INVALID, "analysis evidence reference is invalid")
        if type(self.diagnostic_marker) is not DiagnosticMarker:
            _fail(ANALYSIS_WORKFLOW_INVALID, "diagnostic marker is invalid")
        if type(self.diagnostic_marker_ref) is not DiagnosticMarkerRef:
            _fail(ANALYSIS_WORKFLOW_INVALID, "diagnostic marker reference is invalid")
        if self.analysis_evidence_ref.analysis_id != self.analysis_result.analysis_id:
            _fail(ANALYSIS_WORKFLOW_INVALID, "analysis evidence reference does not match result")
        if self.diagnostic_marker.analysis_id != self.analysis_result.analysis_id:
            _fail(ANALYSIS_WORKFLOW_INVALID, "diagnostic marker does not match result")
        if self.diagnostic_marker.analysis_evidence_id != self.analysis_evidence_ref.evidence_id:
            _fail(ANALYSIS_WORKFLOW_INVALID, "diagnostic marker does not match analysis evidence")
        marker_ref = self.diagnostic_marker_ref
        marker = self.diagnostic_marker
        if (
            marker_ref.marker_id != marker.marker_id
            or marker_ref.analysis_id != marker.analysis_id
            or marker_ref.analysis_evidence_id != marker.analysis_evidence_id
            or marker_ref.diagnostic_session_id != marker.diagnostic_session_id
            or marker_ref.hypothesis_id != marker.hypothesis_id
            or marker_ref.polarity != marker.polarity
            or marker_ref.label != marker.label
            or marker_ref.rationale != marker.rationale
        ):
            _fail(ANALYSIS_WORKFLOW_INVALID, "diagnostic marker reference does not match marker")


@dataclass(frozen=True, slots=True)
class AnalysisBundleRef:
    schema: str
    bundle_id: str
    evidence_id: str
    artifact: ArtifactRef

    def __post_init__(self) -> None:
        if (type(self.schema) is not str or self.schema != _ANALYSIS_BUNDLE_REF_SCHEMA
                or type(self.bundle_id) is not str or _HASH.fullmatch(self.bundle_id) is None):
            _fail(ANALYSIS_WORKFLOW_INVALID, "analysis bundle reference is invalid")
        if (type(self.evidence_id) is not str or _HASH.fullmatch(self.evidence_id) is None
                or type(self.artifact) is not ArtifactRef):
            _fail(ANALYSIS_WORKFLOW_INVALID, "analysis bundle reference is invalid")
        if (self.artifact.sha256 != self.bundle_id or self.artifact.kind != _ANALYSIS_BUNDLE_ROOT
                or self.artifact.media_type != "application/json"):
            _fail(ANALYSIS_WORKFLOW_INVALID, "analysis bundle artifact is invalid")

    def to_dict(self) -> dict[str, object]:
        return {"schema": self.schema, "bundle_id": self.bundle_id,
                "evidence_id": self.evidence_id, "artifact": self.artifact.to_dict()}

    @classmethod
    def from_value(cls, value: object) -> "AnalysisBundleRef":
        if type(value) is not dict or set(value) != {"schema", "bundle_id", "evidence_id", "artifact"}:
            _fail(ANALYSIS_WORKFLOW_INVALID, "analysis bundle reference is invalid")
        try:
            return cls(schema=value["schema"], bundle_id=value["bundle_id"],
                       evidence_id=value["evidence_id"],
                       artifact=ArtifactRef.from_dict(value["artifact"]))
        except AnalysisWorkflowError:
            raise
        except Exception as error:
            _fail(ANALYSIS_WORKFLOW_INVALID, "analysis bundle reference is invalid")
            raise AssertionError from error


def _fail(code: str, message: str) -> None:
    raise AnalysisWorkflowError(code, message)


def _hash(value: object, label: str) -> str:
    if type(value) is not str or _HASH.fullmatch(value) is None:
        _fail(ANALYSIS_WORKFLOW_INVALID, f"{label} is invalid")
    return cast(str, value)


def _diagnostic_hash(value: object, label: str) -> str:
    if type(value) is not str or _DIAGNOSTIC_HASH.fullmatch(value) is None:
        _fail(ANALYSIS_WORKFLOW_INVALID, f"{label} is invalid")
    return cast(str, value)


def _safe_text(value: object, label: str) -> str:
    if type(value) is not str or not value or len(value) > 4096:
        _fail(ANALYSIS_WORKFLOW_INVALID, f"{label} is invalid")
    return value


def _identity_for_ref(reference: MonitorRunRef) -> EvidenceIdentity:
    try:
        return EvidenceIdentity(
            workspace_id=reference.origin_workspace_id,
            project_id=reference.logical_project_id,
            session_id=reference.origin_session_id,
            build_id=reference.build_id,
            elf_sha256=reference.elf_sha256,
            target_device=reference.target_device,
            input_snapshot_sha256=reference.input_snapshot_sha256,
            git_commit=reference.git_head,
            git_dirty=reference.git_dirty,
        )
    except (TypeError, ValueError, OverflowError, EvidenceValidationError) as error:
        _fail(EVIDENCE_INTEGRITY_FAILURE, "replay Evidence identity is invalid")
        raise AssertionError from error


def _expected_run_root(reference: MonitorRunRef) -> RootRecord:
    try:
        return RootRecord(
            root_type="monitor-run",
            root_id=reference.operation_id,
            manifest_id=reference.transcript_evidence_id,
            metadata={
                "fixture_sha256": reference.fixture_sha256,
                "run_ref_sha256": reference.run_ref_sha256,
                "origin_workspace_id": reference.origin_workspace_id,
                "import_workspace_id": reference.import_workspace_id,
                "execution_source": MONITOR_REPLAY_EXECUTION_SOURCE,
                "physical_transport_evidence": False,
            },
        )
    except EvidenceValidationError as error:
        _fail(EVIDENCE_INTEGRITY_FAILURE, "replay run root is invalid")
        raise AssertionError from error


def _load_root(evidence_store: EvidenceStore, root_type: str, root_id: str) -> RootRecord:
    try:
        return get_root(evidence_store, root_type, root_id)
    except EvidenceValidationError as error:
        _fail(EVIDENCE_INTEGRITY_FAILURE, "replay Evidence root is absent or corrupt")
        raise AssertionError from error
    except OSError as error:
        _fail(ENVIRONMENT_FAILURE, "replay Evidence root could not be read")
        raise AssertionError from error
    except Exception as error:
        _fail(ENVIRONMENT_FAILURE, "replay Evidence root could not be read")
        raise AssertionError from error


def _validate_transcript(
    evidence_store: EvidenceStore,
    reference: MonitorRunRef,
) -> EvidenceEnvelope:
    expected_root = _expected_run_root(reference)
    root = _load_root(evidence_store, "monitor-run", reference.operation_id)
    if root.to_dict() != expected_root.to_dict():
        _fail(OPERATION_CONFLICT, "replay run root has a different intent")
    try:
        envelope = evidence_store.get_envelope(reference.transcript_evidence_id)
    except FileNotFoundError as error:
        _fail(EVIDENCE_INTEGRITY_FAILURE, "replay transcript envelope is absent")
        raise AssertionError from error
    except EvidenceValidationError as error:
        _fail(EVIDENCE_INTEGRITY_FAILURE, "replay transcript envelope is corrupt")
        raise AssertionError from error
    except OSError as error:
        _fail(ENVIRONMENT_FAILURE, "replay transcript envelope could not be read")
        raise AssertionError from error
    except Exception as error:
        _fail(ENVIRONMENT_FAILURE, "replay transcript envelope could not be read")
        raise AssertionError from error

    expected_metadata = {
        "operation_id": reference.operation_id,
        "scenario_role": reference.scenario_role,
        "origin_workspace_id": reference.origin_workspace_id,
        "import_workspace_id": reference.import_workspace_id,
        "origin_run_id": reference.origin_run_id,
        "projected_run_id": reference.projected_run_id,
        "fixture_sha256": reference.fixture_sha256,
        "execution_source": MONITOR_REPLAY_EXECUTION_SOURCE,
        "physical_transport_evidence": False,
    }
    if (
        envelope.operation != MONITOR_REPLAY_IMPORT_OPERATION
        or envelope.parents != ()
        or dict(envelope.metadata) != expected_metadata
        or envelope.identity != _identity_for_ref(reference)
        or envelope.produced_at_utc != unix_ns_to_utc(reference.start_captured_unix_ns)
        or len(envelope.artifacts) != 1
        or envelope.artifacts[0].kind != "monitor-replay-transcript"
        or envelope.artifacts[0].media_type != "application/json"
    ):
        _fail(EVIDENCE_INTEGRITY_FAILURE, "replay transcript envelope is inconsistent")
    try:
        raw = evidence_store.read_artifact(
            envelope.artifacts[0], maximum_bytes=MAX_EVIDENCE_READ_BYTES
        )
        body = raw[:-1] if raw.endswith(b"\n") else raw
        decoded = json.loads(body.decode("utf-8"))
        document = MonitorReplayDocument.from_value(decoded)
        canonical = canonical_replay_json_bytes(document.to_dict())
    except (EvidenceValidationError, MonitorReplayError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as error:
        _fail(EVIDENCE_INTEGRITY_FAILURE, "replay transcript artifact is corrupt")
        raise AssertionError from error
    except OSError as error:
        _fail(ENVIRONMENT_FAILURE, "replay transcript artifact could not be read")
        raise AssertionError from error
    except Exception as error:
        _fail(ENVIRONMENT_FAILURE, "replay transcript artifact could not be read")
        raise AssertionError from error
    if raw not in (canonical, canonical + b"\n"):
        _fail(EVIDENCE_INTEGRITY_FAILURE, "replay transcript artifact is not canonical")
    expected_binding = {
        "workspaceId": reference.origin_workspace_id,
        "logicalProjectId": reference.logical_project_id,
        "sessionId": reference.origin_session_id,
        "probeId": reference.probe_id,
        "targetDevice": reference.target_device,
        "physicalTarget": reference.physical_target,
        "buildId": reference.build_id,
        "elfSha256": reference.elf_sha256,
        "inputSnapshotSha256": reference.input_snapshot_sha256,
        "gitHead": reference.git_head,
        "gitDirty": reference.git_dirty,
        "flashSessionId": reference.flash_session_id,
        "leaseId": reference.lease_id,
        "dwarfSha256": reference.dwarf_sha256,
        "svdSha256": reference.svd_sha256,
    }
    batches = document.batches
    if (
        document.source != "toolkit-generated-probe-v2-replay"
        or document.physical_transport_evidence is not False
        or document.scenario_role != reference.scenario_role
        or document.fixture_sha256 != reference.fixture_sha256
        or document.binding.to_dict() != expected_binding
        or not batches
        or tuple(str(batch.run_id) for batch in batches) != (reference.origin_run_id,) * len(batches)
        or tuple(batch.sequence for batch in batches)
        != tuple(range(reference.start_sequence, reference.end_sequence_exclusive))
        or batches[0].group_id != UUID(reference.group_id)
        or any(batch.group_revision != reference.group_revision for batch in batches)
        or batches[0].captured_unix_ns != reference.start_captured_unix_ns
        or batches[-1].captured_unix_ns + 1 != reference.end_captured_unix_ns_exclusive
    ):
        _fail(EVIDENCE_INTEGRITY_FAILURE, "replay transcript does not match its run reference")
    try:
        projected_binding = ObservationBinding(
            workspace_id=reference.import_workspace_id,
            logical_project_id=reference.logical_project_id,
            session_id=reference.projected_session_id,
            probe_id=reference.probe_id,
            target_device=reference.target_device,
            physical_target=reference.physical_target,
            build_id=reference.build_id,
            elf_sha256=reference.elf_sha256,
            input_snapshot_sha256=reference.input_snapshot_sha256,
            git_head=reference.git_head,
            git_dirty=reference.git_dirty,
            flash_session_id=reference.flash_session_id,
            lease_id=reference.lease_id,
            dwarf_sha256=reference.dwarf_sha256,
            svd_sha256=reference.svd_sha256,
        )
        projected_digests = tuple(
            sha256(
                canonical_replay_json_bytes(
                    replace(batch, binding=projected_binding).to_dict()
                )
            ).hexdigest()
            for batch in batches
        )
    except (TypeError, ValueError, OverflowError, MonitorReplayError) as error:
        _fail(EVIDENCE_INTEGRITY_FAILURE, "replay projected batch identity is invalid")
        raise AssertionError from error
    if projected_digests != reference.projected_batch_sha256s:
        _fail(EVIDENCE_INTEGRITY_FAILURE, "replay projected batch digests contradict the run reference")
    _validate_reference_authority(evidence_store, reference, envelope)
    return envelope


def _validate_reference_authority(
    evidence_store: EvidenceStore,
    reference: MonitorRunRef,
    transcript_envelope: EvidenceEnvelope,
) -> None:
    expected_metadata = {
        "operation_id": reference.operation_id,
        "run_ref_sha256": reference.run_ref_sha256,
        "fixture_sha256": reference.fixture_sha256,
        "scenario_role": reference.scenario_role,
        "origin_workspace_id": reference.origin_workspace_id,
        "import_workspace_id": reference.import_workspace_id,
        "execution_source": MONITOR_REPLAY_EXECUTION_SOURCE,
        "physical_transport_evidence": False,
    }
    try:
        root = _load_root(evidence_store, MONITOR_RUN_REF_ROOT_TYPE, reference.operation_id)
        if (
            root.root_type != MONITOR_RUN_REF_ROOT_TYPE
            or root.root_id != reference.operation_id
            or set(root.metadata) != set(expected_metadata)
            or dict(root.metadata) != expected_metadata
        ):
            _fail(EVIDENCE_INTEGRITY_FAILURE, "replay reference root is inconsistent")
        envelope = evidence_store.get_envelope(root.manifest_id)
        if (
            root.manifest_id != str(envelope.evidence_id)
            or envelope.operation != MONITOR_RUN_REF_OPERATION
            or envelope.parents != (str(transcript_envelope.evidence_id),)
            or len(envelope.artifacts) != 1
            or dict(envelope.metadata) != expected_metadata
            or envelope.identity != _identity_for_ref(reference)
            or envelope.produced_at_utc != transcript_envelope.produced_at_utc
        ):
            _fail(EVIDENCE_INTEGRITY_FAILURE, "replay reference envelope is inconsistent")
        artifact = envelope.artifacts[0]
        if artifact.kind != MONITOR_RUN_REF_ARTIFACT_KIND or artifact.media_type != "application/json":
            _fail(EVIDENCE_INTEGRITY_FAILURE, "replay reference artifact is inconsistent")
        raw = evidence_store.read_artifact(
            artifact,
            maximum_bytes=MAX_EVIDENCE_READ_BYTES,
        )
        expected_raw = canonical_replay_json_bytes(reference.to_dict())
        if raw != expected_raw:
            _fail(EVIDENCE_INTEGRITY_FAILURE, "replay reference artifact differs from its reference")
        decoded = json.loads(raw.decode("utf-8"))
        try:
            stored = MonitorRunRef.from_value(decoded)
        except MonitorReplayError as error:
            _fail(EVIDENCE_INTEGRITY_FAILURE, "replay reference artifact is invalid")
            raise AssertionError from error
        if stored != reference or stored.schema != MONITOR_RUN_REF_SCHEMA:
            _fail(EVIDENCE_INTEGRITY_FAILURE, "replay reference artifact contradicts its reference")
    except AnalysisWorkflowError:
        raise
    except FileNotFoundError as error:
        _fail(EVIDENCE_INTEGRITY_FAILURE, "replay reference Evidence is absent")
        raise AssertionError from error
    except (EvidenceValidationError, MonitorReplayError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as error:
        _fail(EVIDENCE_INTEGRITY_FAILURE, "replay reference Evidence is corrupt")
        raise AssertionError from error
    except OSError as error:
        _fail(ENVIRONMENT_FAILURE, "replay reference Evidence could not be read")
        raise AssertionError from error
    except Exception as error:
        _fail(ENVIRONMENT_FAILURE, "replay reference Evidence could not be read")
        raise AssertionError from error


def _validate_diff_evidence(
    evidence_store: EvidenceStore,
    declaration: SourceChangeDeclaration,
    reference: MonitorRunRef,
) -> None:
    try:
        envelope = evidence_store.get_envelope(declaration.diff_evidence_id)
    except (FileNotFoundError, EvidenceValidationError) as error:
        _fail(EVIDENCE_INTEGRITY_FAILURE, "source-change diff Evidence is absent or corrupt")
        raise AssertionError from error
    except OSError as error:
        _fail(ENVIRONMENT_FAILURE, "source-change diff Evidence could not be read")
        raise AssertionError from error
    except Exception as error:
        _fail(ENVIRONMENT_FAILURE, "source-change diff Evidence could not be read")
        raise AssertionError from error
    if (
        envelope.identity.workspace_id != reference.origin_workspace_id
        or envelope.identity.project_id != reference.logical_project_id
        or envelope.identity.target_device != reference.target_device
        or declaration.diff_artifact not in envelope.artifacts
    ):
        _fail(INCOMPATIBLE_IDENTITY, "source-change diff Evidence identity is incompatible")
    try:
        evidence_store.read_artifact(
            declaration.diff_artifact, maximum_bytes=MAX_EVIDENCE_READ_BYTES
        )
    except EvidenceValidationError as error:
        _fail(EVIDENCE_INTEGRITY_FAILURE, "source-change diff artifact is corrupt")
        raise AssertionError from error
    except OSError as error:
        _fail(ENVIRONMENT_FAILURE, "source-change diff artifact could not be read")
        raise AssertionError from error
    except Exception as error:
        _fail(ENVIRONMENT_FAILURE, "source-change diff artifact could not be read")
        raise AssertionError from error


def _validate_inputs(
    paths: WorkspacePaths,
    evidence_store: EvidenceStore,
    request: AnalysisRequest,
    diagnostic_session_id: str,
    hypothesis_id: str,
    polarity: str,
    rationale: str,
    source_change_declaration: SourceChangeDeclaration | None,
) -> tuple[MonitorRunRef, MonitorRunRef, AnalysisLineage]:
    if (
        type(paths) is not WorkspacePaths
        or type(evidence_store) is not EvidenceStore
        or type(request) is not AnalysisRequest
        or type(diagnostic_session_id) is not str
        or type(hypothesis_id) is not str
        or type(polarity) is not str
        or type(rationale) is not str
        or (
            source_change_declaration is not None
            and type(source_change_declaration) is not SourceChangeDeclaration
        )
    ):
        _fail(ANALYSIS_WORKFLOW_INVALID, "analysis workflow arguments are invalid")
    _diagnostic_hash(diagnostic_session_id, "diagnostic session ID")
    _diagnostic_hash(hypothesis_id, "hypothesis ID")
    _safe_text(rationale, "rationale")
    if polarity not in {"supports", "refutes"}:
        _fail(ANALYSIS_WORKFLOW_INVALID, "polarity is invalid")
    before = request.before_run
    after = request.after_run
    if (
        before.scenario_role != "failed-before"
        or after.scenario_role != "fixed-after"
        or before.execution_source != MONITOR_REPLAY_EXECUTION_SOURCE
        or after.execution_source != MONITOR_REPLAY_EXECUTION_SOURCE
        or before.physical_transport_evidence is not False
        or after.physical_transport_evidence is not False
    ):
        _fail(INCOMPATIBLE_IDENTITY, "analysis runs are not non-physical replay roles")
    if (
        before.origin_workspace_id != after.origin_workspace_id
        or before.import_workspace_id != after.import_workspace_id
        or before.logical_project_id != after.logical_project_id
        or before.target_device != after.target_device
        or before.origin_session_id != after.origin_session_id
        or before.projected_session_id != after.projected_session_id
        or before.import_workspace_id != paths.workspace_id
        or after.import_workspace_id != paths.workspace_id
        or before.projected_session_id != paths.session_id
        or after.projected_session_id != paths.session_id
    ):
        _fail(INCOMPATIBLE_IDENTITY, "analysis run identities are incompatible")
    changed = (
        before.input_snapshot_sha256,
        before.build_id,
        before.elf_sha256,
    ) != (
        after.input_snapshot_sha256,
        after.build_id,
        after.elf_sha256,
    )
    declaration_id: str | None = None
    if changed:
        if source_change_declaration is None:
            _fail(INCOMPATIBLE_IDENTITY, "changed firmware requires a source declaration")
        declaration = cast(SourceChangeDeclaration, source_change_declaration)
        if (
            declaration.before_source_sha256 != before.input_snapshot_sha256
            or declaration.after_source_sha256 != after.input_snapshot_sha256
            or declaration.before_build_id != before.build_id
            or declaration.before_elf_sha256 != before.elf_sha256
            or declaration.after_build_id != after.build_id
            or declaration.after_elf_sha256 != after.elf_sha256
            or hypothesis_id not in declaration.claimed_hypothesis_ids
        ):
            _fail(INCOMPATIBLE_IDENTITY, "source declaration does not bridge the replay firmware")
        declaration_id = declaration.declaration_id
    elif source_change_declaration is not None:
        _fail(INCOMPATIBLE_IDENTITY, "identical firmware cannot carry a source declaration")
    try:
        lineage = AnalysisLineage.new(
            before_run=before,
            after_run=after,
            source_change_declaration_id=declaration_id,
        )
    except AnalysisError as error:
        _fail(INCOMPATIBLE_IDENTITY, "analysis lineage is incompatible")
        raise AssertionError from error
    return before, after, lineage


def _slice_static(batch: HistoryBatchSlice) -> tuple[object, ...]:
    return (
        batch.binding,
        batch.group_id,
        batch.group_revision,
        batch.run_id,
        batch.sequence,
        batch.scheduled_unix_ns,
        batch.captured_unix_ns,
        batch.latency_ns,
        batch.actual_rate_hz,
        batch.subscriber_drops,
        batch.history_drops,
        batch.deadline_drops,
        batch.batch_value_count,
    )


def _projected_binding(reference: MonitorRunRef, paths: WorkspacePaths) -> ObservationBinding:
    try:
        return ObservationBinding(
            workspace_id=paths.workspace_id,
            logical_project_id=reference.logical_project_id,
            session_id=paths.session_id,
            probe_id=reference.probe_id,
            target_device=reference.target_device,
            physical_target=reference.physical_target,
            build_id=reference.build_id,
            elf_sha256=reference.elf_sha256,
            input_snapshot_sha256=reference.input_snapshot_sha256,
            git_head=reference.git_head,
            git_dirty=reference.git_dirty,
            flash_session_id=reference.flash_session_id,
            lease_id=reference.lease_id,
            dwarf_sha256=reference.dwarf_sha256,
            svd_sha256=reference.svd_sha256,
        )
    except (TypeError, ValueError, OverflowError) as error:
        _fail(INCOMPATIBLE_IDENTITY, "projected replay binding is invalid")
        raise AssertionError from error


def _query_window(paths: WorkspacePaths, reference: MonitorRunRef) -> tuple[SampleBatch, ...]:
    history: HistoryStore | None = None
    try:
        history = HistoryStore(paths)
        cursor: str | None = None
        seen_cursors: set[str] = set()
        ordered_keys: list[tuple[UUID, int]] = []
        states: dict[tuple[UUID, int], list[object]] = {}
        closed: set[tuple[UUID, int]] = set()
        previous_key: tuple[UUID, int] | None = None
        total_values = 0
        while True:
            page_result: ProtocolResult[HistoryPage] = history.query_history(
                HistoryQuery(
                    session_id=paths.session_id,
                    start_ns=reference.start_captured_unix_ns,
                    end_ns=reference.end_captured_unix_ns_exclusive,
                    limit=MAX_HISTORY_VALUES,
                    cursor=cursor,
                    run_id=UUID(reference.projected_run_id),
                    group_id=UUID(reference.group_id),
                )
            )
            if not page_result.ok or type(page_result.data) is not HistoryPage:
                if page_result.code == "MONITOR_STORAGE_CORRUPT":
                    _fail(EVIDENCE_INTEGRITY_FAILURE, "monitor history is corrupt")
                if page_result.code.startswith("MONITOR_STORAGE"):
                    _fail(ENVIRONMENT_FAILURE, "monitor history could not be queried")
                _fail(ANALYSIS_WORKFLOW_INVALID, "monitor history query failed")
            page = cast(HistoryPage, page_result.data)
            if page.value_count != sum(len(item.values) for item in page.batches):
                _fail(INCOMPATIBLE_IDENTITY, "monitor history page count is inconsistent")
            if not page.batches and page.next_cursor is not None:
                _fail(INCOMPATIBLE_IDENTITY, "monitor history page cursor is inconsistent")
            for item in page.batches:
                if type(item) is not HistoryBatchSlice or not item.values:
                    _fail(INCOMPATIBLE_IDENTITY, "monitor history returned an invalid batch slice")
                key = (item.run_id, item.sequence)
                static = _slice_static(item)
                if previous_key is not None and key != previous_key:
                    closed.add(previous_key)
                if key in closed:
                    _fail(INCOMPATIBLE_IDENTITY, "monitor history batch slices are not contiguous")
                state = states.get(key)
                if state is None:
                    if item.start_ordinal != 0:
                        _fail(INCOMPATIBLE_IDENTITY, "monitor history starts with a partial batch")
                    states[key] = [static, list(item.values), len(item.values)]
                    ordered_keys.append(key)
                else:
                    if state[0] != static or item.start_ordinal != state[2]:
                        _fail(INCOMPATIBLE_IDENTITY, "monitor history batch slices contradict")
                    cast(list[object], state[1]).extend(item.values)
                    state[2] = cast(int, state[2]) + len(item.values)
                total_values += len(item.values)
                if total_values > MAX_HISTORY_VALUES:
                    _fail(INCOMPATIBLE_IDENTITY, "monitor history window exceeds its value limit")
                previous_key = key
            next_cursor = page.next_cursor
            if next_cursor is None:
                break
            if next_cursor in seen_cursors:
                _fail(INCOMPATIBLE_IDENTITY, "monitor history cursor repeated")
            seen_cursors.add(next_cursor)
            cursor = next_cursor

        expected_keys = [
            (UUID(reference.projected_run_id), sequence)
            for sequence in range(reference.start_sequence, reference.end_sequence_exclusive)
        ]
        if ordered_keys != expected_keys or len(ordered_keys) != len(reference.projected_batch_sha256s):
            _fail(INCOMPATIBLE_IDENTITY, "monitor history window does not match its run reference")
        expected_binding = _projected_binding(reference, paths)
        result: list[SampleBatch] = []
        previous_captured: int | None = None
        for index, key in enumerate(ordered_keys):
            static, values, count = states[key]
            if count != cast(tuple[object, ...], static)[-1]:
                _fail(INCOMPATIBLE_IDENTITY, "monitor history batch is incomplete")
            (
                binding,
                group_id,
                group_revision,
                run_id,
                sequence,
                scheduled_unix_ns,
                captured_unix_ns,
                latency_ns,
                actual_rate_hz,
                subscriber_drops,
                history_drops,
                deadline_drops,
                _batch_value_count,
            ) = cast(tuple[object, ...], static)
            if (
                binding != expected_binding
                or group_id != UUID(reference.group_id)
                or run_id != UUID(reference.projected_run_id)
                or sequence != reference.start_sequence + index
                or not reference.start_captured_unix_ns <= cast(int, captured_unix_ns) < reference.end_captured_unix_ns_exclusive
                or (previous_captured is not None and cast(int, captured_unix_ns) < previous_captured)
            ):
                _fail(INCOMPATIBLE_IDENTITY, "monitor history batch identity is incompatible")
            try:
                batch = SampleBatch(
                    binding=cast(ObservationBinding, binding),
                    group_id=cast(UUID, group_id),
                    group_revision=cast(int, group_revision),
                    run_id=cast(UUID, run_id),
                    sequence=cast(int, sequence),
                    scheduled_unix_ns=cast(int, scheduled_unix_ns),
                    captured_unix_ns=cast(int, captured_unix_ns),
                    latency_ns=cast(int, latency_ns),
                    actual_rate_hz=cast(float, actual_rate_hz),
                    subscriber_drops=cast(int, subscriber_drops),
                    history_drops=cast(int, history_drops),
                    deadline_drops=cast(int, deadline_drops),
                    values=tuple(cast(list[object], values)),
                )
            except (TypeError, ValueError, OverflowError) as error:
                _fail(INCOMPATIBLE_IDENTITY, "monitor history batch is invalid")
                raise AssertionError from error
            digest = sha256(canonical_replay_json_bytes(batch.to_dict())).hexdigest()
            if digest != reference.projected_batch_sha256s[index]:
                _fail(INCOMPATIBLE_IDENTITY, "monitor history batch digest differs from its run reference")
            previous_captured = cast(int, captured_unix_ns)
            result.append(batch)
        return tuple(result)
    except AnalysisWorkflowError:
        raise
    except (ValueError, TypeError, OverflowError, MonitorReplayError) as error:
        _fail(INCOMPATIBLE_IDENTITY, "monitor history window is invalid")
        raise AssertionError from error
    except OSError as error:
        _fail(ENVIRONMENT_FAILURE, "monitor history could not be read")
        raise AssertionError from error
    except Exception as error:
        _fail(ENVIRONMENT_FAILURE, "monitor history could not be read")
        raise AssertionError from error
    finally:
        if history is not None:
            history.close()


def _artifact_for_payload(payload: bytes, *, kind: str) -> ArtifactRef:
    digest = sha256(payload).hexdigest()
    return ArtifactRef(
        sha256=digest,
        size_bytes=len(payload),
        relative_path=f"objects/sha256/{digest[:2]}/{digest}",
        kind=kind,
        media_type="application/json",
    )


def _analysis_metadata(
    result: AnalysisResult,
    before: MonitorRunRef,
    after: MonitorRunRef,
    declaration: SourceChangeDeclaration | None,
) -> dict[str, object]:
    return {
        "analysis_id": result.analysis_id,
        "before_run_id": before.run_ref_sha256,
        "after_run_id": after.run_ref_sha256,
        "source_change_declaration_id": None if declaration is None else declaration.declaration_id,
        "origin_workspace_id": after.origin_workspace_id,
        "import_workspace_id": after.import_workspace_id,
        "origin_session_id": after.origin_session_id,
        "execution_source": MONITOR_REPLAY_EXECUTION_SOURCE,
        "physical_transport_evidence": False,
    }


def _marker_metadata(
    marker: DiagnosticMarker,
    analysis_evidence_id: str,
    after: MonitorRunRef,
) -> dict[str, object]:
    return {
        "marker_id": marker.marker_id,
        "analysis_id": marker.analysis_id,
        "analysis_evidence_id": analysis_evidence_id,
        "origin_workspace_id": after.origin_workspace_id,
        "import_workspace_id": after.import_workspace_id,
        "origin_session_id": after.origin_session_id,
        "execution_source": MONITOR_REPLAY_EXECUTION_SOURCE,
        "physical_transport_evidence": False,
    }


def _preflight_checkpoint(
    evidence_store: EvidenceStore,
    root: RootRecord,
    envelope: EvidenceEnvelope,
) -> None:
    try:
        try:
            existing_root = get_root(evidence_store, root.root_type, root.root_id)
        except EvidenceValidationError as error:
            if error.message == "evidence root is absent":
                existing_root = None
            else:
                _fail(EVIDENCE_INTEGRITY_FAILURE, "derived Evidence root is corrupt")
        if existing_root is not None and existing_root.to_dict() != root.to_dict():
            _fail(OPERATION_CONFLICT, "derived Evidence root has a different intent")
        try:
            existing_envelope = evidence_store.get_envelope(str(envelope.evidence_id))
        except FileNotFoundError:
            existing_envelope = None
        if existing_envelope is not None and existing_envelope.to_dict() != envelope.to_dict():
            _fail(OPERATION_CONFLICT, "derived Evidence envelope has different bytes")
    except AnalysisWorkflowError:
        raise
    except OSError as error:
        _fail(ENVIRONMENT_FAILURE, "derived Evidence preflight failed")
        raise AssertionError from error
    except EvidenceValidationError as error:
        _fail(EVIDENCE_INTEGRITY_FAILURE, "derived Evidence preflight failed")
        raise AssertionError from error
    except Exception as error:
        _fail(ENVIRONMENT_FAILURE, "derived Evidence preflight failed")
        raise AssertionError from error


def _publish_checkpoint(
    evidence_store: EvidenceStore,
    root: RootRecord,
    envelope: EvidenceEnvelope,
    payload: bytes,
    *,
    filename: str,
    kind: str,
) -> None:
    try:
        with tempfile.TemporaryDirectory(prefix="stm32-monitor-analysis-") as directory:
            source = Path(directory) / filename
            source.write_bytes(payload)
            artifact = evidence_store.ingest_file(
                source,
                kind=kind,
                media_type="application/json",
            )
        if artifact != envelope.artifacts[0]:
            _fail(EVIDENCE_INTEGRITY_FAILURE, "derived Evidence artifact identity differs")
        evidence_store.put_envelope(envelope)
        put_root(evidence_store, root)
        if get_root(evidence_store, root.root_type, root.root_id).to_dict() != root.to_dict():
            _fail(EVIDENCE_INTEGRITY_FAILURE, "derived Evidence root failed reload validation")
        reloaded = evidence_store.get_envelope(str(envelope.evidence_id))
        if reloaded.to_dict() != envelope.to_dict():
            _fail(EVIDENCE_INTEGRITY_FAILURE, "derived Evidence envelope failed reload validation")
        if evidence_store.read_artifact(reloaded.artifacts[0], maximum_bytes=MAX_EVIDENCE_READ_BYTES) != payload:
            _fail(EVIDENCE_INTEGRITY_FAILURE, "derived Evidence artifact failed reload validation")
    except AnalysisWorkflowError:
        raise
    except EvidenceValidationError as error:
        if "different canonical bytes" in error.message:
            _fail(OPERATION_CONFLICT, "derived Evidence root has a different intent")
        _fail(EVIDENCE_INTEGRITY_FAILURE, "derived Evidence publication failed")
        raise AssertionError from error
    except OSError as error:
        _fail(ENVIRONMENT_FAILURE, "derived Evidence publication failed")
        raise AssertionError from error
    except Exception as error:
        _fail(ENVIRONMENT_FAILURE, "derived Evidence publication failed")
        raise AssertionError from error


def _validate_published_derived(
    evidence_store: EvidenceStore,
    *,
    root_type: str,
    root_id: str,
    expected_envelope: EvidenceEnvelope,
    payload: bytes,
) -> None:
    """Validate an upstream derived checkpoint without repairing or adopting it."""
    root = _load_root(evidence_store, root_type, root_id)
    expected_root = RootRecord(root_type, root_id, str(expected_envelope.evidence_id), dict(expected_envelope.metadata))
    if root.to_dict() != expected_root.to_dict():
        _fail(EVIDENCE_INTEGRITY_FAILURE, "upstream derived root contradicts publication")
    try:
        envelope = evidence_store.get_envelope(str(expected_envelope.evidence_id))
        if envelope.to_dict() != expected_envelope.to_dict():
            _fail(EVIDENCE_INTEGRITY_FAILURE, "upstream derived envelope is corrupt")
        if len(envelope.artifacts) != 1:
            _fail(EVIDENCE_INTEGRITY_FAILURE, "upstream derived artifact is invalid")
        actual = evidence_store.read_artifact(envelope.artifacts[0], maximum_bytes=MAX_EVIDENCE_READ_BYTES)
    except AnalysisWorkflowError:
        raise
    except FileNotFoundError as error:
        _fail(EVIDENCE_INTEGRITY_FAILURE, "upstream derived Evidence is absent")
        raise AssertionError from error
    except EvidenceValidationError as error:
        _fail(EVIDENCE_INTEGRITY_FAILURE, "upstream derived Evidence is corrupt")
        raise AssertionError from error
    except OSError as error:
        _fail(ENVIRONMENT_FAILURE, "upstream derived Evidence could not be read")
        raise AssertionError from error
    except Exception as error:
        _fail(ENVIRONMENT_FAILURE, "upstream derived Evidence could not be read")
        raise AssertionError from error
    if actual != payload:
        _fail(EVIDENCE_INTEGRITY_FAILURE, "upstream derived artifact bytes differ")


def _test_identity_matches_reference(manifest: object, reference: MonitorRunRef) -> bool:
    identity = getattr(manifest, "identity", None)
    if not isinstance(identity, EvidenceIdentity):
        return False
    return (
        identity.workspace_id == reference.origin_workspace_id
        and str(identity.project_id) == reference.logical_project_id
        and identity.build_id == reference.build_id
        and identity.elf_sha256 == reference.elf_sha256
        and identity.target_device == reference.target_device
        and identity.input_snapshot_sha256 == reference.input_snapshot_sha256
        and identity.git_commit == reference.git_head
        and identity.git_dirty == reference.git_dirty
    )


def compare_monitor_runs(
    paths: WorkspacePaths,
    evidence_store: EvidenceStore,
    request: AnalysisRequest,
    diagnostic_session_id: str,
    hypothesis_id: str,
    polarity: str,
    rationale: str,
    source_change_declaration: SourceChangeDeclaration | None = None,
) -> AnalysisPublication:
    """Compare two imported replay windows and publish immutable analysis Evidence."""

    before, after, lineage = _validate_inputs(
        paths,
        evidence_store,
        request,
        diagnostic_session_id,
        hypothesis_id,
        polarity,
        rationale,
        source_change_declaration,
    )
    declaration = source_change_declaration
    if declaration is not None:
        _validate_diff_evidence(evidence_store, declaration, after)
    before_transcript = _validate_transcript(evidence_store, before)
    after_transcript = _validate_transcript(evidence_store, after)
    before_batches = _query_window(paths, before)
    after_batches = _query_window(paths, after)
    try:
        computation = analyze_monitor_windows(request, before_batches, after_batches)
        result = AnalysisResult.new(request=request, computation=computation, lineage=lineage)
    except AnalysisError as error:
        _fail(INCOMPATIBLE_IDENTITY, "analysis windows are incompatible")
        raise AssertionError from error

    analysis_payload = canonical_replay_json_bytes(result.to_dict())
    analysis_artifact = _artifact_for_payload(analysis_payload, kind="monitor-analysis")
    analysis_metadata = _analysis_metadata(result, before, after, declaration)
    try:
        analysis_envelope = EvidenceEnvelope(
            identity=_identity_for_ref(after),
            operation=_MONITOR_ANALYSIS_OPERATION,
            produced_at_utc=unix_ns_to_utc(after.end_captured_unix_ns_exclusive - 1),
            parents=(
                before_transcript.evidence_id,
                after_transcript.evidence_id,
                *(() if declaration is None else (declaration.diff_evidence_id,)),
            ),
            artifacts=(analysis_artifact,),
            metadata=analysis_metadata,
        )
        analysis_root = RootRecord(
            root_type=_MONITOR_ANALYSIS_ROOT,
            root_id=result.analysis_id,
            manifest_id=str(analysis_envelope.evidence_id),
            metadata=analysis_metadata,
        )
        analysis_ref = AnalysisEvidenceRef.new(
            analysis_id=result.analysis_id,
            evidence_id=str(analysis_envelope.evidence_id),
        )
        label = (
            "change-observed"
            if result.changed is True
            else "no-change-observed"
            if result.changed is False
            else "analysis-inconclusive"
        )
        marker = DiagnosticMarker.new(
            analysis_id=result.analysis_id,
            analysis_evidence_id=analysis_ref.evidence_id,
            diagnostic_session_id=diagnostic_session_id,
            hypothesis_id=hypothesis_id,
            polarity=polarity,
            label=label,
            rationale=rationale,
        )
        marker_payload = canonical_replay_json_bytes(marker.to_dict())
        marker_artifact = _artifact_for_payload(marker_payload, kind="diagnostic-marker")
        marker_metadata = _marker_metadata(marker, analysis_ref.evidence_id, after)
        marker_envelope = EvidenceEnvelope(
            identity=_identity_for_ref(after),
            operation=_DIAGNOSTIC_MARKER_OPERATION,
            produced_at_utc=analysis_envelope.produced_at_utc,
            parents=(analysis_ref.evidence_id,),
            artifacts=(marker_artifact,),
            metadata=marker_metadata,
        )
        marker_root = RootRecord(
            root_type=_DIAGNOSTIC_MARKER_ROOT,
            root_id=marker.marker_id,
            manifest_id=str(marker_envelope.evidence_id),
            metadata=marker_metadata,
        )
        marker_ref = DiagnosticMarkerRef.new(
            marker_id=marker.marker_id,
            marker_evidence_id=str(marker_envelope.evidence_id),
            analysis_id=marker.analysis_id,
            analysis_evidence_id=marker.analysis_evidence_id,
            diagnostic_session_id=marker.diagnostic_session_id,
            hypothesis_id=marker.hypothesis_id,
            polarity=marker.polarity,
            label=marker.label,
            rationale=marker.rationale,
        )
    except (EvidenceValidationError, ValueError, TypeError, OverflowError) as error:
        _fail(ANALYSIS_WORKFLOW_INVALID, "analysis publication values are invalid")
        raise AssertionError from error

    _preflight_checkpoint(evidence_store, analysis_root, analysis_envelope)
    _preflight_checkpoint(evidence_store, marker_root, marker_envelope)
    _publish_checkpoint(
        evidence_store,
        analysis_root,
        analysis_envelope,
        analysis_payload,
        filename="analysis.json",
        kind="monitor-analysis",
    )
    _publish_checkpoint(
        evidence_store,
        marker_root,
        marker_envelope,
        marker_payload,
        filename="marker.json",
        kind="diagnostic-marker",
    )
    return AnalysisPublication(result, analysis_ref, marker, marker_ref)


def export_analysis_bundle(
    paths: WorkspacePaths,
    evidence_store: EvidenceStore,
    request: AnalysisRequest,
    publication: AnalysisPublication,
    failed_before_test_run_id: str,
    fixed_after_test_run_id: str,
    source_change_declaration: SourceChangeDeclaration | None = None,
) -> tuple[bytes, AnalysisBundleRef]:
    """Export one deterministic, rooted projection of an accepted replay analysis."""
    if type(publication) is not AnalysisPublication:
        _fail(ANALYSIS_WORKFLOW_INVALID, "analysis publication is invalid")
    if type(failed_before_test_run_id) is not str or type(fixed_after_test_run_id) is not str:
        _fail(ANALYSIS_WORKFLOW_INVALID, "test run IDs are invalid")
    marker = publication.diagnostic_marker
    before, after, lineage = _validate_inputs(
        paths, evidence_store, request,
        marker.diagnostic_session_id, marker.hypothesis_id,
        marker.polarity, marker.rationale, source_change_declaration,
    )
    if before.scenario_role != "failed-before":
        _fail(INCOMPATIBLE_IDENTITY, "failed-before replay identity is invalid")
    if after.scenario_role != "fixed-after":
        _fail(INCOMPATIBLE_IDENTITY, "fixed-after replay identity is invalid")
    if publication.analysis_result.request_digest != request.request_digest:
        _fail(INCOMPATIBLE_IDENTITY, "analysis request does not match publication")
    if publication.analysis_result.identity != lineage:
        _fail(INCOMPATIBLE_IDENTITY, "analysis lineage does not match publication")
    if publication.analysis_evidence_ref.analysis_id != publication.analysis_result.analysis_id:
        _fail(INCOMPATIBLE_IDENTITY, "analysis evidence does not match publication")
    if marker.analysis_id != publication.analysis_result.analysis_id:
        _fail(INCOMPATIBLE_IDENTITY, "diagnostic marker does not match publication")
    if source_change_declaration is not None:
        _validate_diff_evidence(evidence_store, source_change_declaration, after)
    before_transcript = _validate_transcript(evidence_store, before)
    after_transcript = _validate_transcript(evidence_store, after)

    analysis_payload = canonical_replay_json_bytes(publication.analysis_result.to_dict())
    analysis_artifact = _artifact_for_payload(analysis_payload, kind=_MONITOR_ANALYSIS_ROOT)
    analysis_metadata = _analysis_metadata(
        publication.analysis_result, before, after, source_change_declaration
    )
    try:
        analysis_envelope = EvidenceEnvelope(
            identity=_identity_for_ref(after), operation=_MONITOR_ANALYSIS_OPERATION,
            produced_at_utc=unix_ns_to_utc(after.end_captured_unix_ns_exclusive - 1),
            parents=(before_transcript.evidence_id, after_transcript.evidence_id,
                     *(() if source_change_declaration is None else (source_change_declaration.diff_evidence_id,))),
            artifacts=(analysis_artifact,), metadata=analysis_metadata,
        )
        marker_payload = canonical_replay_json_bytes(marker.to_dict())
        marker_artifact = _artifact_for_payload(marker_payload, kind=_DIAGNOSTIC_MARKER_ROOT)
        marker_metadata = _marker_metadata(marker, publication.analysis_evidence_ref.evidence_id, after)
        marker_envelope = EvidenceEnvelope(
            identity=_identity_for_ref(after), operation=_DIAGNOSTIC_MARKER_OPERATION,
            produced_at_utc=analysis_envelope.produced_at_utc,
            parents=(publication.analysis_evidence_ref.evidence_id,),
            artifacts=(marker_artifact,), metadata=marker_metadata,
        )
    except (EvidenceValidationError, ValueError, TypeError, OverflowError) as error:
        _fail(EVIDENCE_INTEGRITY_FAILURE, "upstream derived Evidence is invalid")
        raise AssertionError from error
    if publication.analysis_evidence_ref.evidence_id != str(analysis_envelope.evidence_id):
        _fail(EVIDENCE_INTEGRITY_FAILURE, "analysis evidence reference does not match stored envelope")
    if publication.diagnostic_marker_ref.marker_evidence_id != str(marker_envelope.evidence_id):
        _fail(EVIDENCE_INTEGRITY_FAILURE, "marker evidence reference does not match stored envelope")
    _validate_published_derived(
        evidence_store, root_type=_MONITOR_ANALYSIS_ROOT,
        root_id=publication.analysis_result.analysis_id,
        expected_envelope=analysis_envelope, payload=analysis_payload,
    )
    _validate_published_derived(
        evidence_store, root_type=_DIAGNOSTIC_MARKER_ROOT,
        root_id=marker.marker_id,
        expected_envelope=marker_envelope, payload=marker_payload,
    )

    try:
        repository = TestRunRepository(evidence_store)
        before_test = repository.load(failed_before_test_run_id)
        after_test = repository.load(fixed_after_test_run_id)
    except AnalysisWorkflowError:
        raise
    except (OSError, PermissionError) as error:
        _fail(ENVIRONMENT_FAILURE, "test run evidence could not be read")
        raise AssertionError from error
    except Exception as error:
        _fail(EVIDENCE_INTEGRITY_FAILURE, "test run evidence is absent or corrupt")
        raise AssertionError from error
    for loaded, reference, state, run_id in (
        (before_test, before, "failed", failed_before_test_run_id),
        (after_test, after, "passed", fixed_after_test_run_id),
    ):
        manifest = loaded.manifest
        if (manifest.run_id != run_id or manifest.mode != "target" or manifest.transport != "replay"
                or manifest.state != state or not _test_identity_matches_reference(manifest, reference)):
            _fail(INCOMPATIBLE_IDENTITY, "TestRun does not match replay reference")
        expected_target_root = {
            "mode": "target", "state": state, "execution_source": "replay",
            "physical_transport_evidence": False,
            "origin_workspace_id": reference.origin_workspace_id,
            "import_workspace_id": paths.workspace_id,
        }
        if loaded.root.metadata != expected_target_root:
            _fail(INCOMPATIBLE_IDENTITY, "TestRun root metadata does not match replay reference")
    if before_test.manifest.identity.session_id != after_test.manifest.identity.session_id:
        _fail(INCOMPATIBLE_IDENTITY, "Target TestRuns do not share a session")

    digest_table = [
        {"role": "before-run-ref", "sha256": before.run_ref_sha256},
        {"role": "after-run-ref", "sha256": after.run_ref_sha256},
        {"role": "before-transcript-evidence", "sha256": before.transcript_evidence_id},
        {"role": "after-transcript-evidence", "sha256": after.transcript_evidence_id},
        {"role": "analysis-request", "sha256": request.request_digest},
        {"role": "analysis-result", "sha256": publication.analysis_result.analysis_id},
        {"role": "analysis-evidence", "sha256": publication.analysis_evidence_ref.evidence_id},
        {"role": "diagnostic-marker", "sha256": marker.marker_id},
        {"role": "marker-evidence", "sha256": publication.diagnostic_marker_ref.marker_evidence_id},
    ]
    if source_change_declaration is not None:
        digest_table.append({"role": "source-change-declaration", "sha256": source_change_declaration.declaration_id})
    payload_document = {
        "schema": _ANALYSIS_BUNDLE_SCHEMA,
        "before_run": before.to_dict(),
        "after_run": after.to_dict(),
        "analysis_request": request.to_dict(),
        "analysis_result": publication.analysis_result.to_dict(),
        "analysis_evidence_ref": publication.analysis_evidence_ref.to_dict(),
        "diagnostic_marker": marker.to_dict(),
        "diagnostic_marker_ref": publication.diagnostic_marker_ref.to_dict(),
        "failed_before_test_run_id": failed_before_test_run_id,
        "fixed_after_test_run_id": fixed_after_test_run_id,
        "source_change_declaration_id": None if source_change_declaration is None else source_change_declaration.declaration_id,
        "digest_table": digest_table,
    }
    try:
        payload = canonical_replay_json_bytes(payload_document)
        bundle_id = sha256(payload).hexdigest()
        artifact = _artifact_for_payload(payload, kind=_ANALYSIS_BUNDLE_ROOT)
        metadata = {
            "bundle_id": bundle_id, "analysis_id": publication.analysis_result.analysis_id,
            "failed_before_test_run_id": failed_before_test_run_id,
            "fixed_after_test_run_id": fixed_after_test_run_id,
            "source_change_declaration_id": None if source_change_declaration is None else source_change_declaration.declaration_id,
            "origin_workspace_id": after.origin_workspace_id, "import_workspace_id": after.import_workspace_id,
            "origin_session_id": after.origin_session_id, "execution_source": "replay",
            "physical_transport_evidence": False,
        }
        envelope = EvidenceEnvelope(
            identity=_identity_for_ref(after), operation=_ANALYSIS_BUNDLE_OPERATION,
            produced_at_utc=unix_ns_to_utc(after.end_captured_unix_ns_exclusive - 1),
            parents=(before_transcript.evidence_id, after_transcript.evidence_id,
                     publication.analysis_evidence_ref.evidence_id,
                     publication.diagnostic_marker_ref.marker_evidence_id,
                     *(() if source_change_declaration is None else (source_change_declaration.diff_evidence_id,))),
            artifacts=(artifact,), metadata=metadata,
        )
        root = RootRecord(_ANALYSIS_BUNDLE_ROOT, bundle_id, str(envelope.evidence_id), metadata)
    except (EvidenceValidationError, ValueError, TypeError, OverflowError) as error:
        _fail(ANALYSIS_WORKFLOW_INVALID, "analysis bundle values are invalid")
        raise AssertionError from error
    _preflight_checkpoint(evidence_store, root, envelope)
    _publish_checkpoint(evidence_store, root, envelope, payload, filename="analysis-bundle.json", kind=_ANALYSIS_BUNDLE_ROOT)
    return payload, AnalysisBundleRef(_ANALYSIS_BUNDLE_REF_SCHEMA, bundle_id, str(envelope.evidence_id), artifact)


__all__ = [
    "ANALYSIS_WORKFLOW_INVALID",
    "EVIDENCE_INTEGRITY_FAILURE",
    "ENVIRONMENT_FAILURE",
    "INCOMPATIBLE_IDENTITY",
    "OPERATION_CONFLICT",
    "AnalysisBundleRef",
    "AnalysisPublication",
    "AnalysisWorkflowError",
    "compare_monitor_runs",
    "export_analysis_bundle",
]
