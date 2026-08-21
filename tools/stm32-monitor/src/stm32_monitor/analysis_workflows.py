"""Public History/Evidence workflow for bounded replay analysis publication."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
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
from stm32_toolkit.evidence import gc as _evidence_gc
from stm32_toolkit.evidence.gc import RootRecord, get_root, put_root
from stm32_toolkit.evidence.store import EvidenceStore, MAX_EVIDENCE_READ_BYTES
from stm32_toolkit.paths import WorkspacePaths

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
_REPLAY_ROLES = {"failed-before", "fixed-after"}

# The evidence GC registry is deliberately closed at the Toolkit layer.  These two
# roots are the only derived roots owned by this bounded publication boundary; add
# them before constructing RootRecord values so the existing authoritative root
# validation/GC machinery handles them exactly like the pre-registered roots.
_evidence_gc.REGISTERED_ROOT_TYPES = frozenset(
    (*_evidence_gc.REGISTERED_ROOT_TYPES, _MONITOR_ANALYSIS_ROOT, _DIAGNOSTIC_MARKER_ROOT)
)


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
    except (EvidenceValidationError, MonitorReplayError, UnicodeError, json.JSONDecodeError, TypeError, ValueError, OSError) as error:
        _fail(EVIDENCE_INTEGRITY_FAILURE, "replay transcript artifact is corrupt")
        raise AssertionError from error
    except Exception as error:
        _fail(ENVIRONMENT_FAILURE, "replay transcript artifact could not be read")
        raise AssertionError from error
    if raw not in (canonical, canonical + b"\n"):
        _fail(EVIDENCE_INTEGRITY_FAILURE, "replay transcript artifact is not canonical")
    if (
        document.source != "toolkit-generated-probe-v2-replay"
        or document.physical_transport_evidence is not False
        or document.scenario_role != reference.scenario_role
        or document.fixture_sha256 != reference.fixture_sha256
        or document.binding.workspace_id != reference.origin_workspace_id
        or document.binding.logical_project_id != reference.logical_project_id
        or document.binding.session_id != reference.origin_session_id
        or document.binding.target_device != reference.target_device
        or document.binding.build_id != reference.build_id
        or document.binding.elf_sha256 != reference.elf_sha256
        or document.binding.input_snapshot_sha256 != reference.input_snapshot_sha256
        or document.binding.git_head != reference.git_head
        or document.binding.git_dirty is not reference.git_dirty
        or tuple(str(batch.run_id) for batch in document.batches) != (reference.origin_run_id,) * len(document.batches)
        or tuple(batch.sequence for batch in document.batches)
        != tuple(range(reference.start_sequence, reference.end_sequence_exclusive))
    ):
        _fail(EVIDENCE_INTEGRITY_FAILURE, "replay transcript does not match its run reference")
    return envelope


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


__all__ = [
    "ANALYSIS_WORKFLOW_INVALID",
    "EVIDENCE_INTEGRITY_FAILURE",
    "ENVIRONMENT_FAILURE",
    "INCOMPATIBLE_IDENTITY",
    "OPERATION_CONFLICT",
    "AnalysisPublication",
    "AnalysisWorkflowError",
    "compare_monitor_runs",
]
