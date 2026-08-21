"""Closed, non-physical Probe-v2 replay ingestion for the Monitor module."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
import hashlib
import json
import math
import re
import tempfile
import unicodedata
from pathlib import Path
from typing import cast
from uuid import UUID

from stm32_toolkit.evidence import ArtifactRef, EvidenceEnvelope, EvidenceIdentity, EvidenceValidationError
from stm32_toolkit.evidence.gc import RootRecord, get_root, put_root
from stm32_toolkit.evidence.store import EvidenceStore
from stm32_toolkit.paths import WorkspacePaths, require_safe_session_id

from .history import HistoryBatchSlice, HistoryQuery, HistoryStore, MAX_HISTORY_VALUES
from .models import (
    MAX_SIGNED_INT64,
    ObservationBinding,
    SampleBatch,
    SampleValue,
    WatchItem,
    unix_ns_to_utc,
)


MONITOR_REPLAY_SCHEMA = "stm32-monitor-replay/1"
MONITOR_REPLAY_SOURCE = "toolkit-generated-probe-v2-replay"
MONITOR_RUN_REF_SCHEMA = "stm32-monitor-run-ref/1"
MONITOR_REPLAY_IMPORT_OPERATION = "monitor-replay-import"
MONITOR_REPLAY_EXECUTION_SOURCE = "replay"
MONITOR_REPLAY_PROBE_ID = "replay:probe-v2"
MONITOR_REPLAY_PHYSICAL_TARGET = "replay:non-physical"
MONITOR_REPLAY_FLASH_SESSION_ID = "replay:no-flash"
MONITOR_REPLAY_LEASE_ID = "replay:no-lease"
MONITOR_RUN_ROOT_TYPE = "monitor-run"
MONITOR_RUN_REF_ROOT_TYPE = "monitor-run-ref"
MONITOR_RUN_REF_OPERATION = "monitor-run-ref"
MONITOR_RUN_REF_ARTIFACT_KIND = "monitor-run-ref"
MAX_REPLAY_DOCUMENT_BYTES = 1024 * 1024
MAX_REPLAY_BATCHES = 1024
MAX_REPLAY_JSON_DEPTH = 32
MAX_REPLAY_JSON_NODES = 10_000
MAX_REPLAY_JSON_STRING_CHARS = 1024 * 1024

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
    }
)
_ROLES = frozenset({"failed-before", "fixed-after"})
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_GIT_SHA = re.compile(r"[0-9a-f]{40}\Z")
_DOCUMENT_FIELDS = frozenset(
    {
        "schema",
        "source",
        "physical_transport_evidence",
        "scenario_role",
        "binding",
        "batches",
        "fixture_sha256",
    }
)
_BATCH_FIELDS = frozenset(
    {
        "binding",
        "groupId",
        "groupRevision",
        "runId",
        "sequence",
        "scheduledUnixNs",
        "scheduledAtUtc",
        "capturedUnixNs",
        "capturedAtUtc",
        "latencyNs",
        "actualRateHz",
        "subscriberDrops",
        "historyDrops",
        "deadlineDrops",
        "values",
    }
)
_SAMPLE_FIELDS = frozenset({"watch", "status", "typedValue", "code", "definition"})
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
_REF_FIELD_SET = frozenset(_REF_FIELDS)
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
_INTEGER_BATCH_FIELDS = (
    "groupRevision",
    "sequence",
    "scheduledUnixNs",
    "capturedUnixNs",
    "latencyNs",
    "subscriberDrops",
    "historyDrops",
    "deadlineDrops",
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


@dataclass
class _JsonBudget:
    nodes: int = 0
    string_chars: int = 0


def _json_copy(value: object, *, depth: int = 0, budget: _JsonBudget | None = None) -> object:
    state = budget if budget is not None else _JsonBudget()
    if depth > MAX_REPLAY_JSON_DEPTH:
        _fail(MONITOR_REPLAY_INVALID, "replay JSON exceeds its depth limit")
    state.nodes += 1
    if state.nodes > MAX_REPLAY_JSON_NODES:
        _fail(MONITOR_REPLAY_INVALID, "replay JSON exceeds its node limit")
    if value is None or type(value) is bool:
        return value
    if type(value) is int:
        if not -(1 << 63) <= value <= MAX_SIGNED_INT64:
            _fail(MONITOR_REPLAY_INVALID, "replay JSON integer is out of range")
        return value
    if type(value) is float:
        if not math.isfinite(value):
            _fail(MONITOR_REPLAY_INVALID, "replay JSON number is not finite")
        return value
    if type(value) is str:
        state.string_chars += len(value)
        if state.string_chars > MAX_REPLAY_JSON_STRING_CHARS:
            _fail(MONITOR_REPLAY_INVALID, "replay JSON string data exceeds its limit")
        if unicodedata.normalize("NFC", value) != value:
            _fail(MONITOR_REPLAY_INVALID, "replay JSON strings must use NFC")
        try:
            value.encode("utf-8")
        except UnicodeEncodeError:
            _fail(MONITOR_REPLAY_INVALID, "replay JSON contains invalid Unicode")
        return value
    if isinstance(value, tuple):
        _fail(MONITOR_REPLAY_INVALID, "replay JSON must not contain tuple containers")
    if isinstance(value, Mapping):
        copied: dict[str, object] = {}
        for key, item in value.items():
            if type(key) is not str:
                _fail(MONITOR_REPLAY_INVALID, "replay JSON object keys must be strings")
            if unicodedata.normalize("NFC", key) != key:
                _fail(MONITOR_REPLAY_INVALID, "replay JSON object keys must use NFC")
            if key in copied:
                _fail(MONITOR_REPLAY_INVALID, "replay JSON object keys must be unique")
            copied[key] = _json_copy(item, depth=depth + 1, budget=state)
        return copied
    if isinstance(value, list):
        return [_json_copy(item, depth=depth + 1, budget=state) for item in value]
    _fail(MONITOR_REPLAY_INVALID, "replay JSON contains an unsupported value")


def canonical_replay_json_bytes(value: object) -> bytes:
    """Return the bounded canonical JSON bytes used by replay digests."""

    if type(value) is MonitorReplayDocument or type(value) is MonitorRunRef:
        value = value.to_dict()
    copied = _json_copy(value)
    try:
        return json.dumps(
            copied,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, UnicodeError, ValueError, OverflowError) as error:
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


def _reject_tuples(value: object) -> None:
    if isinstance(value, tuple):
        _fail(MONITOR_REPLAY_INVALID, "replay JSON must not contain tuple containers")
    if isinstance(value, Mapping):
        for key, item in value.items():
            _reject_tuples(key)
            _reject_tuples(item)
    elif isinstance(value, list):
        for item in value:
            _reject_tuples(item)


def _parse_binding(value: object) -> ObservationBinding:
    if type(value) is not dict:
        _fail(MONITOR_REPLAY_INVALID, "replay binding is invalid")
    try:
        binding = ObservationBinding.from_dict(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise MonitorReplayError(MONITOR_REPLAY_INVALID, "replay binding is invalid") from error
    if type(binding) is not ObservationBinding:
        _fail(MONITOR_REPLAY_INVALID, "replay binding is invalid")
    return binding


def _parse_sample(value: object) -> SampleValue:
    if type(value) is not dict or set(value) != _SAMPLE_FIELDS:
        _fail(MONITOR_REPLAY_INVALID, "replay sample fields are not closed")
    watch_value = value["watch"]
    if type(watch_value) is not dict:
        _fail(MONITOR_REPLAY_INVALID, "replay sample watch is invalid")
    try:
        watch = WatchItem.from_dict(watch_value)
        sample = SampleValue(
            watch=watch,
            status=cast(str, value["status"]),
            typed_value=value["typedValue"],
            code=cast(str | None, value["code"]),
            definition=cast(Mapping[str, object] | None, value["definition"]),
        )
    except (TypeError, ValueError, OverflowError) as error:
        raise MonitorReplayError(MONITOR_REPLAY_INVALID, "replay sample is invalid") from error
    if type(sample) is not SampleValue or sample.to_dict() != value:
        _fail(MONITOR_REPLAY_INVALID, "replay sample is not canonical")
    return sample


def _parse_batch(value: object) -> SampleBatch:
    if type(value) is not dict or set(value) != _BATCH_FIELDS:
        _fail(MONITOR_REPLAY_INVALID, "replay batch fields are not closed")
    if type(value["values"]) is not list:
        _fail(MONITOR_REPLAY_INVALID, "replay batch values are invalid")
    if any(type(value[field_name]) is not int for field_name in _INTEGER_BATCH_FIELDS):
        _fail(MONITOR_REPLAY_INVALID, "replay batch integer fields are not canonical")
    if type(value["actualRateHz"]) is not float:
        _fail(MONITOR_REPLAY_INVALID, "replay batch rate must be a canonical float")
    binding = _parse_binding(value["binding"])
    try:
        batch = SampleBatch(
            binding=binding,
            group_id=UUID(cast(str, value["groupId"])),
            group_revision=cast(int, value["groupRevision"]),
            run_id=UUID(cast(str, value["runId"])),
            sequence=cast(int, value["sequence"]),
            scheduled_unix_ns=cast(int, value["scheduledUnixNs"]),
            captured_unix_ns=cast(int, value["capturedUnixNs"]),
            latency_ns=cast(int, value["latencyNs"]),
            actual_rate_hz=cast(float, value["actualRateHz"]),
            subscriber_drops=cast(int, value["subscriberDrops"]),
            history_drops=cast(int, value["historyDrops"]),
            deadline_drops=cast(int, value["deadlineDrops"]),
            values=tuple(_parse_sample(item) for item in value["values"]),
        )
    except MonitorReplayError:
        raise
    except (TypeError, ValueError, OverflowError) as error:
        raise MonitorReplayError(MONITOR_REPLAY_INVALID, "replay batch is invalid") from error
    if type(batch) is not SampleBatch or batch.to_dict() != value:
        _fail(MONITOR_REPLAY_INVALID, "replay batch is not canonical")
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
        _reject_tuples(value)
        if not isinstance(value, Mapping) or set(value) != _DOCUMENT_FIELDS:
            _fail(MONITOR_REPLAY_INVALID, "replay document fields are not closed")
        if type(value["batches"]) is not list:
            _fail(MONITOR_REPLAY_INVALID, "replay document batches must be a JSON array")
        binding = _parse_binding(value["binding"])
        try:
            batches = tuple(_parse_batch(item) for item in value["batches"])
            document = cls(
                schema=cast(str, value["schema"]),
                source=cast(str, value["source"]),
                physical_transport_evidence=cast(bool, value["physical_transport_evidence"]),
                scenario_role=cast(str, value["scenario_role"]),
                binding=binding,
                batches=batches,
                fixture_sha256=cast(str, value["fixture_sha256"]),
            )
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
    def from_value(cls, value: object) -> "MonitorRunRef":
        if type(value) is cls:
            return value
        _reject_tuples(value)
        if not isinstance(value, Mapping) or set(value) != _REF_FIELD_SET:
            _fail(MONITOR_REPLAY_INVALID, "monitor run reference fields are not closed")
        if type(value["projected_batch_sha256s"]) is not list:
            _fail(MONITOR_REPLAY_INVALID, "projected batch digests must be a JSON array")
        try:
            return cls(
                **{
                    field_name: (
                        tuple(value[field_name])
                        if field_name == "projected_batch_sha256s"
                        else value[field_name]
                    )
                    for field_name in _REF_FIELDS
                }
            )
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


def _decode_document_bytes(raw: bytes) -> dict[str, object]:
    if type(raw) is not bytes or not raw or len(raw) > MAX_REPLAY_DOCUMENT_BYTES:
        _fail(EVIDENCE_INTEGRITY_FAILURE, "replay document exceeds its bounded input limit")
    if raw.startswith(b"\xef\xbb\xbf"):
        _fail(EVIDENCE_INTEGRITY_FAILURE, "replay document must not contain a BOM")

    def pairs(items: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, item in items:
            if key in result:
                _fail(EVIDENCE_INTEGRITY_FAILURE, "replay document has duplicate JSON keys")
            result[key] = item
        return result

    def reject_constant(_: str) -> object:
        _fail(EVIDENCE_INTEGRITY_FAILURE, "replay document has a non-finite JSON number")

    try:
        decoded = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=pairs,
            parse_constant=reject_constant,
        )
    except MonitorReplayError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        _fail(EVIDENCE_INTEGRITY_FAILURE, "replay document is not valid UTF-8 JSON")
    try:
        canonical = canonical_replay_json_bytes(decoded)
    except MonitorReplayError:
        _fail(EVIDENCE_INTEGRITY_FAILURE, "replay document is not canonical JSON")
    if raw not in (canonical, canonical + b"\n"):
        _fail(EVIDENCE_INTEGRITY_FAILURE, "replay document is not canonical JSON")
    if type(decoded) is not dict:
        _fail(EVIDENCE_INTEGRITY_FAILURE, "replay document must be a JSON object")
    return decoded


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
            decoded = json.loads(captured.decode("utf-8"))
            stored = MonitorRunRef.from_value(decoded)
        except MonitorReplayError as error:
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
            maximum_bytes=MAX_REPLAY_DOCUMENT_BYTES,
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
    "MAX_REPLAY_BATCHES",
    "MAX_REPLAY_DOCUMENT_BYTES",
    "MONITOR_REPLAY_EXECUTION_SOURCE",
    "MONITOR_REPLAY_FLASH_SESSION_ID",
    "MONITOR_REPLAY_IMPORT_OPERATION",
    "MONITOR_REPLAY_INVALID",
    "MONITOR_REPLAY_LEASE_ID",
    "MONITOR_REPLAY_PHYSICAL_TARGET",
    "MONITOR_REPLAY_PROBE_ID",
    "MONITOR_REPLAY_SCHEMA",
    "MONITOR_REPLAY_SOURCE",
    "MONITOR_RUN_REF_ARTIFACT_KIND",
    "MONITOR_RUN_REF_OPERATION",
    "MONITOR_RUN_REF_ROOT_TYPE",
    "MONITOR_RUN_REF_SCHEMA",
    "MonitorReplayDocument",
    "MonitorReplayError",
    "MonitorRunRef",
    "OPERATION_CONFLICT",
    "canonical_replay_json_bytes",
    "ingest_monitor_replay",
]
