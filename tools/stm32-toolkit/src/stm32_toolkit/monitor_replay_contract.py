"""Dependency-neutral wire validation for the Monitor replay boundary."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
import hashlib
import json
import math
import re
import unicodedata
from uuid import UUID


MONITOR_REPLAY_SCHEMA = "stm32-monitor-replay/1"
MONITOR_REPLAY_SOURCE = "toolkit-generated-probe-v2-replay"
MONITOR_RUN_REF_SCHEMA = "stm32-monitor-run-ref/1"
MONITOR_REPLAY_EXECUTION_SOURCE = "replay"
MONITOR_REPLAY_PROBE_ID = "replay:probe-v2"
MONITOR_REPLAY_PHYSICAL_TARGET = "replay:non-physical"
MONITOR_REPLAY_FLASH_SESSION_ID = "replay:no-flash"
MONITOR_REPLAY_LEASE_ID = "replay:no-lease"
MAX_REPLAY_DOCUMENT_BYTES = 1024 * 1024
MAX_REPLAY_BATCHES = 1024
MAX_REPLAY_JSON_DEPTH = 32
MAX_REPLAY_JSON_NODES = 10_000
MAX_REPLAY_JSON_STRING_CHARS = 1024 * 1024
MIN_SIGNED_INT64 = -(1 << 63)
MAX_SIGNED_INT64 = (1 << 63) - 1

_ROLES = frozenset({"failed-before", "fixed-after"})
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_GIT_SHA = re.compile(r"[0-9a-f]{40}\Z")
_SESSION_ID = re.compile(r"[a-z0-9][a-z0-9_-]*\Z")
_WINDOWS_DEVICE_NAMES = {
    "con",
    "prn",
    "aux",
    "nul",
    *(f"com{number}" for number in range(1, 10)),
    *(f"lpt{number}" for number in range(1, 10)),
}
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
_BINDING_FIELDS = frozenset(
    {
        "workspaceId",
        "logicalProjectId",
        "sessionId",
        "probeId",
        "targetDevice",
        "physicalTarget",
        "buildId",
        "elfSha256",
        "inputSnapshotSha256",
        "gitHead",
        "gitDirty",
        "flashSessionId",
        "leaseId",
        "dwarfSha256",
        "svdSha256",
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
_VARIABLE_WATCH_FIELDS = frozenset({"kind", "expression"})
_REGISTER_WATCH_FIELDS = frozenset({"kind", "registerPath"})
_REF_FIELDS = frozenset(
    {
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
    }
)


class ReplayContractError(ValueError):
    """A bounded failure at the shared replay wire boundary."""


class _JsonBudget:
    __slots__ = ("nodes", "string_chars", "active")

    def __init__(self) -> None:
        self.nodes = 0
        self.string_chars = 0
        self.active: set[int] = set()


def _fail(message: str) -> None:
    raise ReplayContractError(message)


def _copy_json(value: object, *, depth: int = 0, budget: _JsonBudget | None = None) -> object:
    state = budget if budget is not None else _JsonBudget()
    if depth > MAX_REPLAY_JSON_DEPTH:
        _fail("replay JSON exceeds its depth limit")
    state.nodes += 1
    if state.nodes > MAX_REPLAY_JSON_NODES:
        _fail("replay JSON exceeds its node limit")
    if value is None or type(value) is bool:
        return value
    if type(value) is int:
        if not MIN_SIGNED_INT64 <= value <= MAX_SIGNED_INT64:
            _fail("replay JSON integer is out of range")
        return value
    if type(value) is float:
        if not math.isfinite(value):
            _fail("replay JSON number is not finite")
        return value
    if type(value) is str:
        state.string_chars += len(value)
        if state.string_chars > MAX_REPLAY_JSON_STRING_CHARS:
            _fail("replay JSON string data exceeds its limit")
        if unicodedata.normalize("NFC", value) != value:
            _fail("replay JSON strings must use NFC")
        try:
            value.encode("utf-8")
        except UnicodeEncodeError as error:
            raise ReplayContractError("replay JSON contains invalid Unicode") from error
        return value
    if isinstance(value, tuple):
        _fail("replay JSON must not contain tuple containers")
    if isinstance(value, Mapping):
        identity = id(value)
        if identity in state.active:
            _fail("replay JSON contains a cycle")
        state.active.add(identity)
        try:
            copied: dict[str, object] = {}
            for key, item in value.items():
                if type(key) is not str:
                    _fail("replay JSON object keys must be strings")
                if unicodedata.normalize("NFC", key) != key:
                    _fail("replay JSON object keys must use NFC")
                if key in copied:
                    _fail("replay JSON object keys must be unique")
                copied[key] = _copy_json(item, depth=depth + 1, budget=state)
            return copied
        finally:
            state.active.remove(identity)
    if isinstance(value, list):
        identity = id(value)
        if identity in state.active:
            _fail("replay JSON contains a cycle")
        state.active.add(identity)
        try:
            return [_copy_json(item, depth=depth + 1, budget=state) for item in value]
        finally:
            state.active.remove(identity)
    _fail("replay JSON contains an unsupported value")


def canonical_replay_json_bytes(value: object) -> bytes:
    """Return the bounded canonical JSON bytes used by replay digests."""

    copied = _copy_json(value)
    try:
        return json.dumps(
            copied,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, UnicodeError, ValueError, OverflowError) as error:
        raise ReplayContractError("replay JSON is not canonical") from error


def decode_canonical_json_bytes(
    raw: bytes,
    *,
    allow_final_lf: bool = False,
    require_object: bool = True,
) -> object:
    """Decode one bounded canonical JSON payload without provider dependencies."""

    if type(raw) is not bytes or not raw or len(raw) > MAX_REPLAY_DOCUMENT_BYTES:
        _fail("replay JSON exceeds its bounded input limit")
    if raw.startswith(b"\xef\xbb\xbf"):
        _fail("replay JSON must not contain a BOM")
    candidate = raw[:-1] if allow_final_lf and raw.endswith(b"\n") else raw

    def pairs(items: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, item in items:
            if key in result:
                _fail("replay JSON has duplicate object keys")
            result[key] = item
        return result

    def reject_constant(_: str) -> object:
        _fail("replay JSON contains a non-finite number")

    try:
        decoded = json.loads(
            candidate.decode("utf-8"),
            object_pairs_hook=pairs,
            parse_constant=reject_constant,
        )
    except ReplayContractError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ReplayContractError("replay JSON is not valid UTF-8 JSON") from error
    try:
        canonical = canonical_replay_json_bytes(decoded)
    except ReplayContractError:
        raise
    if raw != canonical and not (allow_final_lf and raw == canonical + b"\n"):
        _fail("replay JSON is not canonical")
    copied = _copy_json(decoded)
    if require_object and type(copied) is not dict:
        _fail("replay JSON must be an object")
    return copied


def _mapping(value: object, fields: frozenset[str], label: str) -> dict[str, object]:
    if type(value) is not dict or set(value) != fields:
        _fail(f"{label} fields are not closed")
    return value


def _text(value: object, label: str, maximum: int) -> str:
    if (
        type(value) is not str
        or not value
        or len(value) > maximum
        or value.strip() != value
        or unicodedata.normalize("NFC", value) != value
        or any(ord(character) < 32 for character in value)
    ):
        _fail(f"{label} is invalid")
    return value


def _hash(value: object, label: str) -> str:
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        _fail(f"{label} is invalid")
    return value


def _uuid(value: object, label: str) -> str:
    if type(value) is not str:
        _fail(f"{label} is invalid")
    try:
        parsed = UUID(value)
    except (TypeError, ValueError) as error:
        raise ReplayContractError(f"{label} is invalid") from error
    if str(parsed) != value:
        _fail(f"{label} is invalid")
    return value


def _session(value: object, label: str) -> str:
    if (
        type(value) is not str
        or _SESSION_ID.fullmatch(value) is None
        or value in _WINDOWS_DEVICE_NAMES
    ):
        _fail(f"{label} is invalid")
    return value


def _integer(value: object, label: str, *, positive: bool = False) -> int:
    minimum = 1 if positive else 0
    if type(value) is not int or not minimum <= value <= MAX_SIGNED_INT64:
        _fail(f"{label} is invalid")
    return value


def _timestamp(unix_ns: int, label: str) -> str:
    seconds, remainder = divmod(unix_ns, 1_000_000_000)
    try:
        timestamp = datetime.fromtimestamp(seconds, tz=timezone.utc).replace(
            microsecond=remainder // 1_000
        )
    except (OSError, OverflowError, ValueError) as error:
        raise ReplayContractError(f"{label} is invalid") from error
    return timestamp.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _validate_binding(value: object) -> dict[str, object]:
    binding = _mapping(value, _BINDING_FIELDS, "replay binding")
    for field in (
        "workspaceId",
        "buildId",
        "elfSha256",
        "inputSnapshotSha256",
        "dwarfSha256",
    ):
        _hash(binding[field], field)
    if binding["svdSha256"] is not None:
        _hash(binding["svdSha256"], "svdSha256")
    _uuid(binding["logicalProjectId"], "logicalProjectId")
    _session(binding["sessionId"], "sessionId")
    for field in ("probeId", "targetDevice", "physicalTarget", "flashSessionId", "leaseId"):
        _text(binding[field], field, 256)
    if type(binding["gitDirty"]) is not bool:
        _fail("gitDirty is invalid")
    if type(binding["gitHead"]) is not str or _GIT_SHA.fullmatch(binding["gitHead"]) is None:
        _fail("gitHead is invalid")
    if (
        binding["probeId"] != MONITOR_REPLAY_PROBE_ID
        or binding["physicalTarget"] != MONITOR_REPLAY_PHYSICAL_TARGET
        or binding["flashSessionId"] != MONITOR_REPLAY_FLASH_SESSION_ID
        or binding["leaseId"] != MONITOR_REPLAY_LEASE_ID
    ):
        _fail("replay binding labels are invalid")
    return binding


def _validate_watch(value: object) -> dict[str, object]:
    if type(value) is not dict:
        _fail("replay watch is invalid")
    kind = value.get("kind")
    if kind == "variable":
        watch = _mapping(value, _VARIABLE_WATCH_FIELDS, "variable watch")
        _text(watch["expression"], "watch selector", 512)
        return watch
    if kind == "register":
        watch = _mapping(value, _REGISTER_WATCH_FIELDS, "register watch")
        _text(watch["registerPath"], "watch selector", 512)
        return watch
    _fail("replay watch kind is invalid")


def _validate_sample(value: object) -> dict[str, object]:
    sample = _mapping(value, _SAMPLE_FIELDS, "replay sample")
    _validate_watch(sample["watch"])
    status = sample["status"]
    if type(status) is not str or status not in {"OK", "ERROR"}:
        _fail("replay sample status is invalid")
    typed_value = sample["typedValue"]
    code = sample["code"]
    if status == "OK":
        if typed_value is None or code is not None:
            _fail("replay successful sample is invalid")
    else:
        if typed_value is not None or type(code) is not str:
            _fail("replay failed sample is invalid")
        _text(code, "sample code", 128)
    definition = sample["definition"]
    if definition is not None and type(definition) is not dict:
        _fail("sample definition is invalid")
    return sample


def _validate_batch(value: object, binding: dict[str, object]) -> dict[str, object]:
    batch = _mapping(value, _BATCH_FIELDS, "replay batch")
    if batch["binding"] != binding:
        _fail("replay batch binding contradicts the document binding")
    _uuid(batch["groupId"], "groupId")
    _uuid(batch["runId"], "runId")
    _integer(batch["groupRevision"], "groupRevision", positive=True)
    for field in (
        "sequence",
        "scheduledUnixNs",
        "capturedUnixNs",
        "latencyNs",
        "subscriberDrops",
        "historyDrops",
        "deadlineDrops",
    ):
        _integer(batch[field], field)
    if batch["capturedUnixNs"] < batch["scheduledUnixNs"]:
        _fail("replay batch captured time precedes scheduled time")
    if batch["scheduledAtUtc"] != _timestamp(batch["scheduledUnixNs"], "scheduledAtUtc"):
        _fail("scheduledAtUtc is invalid")
    if batch["capturedAtUtc"] != _timestamp(batch["capturedUnixNs"], "capturedAtUtc"):
        _fail("capturedAtUtc is invalid")
    actual_rate = batch["actualRateHz"]
    if type(actual_rate) is not float or not math.isfinite(actual_rate) or actual_rate < 0:
        _fail("actualRateHz is invalid")
    values = batch["values"]
    if type(values) is not list or not values or len(values) > 256:
        _fail("replay batch values are invalid")
    for sample in values:
        _validate_sample(sample)
    return batch


def validate_replay_document(value: object) -> dict[str, object]:
    """Return a deep canonical wire copy of a replay document."""

    document = _copy_json(value)
    if type(document) is not dict:
        _fail("replay document must be an object")
    document = _mapping(document, _DOCUMENT_FIELDS, "replay document")
    if document["schema"] != MONITOR_REPLAY_SCHEMA:
        _fail("replay document schema is invalid")
    if document["source"] != MONITOR_REPLAY_SOURCE:
        _fail("replay document source is invalid")
    if type(document["physical_transport_evidence"]) is not bool or document["physical_transport_evidence"]:
        _fail("replay document physical evidence must be false")
    if type(document["scenario_role"]) is not str or document["scenario_role"] not in _ROLES:
        _fail("replay document scenario role is invalid")
    binding = _validate_binding(document["binding"])
    _hash(document["fixture_sha256"], "fixture_sha256")
    batches = document["batches"]
    if type(batches) is not list or not batches or len(batches) > MAX_REPLAY_BATCHES:
        _fail("replay document batches are invalid")
    parsed = [_validate_batch(batch, binding) for batch in batches]
    first = parsed[0]
    first_group = first["groupId"]
    first_revision = first["groupRevision"]
    first_run = first["runId"]
    selectors = [sample["watch"] for sample in first["values"]]
    if len({canonical_replay_json_bytes(item) for item in selectors}) != len(selectors):
        _fail("replay document selectors are not unique")
    previous_sequence: int | None = None
    previous_scheduled: int | None = None
    previous_captured: int | None = None
    for index, batch in enumerate(parsed):
        if (
            batch["groupId"] != first_group
            or batch["groupRevision"] != first_revision
            or batch["runId"] != first_run
            or batch["sequence"] != (first["sequence"] + index)
            or [sample["watch"] for sample in batch["values"]] != selectors
        ):
            _fail("replay document batch chain is invalid")
        sequence = batch["sequence"]
        scheduled = batch["scheduledUnixNs"]
        captured = batch["capturedUnixNs"]
        if previous_sequence is not None and sequence != previous_sequence + 1:
            _fail("replay document sequences are not contiguous")
        if previous_scheduled is not None and scheduled <= previous_scheduled:
            _fail("replay document scheduled times are not increasing")
        if previous_captured is not None and captured <= previous_captured:
            _fail("replay document captured times are not increasing")
        previous_sequence = sequence
        previous_scheduled = scheduled
        previous_captured = captured
    unsigned = {key: item for key, item in document.items() if key != "fixture_sha256"}
    expected = hashlib.sha256(canonical_replay_json_bytes(unsigned)).hexdigest()
    if document["fixture_sha256"] != expected:
        _fail("replay document fixture digest is invalid")
    return document


def validate_run_reference(value: object) -> dict[str, object]:
    """Return a deep canonical wire copy of a MonitorRunRef."""

    reference = _copy_json(value)
    if type(reference) is not dict:
        _fail("monitor run reference must be an object")
    reference = _mapping(reference, _REF_FIELDS, "monitor run reference")
    if reference["schema"] != MONITOR_RUN_REF_SCHEMA:
        _fail("monitor run reference schema is invalid")
    operation_id = _uuid(reference["operation_id"], "operation_id")
    if type(reference["scenario_role"]) is not str or reference["scenario_role"] not in _ROLES:
        _fail("monitor run reference scenario role is invalid")
    if reference["execution_source"] != MONITOR_REPLAY_EXECUTION_SOURCE:
        _fail("monitor run reference execution source is invalid")
    if type(reference["physical_transport_evidence"]) is not bool or reference["physical_transport_evidence"]:
        _fail("monitor run reference physical evidence must be false")
    for field in ("origin_workspace_id", "import_workspace_id"):
        _hash(reference[field], field)
    _uuid(reference["logical_project_id"], "logical_project_id")
    _session(reference["origin_session_id"], "origin_session_id")
    _session(reference["projected_session_id"], "projected_session_id")
    origin_run_id = _uuid(reference["origin_run_id"], "origin_run_id")
    projected_run_id = _uuid(reference["projected_run_id"], "projected_run_id")
    if operation_id != origin_run_id or projected_run_id != origin_run_id:
        _fail("monitor run reference operation and run IDs contradict")
    for field in ("target_device", "probe_id", "physical_target", "flash_session_id", "lease_id"):
        _text(reference[field], field, 256)
    if (
        reference["probe_id"] != MONITOR_REPLAY_PROBE_ID
        or reference["physical_target"] != MONITOR_REPLAY_PHYSICAL_TARGET
        or reference["flash_session_id"] != MONITOR_REPLAY_FLASH_SESSION_ID
        or reference["lease_id"] != MONITOR_REPLAY_LEASE_ID
    ):
        _fail("monitor run reference labels are invalid")
    for field in (
        "build_id",
        "elf_sha256",
        "input_snapshot_sha256",
        "dwarf_sha256",
        "fixture_sha256",
        "transcript_evidence_id",
    ):
        _hash(reference[field], field)
    if reference["svd_sha256"] is not None:
        _hash(reference["svd_sha256"], "svd_sha256")
    if type(reference["git_head"]) is not str or _GIT_SHA.fullmatch(reference["git_head"]) is None:
        _fail("git_head is invalid")
    if type(reference["git_dirty"]) is not bool:
        _fail("git_dirty is invalid")
    _uuid(reference["group_id"], "group_id")
    _integer(reference["group_revision"], "group_revision", positive=True)
    for field in (
        "start_sequence",
        "end_sequence_exclusive",
        "start_captured_unix_ns",
        "end_captured_unix_ns_exclusive",
    ):
        _integer(reference[field], field)
    if (
        reference["end_sequence_exclusive"] <= reference["start_sequence"]
        or reference["end_captured_unix_ns_exclusive"] <= reference["start_captured_unix_ns"]
    ):
        _fail("monitor run reference windows are invalid")
    projected = reference["projected_batch_sha256s"]
    if type(projected) is not list or not projected or len(projected) > MAX_REPLAY_BATCHES:
        _fail("projected batch digests are invalid")
    for digest in projected:
        _hash(digest, "projected batch digest")
    _hash(reference["run_ref_sha256"], "run_ref_sha256")
    unsigned = {key: item for key, item in reference.items() if key != "run_ref_sha256"}
    expected = hashlib.sha256(canonical_replay_json_bytes(unsigned)).hexdigest()
    if reference["run_ref_sha256"] != expected:
        _fail("monitor run reference digest is invalid")
    return reference


__all__ = [
    "MAX_REPLAY_BATCHES",
    "MAX_REPLAY_DOCUMENT_BYTES",
    "MAX_REPLAY_JSON_DEPTH",
    "MAX_REPLAY_JSON_NODES",
    "MAX_REPLAY_JSON_STRING_CHARS",
    "ReplayContractError",
    "MONITOR_REPLAY_EXECUTION_SOURCE",
    "MONITOR_REPLAY_FLASH_SESSION_ID",
    "MONITOR_REPLAY_LEASE_ID",
    "MONITOR_REPLAY_PHYSICAL_TARGET",
    "MONITOR_REPLAY_PROBE_ID",
    "MONITOR_REPLAY_SCHEMA",
    "MONITOR_REPLAY_SOURCE",
    "MONITOR_RUN_REF_SCHEMA",
    "canonical_replay_json_bytes",
    "decode_canonical_json_bytes",
    "validate_replay_document",
    "validate_run_reference",
]
