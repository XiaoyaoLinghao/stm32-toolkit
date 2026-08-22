"""Closed, non-physical Probe-v2 replay ingestion for the Monitor module."""

from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import json
import math
import re
import tempfile
import unicodedata
from collections.abc import Mapping
from pathlib import Path
from typing import cast
from uuid import UUID

from stm32_toolkit.evidence import (
    ArtifactRef,
    EvidenceEnvelope,
    EvidenceIdentity,
    EvidenceValidationError,
)
from stm32_toolkit.evidence.model import (
    MAX_JSON_DEPTH as _EVIDENCE_JSON_DEPTH,
)
from stm32_toolkit.evidence.gc import RootRecord, get_root, put_root
from stm32_toolkit.monitor_replay_contract import (
    MAX_REPLAY_BATCHES,
    MAX_REPLAY_DOCUMENT_BYTES,
    MONITOR_REPLAY_EXECUTION_SOURCE,
    MONITOR_REPLAY_FLASH_SESSION_ID,
    MONITOR_REPLAY_LEASE_ID,
    MONITOR_REPLAY_PHYSICAL_TARGET,
    MONITOR_REPLAY_PROBE_ID,
    MONITOR_REPLAY_SCHEMA,
    MONITOR_REPLAY_SOURCE,
    MONITOR_RUN_REF_SCHEMA,
    MONITOR_RUN_REF_SCHEMA_V2,
    ReplayContractError,
    canonical_replay_json_bytes as _contract_canonical_replay_json_bytes,
    decode_canonical_json_bytes,
    validate_replay_document,
    validate_run_reference,
)
from stm32_toolkit.evidence.store import MAX_EVIDENCE_READ_BYTES, EvidenceStore
from stm32_toolkit.project_model import ProjectManifestError, load_project_model
from stm32_toolkit.testing.publication import TestRunRepository
from stm32_toolkit.paths import WorkspacePaths, require_safe_session_id

from .history import (
    HistoryBatchSlice,
    HistoryPage,
    HistoryQuery,
    HistoryStore,
    MAX_HISTORY_VALUES,
)
from .models import (
    MAX_JSON_STRING_CHARS as _MONITOR_JSON_STRING_CHARS,
    MAX_SIGNED_INT64,
    ObservationBinding,
    SampleBatch,
    SampleValue,
    WatchItem,
    unix_ns_to_utc,
)


MONITOR_REPLAY_IMPORT_OPERATION = "monitor-replay-import"
MONITOR_RUN_ROOT_TYPE = "monitor-run"
MONITOR_RUN_REF_ROOT_TYPE = "monitor-run-ref"
MONITOR_RUN_REF_OPERATION = "monitor-run-ref"
MONITOR_RUN_REF_ARTIFACT_KIND = "monitor-run-ref"
MONITOR_PHYSICAL_INVALID = "MONITOR_PHYSICAL_INVALID"
INCOMPATIBLE_IDENTITY = "INCOMPATIBLE_IDENTITY"
MONITOR_PHYSICAL_TRANSCRIPT_SCHEMA = "stm32-monitor-physical-transcript/1"
MONITOR_PHYSICAL_SOURCE = "toolkit-live-history"
MONITOR_PHYSICAL_WINDOW_OPERATION = "monitor-physical-window"
MAX_PHYSICAL_TRANSCRIPT_BYTES = MAX_EVIDENCE_READ_BYTES
_PHYSICAL_JSON_NODES = 1_000_000

MONITOR_REPLAY_INVALID = "MONITOR_REPLAY_INVALID"
EVIDENCE_INTEGRITY_FAILURE = "EVIDENCE_INTEGRITY_FAILURE"
OPERATION_CONFLICT = "OPERATION_CONFLICT"
ENVIRONMENT_FAILURE = "ENVIRONMENT_FAILURE"
_ERROR_CODES = frozenset(
    {
        MONITOR_REPLAY_INVALID,
        EVIDENCE_INTEGRITY_FAILURE,
        OPERATION_CONFLICT,
        ENVIRONMENT_FAILURE,
        MONITOR_PHYSICAL_INVALID,
        INCOMPATIBLE_IDENTITY,
    }
)
_ROLES = frozenset({"failed-before", "fixed-after"})
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_GIT_SHA = re.compile(r"[0-9a-f]{40}\Z")
_REF_FIELDS = (
    "schema",
    "operation_id",
    "scenario_role",
    "execution_source",
    "physical_transport_evidence",
    "origin_workspace_id",
    "import_workspace_id",
    "logical_project_id",
    "origin_session_id",
    "projected_session_id",
    "origin_run_id",
    "projected_run_id",
    "target_device",
    "probe_id",
    "physical_target",
    "build_id",
    "elf_sha256",
    "input_snapshot_sha256",
    "git_head",
    "git_dirty",
    "flash_session_id",
    "lease_id",
    "dwarf_sha256",
    "svd_sha256",
    "group_id",
    "group_revision",
    "start_sequence",
    "end_sequence_exclusive",
    "start_captured_unix_ns",
    "end_captured_unix_ns_exclusive",
    "fixture_sha256",
    "projected_batch_sha256s",
    "transcript_evidence_id",
    "run_ref_sha256",
)
_REF_FIELDS_V2 = tuple(
    "source_record_sha256" if field == "fixture_sha256" else field
    for field in _REF_FIELDS
)
_EVIDENCE_METADATA_FIELDS = frozenset(
    {
        "operation_id",
        "scenario_role",
        "origin_workspace_id",
        "import_workspace_id",
        "origin_run_id",
        "projected_run_id",
        "fixture_sha256",
        "execution_source",
        "physical_transport_evidence",
    }
)
_ROOT_METADATA_FIELDS = frozenset(
    {
        "fixture_sha256",
        "run_ref_sha256",
        "origin_workspace_id",
        "import_workspace_id",
        "execution_source",
        "physical_transport_evidence",
    }
)
_REFERENCE_ROOT_METADATA_FIELDS = frozenset(
    {
        "operation_id",
        "run_ref_sha256",
        "fixture_sha256",
        "scenario_role",
        "origin_workspace_id",
        "import_workspace_id",
        "execution_source",
        "physical_transport_evidence",
    }
)


class MonitorReplayError(ValueError):
    """A bounded public failure from the Monitor replay boundary."""

    def __init__(self, code: str, message: str) -> None:
        if type(code) is not str or code not in _ERROR_CODES:
            raise ValueError("unknown monitor replay error code")
        if type(message) is not str or not message or len(message) > 256:
            raise ValueError("monitor replay error message is invalid")
        super().__init__(message)
        self._code = code
        self._message = message

    @property
    def code(self) -> str:
        return self._code

    @property
    def message(self) -> str:
        return self._message


def _fail(code: str, message: str) -> None:
    raise MonitorReplayError(code, message)


def canonical_replay_json_bytes(value: object) -> bytes:
    """Return the bounded canonical JSON bytes used by replay digests."""

    if type(value) is MonitorReplayDocument or type(value) is MonitorRunRef:
        value = value.to_dict()
    try:
        return _contract_canonical_replay_json_bytes(value)
    except ReplayContractError as error:
        raise MonitorReplayError(MONITOR_REPLAY_INVALID, "replay JSON is not canonical") from error


def _require_hash(value: object, label: str, *, code: str = MONITOR_REPLAY_INVALID) -> str:
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        _fail(code, f"{label} is invalid")
    return cast(str, value)


def _require_uuid(value: object, label: str, *, code: str = MONITOR_REPLAY_INVALID) -> str:
    if type(value) is not str:
        _fail(code, f"{label} is invalid")
    try:
        parsed = UUID(value)
    except (TypeError, ValueError):
        _fail(code, f"{label} is invalid")
    if str(parsed) != value:
        _fail(code, f"{label} is invalid")
    return cast(str, value)


def _require_text(value: object, label: str, *, code: str = MONITOR_REPLAY_INVALID) -> str:
    if type(value) is not str or not value or len(value) > 256:
        _fail(code, f"{label} is invalid")
    if any(ord(character) < 32 for character in value):
        _fail(code, f"{label} is invalid")
    if unicodedata.normalize("NFC", value) != value:
        _fail(code, f"{label} is invalid")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        _fail(code, f"{label} is invalid")
    return value


def _parse_binding(value: object) -> ObservationBinding:
    try:
        binding = ObservationBinding.from_dict(cast(dict[str, object], value))
    except (KeyError, TypeError, ValueError, OverflowError) as error:
        raise MonitorReplayError(MONITOR_REPLAY_INVALID, "replay binding is invalid") from error
    return binding


def _parse_sample(value: object) -> SampleValue:
    try:
        sample_value = cast(dict[str, object], value)
        watch_value = cast(dict[str, object], sample_value["watch"])
        watch = WatchItem.from_dict(watch_value)
        sample = SampleValue(
            watch=watch,
            status=cast(str, sample_value["status"]),
            typed_value=sample_value["typedValue"],
            code=cast(str | None, sample_value["code"]),
            definition=cast(dict[str, object] | None, sample_value["definition"]),
        )
    except (KeyError, TypeError, ValueError, OverflowError) as error:
        raise MonitorReplayError(MONITOR_REPLAY_INVALID, "replay sample is invalid") from error
    return sample


def _parse_batch(value: object) -> SampleBatch:
    try:
        batch_value = cast(dict[str, object], value)
        binding = _parse_binding(batch_value["binding"])
        batch = SampleBatch(
            binding=binding,
            group_id=UUID(cast(str, batch_value["groupId"])),
            group_revision=cast(int, batch_value["groupRevision"]),
            run_id=UUID(cast(str, batch_value["runId"])),
            sequence=cast(int, batch_value["sequence"]),
            scheduled_unix_ns=cast(int, batch_value["scheduledUnixNs"]),
            captured_unix_ns=cast(int, batch_value["capturedUnixNs"]),
            latency_ns=cast(int, batch_value["latencyNs"]),
            actual_rate_hz=cast(float, batch_value["actualRateHz"]),
            subscriber_drops=cast(int, batch_value["subscriberDrops"]),
            history_drops=cast(int, batch_value["historyDrops"]),
            deadline_drops=cast(int, batch_value["deadlineDrops"]),
            values=tuple(_parse_sample(item) for item in cast(list[object], batch_value["values"])),
        )
    except MonitorReplayError:
        raise
    except (KeyError, TypeError, ValueError, OverflowError) as error:
        raise MonitorReplayError(MONITOR_REPLAY_INVALID, "replay batch is invalid") from error
    return batch


def _document_unsigned(document: "MonitorReplayDocument") -> dict[str, object]:
    payload = document.to_dict()
    payload.pop("fixture_sha256", None)
    return payload


@dataclass(frozen=True, slots=True)
class MonitorReplayDocument:
    schema: str
    source: str
    physical_transport_evidence: bool
    scenario_role: str
    binding: ObservationBinding
    batches: tuple[SampleBatch, ...]
    fixture_sha256: str

    def __post_init__(self) -> None:
        if self.schema != MONITOR_REPLAY_SCHEMA:
            _fail(MONITOR_REPLAY_INVALID, "replay document schema is invalid")
        if self.source != MONITOR_REPLAY_SOURCE:
            _fail(MONITOR_REPLAY_INVALID, "replay document source is invalid")
        if type(self.physical_transport_evidence) is not bool or self.physical_transport_evidence:
            _fail(MONITOR_REPLAY_INVALID, "replay document physical evidence must be false")
        if self.scenario_role not in _ROLES:
            _fail(MONITOR_REPLAY_INVALID, "replay document scenario role is invalid")
        if type(self.binding) is not ObservationBinding:
            _fail(MONITOR_REPLAY_INVALID, "replay document binding is invalid")
        if (
            self.binding.probe_id != MONITOR_REPLAY_PROBE_ID
            or self.binding.physical_target != MONITOR_REPLAY_PHYSICAL_TARGET
            or self.binding.flash_session_id != MONITOR_REPLAY_FLASH_SESSION_ID
            or self.binding.lease_id != MONITOR_REPLAY_LEASE_ID
        ):
            _fail(MONITOR_REPLAY_INVALID, "replay document labels are invalid")
        if type(self.batches) is not tuple or not self.batches or len(self.batches) > MAX_REPLAY_BATCHES:
            _fail(MONITOR_REPLAY_INVALID, "replay document batches are invalid")
        if type(self.fixture_sha256) is not str or _SHA256.fullmatch(self.fixture_sha256) is None:
            _fail(MONITOR_REPLAY_INVALID, "replay document fixture digest is invalid")
        selectors: tuple[WatchItem, ...] | None = None
        previous_sequence: int | None = None
        previous_scheduled: int | None = None
        previous_captured: int | None = None
        first_group: object | None = None
        first_revision: int | None = None
        first_run: object | None = None
        for index, batch in enumerate(self.batches):
            if type(batch) is not SampleBatch or len(batch.values) == 0:
                _fail(MONITOR_REPLAY_INVALID, "replay document batch chain is invalid")
            if batch.binding != self.binding:
                _fail(MONITOR_REPLAY_INVALID, "replay document binding contradicts a batch")
            if index == 0:
                first_group = batch.group_id
                first_revision = batch.group_revision
                first_run = batch.run_id
                selectors = tuple(item.watch for item in batch.values)
            else:
                if batch.group_id != first_group or batch.group_revision != first_revision or batch.run_id != first_run:
                    _fail(MONITOR_REPLAY_INVALID, "replay document batch identity is inconsistent")
                if tuple(item.watch for item in batch.values) != selectors:
                    _fail(MONITOR_REPLAY_INVALID, "replay document selector vocabulary is inconsistent")
            if selectors is not None and len(set(selectors)) != len(selectors):
                _fail(MONITOR_REPLAY_INVALID, "replay document selectors are not unique")
            if previous_sequence is not None and batch.sequence != previous_sequence + 1:
                _fail(MONITOR_REPLAY_INVALID, "replay document sequences are not contiguous")
            if previous_scheduled is not None and batch.scheduled_unix_ns <= previous_scheduled:
                _fail(MONITOR_REPLAY_INVALID, "replay document scheduled times are not increasing")
            if previous_captured is not None and batch.captured_unix_ns <= previous_captured:
                _fail(MONITOR_REPLAY_INVALID, "replay document captured times are not increasing")
            previous_sequence = batch.sequence
            previous_scheduled = batch.scheduled_unix_ns
            previous_captured = batch.captured_unix_ns
        expected_digest = hashlib.sha256(canonical_replay_json_bytes(_document_unsigned(self))).hexdigest()
        if self.fixture_sha256 != expected_digest:
            _fail(MONITOR_REPLAY_INVALID, "replay document fixture digest is invalid")

    @classmethod
    def from_value(cls, value: object) -> "MonitorReplayDocument":
        if type(value) is cls:
            return value
        try:
            wire = validate_replay_document(value)
            binding = _parse_binding(wire["binding"])
            batches = tuple(_parse_batch(item) for item in cast(list[object], wire["batches"]))
            document = cls(
                schema=cast(str, wire["schema"]),
                source=cast(str, wire["source"]),
                physical_transport_evidence=cast(bool, wire["physical_transport_evidence"]),
                scenario_role=cast(str, wire["scenario_role"]),
                binding=binding,
                batches=batches,
                fixture_sha256=cast(str, wire["fixture_sha256"]),
            )
        except ReplayContractError as error:
            raise MonitorReplayError(MONITOR_REPLAY_INVALID, "replay document failed closed validation") from error
        except MonitorReplayError:
            raise
        except (TypeError, ValueError, OverflowError) as error:
            raise MonitorReplayError(MONITOR_REPLAY_INVALID, "replay document is invalid") from error
        return document

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "source": self.source,
            "physical_transport_evidence": self.physical_transport_evidence,
            "scenario_role": self.scenario_role,
            "binding": self.binding.to_dict(),
            "batches": [batch.to_dict() for batch in self.batches],
            "fixture_sha256": self.fixture_sha256,
        }


def _ref_unsigned(reference: "MonitorRunRef") -> dict[str, object]:
    payload = reference.to_dict()
    payload.pop("run_ref_sha256", None)
    return payload


@dataclass(frozen=True, slots=True)
class MonitorRunRef:
    schema: str
    operation_id: str
    scenario_role: str
    execution_source: str
    physical_transport_evidence: bool
    origin_workspace_id: str
    import_workspace_id: str
    logical_project_id: str
    origin_session_id: str
    projected_session_id: str
    origin_run_id: str
    projected_run_id: str
    target_device: str
    probe_id: str
    physical_target: str
    build_id: str
    elf_sha256: str
    input_snapshot_sha256: str
    git_head: str
    git_dirty: bool
    flash_session_id: str
    lease_id: str
    dwarf_sha256: str
    svd_sha256: str | None
    group_id: str
    group_revision: int
    start_sequence: int
    end_sequence_exclusive: int
    start_captured_unix_ns: int
    end_captured_unix_ns_exclusive: int
    fixture_sha256: str
    projected_batch_sha256s: tuple[str, ...]
    transcript_evidence_id: str
    run_ref_sha256: str

    def __post_init__(self) -> None:
        if self.schema != MONITOR_RUN_REF_SCHEMA:
            _fail(MONITOR_REPLAY_INVALID, "monitor run reference schema is invalid")
        operation = _require_uuid(self.operation_id, "operation_id")
        if self.scenario_role not in _ROLES:
            _fail(MONITOR_REPLAY_INVALID, "monitor run reference scenario role is invalid")
        if self.execution_source != MONITOR_REPLAY_EXECUTION_SOURCE:
            _fail(MONITOR_REPLAY_INVALID, "monitor run reference execution source is invalid")
        if type(self.physical_transport_evidence) is not bool or self.physical_transport_evidence:
            _fail(MONITOR_REPLAY_INVALID, "monitor run reference physical evidence must be false")
        for field_name in ("origin_workspace_id", "import_workspace_id"):
            _require_hash(getattr(self, field_name), field_name)
        project = _require_uuid(self.logical_project_id, "logical_project_id")
        origin_session = require_safe_session_id(self.origin_session_id)
        projected_session = require_safe_session_id(self.projected_session_id)
        origin_run = _require_uuid(self.origin_run_id, "origin_run_id")
        projected_run = _require_uuid(self.projected_run_id, "projected_run_id")
        if operation != origin_run or projected_run != origin_run:
            _fail(MONITOR_REPLAY_INVALID, "monitor run reference operation and run IDs contradict")
        for field_name in ("target_device", "probe_id", "physical_target", "flash_session_id", "lease_id"):
            _require_text(getattr(self, field_name), field_name)
        if (
            self.probe_id != MONITOR_REPLAY_PROBE_ID
            or self.physical_target != MONITOR_REPLAY_PHYSICAL_TARGET
            or self.flash_session_id != MONITOR_REPLAY_FLASH_SESSION_ID
            or self.lease_id != MONITOR_REPLAY_LEASE_ID
        ):
            _fail(MONITOR_REPLAY_INVALID, "monitor run reference labels are invalid")
        for field_name in ("build_id", "elf_sha256", "input_snapshot_sha256", "dwarf_sha256", "fixture_sha256", "transcript_evidence_id"):
            _require_hash(getattr(self, field_name), field_name)
        if type(self.svd_sha256) is not (str if self.svd_sha256 is not None else type(None)):
            _fail(MONITOR_REPLAY_INVALID, "svd_sha256 is invalid")
        if self.svd_sha256 is not None:
            _require_hash(self.svd_sha256, "svd_sha256")
        if type(self.git_head) is not str or _GIT_SHA.fullmatch(self.git_head) is None:
            _fail(MONITOR_REPLAY_INVALID, "git_head is invalid")
        if type(self.git_dirty) is not bool:
            _fail(MONITOR_REPLAY_INVALID, "git_dirty is invalid")
        group = _require_uuid(self.group_id, "group_id")
        if type(self.group_revision) is not int or isinstance(self.group_revision, bool) or not 1 <= self.group_revision <= MAX_SIGNED_INT64:
            _fail(MONITOR_REPLAY_INVALID, "group_revision is invalid")
        for field_name in ("start_sequence", "end_sequence_exclusive", "start_captured_unix_ns", "end_captured_unix_ns_exclusive"):
            value = getattr(self, field_name)
            if type(value) is not int or isinstance(value, bool) or not 0 <= value <= MAX_SIGNED_INT64:
                _fail(MONITOR_REPLAY_INVALID, f"{field_name} is invalid")
        if self.end_sequence_exclusive <= self.start_sequence or self.end_captured_unix_ns_exclusive <= self.start_captured_unix_ns:
            _fail(MONITOR_REPLAY_INVALID, "monitor run reference windows are invalid")
        if type(self.projected_batch_sha256s) is not tuple or not self.projected_batch_sha256s or len(self.projected_batch_sha256s) > MAX_REPLAY_BATCHES:
            _fail(MONITOR_REPLAY_INVALID, "projected batch digests are invalid")
        for digest in self.projected_batch_sha256s:
            _require_hash(digest, "projected batch digest")
        _ = project, origin_session, projected_session, group
        if type(self.run_ref_sha256) is not str or _SHA256.fullmatch(self.run_ref_sha256) is None:
            _fail(MONITOR_REPLAY_INVALID, "run reference digest is invalid")
        expected_digest = hashlib.sha256(canonical_replay_json_bytes(_ref_unsigned(self))).hexdigest()
        if self.run_ref_sha256 != expected_digest:
            _fail(MONITOR_REPLAY_INVALID, "run reference digest is invalid")

    @classmethod
    def from_value(cls, value: object) -> "MonitorRunRef | MonitorRunRefV2":
        if type(value) is cls:
            return value
        try:
            wire = validate_run_reference(value)
            if wire["schema"] == MONITOR_RUN_REF_SCHEMA_V2:
                return MonitorRunRefV2.from_value(wire)
            return cls(
                **{
                    field_name: (
                        tuple(wire[field_name])
                        if field_name == "projected_batch_sha256s"
                        else wire[field_name]
                    )
                    for field_name in _REF_FIELDS
                }
            )
        except ReplayContractError as error:
            raise MonitorReplayError(MONITOR_REPLAY_INVALID, "monitor run reference failed closed validation") from error
        except MonitorReplayError:
            raise
        except (TypeError, ValueError, OverflowError) as error:
            raise MonitorReplayError(MONITOR_REPLAY_INVALID, "monitor run reference is invalid") from error

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "operation_id": self.operation_id,
            "scenario_role": self.scenario_role,
            "execution_source": self.execution_source,
            "physical_transport_evidence": self.physical_transport_evidence,
            "origin_workspace_id": self.origin_workspace_id,
            "import_workspace_id": self.import_workspace_id,
            "logical_project_id": self.logical_project_id,
            "origin_session_id": self.origin_session_id,
            "projected_session_id": self.projected_session_id,
            "origin_run_id": self.origin_run_id,
            "projected_run_id": self.projected_run_id,
            "target_device": self.target_device,
            "probe_id": self.probe_id,
            "physical_target": self.physical_target,
            "build_id": self.build_id,
            "elf_sha256": self.elf_sha256,
            "input_snapshot_sha256": self.input_snapshot_sha256,
            "git_head": self.git_head,
            "git_dirty": self.git_dirty,
            "flash_session_id": self.flash_session_id,
            "lease_id": self.lease_id,
            "dwarf_sha256": self.dwarf_sha256,
            "svd_sha256": self.svd_sha256,
            "group_id": self.group_id,
            "group_revision": self.group_revision,
            "start_sequence": self.start_sequence,
            "end_sequence_exclusive": self.end_sequence_exclusive,
            "start_captured_unix_ns": self.start_captured_unix_ns,
            "end_captured_unix_ns_exclusive": self.end_captured_unix_ns_exclusive,
            "fixture_sha256": self.fixture_sha256,
            "projected_batch_sha256s": list(self.projected_batch_sha256s),
            "transcript_evidence_id": self.transcript_evidence_id,
            "run_ref_sha256": self.run_ref_sha256,
        }


@dataclass(frozen=True, slots=True)
class MonitorRunRefV2:
    """Generic Monitor run reference v2 with a source-record digest."""

    schema: str
    operation_id: str
    scenario_role: str
    execution_source: str
    physical_transport_evidence: bool
    origin_workspace_id: str
    import_workspace_id: str
    logical_project_id: str
    origin_session_id: str
    projected_session_id: str
    origin_run_id: str
    projected_run_id: str
    target_device: str
    probe_id: str
    physical_target: str
    build_id: str
    elf_sha256: str
    input_snapshot_sha256: str
    git_head: str
    git_dirty: bool
    flash_session_id: str
    lease_id: str
    dwarf_sha256: str
    svd_sha256: str | None
    group_id: str
    group_revision: int
    start_sequence: int
    end_sequence_exclusive: int
    start_captured_unix_ns: int
    end_captured_unix_ns_exclusive: int
    source_record_sha256: str
    projected_batch_sha256s: tuple[str, ...]
    transcript_evidence_id: str
    run_ref_sha256: str

    def __post_init__(self) -> None:
        if self.schema != MONITOR_RUN_REF_SCHEMA_V2:
            _fail(MONITOR_REPLAY_INVALID, "monitor run reference schema is invalid")
        try:
            validate_run_reference(self.to_dict())
        except ReplayContractError as error:
            raise MonitorReplayError(
                MONITOR_REPLAY_INVALID,
                "monitor run reference failed closed validation",
            ) from error

    @classmethod
    def from_value(cls, value: object) -> "MonitorRunRefV2":
        if type(value) is cls:
            return value
        try:
            wire = validate_run_reference(value)
            if wire["schema"] != MONITOR_RUN_REF_SCHEMA_V2:
                raise ReplayContractError("monitor run reference schema is invalid")
            return cls(
                **{
                    field_name: (
                        tuple(wire[field_name])
                        if field_name == "projected_batch_sha256s"
                        else wire[field_name]
                    )
                    for field_name in _REF_FIELDS_V2
                }
            )
        except ReplayContractError as error:
            raise MonitorReplayError(
                MONITOR_REPLAY_INVALID,
                "monitor run reference failed closed validation",
            ) from error
        except MonitorReplayError:
            raise
        except (TypeError, ValueError, OverflowError) as error:
            raise MonitorReplayError(
                MONITOR_REPLAY_INVALID,
                "monitor run reference is invalid",
            ) from error

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "operation_id": self.operation_id,
            "scenario_role": self.scenario_role,
            "execution_source": self.execution_source,
            "physical_transport_evidence": self.physical_transport_evidence,
            "origin_workspace_id": self.origin_workspace_id,
            "import_workspace_id": self.import_workspace_id,
            "logical_project_id": self.logical_project_id,
            "origin_session_id": self.origin_session_id,
            "projected_session_id": self.projected_session_id,
            "origin_run_id": self.origin_run_id,
            "projected_run_id": self.projected_run_id,
            "target_device": self.target_device,
            "probe_id": self.probe_id,
            "physical_target": self.physical_target,
            "build_id": self.build_id,
            "elf_sha256": self.elf_sha256,
            "input_snapshot_sha256": self.input_snapshot_sha256,
            "git_head": self.git_head,
            "git_dirty": self.git_dirty,
            "flash_session_id": self.flash_session_id,
            "lease_id": self.lease_id,
            "dwarf_sha256": self.dwarf_sha256,
            "svd_sha256": self.svd_sha256,
            "group_id": self.group_id,
            "group_revision": self.group_revision,
            "start_sequence": self.start_sequence,
            "end_sequence_exclusive": self.end_sequence_exclusive,
            "start_captured_unix_ns": self.start_captured_unix_ns,
            "end_captured_unix_ns_exclusive": self.end_captured_unix_ns_exclusive,
            "source_record_sha256": self.source_record_sha256,
            "projected_batch_sha256s": list(self.projected_batch_sha256s),
            "transcript_evidence_id": self.transcript_evidence_id,
            "run_ref_sha256": self.run_ref_sha256,
        }


def _decode_document_bytes(raw: bytes) -> dict[str, object]:
    try:
        decoded = decode_canonical_json_bytes(
            raw,
            allow_final_lf=True,
            require_object=True,
        )
    except ReplayContractError as error:
        raise MonitorReplayError(
            EVIDENCE_INTEGRITY_FAILURE,
            "replay document failed closed JSON validation",
        ) from error
    return cast(dict[str, object], decoded)


def _read_document(path_value: object) -> bytes:
    if not isinstance(path_value, (str, Path)):
        _fail(MONITOR_REPLAY_INVALID, "document_file must be a path")
    try:
        path = Path(path_value)
        return EvidenceStore._read_file_bytes(path, maximum_bytes=MAX_REPLAY_DOCUMENT_BYTES)
    except MonitorReplayError:
        raise
    except (EvidenceValidationError, FileNotFoundError, OSError, TypeError, ValueError):
        _fail(EVIDENCE_INTEGRITY_FAILURE, "replay document could not be read safely")


def _project_binding(binding: ObservationBinding, paths: WorkspacePaths) -> ObservationBinding:
    try:
        return ObservationBinding(
            workspace_id=paths.workspace_id,
            logical_project_id=binding.logical_project_id,
            session_id=paths.session_id,
            probe_id=binding.probe_id,
            target_device=binding.target_device,
            physical_target=binding.physical_target,
            build_id=binding.build_id,
            elf_sha256=binding.elf_sha256,
            input_snapshot_sha256=binding.input_snapshot_sha256,
            git_head=binding.git_head,
            git_dirty=binding.git_dirty,
            flash_session_id=binding.flash_session_id,
            lease_id=binding.lease_id,
            dwarf_sha256=binding.dwarf_sha256,
            svd_sha256=binding.svd_sha256,
        )
    except (TypeError, ValueError, OverflowError) as error:
        raise MonitorReplayError(EVIDENCE_INTEGRITY_FAILURE, "replay projection identity is invalid") from error


def _project_batches(document: MonitorReplayDocument, paths: WorkspacePaths) -> tuple[SampleBatch, ...]:
    projected_binding = _project_binding(document.binding, paths)
    return tuple(replace(batch, binding=projected_binding) for batch in document.batches)


def _batch_digest(batch: SampleBatch) -> str:
    return hashlib.sha256(canonical_replay_json_bytes(batch.to_dict())).hexdigest()


def _make_reference(
    document: MonitorReplayDocument,
    paths: WorkspacePaths,
    operation_id: str,
    projected: tuple[SampleBatch, ...],
    transcript_evidence_id: str,
) -> MonitorRunRef:
    first = projected[0]
    last = projected[-1]
    payload: dict[str, object] = {
        "schema": MONITOR_RUN_REF_SCHEMA,
        "operation_id": operation_id,
        "scenario_role": document.scenario_role,
        "execution_source": MONITOR_REPLAY_EXECUTION_SOURCE,
        "physical_transport_evidence": False,
        "origin_workspace_id": document.binding.workspace_id,
        "import_workspace_id": paths.workspace_id,
        "logical_project_id": document.binding.logical_project_id,
        "origin_session_id": document.binding.session_id,
        "projected_session_id": paths.session_id,
        "origin_run_id": str(first.run_id),
        "projected_run_id": str(first.run_id),
        "target_device": document.binding.target_device,
        "probe_id": document.binding.probe_id,
        "physical_target": document.binding.physical_target,
        "build_id": document.binding.build_id,
        "elf_sha256": document.binding.elf_sha256,
        "input_snapshot_sha256": document.binding.input_snapshot_sha256,
        "git_head": document.binding.git_head,
        "git_dirty": document.binding.git_dirty,
        "flash_session_id": document.binding.flash_session_id,
        "lease_id": document.binding.lease_id,
        "dwarf_sha256": document.binding.dwarf_sha256,
        "svd_sha256": document.binding.svd_sha256,
        "group_id": str(first.group_id),
        "group_revision": first.group_revision,
        "start_sequence": first.sequence,
        "end_sequence_exclusive": last.sequence + 1,
        "start_captured_unix_ns": first.captured_unix_ns,
        "end_captured_unix_ns_exclusive": last.captured_unix_ns + 1,
        "fixture_sha256": document.fixture_sha256,
        "projected_batch_sha256s": [_batch_digest(batch) for batch in projected],
        "transcript_evidence_id": transcript_evidence_id,
        "run_ref_sha256": "0" * 64,
    }
    unsigned = dict(payload)
    unsigned.pop("run_ref_sha256")
    payload["run_ref_sha256"] = hashlib.sha256(canonical_replay_json_bytes(unsigned)).hexdigest()
    return MonitorRunRef.from_value(payload)


def _expected_transcript_envelope(
    raw: bytes,
    document: MonitorReplayDocument,
    paths: WorkspacePaths,
    operation_id: str,
) -> EvidenceEnvelope:
    digest = hashlib.sha256(raw).hexdigest()
    artifact = ArtifactRef(
        sha256=digest,
        size_bytes=len(raw),
        relative_path=f"objects/sha256/{digest[:2]}/{digest}",
        kind="monitor-replay-transcript",
        media_type="application/json",
    )
    metadata = {
        "operation_id": operation_id,
        "scenario_role": document.scenario_role,
        "origin_workspace_id": document.binding.workspace_id,
        "import_workspace_id": paths.workspace_id,
        "origin_run_id": str(document.batches[0].run_id),
        "projected_run_id": str(document.batches[0].run_id),
        "fixture_sha256": document.fixture_sha256,
        "execution_source": MONITOR_REPLAY_EXECUTION_SOURCE,
        "physical_transport_evidence": False,
    }
    if set(metadata) != _EVIDENCE_METADATA_FIELDS:
        _fail(EVIDENCE_INTEGRITY_FAILURE, "replay Evidence metadata is not closed")
    try:
        identity = EvidenceIdentity(
            workspace_id=document.binding.workspace_id,
            project_id=document.binding.logical_project_id,
            session_id=document.binding.session_id,
            build_id=document.binding.build_id,
            elf_sha256=document.binding.elf_sha256,
            target_device=document.binding.target_device,
            input_snapshot_sha256=document.binding.input_snapshot_sha256,
            git_commit=document.binding.git_head,
            git_dirty=document.binding.git_dirty,
        )
        return EvidenceEnvelope(
            identity=identity,
            operation=MONITOR_REPLAY_IMPORT_OPERATION,
            produced_at_utc=unix_ns_to_utc(document.batches[0].captured_unix_ns),
            parents=(),
            artifacts=(artifact,),
            metadata=metadata,
        )
    except EvidenceValidationError as error:
        raise MonitorReplayError(
            EVIDENCE_INTEGRITY_FAILURE,
            "replay Evidence identity is invalid",
        ) from error


def _expected_root(reference: MonitorRunRef) -> RootRecord:
    metadata = {
        "fixture_sha256": reference.fixture_sha256,
        "run_ref_sha256": reference.run_ref_sha256,
        "origin_workspace_id": reference.origin_workspace_id,
        "import_workspace_id": reference.import_workspace_id,
        "execution_source": MONITOR_REPLAY_EXECUTION_SOURCE,
        "physical_transport_evidence": False,
    }
    if set(metadata) != _ROOT_METADATA_FIELDS:
        _fail(EVIDENCE_INTEGRITY_FAILURE, "monitor run root metadata is not closed")
    try:
        return RootRecord(
            root_type=MONITOR_RUN_ROOT_TYPE,
            root_id=reference.operation_id,
            manifest_id=reference.transcript_evidence_id,
            metadata=metadata,
        )
    except EvidenceValidationError as error:
        raise MonitorReplayError(
            EVIDENCE_INTEGRITY_FAILURE,
            "monitor run root is invalid",
        ) from error


def _reference_metadata(reference: MonitorRunRef) -> dict[str, object]:
    metadata = {
        "operation_id": reference.operation_id,
        "run_ref_sha256": reference.run_ref_sha256,
        "fixture_sha256": reference.fixture_sha256,
        "scenario_role": reference.scenario_role,
        "origin_workspace_id": reference.origin_workspace_id,
        "import_workspace_id": reference.import_workspace_id,
        "execution_source": MONITOR_REPLAY_EXECUTION_SOURCE,
        "physical_transport_evidence": False,
    }
    if set(metadata) != _REFERENCE_ROOT_METADATA_FIELDS:
        _fail(EVIDENCE_INTEGRITY_FAILURE, "monitor run reference metadata is not closed")
    return metadata


def _expected_reference_envelope(
    reference: MonitorRunRef,
    transcript_envelope: EvidenceEnvelope,
) -> EvidenceEnvelope:
    raw = canonical_replay_json_bytes(reference.to_dict())
    digest = hashlib.sha256(raw).hexdigest()
    artifact = ArtifactRef(
        sha256=digest,
        size_bytes=len(raw),
        relative_path=f"objects/sha256/{digest[:2]}/{digest}",
        kind=MONITOR_RUN_REF_ARTIFACT_KIND,
        media_type="application/json",
    )
    metadata = _reference_metadata(reference)
    try:
        return EvidenceEnvelope(
            identity=transcript_envelope.identity,
            operation=MONITOR_RUN_REF_OPERATION,
            produced_at_utc=transcript_envelope.produced_at_utc,
            parents=(reference.transcript_evidence_id,),
            artifacts=(artifact,),
            metadata=metadata,
        )
    except EvidenceValidationError as error:
        raise MonitorReplayError(
            EVIDENCE_INTEGRITY_FAILURE,
            "monitor run reference Evidence is invalid",
        ) from error


def _expected_reference_root(
    reference: MonitorRunRef,
    reference_envelope: EvidenceEnvelope,
) -> RootRecord:
    metadata = _reference_metadata(reference)
    try:
        return RootRecord(
            root_type=MONITOR_RUN_REF_ROOT_TYPE,
            root_id=reference.operation_id,
            manifest_id=str(reference_envelope.evidence_id),
            metadata=metadata,
        )
    except EvidenceValidationError as error:
        raise MonitorReplayError(
            EVIDENCE_INTEGRITY_FAILURE,
            "monitor run reference root is invalid",
        ) from error


def _load_monitor_reference_root(
    evidence_store: EvidenceStore,
    operation_id: str,
) -> RootRecord | None:
    try:
        return get_root(evidence_store, MONITOR_RUN_REF_ROOT_TYPE, operation_id)
    except EvidenceValidationError as error:
        if error.message == "evidence root is absent":
            return None
        raise MonitorReplayError(
            EVIDENCE_INTEGRITY_FAILURE,
            "monitor run reference root is corrupt",
        ) from error
    except Exception as error:
        raise MonitorReplayError(
            ENVIRONMENT_FAILURE,
            "monitor run reference root could not be read",
        ) from error


def _has_non_missing_os_error(error: BaseException) -> bool:
    seen: set[int] = set()
    current: BaseException | None = error
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, OSError) and not isinstance(current, FileNotFoundError):
            return True
        current = current.__cause__ or current.__context__
    return False


def _validate_existing_reference_root(
    root: RootRecord,
    expected_root: RootRecord,
    expected_envelope: EvidenceEnvelope,
    reference: MonitorRunRef,
    evidence_store: EvidenceStore,
) -> None:
    if root.to_dict() != expected_root.to_dict():
        _fail(OPERATION_CONFLICT, "operation reference root has a different intent")
    try:
        envelope = evidence_store.get_envelope(root.manifest_id)
        if envelope.to_dict() != expected_envelope.to_dict():
            raise ValueError("reference envelope differs from the operation reference root")
        if envelope.parents != (reference.transcript_evidence_id,):
            raise ValueError("reference envelope parent is not the transcript Evidence")
        if len(envelope.artifacts) != 1:
            raise ValueError("reference envelope artifact set is invalid")
        artifact = envelope.artifacts[0]
        if artifact.kind != MONITOR_RUN_REF_ARTIFACT_KIND or artifact.media_type != "application/json":
            raise ValueError("reference envelope artifact descriptor is invalid")
        captured = evidence_store.read_artifact(
            artifact,
            maximum_bytes=MAX_REPLAY_DOCUMENT_BYTES,
        )
        expected_bytes = canonical_replay_json_bytes(reference.to_dict())
        if captured != expected_bytes:
            raise ValueError("reference artifact bytes differ from the operation reference")
        try:
            decoded = decode_canonical_json_bytes(captured, require_object=True)
            stored = MonitorRunRef.from_value(decoded)
        except (MonitorReplayError, ReplayContractError) as error:
            raise ValueError("reference artifact is not a complete canonical MonitorRunRef") from error
        if stored.to_dict() != reference.to_dict():
            raise ValueError("reference artifact differs from the operation reference")
    except MonitorReplayError:
        raise
    except FileNotFoundError as error:
        raise MonitorReplayError(
            EVIDENCE_INTEGRITY_FAILURE,
            "monitor run reference Evidence is absent",
        ) from error
    except OSError as error:
        raise MonitorReplayError(
            ENVIRONMENT_FAILURE,
            "monitor run reference Evidence provider failed",
        ) from error
    except EvidenceValidationError as error:
        if _has_non_missing_os_error(error):
            raise MonitorReplayError(
                ENVIRONMENT_FAILURE,
                "monitor run reference Evidence provider failed",
            ) from error
        raise MonitorReplayError(
            EVIDENCE_INTEGRITY_FAILURE,
            "monitor run reference Evidence is corrupt",
        ) from error
    except Exception as error:
        if _has_non_missing_os_error(error):
            raise MonitorReplayError(
                ENVIRONMENT_FAILURE,
                "monitor run reference Evidence provider failed",
            ) from error
        raise MonitorReplayError(
            EVIDENCE_INTEGRITY_FAILURE,
            "monitor run reference Evidence is corrupt",
        ) from error


def _load_monitor_root(
    evidence_store: EvidenceStore,
    operation_id: str,
) -> RootRecord | None:
    try:
        return get_root(evidence_store, MONITOR_RUN_ROOT_TYPE, operation_id)
    except EvidenceValidationError as error:
        if error.message == "evidence root is absent":
            return None
        raise MonitorReplayError(
            EVIDENCE_INTEGRITY_FAILURE,
            "monitor run root is corrupt",
        ) from error
    except Exception as error:
        raise MonitorReplayError(
            ENVIRONMENT_FAILURE,
            "monitor run root could not be read",
        ) from error


def _validate_existing_root(
    root: RootRecord,
    expected_root: RootRecord,
    expected_envelope: EvidenceEnvelope,
    raw: bytes,
    evidence_store: EvidenceStore,
    *,
    maximum_bytes: int = MAX_REPLAY_DOCUMENT_BYTES,
) -> None:
    if root.to_dict() != expected_root.to_dict():
        _fail(OPERATION_CONFLICT, "operation root has a different intent")
    try:
        envelope = evidence_store.get_envelope(root.manifest_id)
        if envelope.to_dict() != expected_envelope.to_dict():
            raise ValueError("transcript envelope differs from the operation root")
        if len(envelope.artifacts) != 1:
            raise ValueError("transcript envelope artifact set is invalid")
        captured = evidence_store.read_artifact(
            envelope.artifacts[0],
            maximum_bytes=maximum_bytes,
        )
        if captured != raw:
            raise ValueError("transcript artifact bytes differ from the operation root")
    except MonitorReplayError:
        raise
    except FileNotFoundError as error:
        raise MonitorReplayError(
            EVIDENCE_INTEGRITY_FAILURE,
            "monitor run transcript Evidence is absent",
        ) from error
    except OSError as error:
        raise MonitorReplayError(
            ENVIRONMENT_FAILURE,
            "monitor run transcript Evidence provider failed",
        ) from error
    except EvidenceValidationError as error:
        if _has_non_missing_os_error(error):
            raise MonitorReplayError(
                ENVIRONMENT_FAILURE,
                "monitor run transcript Evidence provider failed",
            ) from error
        raise MonitorReplayError(
            EVIDENCE_INTEGRITY_FAILURE,
            "monitor run transcript evidence is corrupt",
        ) from error
    except Exception as error:
        raise MonitorReplayError(
            EVIDENCE_INTEGRITY_FAILURE,
            "monitor run transcript evidence is corrupt",
        ) from error


def _load_existing_batches(history: HistoryStore, paths: WorkspacePaths, run_id: UUID) -> tuple[SampleBatch, ...]:
    result = history.query_history(
        HistoryQuery(
            session_id=paths.session_id,
            start_ns=0,
            end_ns=MAX_SIGNED_INT64,
            limit=MAX_HISTORY_VALUES,
            run_id=run_id,
        )
    )
    if not result.ok or result.data is None:
        raise MonitorReplayError(ENVIRONMENT_FAILURE, "monitor history preflight failed")
    page = result.data
    if page.next_cursor is not None:
        raise MonitorReplayError(OPERATION_CONFLICT, "operation already has an oversized history window")
    batches: list[SampleBatch] = []
    for history_slice in page.batches:
        if (
            type(history_slice) is not HistoryBatchSlice
            or history_slice.start_ordinal != 0
            or len(history_slice.values) != history_slice.batch_value_count
        ):
            raise MonitorReplayError(OPERATION_CONFLICT, "operation has a partial history window")
        try:
            batches.append(
                SampleBatch(
                    binding=history_slice.binding,
                    group_id=history_slice.group_id,
                    group_revision=history_slice.group_revision,
                    run_id=history_slice.run_id,
                    sequence=history_slice.sequence,
                    scheduled_unix_ns=history_slice.scheduled_unix_ns,
                    captured_unix_ns=history_slice.captured_unix_ns,
                    latency_ns=history_slice.latency_ns,
                    actual_rate_hz=history_slice.actual_rate_hz,
                    subscriber_drops=history_slice.subscriber_drops,
                    history_drops=history_slice.history_drops,
                    deadline_drops=history_slice.deadline_drops,
                    values=history_slice.values,
                )
            )
        except (TypeError, ValueError, OverflowError) as error:
            raise MonitorReplayError(ENVIRONMENT_FAILURE, "monitor history contains invalid replay data") from error
    return tuple(batches)


def _publish_transcript(
    raw: bytes,
    expected_envelope: EvidenceEnvelope,
    evidence_store: EvidenceStore,
) -> str:
    try:
        with tempfile.TemporaryDirectory(prefix="stm32-monitor-replay-") as directory:
            source = Path(directory) / "transcript.json"
            source.write_bytes(raw)
            artifact = evidence_store.ingest_file(
                source,
                kind="monitor-replay-transcript",
                media_type="application/json",
            )
        if artifact != expected_envelope.artifacts[0]:
            raise EvidenceValidationError(
                "EVIDENCE_CORRUPT",
                "transcript artifact identity differs from the expected source",
            )
        evidence_store.put_envelope(expected_envelope)
        return str(expected_envelope.evidence_id)
    except MonitorReplayError:
        raise
    except Exception as error:
        raise MonitorReplayError(ENVIRONMENT_FAILURE, "replay Evidence publication failed") from error


def _resolve_reference_root_race(
    evidence_store: EvidenceStore,
    expected_root: RootRecord,
) -> None:
    try:
        winner = get_root(
            evidence_store,
            expected_root.root_type,
            expected_root.root_id,
        )
    except FileNotFoundError as error:
        raise MonitorReplayError(
            ENVIRONMENT_FAILURE,
            "reference root disappeared during publication",
        ) from error
    except EvidenceValidationError as error:
        if error.message == "evidence root is absent":
            raise MonitorReplayError(
                ENVIRONMENT_FAILURE,
                "reference root disappeared during publication",
            ) from error
        raise MonitorReplayError(
            EVIDENCE_INTEGRITY_FAILURE,
            "reference root winner is corrupt",
        ) from error
    except OSError as error:
        raise MonitorReplayError(
            ENVIRONMENT_FAILURE,
            "reference root winner could not be read",
        ) from error
    except Exception as error:
        if _has_non_missing_os_error(error):
            raise MonitorReplayError(
                ENVIRONMENT_FAILURE,
                "reference root winner could not be read",
            ) from error
        raise MonitorReplayError(
            EVIDENCE_INTEGRITY_FAILURE,
            "reference root winner is corrupt",
        ) from error
    if winner.to_dict() != expected_root.to_dict():
        _fail(OPERATION_CONFLICT, "operation reference root changed before publication")


def _publish_reference(
    reference: MonitorRunRef,
    expected_envelope: EvidenceEnvelope,
    expected_root: RootRecord,
    evidence_store: EvidenceStore,
) -> None:
    raw = canonical_replay_json_bytes(reference.to_dict())
    try:
        with tempfile.TemporaryDirectory(prefix="stm32-monitor-replay-ref-") as directory:
            source = Path(directory) / "run-ref.json"
            source.write_bytes(raw)
            artifact = evidence_store.ingest_file(
                source,
                kind=MONITOR_RUN_REF_ARTIFACT_KIND,
                media_type="application/json",
            )
        if artifact != expected_envelope.artifacts[0]:
            raise EvidenceValidationError(
                "EVIDENCE_CORRUPT",
                "reference artifact identity differs from the expected reference",
            )
        evidence_store.put_envelope(expected_envelope)
        try:
            put_root(evidence_store, expected_root)
        except EvidenceValidationError as error:
            if error.message == "root identity already has different canonical bytes":
                _resolve_reference_root_race(evidence_store, expected_root)
                return
            raise
    except MonitorReplayError:
        raise
    except OSError as error:
        raise MonitorReplayError(
            ENVIRONMENT_FAILURE,
            "monitor run reference Evidence provider failed",
        ) from error
    except EvidenceValidationError as error:
        if _has_non_missing_os_error(error):
            raise MonitorReplayError(
                ENVIRONMENT_FAILURE,
                "monitor run reference Evidence provider failed",
            ) from error
        raise MonitorReplayError(
            EVIDENCE_INTEGRITY_FAILURE,
            "monitor run reference Evidence publication is corrupt",
        ) from error
    except Exception as error:
        if _has_non_missing_os_error(error):
            raise MonitorReplayError(
                ENVIRONMENT_FAILURE,
                "monitor run reference Evidence provider failed",
            ) from error
        raise MonitorReplayError(
            ENVIRONMENT_FAILURE,
            "monitor run reference Evidence publication failed",
        ) from error


def _physical_invalid(message: str) -> None:
    _fail(MONITOR_PHYSICAL_INVALID, message)


def _physical_canonical_json_bytes(value: object) -> bytes:
    """Encode physical transcript JSON under its independent 64 MiB budget."""

    try:
        copied = _physical_copy_json(value)
        raw = json.dumps(
            copied,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError, UnicodeError, RecursionError) as error:
        raise MonitorReplayError(
            MONITOR_PHYSICAL_INVALID,
            "physical Monitor transcript is invalid",
        ) from error
    if len(raw) > MAX_PHYSICAL_TRANSCRIPT_BYTES:
        _physical_invalid("physical Monitor transcript exceeds its size limit")
    return raw


def _physical_copy_json(
    value: object,
    *,
    depth: int = 0,
    nodes: list[int] | None = None,
    active: set[int] | None = None,
) -> object:
    state_nodes = nodes if nodes is not None else [0]
    state_active = active if active is not None else set()
    if depth > _EVIDENCE_JSON_DEPTH:
        raise ValueError("physical transcript JSON exceeds its depth limit")
    state_nodes[0] += 1
    if state_nodes[0] > _PHYSICAL_JSON_NODES:
        raise ValueError("physical transcript JSON exceeds its node limit")
    if value is None or type(value) is bool:
        return value
    if type(value) is int:
        if not -MAX_SIGNED_INT64 <= value <= MAX_SIGNED_INT64:
            raise ValueError("physical transcript integer is out of range")
        return value
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError("physical transcript number is not finite")
        return value
    if isinstance(value, str):
        if (
            unicodedata.normalize("NFC", value) != value
            or len(value) > _MONITOR_JSON_STRING_CHARS
        ):
            raise ValueError("physical transcript string is invalid")
        return value
    if isinstance(value, tuple):
        raise ValueError("physical transcript JSON must not contain tuples")
    if isinstance(value, Mapping):
        identity = id(value)
        if identity in state_active:
            raise ValueError("physical transcript JSON contains a cycle")
        state_active.add(identity)
        try:
            copied: dict[str, object] = {}
            for key, item in value.items():
                if type(key) is not str or unicodedata.normalize("NFC", key) != key:
                    raise ValueError("physical transcript JSON key is invalid")
                if key in copied:
                    raise ValueError("physical transcript JSON key is duplicated")
                copied[key] = _physical_copy_json(
                    item,
                    depth=depth + 1,
                    nodes=state_nodes,
                    active=state_active,
                )
            return copied
        finally:
            state_active.remove(identity)
    if isinstance(value, list):
        identity = id(value)
        if identity in state_active:
            raise ValueError("physical transcript JSON contains a cycle")
        state_active.add(identity)
        try:
            return [
                _physical_copy_json(
                    item,
                    depth=depth + 1,
                    nodes=state_nodes,
                    active=state_active,
                )
                for item in value
            ]
        finally:
            state_active.remove(identity)
    raise TypeError("physical transcript JSON contains an unsupported value")


def _physical_identity_error(message: str) -> None:
    _fail(INCOMPATIBLE_IDENTITY, message)


def _physical_int(value: object, label: str) -> int:
    if type(value) is not int or isinstance(value, bool) or not 0 <= value <= MAX_SIGNED_INT64:
        _physical_invalid(f"{label} is invalid")
    return cast(int, value)


def _physical_operation_id(value: object, label: str) -> str:
    try:
        return _require_uuid(value, label, code=MONITOR_PHYSICAL_INVALID)
    except MonitorReplayError:
        raise


def _physical_probe_selector(value: object) -> str:
    if (
        type(value) is not str
        or not value
        or value.strip() != value
        or unicodedata.normalize("NFC", value) != value
        or any(ord(character) < 32 for character in value)
    ):
        _physical_invalid("probe_id is invalid")
    return cast(str, value)


def _physical_expected_root_metadata(reference: MonitorRunRefV2) -> dict[str, object]:
    return {
        "source_record_sha256": reference.source_record_sha256,
        "run_ref_sha256": reference.run_ref_sha256,
        "origin_workspace_id": reference.origin_workspace_id,
        "import_workspace_id": reference.import_workspace_id,
        "execution_source": "physical",
        "physical_transport_evidence": True,
    }


def _physical_reference_metadata(reference: MonitorRunRefV2) -> dict[str, object]:
    return {
        "operation_id": reference.operation_id,
        "run_ref_sha256": reference.run_ref_sha256,
        "source_record_sha256": reference.source_record_sha256,
        "scenario_role": reference.scenario_role,
        "origin_workspace_id": reference.origin_workspace_id,
        "import_workspace_id": reference.import_workspace_id,
        "execution_source": "physical",
        "physical_transport_evidence": True,
    }


def _physical_transcript_wire(
    *,
    scenario_role: str,
    test_run_id: str,
    batches: tuple[SampleBatch, ...],
) -> dict[str, object]:
    if not batches:
        _physical_identity_error("physical history window is empty")
    return {
        "schema": MONITOR_PHYSICAL_TRANSCRIPT_SCHEMA,
        "source": MONITOR_PHYSICAL_SOURCE,
        "scenario_role": scenario_role,
        "test_run_id": test_run_id,
        "execution_source": "physical",
        "physical_transport_evidence": True,
        "binding": batches[0].binding.to_dict(),
        "batches": [batch.to_dict() for batch in batches],
    }


def _physical_transcript_envelope(
    *,
    raw: bytes,
    scenario_role: str,
    test_run_id: str,
    batches: tuple[SampleBatch, ...],
    paths: WorkspacePaths,
) -> EvidenceEnvelope:
    binding = batches[0].binding
    source_record_sha256 = hashlib.sha256(raw).hexdigest()
    artifact = ArtifactRef(
        sha256=source_record_sha256,
        size_bytes=len(raw),
        relative_path=f"objects/sha256/{source_record_sha256[:2]}/{source_record_sha256}",
        kind="monitor-physical-transcript",
        media_type="application/json",
    )
    try:
        identity = EvidenceIdentity(
            workspace_id=binding.workspace_id,
            project_id=binding.logical_project_id,
            session_id=binding.session_id,
            build_id=binding.build_id,
            elf_sha256=binding.elf_sha256,
            target_device=binding.target_device,
            input_snapshot_sha256=binding.input_snapshot_sha256,
            git_commit=binding.git_head,
            git_dirty=binding.git_dirty,
        )
        metadata = {
            "operation_id": str(batches[0].run_id),
            "scenario_role": scenario_role,
            "test_run_id": test_run_id,
            "origin_workspace_id": binding.workspace_id,
            "import_workspace_id": paths.workspace_id,
            "origin_session_id": binding.session_id,
            "projected_session_id": paths.session_id,
            "origin_run_id": str(batches[0].run_id),
            "projected_run_id": str(batches[0].run_id),
            "source_record_sha256": source_record_sha256,
            "execution_source": "physical",
            "physical_transport_evidence": True,
        }
        return EvidenceEnvelope(
            identity=identity,
            operation=MONITOR_PHYSICAL_WINDOW_OPERATION,
            produced_at_utc=unix_ns_to_utc(batches[0].captured_unix_ns),
            parents=(),
            artifacts=(artifact,),
            metadata=metadata,
        )
    except EvidenceValidationError as error:
        raise MonitorReplayError(
            EVIDENCE_INTEGRITY_FAILURE,
            "physical Monitor transcript Evidence is invalid",
        ) from error


def _physical_reference_envelope(
    reference: MonitorRunRefV2,
    transcript_envelope: EvidenceEnvelope,
) -> EvidenceEnvelope:
    raw = canonical_replay_json_bytes(reference.to_dict())
    digest = hashlib.sha256(raw).hexdigest()
    artifact = ArtifactRef(
        sha256=digest,
        size_bytes=len(raw),
        relative_path=f"objects/sha256/{digest[:2]}/{digest}",
        kind=MONITOR_RUN_REF_ARTIFACT_KIND,
        media_type="application/json",
    )
    try:
        return EvidenceEnvelope(
            identity=transcript_envelope.identity,
            operation=MONITOR_RUN_REF_OPERATION,
            produced_at_utc=transcript_envelope.produced_at_utc,
            parents=(reference.transcript_evidence_id,),
            artifacts=(artifact,),
            metadata=_physical_reference_metadata(reference),
        )
    except EvidenceValidationError as error:
        raise MonitorReplayError(
            EVIDENCE_INTEGRITY_FAILURE,
            "physical Monitor run reference Evidence is invalid",
        ) from error


def _physical_reference_root(
    reference: MonitorRunRefV2,
    envelope: EvidenceEnvelope,
) -> RootRecord:
    try:
        return RootRecord(
            root_type=MONITOR_RUN_REF_ROOT_TYPE,
            root_id=reference.operation_id,
            manifest_id=str(envelope.evidence_id),
            metadata=_physical_reference_metadata(reference),
        )
    except EvidenceValidationError as error:
        raise MonitorReplayError(
            EVIDENCE_INTEGRITY_FAILURE,
            "physical Monitor run reference root is invalid",
        ) from error


def _physical_transcript_root(reference: MonitorRunRefV2) -> RootRecord:
    try:
        return RootRecord(
            root_type=MONITOR_RUN_ROOT_TYPE,
            root_id=reference.operation_id,
            manifest_id=reference.transcript_evidence_id,
            metadata=_physical_expected_root_metadata(reference),
        )
    except EvidenceValidationError as error:
        raise MonitorReplayError(
            EVIDENCE_INTEGRITY_FAILURE,
            "physical Monitor transcript root is invalid",
        ) from error


def _physical_make_reference(
    *,
    scenario_role: str,
    operation_id: str,
    test_run_id: str,
    batches: tuple[SampleBatch, ...],
    transcript_evidence_id: str,
    source_record_sha256: str,
) -> MonitorRunRefV2:
    first = batches[0]
    last = batches[-1]
    binding = first.binding
    payload: dict[str, object] = {
        "schema": MONITOR_RUN_REF_SCHEMA_V2,
        "operation_id": operation_id,
        "scenario_role": scenario_role,
        "execution_source": "physical",
        "physical_transport_evidence": True,
        "origin_workspace_id": binding.workspace_id,
        "import_workspace_id": binding.workspace_id,
        "logical_project_id": binding.logical_project_id,
        "origin_session_id": binding.session_id,
        "projected_session_id": binding.session_id,
        "origin_run_id": operation_id,
        "projected_run_id": operation_id,
        "target_device": binding.target_device,
        "probe_id": binding.probe_id,
        "physical_target": binding.physical_target,
        "build_id": binding.build_id,
        "elf_sha256": binding.elf_sha256,
        "input_snapshot_sha256": binding.input_snapshot_sha256,
        "git_head": binding.git_head,
        "git_dirty": binding.git_dirty,
        "flash_session_id": binding.flash_session_id,
        "lease_id": binding.lease_id,
        "dwarf_sha256": binding.dwarf_sha256,
        "svd_sha256": binding.svd_sha256,
        "group_id": str(first.group_id),
        "group_revision": first.group_revision,
        "start_sequence": first.sequence,
        "end_sequence_exclusive": last.sequence + 1,
        "start_captured_unix_ns": first.captured_unix_ns,
        "end_captured_unix_ns_exclusive": last.captured_unix_ns + 1,
        "source_record_sha256": source_record_sha256,
        "projected_batch_sha256s": [_batch_digest(batch) for batch in batches],
        "transcript_evidence_id": transcript_evidence_id,
        "run_ref_sha256": "0" * 64,
    }
    unsigned = dict(payload)
    unsigned.pop("run_ref_sha256")
    payload["run_ref_sha256"] = hashlib.sha256(
        canonical_replay_json_bytes(unsigned)
    ).hexdigest()
    try:
        reference = MonitorRunRefV2.from_value(payload)
    except MonitorReplayError:
        raise
    return reference


def _physical_sample_batch_from_slice(
    history_slice: HistoryBatchSlice,
    values: tuple[SampleValue, ...],
) -> SampleBatch:
    """Construct one complete batch and preserve its model-boundary errors."""

    try:
        return SampleBatch(
            binding=history_slice.binding,
            group_id=history_slice.group_id,
            group_revision=history_slice.group_revision,
            run_id=history_slice.run_id,
            sequence=history_slice.sequence,
            scheduled_unix_ns=history_slice.scheduled_unix_ns,
            captured_unix_ns=history_slice.captured_unix_ns,
            latency_ns=history_slice.latency_ns,
            actual_rate_hz=history_slice.actual_rate_hz,
            subscriber_drops=history_slice.subscriber_drops,
            history_drops=history_slice.history_drops,
            deadline_drops=history_slice.deadline_drops,
            values=values,
        )
    except (TypeError, ValueError, OverflowError) as error:
        raise MonitorReplayError(
            EVIDENCE_INTEGRITY_FAILURE,
            "physical Monitor history contains invalid data",
        ) from error


def _physical_history_batches(
    *,
    paths: WorkspacePaths,
    run_id: str,
    group_id: UUID,
    start_sequence: int,
    end_sequence_exclusive: int,
    start_captured_unix_ns: int,
    end_captured_unix_ns_exclusive: int,
) -> tuple[SampleBatch, ...]:
    try:
        history = HistoryStore(paths)
    except (OSError, TypeError, ValueError) as error:
        raise MonitorReplayError(
            ENVIRONMENT_FAILURE,
            "physical Monitor history provider failed",
        ) from error
    except Exception as error:
        raise MonitorReplayError(
            ENVIRONMENT_FAILURE,
            "physical Monitor history provider failed",
        ) from error
    cursor: str | None = None
    seen_cursors: set[str] = set()
    slices: list[HistoryBatchSlice] = []
    fragment_values = 0
    try:
        monitor_run_uuid = UUID(run_id)
        while True:
            result = history.query_history(
                HistoryQuery(
                    session_id=paths.session_id,
                    start_ns=start_captured_unix_ns,
                    end_ns=end_captured_unix_ns_exclusive,
                    limit=MAX_HISTORY_VALUES,
                    cursor=cursor,
                    run_id=monitor_run_uuid,
                    group_id=group_id,
                )
            )
            if not result.ok or result.data is None:
                if result.code in {"MONITOR_STORAGE_CORRUPT", "MONITOR_STORAGE_INVALID"}:
                    _fail(EVIDENCE_INTEGRITY_FAILURE, "physical Monitor history is corrupt")
                _fail(ENVIRONMENT_FAILURE, "physical Monitor history provider failed")
            page = result.data
            if type(page) is not HistoryPage or type(page.batches) is not tuple:
                _fail(EVIDENCE_INTEGRITY_FAILURE, "physical Monitor history page is corrupt")
            for history_slice in page.batches:
                if (
                    type(history_slice) is not HistoryBatchSlice
                    or type(history_slice.values) is not tuple
                    or not history_slice.values
                    or any(type(value) is not SampleValue for value in history_slice.values)
                ):
                    _fail(
                        EVIDENCE_INTEGRITY_FAILURE,
                        "physical Monitor history contains invalid fragments",
                    )
                fragment_values += len(history_slice.values)
                if fragment_values > MAX_HISTORY_VALUES:
                    _physical_identity_error("physical Monitor history window is too large")
                slices.append(history_slice)
            next_cursor = page.next_cursor
            if next_cursor is None:
                break
            if next_cursor in seen_cursors:
                _fail(EVIDENCE_INTEGRITY_FAILURE, "physical Monitor history cursor repeated")
            seen_cursors.add(next_cursor)
            cursor = next_cursor
        if not slices:
            _physical_identity_error("physical Monitor history window is empty")
        batches: list[SampleBatch] = []
        closed_keys: set[tuple[object, ...]] = set()
        current_key: tuple[object, ...] | None = None
        current_evidence: tuple[object, ...] | None = None
        current_slice: HistoryBatchSlice | None = None
        current_values: list[SampleValue] = []
        current_next_ordinal = 0
        total_values = 0

        def finish_current() -> None:
            nonlocal current_key, current_evidence, current_slice
            nonlocal current_values, current_next_ordinal, total_values
            if current_slice is None or current_key is None or current_evidence is None:
                return
            if current_next_ordinal != current_slice.batch_value_count:
                _physical_identity_error(
                    "physical Monitor history ended with a partial batch"
                )
            reconstructed = _physical_sample_batch_from_slice(
                current_slice,
                tuple(current_values),
            )
            batches.append(reconstructed)
            if len(batches) > MAX_REPLAY_BATCHES:
                _physical_identity_error("physical Monitor history has too many batches")
            closed_keys.add(current_key)
            total_values += len(current_values)
            if total_values > MAX_HISTORY_VALUES:
                _physical_identity_error("physical Monitor history window is too large")
            current_key = None
            current_evidence = None
            current_slice = None
            current_values = []
            current_next_ordinal = 0

        for history_slice in slices:
            if type(history_slice) is not HistoryBatchSlice:
                _physical_identity_error("physical Monitor history contains invalid slices")
            key = (
                history_slice.binding.workspace_id,
                history_slice.binding.session_id,
                history_slice.run_id,
                history_slice.sequence,
            )
            evidence = (
                history_slice.binding,
                history_slice.group_id,
                history_slice.group_revision,
                history_slice.run_id,
                history_slice.sequence,
                history_slice.scheduled_unix_ns,
                history_slice.captured_unix_ns,
                history_slice.latency_ns,
                history_slice.actual_rate_hz,
                history_slice.subscriber_drops,
                history_slice.history_drops,
                history_slice.deadline_drops,
                history_slice.batch_value_count,
            )
            if current_key != key:
                if current_key is not None:
                    finish_current()
                if key in closed_keys or history_slice.start_ordinal != 0:
                    _physical_identity_error(
                        "physical Monitor history fragments are reordered or incomplete"
                    )
                current_key = key
                current_evidence = evidence
                current_slice = history_slice
                current_values = []
                current_next_ordinal = 0
            elif current_evidence != evidence:
                _physical_identity_error(
                    "physical Monitor history fragment metadata changed"
                )
            if history_slice.start_ordinal != current_next_ordinal:
                _physical_identity_error(
                    "physical Monitor history fragments have a gap or overlap"
                )
            current_values.extend(history_slice.values)
            current_next_ordinal += len(history_slice.values)
            if current_slice is None or current_next_ordinal > current_slice.batch_value_count:
                _physical_identity_error("physical Monitor history fragment exceeds its batch")
            if total_values + current_next_ordinal > MAX_HISTORY_VALUES:
                _physical_identity_error("physical Monitor history window is too large")
        finish_current()
        expected_sequences = tuple(range(start_sequence, end_sequence_exclusive))
        if tuple(batch.sequence for batch in batches) != expected_sequences:
            _physical_identity_error("physical Monitor history sequence window is invalid")
        first = batches[0]
        last = batches[-1]
        if (
            first.captured_unix_ns != start_captured_unix_ns
            or last.captured_unix_ns + 1 != end_captured_unix_ns_exclusive
        ):
            _physical_identity_error("physical Monitor history time window is invalid")
        selectors = tuple(value.watch for value in first.values)
        if any(
            tuple(value.watch for value in batch.values) != selectors
            or batch.captured_unix_ns <= previous.captured_unix_ns
            for previous, batch in zip(batches, batches[1:])
        ):
            _physical_identity_error("physical Monitor history sample chain is invalid")
        if any(
            batch.group_id != group_id
            or batch.run_id != monitor_run_uuid
            or batch.binding != first.binding
            or batch.group_revision != first.group_revision
            for batch in batches
        ):
            _physical_identity_error("physical Monitor history binding is inconsistent")
        return tuple(batches)
    finally:
        history.close()


def _physical_project_batches(
    batches: tuple[SampleBatch, ...],
    raw_probe_id: str,
) -> tuple[SampleBatch, ...]:
    hashed_probe_id = hashlib.sha256(raw_probe_id.encode("utf-8")).hexdigest()
    projected_binding = replace(batches[0].binding, probe_id=hashed_probe_id)
    return tuple(replace(batch, binding=projected_binding) for batch in batches)


def _physical_test_run(
    evidence_store: EvidenceStore,
    test_run_id: str,
) -> object:
    try:
        published = TestRunRepository(evidence_store).load(test_run_id)
    except EvidenceValidationError as error:
        raise MonitorReplayError(
            EVIDENCE_INTEGRITY_FAILURE,
            "physical TestRun Evidence is corrupt",
        ) from error
    except (OSError, TypeError, ValueError) as error:
        raise MonitorReplayError(
            ENVIRONMENT_FAILURE,
            "physical TestRun provider failed",
        ) from error
    metadata = dict(published.root.metadata)
    if (
        published.envelope.operation != "target-test-physical"
        or metadata.get("execution_source") != "physical"
        or metadata.get("physical_transport_evidence") is not True
        or published.manifest.mode != "target"
        or published.manifest.transport not in {"mailbox", "rtt", "uart", "semihosting"}
        or published.manifest.state not in {"passed", "failed", "error"}
    ):
        _physical_identity_error("linked TestRun is not an accepted physical Target run")
    return published


def _physical_validate_binding(
    *,
    published: object,
    batches: tuple[SampleBatch, ...],
    paths: WorkspacePaths,
    raw_probe_id: str,
    scenario_role: str,
) -> None:
    first = batches[0]
    binding = first.binding
    try:
        project = load_project_model(paths.project_root)
    except ProjectManifestError as error:
        raise MonitorReplayError(
            ENVIRONMENT_FAILURE,
            "physical Project manifest could not be loaded",
        ) from error
    except (OSError, TypeError, ValueError) as error:
        raise MonitorReplayError(
            ENVIRONMENT_FAILURE,
            "physical Project provider failed",
        ) from error
    if (
        project.schema_version != 3
        or str(project.logical_project_id) != binding.logical_project_id
        or project.debug.backend != "pyocd"
        or project.debug.target != binding.physical_target
        or project.target.device != binding.target_device
        or binding.workspace_id != paths.workspace_id
        or binding.session_id != paths.session_id
        or binding.probe_id != raw_probe_id
        or hashlib.sha256(raw_probe_id.encode("utf-8")).hexdigest()
        != str(published.root.metadata.get("probe_id"))
        or binding.flash_session_id != published.root.metadata.get("flash_session_id")
        or binding.lease_id != published.root.metadata.get("lease_id")
        or binding.target_device != published.root.metadata.get("target_id")
        or published.root.metadata.get("origin_workspace_id") != paths.workspace_id
        or published.root.metadata.get("import_workspace_id") != paths.workspace_id
        or published.root.metadata.get("origin_session_id") != paths.session_id
        or published.root.metadata.get("import_session_id") != paths.session_id
        or published.manifest.identity.workspace_id != binding.workspace_id
        or published.manifest.identity.project_id != binding.logical_project_id
        or published.manifest.identity.session_id != binding.session_id
        or published.manifest.identity.build_id != binding.build_id
        or published.manifest.identity.elf_sha256 != binding.elf_sha256
        or published.manifest.identity.target_device != binding.target_device
        or published.manifest.identity.input_snapshot_sha256 != binding.input_snapshot_sha256
        or published.manifest.identity.git_commit != binding.git_head
        or published.manifest.identity.git_dirty != binding.git_dirty
    ):
        _physical_identity_error("physical TestRun and Monitor history identity differ")
    expected_state = {"failed-before": "failed", "fixed-after": "passed"}[scenario_role]
    if published.manifest.state != expected_state:
        _physical_identity_error("physical TestRun state contradicts the scenario role")


def _parse_physical_transcript(
    raw: bytes,
) -> tuple[dict[str, object], tuple[SampleBatch, ...]]:
    try:
        wire = _decode_physical_json_bytes(raw)
        if type(wire) is not dict or set(wire) != {
            "schema",
            "source",
            "scenario_role",
            "test_run_id",
            "execution_source",
            "physical_transport_evidence",
            "binding",
            "batches",
        }:
            raise ReplayContractError("physical transcript fields are not closed")
        if (
            wire["schema"] != MONITOR_PHYSICAL_TRANSCRIPT_SCHEMA
            or wire["source"] != MONITOR_PHYSICAL_SOURCE
            or wire["execution_source"] != "physical"
            or wire["physical_transport_evidence"] is not True
            or wire["scenario_role"] not in _ROLES
        ):
            raise ReplayContractError("physical transcript provenance is invalid")
        _require_text(wire["test_run_id"], "test_run_id")
        binding = _parse_binding(wire["binding"])
        if (
            _SHA256.fullmatch(binding.probe_id) is None
            or binding.physical_target.startswith("replay:")
            or binding.flash_session_id.startswith("replay:")
            or binding.lease_id.startswith("replay:")
        ):
            raise ReplayContractError("physical transcript labels are invalid")
        raw_batches = wire["batches"]
        if type(raw_batches) is not list or not raw_batches or len(raw_batches) > MAX_REPLAY_BATCHES:
            raise ReplayContractError("physical transcript batches are invalid")
        batches = tuple(_parse_batch(item) for item in cast(list[object], raw_batches))
        first = batches[0]
        selectors = tuple(item.watch for item in first.values)
        previous_sequence: int | None = None
        previous_captured: int | None = None
        for batch in batches:
            if (
                batch.binding != binding
                or batch.group_id != first.group_id
                or batch.group_revision != first.group_revision
                or batch.run_id != first.run_id
                or tuple(item.watch for item in batch.values) != selectors
                or not batch.values
            ):
                raise ReplayContractError("physical transcript batch identity is invalid")
            if previous_sequence is not None and batch.sequence != previous_sequence + 1:
                raise ReplayContractError("physical transcript sequences are not contiguous")
            if previous_captured is not None and batch.captured_unix_ns <= previous_captured:
                raise ReplayContractError("physical transcript captured times are not increasing")
            previous_sequence = batch.sequence
            previous_captured = batch.captured_unix_ns
        return cast(dict[str, object], wire), batches
    except MonitorReplayError:
        raise
    except ReplayContractError as error:
        raise MonitorReplayError(
            EVIDENCE_INTEGRITY_FAILURE,
            "physical Monitor transcript is corrupt",
        ) from error
    except (KeyError, TypeError, ValueError, OverflowError) as error:
        raise MonitorReplayError(
            EVIDENCE_INTEGRITY_FAILURE,
            "physical Monitor transcript is corrupt",
        ) from error


def _decode_physical_json_bytes(raw: bytes) -> object:
    """Decode one canonical physical transcript without the replay 1 MiB limit."""

    if type(raw) is not bytes or len(raw) > MAX_PHYSICAL_TRANSCRIPT_BYTES:
        raise ReplayContractError("physical transcript bytes exceed their size limit")
    if raw.startswith(b"\xef\xbb\xbf"):
        raise ReplayContractError("physical transcript must not include a BOM")

    def pairs(items: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in items:
            if key in result:
                raise ReplayContractError("physical transcript has duplicate keys")
            result[key] = value
        return result

    def reject_constant(text: str) -> object:
        raise ReplayContractError(f"physical transcript has a non-finite number: {text}")

    try:
        decoded = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=pairs,
            parse_constant=reject_constant,
        )
    except ReplayContractError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, RecursionError) as error:
        raise ReplayContractError("physical transcript is not valid UTF-8 JSON") from error
    try:
        canonical = json.dumps(
            _physical_copy_json(decoded),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError, UnicodeError, RecursionError) as error:
        raise ReplayContractError("physical transcript canonical JSON is invalid") from error
    if len(canonical) > MAX_PHYSICAL_TRANSCRIPT_BYTES or canonical != raw:
        raise ReplayContractError("physical transcript JSON is not canonical")
    if type(decoded) is not dict:
        raise ReplayContractError("physical transcript must be a JSON object")
    return decoded


def _physical_publish_transcript(
    raw: bytes,
    expected_envelope: EvidenceEnvelope,
    expected_root: RootRecord,
    evidence_store: EvidenceStore,
) -> None:
    try:
        with tempfile.TemporaryDirectory(prefix="stm32-monitor-physical-") as directory:
            source = Path(directory) / "transcript.json"
            source.write_bytes(raw)
            artifact = evidence_store.ingest_file(
                source,
                kind="monitor-physical-transcript",
                media_type="application/json",
            )
        if artifact != expected_envelope.artifacts[0]:
            raise EvidenceValidationError(
                "EVIDENCE_CORRUPT",
                "physical transcript artifact identity differs from the expected source",
            )
        evidence_store.put_envelope(expected_envelope)
        try:
            put_root(evidence_store, expected_root)
        except EvidenceValidationError as error:
            if error.message == "root identity already has different canonical bytes":
                winner = _load_monitor_root(evidence_store, expected_root.root_id)
                if winner is None:
                    _fail(ENVIRONMENT_FAILURE, "physical Monitor transcript root disappeared")
                _validate_existing_root(
                    winner,
                    expected_root,
                    expected_envelope,
                    raw,
                    evidence_store,
                    maximum_bytes=MAX_PHYSICAL_TRANSCRIPT_BYTES,
                )
                return
            raise
    except MonitorReplayError:
        raise
    except OSError as error:
        raise MonitorReplayError(
            ENVIRONMENT_FAILURE,
            "physical Monitor transcript provider failed",
        ) from error
    except EvidenceValidationError as error:
        raise MonitorReplayError(
            EVIDENCE_INTEGRITY_FAILURE,
            "physical Monitor transcript publication is corrupt",
        ) from error
    except Exception as error:
        raise MonitorReplayError(
            ENVIRONMENT_FAILURE,
            "physical Monitor transcript publication failed",
        ) from error


def _physical_publish_reference(
    reference: MonitorRunRefV2,
    expected_envelope: EvidenceEnvelope,
    expected_root: RootRecord,
    evidence_store: EvidenceStore,
) -> None:
    raw = canonical_replay_json_bytes(reference.to_dict())
    try:
        with tempfile.TemporaryDirectory(prefix="stm32-monitor-physical-ref-") as directory:
            source = Path(directory) / "run-ref.json"
            source.write_bytes(raw)
            artifact = evidence_store.ingest_file(
                source,
                kind=MONITOR_RUN_REF_ARTIFACT_KIND,
                media_type="application/json",
            )
        if artifact != expected_envelope.artifacts[0]:
            raise EvidenceValidationError(
                "EVIDENCE_CORRUPT",
                "physical reference artifact identity differs from the expected reference",
            )
        evidence_store.put_envelope(expected_envelope)
        try:
            put_root(evidence_store, expected_root)
        except EvidenceValidationError as error:
            if error.message == "root identity already has different canonical bytes":
                _resolve_reference_root_race(evidence_store, expected_root)
                return
            raise
    except MonitorReplayError:
        raise
    except OSError as error:
        raise MonitorReplayError(
            ENVIRONMENT_FAILURE,
            "physical Monitor reference provider failed",
        ) from error
    except EvidenceValidationError as error:
        raise MonitorReplayError(
            EVIDENCE_INTEGRITY_FAILURE,
            "physical Monitor reference publication is corrupt",
        ) from error
    except Exception as error:
        raise MonitorReplayError(
            ENVIRONMENT_FAILURE,
            "physical Monitor reference publication failed",
        ) from error


def load_monitor_run_reference(
    paths: WorkspacePaths,
    evidence_store: EvidenceStore,
    operation_id: str,
) -> MonitorRunRefV2:
    """Reload one immutable physical Monitor run reference from Evidence."""

    if type(paths) is not WorkspacePaths or type(evidence_store) is not EvidenceStore:
        _physical_invalid("paths and evidence_store have invalid types")
    operation = _physical_operation_id(operation_id, "operation_id")
    reference_root = _load_monitor_reference_root(evidence_store, operation)
    transcript_root = _load_monitor_root(evidence_store, operation)
    if reference_root is None or transcript_root is None:
        _fail(EVIDENCE_INTEGRITY_FAILURE, "physical Monitor reference is incomplete")
    try:
        reference_envelope = evidence_store.get_envelope(reference_root.manifest_id)
        if (
            reference_envelope.operation != MONITOR_RUN_REF_OPERATION
            or reference_envelope.parents != (transcript_root.manifest_id,)
            or len(reference_envelope.artifacts) != 1
        ):
            raise ReplayContractError("physical reference envelope is invalid")
        reference_bytes = evidence_store.read_artifact(
            reference_envelope.artifacts[0],
            maximum_bytes=MAX_REPLAY_DOCUMENT_BYTES,
        )
        decoded_reference = decode_canonical_json_bytes(
            reference_bytes,
            require_object=True,
        )
        try:
            reference = MonitorRunRefV2.from_value(decoded_reference)
        except MonitorReplayError as error:
            raise ReplayContractError("physical reference bytes are invalid") from error
        if reference.operation_id != operation:
            raise ReplayContractError("physical reference operation ID is invalid")
        if reference_root.metadata != _physical_reference_metadata(reference):
            raise ReplayContractError("physical reference root metadata is invalid")
        if reference_envelope.metadata != _physical_reference_metadata(reference):
            raise ReplayContractError("physical reference envelope metadata is invalid")
        if reference_root.manifest_id != reference_envelope.evidence_id:
            raise ReplayContractError("physical reference root manifest is invalid")
        if reference_bytes != canonical_replay_json_bytes(reference.to_dict()):
            raise ReplayContractError("physical reference bytes are not canonical")

        transcript_envelope = evidence_store.get_envelope(transcript_root.manifest_id)
        if (
            transcript_envelope.operation != MONITOR_PHYSICAL_WINDOW_OPERATION
            or transcript_envelope.parents != ()
            or len(transcript_envelope.artifacts) != 1
        ):
            raise ReplayContractError("physical transcript envelope is invalid")
        transcript_bytes = evidence_store.read_artifact(
            transcript_envelope.artifacts[0],
            maximum_bytes=MAX_PHYSICAL_TRANSCRIPT_BYTES,
        )
        wire, batches = _parse_physical_transcript(transcript_bytes)
        source_digest = hashlib.sha256(transcript_bytes).hexdigest()
        if source_digest != reference.source_record_sha256:
            raise ReplayContractError("physical transcript digest differs from reference")
        if transcript_envelope.evidence_id != reference.transcript_evidence_id:
            raise ReplayContractError("physical transcript evidence ID differs from reference")
        if transcript_root.manifest_id != transcript_envelope.evidence_id:
            raise ReplayContractError("physical transcript root manifest is invalid")
        if transcript_root.metadata != _physical_expected_root_metadata(reference):
            raise ReplayContractError("physical transcript root metadata is invalid")
        binding = batches[0].binding
        expected_identity = EvidenceIdentity(
            workspace_id=binding.workspace_id,
            project_id=binding.logical_project_id,
            session_id=binding.session_id,
            build_id=binding.build_id,
            elf_sha256=binding.elf_sha256,
            target_device=binding.target_device,
            input_snapshot_sha256=binding.input_snapshot_sha256,
            git_commit=binding.git_head,
            git_dirty=binding.git_dirty,
        )
        if transcript_envelope.identity != expected_identity:
            raise ReplayContractError("physical transcript identity is invalid")
        if (
            wire["schema"] != MONITOR_PHYSICAL_TRANSCRIPT_SCHEMA
            or wire["source"] != MONITOR_PHYSICAL_SOURCE
            or wire["execution_source"] != reference.execution_source
            or wire["physical_transport_evidence"] is not reference.physical_transport_evidence
            or wire["scenario_role"] != reference.scenario_role
            or reference.origin_workspace_id != binding.workspace_id
            or reference.import_workspace_id != binding.workspace_id
            or reference.logical_project_id != binding.logical_project_id
            or reference.origin_session_id != binding.session_id
            or reference.projected_session_id != binding.session_id
            or reference.origin_run_id != operation
            or reference.projected_run_id != operation
            or str(batches[0].run_id) != operation
            or reference.target_device != binding.target_device
            or reference.probe_id != binding.probe_id
            or reference.physical_target != binding.physical_target
            or reference.build_id != binding.build_id
            or reference.elf_sha256 != binding.elf_sha256
            or reference.input_snapshot_sha256 != binding.input_snapshot_sha256
            or reference.git_head != binding.git_head
            or reference.git_dirty is not binding.git_dirty
            or reference.flash_session_id != binding.flash_session_id
            or reference.lease_id != binding.lease_id
            or reference.dwarf_sha256 != binding.dwarf_sha256
            or reference.svd_sha256 != binding.svd_sha256
            or binding.workspace_id != paths.workspace_id
            or binding.session_id != paths.session_id
            or reference.import_workspace_id != paths.workspace_id
            or reference.projected_session_id != paths.session_id
            or reference.origin_workspace_id != reference.import_workspace_id
            or reference.origin_session_id != reference.projected_session_id
            or reference.origin_run_id != operation
            or reference.projected_run_id != operation
            or reference.group_id != str(batches[0].group_id)
            or reference.group_revision != batches[0].group_revision
            or reference.start_sequence != batches[0].sequence
            or reference.end_sequence_exclusive != batches[-1].sequence + 1
            or reference.start_captured_unix_ns != batches[0].captured_unix_ns
            or reference.end_captured_unix_ns_exclusive != batches[-1].captured_unix_ns + 1
            or reference.projected_batch_sha256s
            != tuple(_batch_digest(batch) for batch in batches)
        ):
            raise ReplayContractError("physical transcript and reference windows differ")
        expected_transcript_metadata = dict(
            _physical_transcript_envelope(
                raw=transcript_bytes,
                scenario_role=cast(str, wire["scenario_role"]),
                test_run_id=cast(str, wire["test_run_id"]),
                batches=batches,
                paths=paths,
            ).metadata
        )
        if dict(transcript_envelope.metadata) != expected_transcript_metadata:
            raise ReplayContractError("physical transcript metadata is invalid")
        return reference
    except MonitorReplayError:
        raise
    except EvidenceValidationError as error:
        if _has_non_missing_os_error(error):
            raise MonitorReplayError(
                ENVIRONMENT_FAILURE,
                "physical Monitor Evidence provider failed",
            ) from error
        raise MonitorReplayError(
            EVIDENCE_INTEGRITY_FAILURE,
            "physical Monitor Evidence is corrupt",
        ) from error
    except OSError as error:
        if isinstance(error, FileNotFoundError):
            raise MonitorReplayError(
                EVIDENCE_INTEGRITY_FAILURE,
                "physical Monitor Evidence is corrupt",
            ) from error
        raise MonitorReplayError(
            ENVIRONMENT_FAILURE,
            "physical Monitor Evidence provider failed",
        ) from error
    except (ReplayContractError, TypeError, ValueError, OverflowError) as error:
        raise MonitorReplayError(
            EVIDENCE_INTEGRITY_FAILURE,
            "physical Monitor Evidence is corrupt",
        ) from error


def publish_physical_monitor_run(
    paths: WorkspacePaths,
    evidence_store: EvidenceStore,
    *,
    scenario_role: str,
    test_run_id: str,
    run_id: str,
    group_id: str,
    start_sequence: int,
    end_sequence_exclusive: int,
    start_captured_unix_ns: int,
    end_captured_unix_ns_exclusive: int,
    probe_id: str,
) -> MonitorRunRefV2:
    """Publish one complete live physical History window as a durable v2 reference."""

    if type(paths) is not WorkspacePaths or type(evidence_store) is not EvidenceStore:
        _physical_invalid("paths and evidence_store have invalid types")
    if scenario_role not in _ROLES:
        _physical_invalid("scenario_role is invalid")
    test_run_id = _require_text(test_run_id, "test_run_id", code=MONITOR_PHYSICAL_INVALID)
    operation = _physical_operation_id(run_id, "run_id")
    group_text = _physical_operation_id(group_id, "group_id")
    group_uuid = UUID(group_text)
    start_sequence = _physical_int(start_sequence, "start_sequence")
    end_sequence_exclusive = _physical_int(end_sequence_exclusive, "end_sequence_exclusive")
    start_captured_unix_ns = _physical_int(start_captured_unix_ns, "start_captured_unix_ns")
    end_captured_unix_ns_exclusive = _physical_int(
        end_captured_unix_ns_exclusive,
        "end_captured_unix_ns_exclusive",
    )
    if (
        end_sequence_exclusive <= start_sequence
        or end_captured_unix_ns_exclusive <= start_captured_unix_ns
    ):
        _physical_invalid("physical Monitor window is invalid")
    raw_probe_id = _physical_probe_selector(probe_id)

    # A complete reference is authoritative for request intent.  Check it
    # before touching the live TestRun or History providers so a changed
    # retry cannot observe or mutate a different window.
    existing_reference_root = _load_monitor_reference_root(evidence_store, operation)
    if existing_reference_root is not None:
        existing_reference = load_monitor_run_reference(
            paths,
            evidence_store,
            operation,
        )
        if (
            existing_reference.scenario_role != scenario_role
            or existing_reference.group_id != group_text
            or existing_reference.start_sequence != start_sequence
            or existing_reference.end_sequence_exclusive != end_sequence_exclusive
            or existing_reference.start_captured_unix_ns != start_captured_unix_ns
            or existing_reference.end_captured_unix_ns_exclusive
            != end_captured_unix_ns_exclusive
        ):
            _fail(OPERATION_CONFLICT, "complete physical reference intent differs")

    published = _physical_test_run(evidence_store, test_run_id)
    batches = _physical_history_batches(
        paths=paths,
        run_id=operation,
        group_id=group_uuid,
        start_sequence=start_sequence,
        end_sequence_exclusive=end_sequence_exclusive,
        start_captured_unix_ns=start_captured_unix_ns,
        end_captured_unix_ns_exclusive=end_captured_unix_ns_exclusive,
    )
    _physical_validate_binding(
        published=published,
        batches=batches,
        paths=paths,
        raw_probe_id=raw_probe_id,
        scenario_role=scenario_role,
    )
    projected = _physical_project_batches(batches, raw_probe_id)
    transcript_wire = _physical_transcript_wire(
        scenario_role=scenario_role,
        test_run_id=test_run_id,
        batches=projected,
    )
    transcript_raw = _physical_canonical_json_bytes(transcript_wire)
    transcript_envelope = _physical_transcript_envelope(
        raw=transcript_raw,
        scenario_role=scenario_role,
        test_run_id=test_run_id,
        batches=projected,
        paths=paths,
    )
    source_digest = hashlib.sha256(transcript_raw).hexdigest()
    reference = _physical_make_reference(
        scenario_role=scenario_role,
        operation_id=operation,
        test_run_id=test_run_id,
        batches=projected,
        transcript_evidence_id=str(transcript_envelope.evidence_id),
        source_record_sha256=source_digest,
    )
    reference_envelope = _physical_reference_envelope(reference, transcript_envelope)
    transcript_root = _physical_transcript_root(reference)
    reference_root = _physical_reference_root(reference, reference_envelope)

    # Both authoritative roots are checked against complete bytes before any root write.
    existing_transcript_root = _load_monitor_root(evidence_store, operation)
    existing_reference_root = _load_monitor_reference_root(evidence_store, operation)
    if existing_transcript_root is None and existing_reference_root is not None:
        _fail(EVIDENCE_INTEGRITY_FAILURE, "physical reference exists without its transcript root")
    if existing_transcript_root is not None:
        _validate_existing_root(
            existing_transcript_root,
            transcript_root,
            transcript_envelope,
            transcript_raw,
            evidence_store,
            maximum_bytes=MAX_PHYSICAL_TRANSCRIPT_BYTES,
        )
    if existing_reference_root is not None:
        _validate_existing_reference_root(
            existing_reference_root,
            reference_root,
            reference_envelope,
            reference,
            evidence_store,
        )
    if existing_transcript_root is None:
        _physical_publish_transcript(
            transcript_raw,
            transcript_envelope,
            transcript_root,
            evidence_store,
        )
    if existing_reference_root is None:
        _physical_publish_reference(
            reference,
            reference_envelope,
            reference_root,
            evidence_store,
        )
    return load_monitor_run_reference(paths, evidence_store, operation)


def ingest_monitor_replay(
    paths: WorkspacePaths,
    evidence_store: EvidenceStore,
    operation_id: str,
    document_file: Path | str,
) -> MonitorRunRef:
    """Validate one frozen replay document and project it through public HistoryStore."""

    if type(paths) is not WorkspacePaths or type(evidence_store) is not EvidenceStore:
        _fail(MONITOR_REPLAY_INVALID, "paths and evidence_store have invalid types")
    operation = _require_uuid(operation_id, "operation_id")
    raw = _read_document(document_file)
    decoded = _decode_document_bytes(raw)
    try:
        document = MonitorReplayDocument.from_value(decoded)
    except MonitorReplayError as error:
        raise MonitorReplayError(EVIDENCE_INTEGRITY_FAILURE, "replay document failed closed validation") from error
    if operation != str(document.batches[0].run_id):
        _fail(MONITOR_REPLAY_INVALID, "operation_id does not match the frozen replay run")
    try:
        projected = _project_batches(document, paths)
        if sum(len(batch.values) for batch in projected) > MAX_HISTORY_VALUES:
            _fail(EVIDENCE_INTEGRITY_FAILURE, "replay history window exceeds its value limit")
        expected_envelope = _expected_transcript_envelope(
            raw,
            document,
            paths,
            operation,
        )
        try:
            reference = _make_reference(
                document,
                paths,
                operation,
                projected,
                str(expected_envelope.evidence_id),
            )
        except MonitorReplayError as error:
            raise MonitorReplayError(
                EVIDENCE_INTEGRITY_FAILURE,
                "replay reference window is invalid",
            ) from error
        expected_root = _expected_root(reference)
        expected_reference_envelope = _expected_reference_envelope(
            reference,
            expected_envelope,
        )
        expected_reference_root = _expected_reference_root(
            reference,
            expected_reference_envelope,
        )
    except MonitorReplayError:
        raise
    try:
        root = _load_monitor_root(evidence_store, operation)
        reference_root = _load_monitor_reference_root(evidence_store, operation)
        if root is None and reference_root is not None:
            _fail(
                EVIDENCE_INTEGRITY_FAILURE,
                "monitor run reference exists without its transcript root",
            )
        history = HistoryStore(paths)
    except MonitorReplayError:
        raise
    except Exception as error:
        raise MonitorReplayError(ENVIRONMENT_FAILURE, "monitor replay storage failed") from error
    try:
        if root is not None:
            _validate_existing_root(
                root,
                expected_root,
                expected_envelope,
                raw,
                evidence_store,
            )
        if reference_root is not None:
            _validate_existing_reference_root(
                reference_root,
                expected_reference_root,
                expected_reference_envelope,
                reference,
                evidence_store,
            )
        existing = _load_existing_batches(history, paths, projected[0].run_id)
        if root is None:
            if existing:
                _fail(OPERATION_CONFLICT, "operation history exists without its authoritative root")
            _publish_transcript(raw, expected_envelope, evidence_store)
            try:
                put_root(evidence_store, expected_root)
            except EvidenceValidationError as error:
                if error.message == "root identity already has different canonical bytes":
                    _fail(OPERATION_CONFLICT, "operation root changed before publication")
                raise MonitorReplayError(
                    ENVIRONMENT_FAILURE,
                    "monitor run root publication failed",
                ) from error
        elif existing and existing != projected:
            _fail(OPERATION_CONFLICT, "operation history does not match its authoritative root")

        if reference_root is None:
            _publish_reference(
                reference,
                expected_reference_envelope,
                expected_reference_root,
                evidence_store,
            )
        if existing:
            return reference

        result = history.append_batches(projected)
        if not result.ok:
            if result.code == "MONITOR_STORAGE_INVALID":
                _fail(OPERATION_CONFLICT, "operation history changed before append")
            _fail(ENVIRONMENT_FAILURE, "monitor history append failed")
        return reference
    except MonitorReplayError:
        raise
    except Exception as error:
        raise MonitorReplayError(ENVIRONMENT_FAILURE, "monitor replay storage failed") from error
    finally:
        history.close()


__all__ = [
    "EVIDENCE_INTEGRITY_FAILURE",
    "ENVIRONMENT_FAILURE",
    "INCOMPATIBLE_IDENTITY",
    "MAX_REPLAY_BATCHES",
    "MAX_REPLAY_DOCUMENT_BYTES",
    "MAX_PHYSICAL_TRANSCRIPT_BYTES",
    "MONITOR_REPLAY_EXECUTION_SOURCE",
    "MONITOR_REPLAY_FLASH_SESSION_ID",
    "MONITOR_REPLAY_IMPORT_OPERATION",
    "MONITOR_REPLAY_INVALID",
    "MONITOR_REPLAY_LEASE_ID",
    "MONITOR_REPLAY_PHYSICAL_TARGET",
    "MONITOR_REPLAY_PROBE_ID",
    "MONITOR_REPLAY_SCHEMA",
    "MONITOR_REPLAY_SOURCE",
    "MONITOR_PHYSICAL_INVALID",
    "MONITOR_PHYSICAL_SOURCE",
    "MONITOR_PHYSICAL_TRANSCRIPT_SCHEMA",
    "MONITOR_PHYSICAL_WINDOW_OPERATION",
    "MONITOR_RUN_REF_ARTIFACT_KIND",
    "MONITOR_RUN_REF_OPERATION",
    "MONITOR_RUN_REF_ROOT_TYPE",
    "MONITOR_RUN_REF_SCHEMA",
    "MONITOR_RUN_REF_SCHEMA_V2",
    "MonitorReplayDocument",
    "MonitorReplayError",
    "MonitorRunRef",
    "MonitorRunRefV2",
    "OPERATION_CONFLICT",
    "canonical_replay_json_bytes",
    "ingest_monitor_replay",
    "load_monitor_run_reference",
    "publish_physical_monitor_run",
]
