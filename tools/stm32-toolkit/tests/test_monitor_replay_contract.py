from __future__ import annotations

from copy import deepcopy
import hashlib
import importlib
import json
from pathlib import Path
from types import ModuleType
from uuid import UUID

import pytest

from stm32_monitor.replay import (
    MonitorReplayDocument,
    MonitorReplayError,
    MonitorRunRef,
    canonical_replay_json_bytes,
    ingest_monitor_replay,
)
from stm32_monitor.models import SampleValue, WatchItem
from stm32_toolkit.evidence.store import EvidenceStore
from stm32_toolkit.paths import WorkspacePaths


FIXTURES = Path(__file__).parent / "fixtures" / "vs03" / "target"
MONITOR_FIXTURES = Path(__file__).parents[2] / "stm32-monitor" / "tests" / "fixtures" / "vs03"
PROJECT_ID = UUID("123e4567-e89b-42d3-a456-426614174000")
RUN_IDS = {
    "failed-before": "33333333-3333-4333-8333-333333333333",
    "fixed-after": "44444444-4444-4444-8444-444444444444",
}


def _contract() -> ModuleType:
    try:
        return importlib.import_module("stm32_toolkit.monitor_replay_contract")
    except ModuleNotFoundError:
        pytest.fail("shared replay wire contract is not implemented")


def _document(role: str) -> dict[str, object]:
    raw = (MONITOR_FIXTURES / f"{role}.json").read_bytes()
    return json.loads(raw[:-1].decode("utf-8"))


def _reference(tmp_path: Path, role: str) -> dict[str, object]:
    project = tmp_path / f"project-{role}"
    project.mkdir()
    paths = WorkspacePaths.from_roots(
        tmp_path / f"state-{role}",
        project,
        PROJECT_ID,
        f"contract-{role}",
    )
    evidence = EvidenceStore(paths.workspace_root / "evidence")
    return ingest_monitor_replay(
        paths,
        evidence,
        RUN_IDS[role],
        MONITOR_FIXTURES / f"{role}.json",
    ).to_dict()


def _selector_key(watch: dict[str, object]) -> str:
    return "expression" if watch["kind"] == "variable" else "registerPath"


def _raw_canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _redigest_document(document: dict[str, object]) -> None:
    unsigned = {key: value for key, value in document.items() if key != "fixture_sha256"}
    document["fixture_sha256"] = hashlib.sha256(_raw_canonical_json_bytes(unsigned)).hexdigest()


def _redigest_reference(reference: dict[str, object]) -> None:
    unsigned = {key: value for key, value in reference.items() if key != "run_ref_sha256"}
    reference["run_ref_sha256"] = hashlib.sha256(_raw_canonical_json_bytes(unsigned)).hexdigest()


def _document_digest(document: dict[str, object]) -> str:
    unsigned = {key: value for key, value in document.items() if key != "fixture_sha256"}
    return hashlib.sha256(_raw_canonical_json_bytes(unsigned)).hexdigest()


def _reference_digest(reference: dict[str, object]) -> str:
    unsigned = {key: value for key, value in reference.items() if key != "run_ref_sha256"}
    return hashlib.sha256(_raw_canonical_json_bytes(unsigned)).hexdigest()


def _redigest_public_document(
    contract: ModuleType, document: dict[str, object]
) -> None:
    unsigned = {key: value for key, value in document.items() if key != "fixture_sha256"}
    document["fixture_sha256"] = hashlib.sha256(
        contract.canonical_replay_json_bytes(unsigned)
    ).hexdigest()


def _redigest_public_reference(
    contract: ModuleType, reference: dict[str, object]
) -> None:
    unsigned = {key: value for key, value in reference.items() if key != "run_ref_sha256"}
    reference["run_ref_sha256"] = hashlib.sha256(
        contract.canonical_replay_json_bytes(unsigned)
    ).hexdigest()


def _physical_transcript(source: dict[str, object]) -> dict[str, object]:
    binding = deepcopy(source["binding"])
    binding.update(
        {
            "probeId": hashlib.sha256(b"probe/serial/01").hexdigest(),
            "physicalTarget": "board:fixture-01",
            "flashSessionId": "flash-session-01",
            "leaseId": "lease-01",
        }
    )
    batches = []
    for batch in source["batches"]:
        copy = deepcopy(batch)
        copy["binding"] = deepcopy(binding)
        batches.append(copy)
    return {
        "schema": "stm32-monitor-physical-transcript/1",
        "source": "toolkit-live-history",
        "scenario_role": source["scenario_role"],
        "test_run_id": "physical-test-run-01",
        "execution_source": "physical",
        "physical_transport_evidence": True,
        "binding": binding,
        "batches": batches,
    }


def _physical_v2_reference() -> dict[str, object]:
    run_id = "11111111-1111-4111-8111-111111111111"
    reference: dict[str, object] = {
        "schema": "stm32-monitor-run-ref/2",
        "operation_id": run_id,
        "scenario_role": "failed-before",
        "execution_source": "physical",
        "physical_transport_evidence": True,
        "origin_workspace_id": "a" * 64,
        "import_workspace_id": "a" * 64,
        "logical_project_id": "123e4567-e89b-42d3-a456-426614174000",
        "origin_session_id": "session",
        "projected_session_id": "session",
        "origin_run_id": run_id,
        "projected_run_id": run_id,
        "target_device": "stm32f429zi",
        "probe_id": "b" * 64,
        "physical_target": "stm32f429zi",
        "build_id": "c" * 64,
        "elf_sha256": "d" * 64,
        "input_snapshot_sha256": "e" * 64,
        "git_head": "f" * 40,
        "git_dirty": False,
        "flash_session_id": "flash",
        "lease_id": "lease",
        "dwarf_sha256": "1" * 64,
        "svd_sha256": None,
        "group_id": "123e4567-e89b-42d3-a456-426614174001",
        "group_revision": 1,
        "start_sequence": 0,
        "end_sequence_exclusive": 2,
        "start_captured_unix_ns": 1,
        "end_captured_unix_ns_exclusive": 3,
        "source_record_sha256": "2" * 64,
        "projected_batch_sha256s": ["3" * 64, "4" * 64],
        "transcript_evidence_id": "5" * 64,
        "run_ref_sha256": "0" * 64,
    }
    unsigned = {key: value for key, value in reference.items() if key != "run_ref_sha256"}
    reference["run_ref_sha256"] = hashlib.sha256(_raw_canonical_json_bytes(unsigned)).hexdigest()
    return reference


def _document_bindings(document: dict[str, object]) -> list[dict[str, object]]:
    return [
        document["binding"],
        *[batch["binding"] for batch in document["batches"]],
    ]


def _set_binding_field(document: dict[str, object], field: str, value: object) -> None:
    for binding in _document_bindings(document):
        binding[field] = deepcopy(value)


def _remove_binding_field(document: dict[str, object], field: str) -> None:
    for binding in _document_bindings(document):
        binding.pop(field)


def _set_batch_field(document: dict[str, object], field: str, value: object) -> None:
    for batch in document["batches"]:
        batch[field] = deepcopy(value)


def _replace_first_selector_in_all_batches(
    document: dict[str, object], replacement: str
) -> None:
    source_watch = document["batches"][0]["values"][0]["watch"]
    field = _selector_key(source_watch)
    original = source_watch[field]
    replaced = 0
    for batch in document["batches"]:
        for sample in batch["values"]:
            watch = sample["watch"]
            if _selector_key(watch) == field and watch[field] == original:
                watch[field] = replacement
                replaced += 1
    assert replaced >= 2


def _deep_json(depth: int) -> object:
    value: object = None
    for _ in range(depth):
        value = {"nested": value}
    return value


def _assert_bool_target_isolated(
    source: dict[str, object], candidate: dict[str, object]
) -> None:
    assert candidate["batches"][0]["subscriberDrops"] is True
    assert candidate["batches"][1]["subscriberDrops"] == source["batches"][1]["subscriberDrops"]
    restored = deepcopy(candidate)
    restored["batches"][0]["subscriberDrops"] = source["batches"][0]["subscriberDrops"]
    restored["fixture_sha256"] = source["fixture_sha256"]
    assert restored == source


def _assert_group_id_target_isolated(
    source: dict[str, object], candidate: dict[str, object]
) -> None:
    replacement = candidate["batches"][0]["groupId"]
    assert replacement != source["batches"][0]["groupId"]
    assert all(batch["groupId"] == replacement for batch in candidate["batches"])
    restored = deepcopy(candidate)
    for index, batch in enumerate(restored["batches"]):
        batch["groupId"] = source["batches"][index]["groupId"]
    restored["fixture_sha256"] = source["fixture_sha256"]
    assert restored == source


def _assert_group_revision_target_isolated(
    source: dict[str, object], candidate: dict[str, object]
) -> None:
    replacement = candidate["batches"][0]["groupRevision"]
    assert replacement != source["batches"][0]["groupRevision"]
    assert all(batch["groupRevision"] == replacement for batch in candidate["batches"])
    restored = deepcopy(candidate)
    for index, batch in enumerate(restored["batches"]):
        batch["groupRevision"] = source["batches"][index]["groupRevision"]
    restored["fixture_sha256"] = source["fixture_sha256"]
    assert restored == source


def _assert_reference_group_id_target_isolated(
    source: dict[str, object], candidate: dict[str, object]
) -> None:
    assert candidate["group_id"] != source["group_id"]
    assert candidate["operation_id"] == source["operation_id"]
    assert candidate["origin_run_id"] == source["origin_run_id"]
    assert candidate["projected_run_id"] == source["projected_run_id"]
    restored = deepcopy(candidate)
    restored["group_id"] = source["group_id"]
    restored["run_ref_sha256"] = source["run_ref_sha256"]
    assert restored == source


_DOCUMENT_TARGET_TABLE = {
    "bool-as-int": {
        "target": "subscriberDrops must reject bool-as-int",
        "coherence": "change only batch zero's unbound subscriberDrops count",
        "oracle": _assert_bool_target_isolated,
    },
    "uuid": {
        "target": "groupId must be a valid UUID",
        "coherence": "apply one replacement groupId to every batch",
        "oracle": _assert_group_id_target_isolated,
    },
    "range": {
        "target": "groupRevision must remain positive",
        "coherence": "apply one replacement groupRevision to every batch",
        "oracle": _assert_group_revision_target_isolated,
    },
}

_REFERENCE_TARGET_TABLE = {
    "reference-uuid": {
        "target": "group_id must be a valid UUID",
        "coherence": "change only group_id and preserve operation/run identity",
        "oracle": _assert_reference_group_id_target_isolated,
    },
}


def _run_target_sensitivity_oracle(
    table: dict[str, dict[str, object]],
    case_name: str,
    source: dict[str, object],
    candidate: dict[str, object],
) -> None:
    row = table.get(case_name)
    if row is not None:
        row["oracle"](source, candidate)


def _document_mutations(document: dict[str, object]) -> dict[str, dict[str, object]]:
    def fresh() -> dict[str, object]:
        return deepcopy(document)

    cases: dict[str, dict[str, object]] = {}

    value = fresh()
    value["unexpected"] = True
    _redigest_document(value)
    cases["document-extra"] = value

    value = fresh()
    value.pop("batches")
    _redigest_document(value)
    cases["document-missing"] = value

    value = fresh()
    _set_binding_field(value, "unexpected", True)
    _redigest_document(value)
    cases["binding-extra"] = value

    value = fresh()
    _remove_binding_field(value, "workspaceId")
    _redigest_document(value)
    cases["binding-missing"] = value

    value = fresh()
    value["batches"][0]["unexpected"] = True
    _redigest_document(value)
    cases["batch-extra"] = value

    value = fresh()
    value["batches"][0].pop("values")
    _redigest_document(value)
    cases["batch-missing"] = value

    value = fresh()
    value["batches"][0]["values"][0]["unexpected"] = True
    _redigest_document(value)
    cases["sample-extra"] = value

    value = fresh()
    value["batches"][0]["values"][0].pop("status")
    _redigest_document(value)
    cases["sample-missing"] = value

    value = fresh()
    watch = value["batches"][0]["values"][0]["watch"]
    watch["unexpected"] = True
    _redigest_document(value)
    cases["watch-extra"] = value

    value = fresh()
    watch = value["batches"][0]["values"][0]["watch"]
    watch.pop(_selector_key(watch))
    _redigest_document(value)
    cases["watch-missing"] = value

    value = fresh()
    _replace_first_selector_in_all_batches(value, " counter")
    _redigest_document(value)
    cases["selector-whitespace"] = value

    value = fresh()
    _replace_first_selector_in_all_batches(value, "e\u0301")
    _redigest_document(value)
    cases["selector-nfc"] = value

    value = fresh()
    _replace_first_selector_in_all_batches(value, "bad\u0000selector")
    _redigest_document(value)
    cases["selector-control"] = value

    value = fresh()
    value["batches"][0]["subscriberDrops"] = True
    _redigest_document(value)
    cases["bool-as-int"] = value

    value = fresh()
    value["batches"][0]["actualRateHz"] = 1
    _redigest_document(value)
    cases["integer-rate"] = value

    value = fresh()
    value["batches"][0]["scheduledAtUtc"] = "1970-01-01T00:00:00.000000Z"
    _redigest_document(value)
    cases["timestamp"] = value

    value = fresh()
    group_id = value["batches"][0]["groupId"]
    _set_batch_field(value, "groupId", f"{group_id[:-1]}A")
    _redigest_document(value)
    cases["uuid"] = value

    value = fresh()
    _set_binding_field(value, "buildId", "g" * 64)
    _redigest_document(value)
    cases["hash"] = value

    value = fresh()
    _set_batch_field(value, "groupRevision", 0)
    _redigest_document(value)
    cases["range"] = value

    value = fresh()
    value["batches"][0]["values"][0]["typedValue"] = _deep_json(40)
    _redigest_document(value)
    cases["typed-json-bounds"] = value

    value = fresh()
    value["batches"][0]["values"][0]["definition"] = []
    _redigest_document(value)
    cases["definition-json-shape"] = value

    value = fresh()
    value["batches"] = list(reversed(value["batches"]))
    _redigest_document(value)
    cases["batch-order"] = value

    value = fresh()
    second_watch = value["batches"][1]["values"][0]["watch"]
    second_watch[_selector_key(second_watch)] = "different.selector"
    _redigest_document(value)
    cases["batch-vocabulary"] = value

    value = fresh()
    value["fixture_sha256"] = "0" * 64
    cases["fixture-digest"] = value
    return cases


def _reference_mutations(reference: dict[str, object]) -> dict[str, dict[str, object]]:
    def fresh() -> dict[str, object]:
        return deepcopy(reference)

    cases: dict[str, dict[str, object]] = {}

    value = fresh()
    value["unexpected"] = True
    _redigest_reference(value)
    cases["reference-extra"] = value

    value = fresh()
    value.pop("projected_batch_sha256s")
    _redigest_reference(value)
    cases["reference-missing"] = value

    value = fresh()
    value["projected_batch_sha256s"] = ["bad"]
    _redigest_reference(value)
    cases["projected-digest-list"] = value

    value = fresh()
    value["run_ref_sha256"] = "0" * 64
    cases["unsigned-ref-digest"] = value

    value = fresh()
    value["group_revision"] = 0
    _redigest_reference(value)
    cases["reference-range"] = value

    value = fresh()
    value["build_id"] = "g" * 64
    _redigest_reference(value)
    cases["reference-hash"] = value

    value = fresh()
    group_id = value["group_id"]
    value["group_id"] = f"{group_id[:-1]}A"
    _redigest_reference(value)
    cases["reference-uuid"] = value

    value = fresh()
    value["fixture_sha256"] = "0" * 64
    cases["reference-fixture-digest"] = value
    return cases


@pytest.mark.parametrize("role", ("failed-before", "fixed-after"))
def test_shared_contract_accepts_the_two_real_replay_documents_without_mutation(
    role: str,
) -> None:
    contract = _contract()
    payload = _document(role)
    before = deepcopy(payload)
    document = MonitorReplayDocument.from_value(payload)
    shared = contract.validate_replay_document(payload)
    assert document.to_dict() == payload
    assert shared == payload
    assert shared is not payload
    assert shared["binding"] is not payload["binding"]
    assert payload == before
    assert contract.canonical_replay_json_bytes(payload) == canonical_replay_json_bytes(payload)


@pytest.mark.parametrize("role", ("failed-before", "fixed-after"))
def test_shared_byte_decoder_reloads_canonical_replay_fixture_and_optional_final_lf(
    role: str,
) -> None:
    contract = _contract()
    with_final_lf = (MONITOR_FIXTURES / f"{role}.json").read_bytes()
    assert with_final_lf.endswith(b"\n")
    raw = with_final_lf[:-1]
    before = bytes(raw)

    decoded = contract.decode_canonical_json_bytes(raw)
    validated = contract.validate_replay_document(decoded)
    assert decoded == _document(role)
    assert validated == decoded
    assert raw == before

    with pytest.raises(contract.ReplayContractError):
        contract.decode_canonical_json_bytes(with_final_lf)
    assert contract.decode_canonical_json_bytes(with_final_lf, allow_final_lf=True) == decoded
    assert with_final_lf == before + b"\n"


def test_shared_physical_byte_decoder_reloads_canonical_transcript_without_mutation() -> None:
    contract = _contract()
    payload = _physical_transcript(_document("failed-before"))
    raw = contract.canonical_physical_json_bytes(payload)
    before = bytes(raw)

    decoded = contract.decode_physical_transcript_bytes(raw)

    assert decoded == payload
    assert contract.validate_physical_transcript(decoded) == payload
    assert raw == before


@pytest.mark.parametrize(
    ("case_name", "expected_message"),
    (
        pytest.param(
            "empty",
            "physical transcript bytes exceed their bounded input limit",
            id="empty",
        ),
        pytest.param(
            "bom",
            "physical transcript JSON must not contain a BOM",
            id="bom",
        ),
        pytest.param(
            "duplicate-key",
            "physical transcript JSON has duplicate object keys",
            id="duplicate-key",
        ),
        pytest.param(
            "scalar-root",
            "physical transcript JSON must be an object",
            id="scalar-root",
        ),
        pytest.param(
            "noncanonical",
            "physical transcript JSON is not canonical",
            id="noncanonical",
        ),
    ),
)
def test_shared_physical_byte_decoder_rejects_public_encoding_and_size_variants(
    case_name: str, expected_message: str
) -> None:
    contract = _contract()
    payload = _physical_transcript(_document("failed-before"))
    source_before = deepcopy(payload)
    canonical = contract.canonical_physical_json_bytes(payload)
    assert contract.decode_physical_transcript_bytes(canonical) == payload
    assert payload == source_before

    if case_name == "empty":
        raw = canonical[:0]
    elif case_name == "bom":
        raw = b"\xef\xbb\xbf" + canonical
    elif case_name == "duplicate-key":
        schema = b'"schema":"stm32-monitor-physical-transcript/1"'
        assert schema in canonical
        raw = canonical.replace(schema, schema + b"," + schema, 1)
    elif case_name == "scalar-root":
        raw = b"[]"
    else:
        raw = b" " + canonical

    before = bytes(raw)
    with pytest.raises(contract.ReplayContractError) as error:
        contract.decode_physical_transcript_bytes(raw)

    assert str(error.value) == expected_message
    assert raw == before


@pytest.mark.parametrize(
    ("case_name", "raw"),
    [
        pytest.param("duplicate-key", b'{"a":1,"a":2}', id="duplicate-key"),
        pytest.param("bom", b"\xef\xbb\xbf{}", id="bom"),
        pytest.param("noncanonical-whitespace", b'{ "a": 1}', id="noncanonical-whitespace"),
        pytest.param("invalid-utf8", b"\xff", id="invalid-utf8"),
        pytest.param("scalar-root", b"1", id="scalar-root"),
        pytest.param(
            "depth-limit",
            json.dumps(_deep_json(33), sort_keys=True, separators=(",", ":")).encode("utf-8"),
            id="depth-limit",
        ),
        pytest.param(
            "node-limit",
            json.dumps([0] * 10_000, separators=(",", ":")).encode("utf-8"),
            id="node-limit",
        ),
        pytest.param("input-size-limit", b"0" * (1024 * 1024 + 1), id="input-size-limit"),
    ],
)
def test_shared_byte_decoder_rejects_caller_meaningful_raw_wire_failures(
    case_name: str, raw: bytes,
) -> None:
    contract = _contract()
    before = bytes(raw)

    with pytest.raises(contract.ReplayContractError):
        contract.decode_canonical_json_bytes(raw)

    assert case_name
    assert raw == before


@pytest.mark.parametrize(
    ("field", "value", "recompute_digest"),
    [
        ("physical_transport_evidence", False, False),
        ("end_sequence_exclusive", 0, True),
    ],
)
def test_shared_v2_reference_rejects_provenance_and_window_contradictions(
    field: str, value: object, recompute_digest: bool,
) -> None:
    contract = _contract()
    source = _physical_v2_reference()
    validated = contract.validate_run_reference(source)
    assert validated == source
    assert source == _physical_v2_reference()

    candidate = deepcopy(source)
    candidate[field] = value
    if recompute_digest:
        unsigned = {key: item for key, item in candidate.items() if key != "run_ref_sha256"}
        candidate["run_ref_sha256"] = hashlib.sha256(_raw_canonical_json_bytes(unsigned)).hexdigest()
    before = deepcopy(candidate)

    with pytest.raises(contract.ReplayContractError):
        contract.validate_run_reference(candidate)

    assert candidate == before


@pytest.mark.parametrize("role", ("failed-before", "fixed-after"))
def test_shared_contract_accepts_the_two_real_run_references_without_mutation(
    tmp_path: Path,
    role: str,
) -> None:
    contract = _contract()
    payload = _reference(tmp_path, role)
    before = deepcopy(payload)
    reference = MonitorRunRef.from_value(payload)
    shared = contract.validate_run_reference(payload)
    assert reference.to_dict() == payload
    assert shared == payload
    assert shared is not payload
    assert shared["projected_batch_sha256s"] is not payload["projected_batch_sha256s"]
    assert payload == before


def test_shared_contract_rejects_replay_source_v2_reference(tmp_path: Path) -> None:
    contract = _contract()
    payload = _reference(tmp_path, "failed-before")
    payload["schema"] = "stm32-monitor-run-ref/2"
    payload["source_record_sha256"] = payload.pop("fixture_sha256")
    payload["execution_source"] = "replay"
    payload["physical_transport_evidence"] = False
    payload["probe_id"] = "replay:probe-v2"
    payload["physical_target"] = "replay:non-physical"
    payload["flash_session_id"] = "replay:no-flash"
    payload["lease_id"] = "replay:no-lease"
    unsigned = {key: value for key, value in payload.items() if key != "run_ref_sha256"}
    payload["run_ref_sha256"] = hashlib.sha256(
        _raw_canonical_json_bytes(unsigned)
    ).hexdigest()

    with pytest.raises(contract.ReplayContractError):
        contract.validate_run_reference(payload)


@pytest.mark.parametrize("role", ("failed-before", "fixed-after"))
def test_shared_contract_accepts_closed_physical_transcript_without_raw_selector(
    role: str,
) -> None:
    contract = _contract()
    payload = _physical_transcript(_document(role))
    before = deepcopy(payload)
    validated = contract.validate_physical_transcript(payload)
    assert validated == payload
    assert validated is not payload
    assert validated["binding"] is not payload["binding"]
    assert b"probe/serial/01" not in contract.canonical_physical_json_bytes(payload)
    assert payload == before

    extra = deepcopy(payload)
    extra["unexpected"] = True
    with pytest.raises(contract.ReplayContractError):
        contract.validate_physical_transcript(extra)


@pytest.mark.parametrize(
    ("mutation", "expected_message"),
    (
        ("schema", "physical transcript schema is invalid"),
        ("source", "physical transcript source is invalid"),
        ("execution-source", "physical transcript execution source is invalid"),
        ("physical-evidence", "physical transcript physical evidence must be true"),
        ("scenario-role", "physical transcript scenario role is invalid"),
        ("test-run-id", "test_run_id is invalid"),
        ("binding-probe", "physical binding labels are invalid"),
        ("binding-git", "gitHead is invalid"),
        ("binding-svd", "svdSha256 is invalid"),
        ("empty-batches", "physical transcript batches are invalid"),
        ("batch-shape", "physical transcript batches are invalid"),
        ("batch-binding", "replay batch binding contradicts the document binding"),
        ("batch-group", "physical transcript batch identity is invalid"),
        ("batch-revision", "physical transcript batch identity is invalid"),
        ("batch-run", "physical transcript batch identity is invalid"),
        ("batch-sequence", "physical transcript sequences are not contiguous"),
        ("batch-captured", "physical transcript captured times are not increasing"),
        ("batch-selector", "physical transcript batch identity is invalid"),
        ("duplicate-selector", "physical transcript selectors are not unique"),
        ("empty-values", "replay batch values are invalid"),
        ("sample-status", "replay sample status is invalid"),
        ("sample-code", "replay successful sample is invalid"),
        ("sample-definition", "sample definition is invalid"),
        ("integer-rate", "actualRateHz is invalid"),
        ("captured-before-scheduled", "replay batch captured time precedes scheduled time"),
        ("value-budget", "physical transcript values exceed their limit"),
    ),
)
def test_shared_physical_contract_rejects_nested_wire_mutations(
    mutation: str, expected_message: str
) -> None:
    contract = _contract()
    candidate = _physical_transcript(_document("failed-before"))
    if mutation == "schema":
        candidate["schema"] = "stm32-monitor-physical-transcript/9"
    elif mutation == "source":
        candidate["source"] = "untrusted-source"
    elif mutation == "execution-source":
        candidate["execution_source"] = "replay"
    elif mutation == "physical-evidence":
        candidate["physical_transport_evidence"] = False
    elif mutation == "scenario-role":
        candidate["scenario_role"] = "other"
    elif mutation == "test-run-id":
        candidate["test_run_id"] = ""
    elif mutation == "binding-probe":
        candidate["binding"]["probeId"] = "replay:probe-v2"
    elif mutation == "binding-git":
        candidate["binding"]["gitHead"] = "g" * 40
    elif mutation == "binding-svd":
        candidate["binding"]["svdSha256"] = "invalid"
    elif mutation == "empty-batches":
        candidate["batches"] = []
    elif mutation == "batch-shape":
        candidate["batches"] = {}
    elif mutation == "batch-binding":
        candidate["batches"][1]["binding"] = deepcopy(candidate["binding"])
        candidate["batches"][1]["binding"]["workspaceId"] = "b" * 64
    elif mutation == "batch-group":
        candidate["batches"][1]["groupId"] = "55555555-5555-4555-8555-555555555555"
    elif mutation == "batch-revision":
        candidate["batches"][1]["groupRevision"] = 2
    elif mutation == "batch-run":
        candidate["batches"][1]["runId"] = "55555555-5555-4555-8555-555555555555"
    elif mutation == "batch-sequence":
        candidate["batches"][1]["sequence"] = 2
    elif mutation == "batch-captured":
        first = candidate["batches"][0]
        second = candidate["batches"][1]
        # Keep both rows valid against their own scheduled time and UTC/latency
        # fields, then violate only the cross-batch increasing-capture rule.
        first["capturedUnixNs"] = second["capturedUnixNs"]
        first["capturedAtUtc"] = second["capturedAtUtc"]
        first["latencyNs"] = first["capturedUnixNs"] - first["scheduledUnixNs"]
    elif mutation == "batch-selector":
        watch = candidate["batches"][1]["values"][0]["watch"]
        watch[_selector_key(watch)] = "different.selector"
    elif mutation == "duplicate-selector":
        first_values = candidate["batches"][0]["values"]
        first_values.append(deepcopy(first_values[0]))
    elif mutation == "empty-values":
        candidate["batches"][0]["values"] = []
    elif mutation == "sample-status":
        candidate["batches"][0]["values"][0]["status"] = "UNKNOWN"
    elif mutation == "sample-code":
        candidate["batches"][0]["values"][0]["code"] = "NATIVE_ERROR"
    elif mutation == "sample-definition":
        candidate["batches"][0]["values"][0]["definition"] = []
    elif mutation == "integer-rate":
        candidate["batches"][0]["actualRateHz"] = 1
    elif mutation == "captured-before-scheduled":
        candidate["batches"][0]["capturedUnixNs"] = candidate["batches"][0]["scheduledUnixNs"] - 1
    elif mutation == "value-budget":
        first = candidate["batches"][0]
        source_sample = first["values"][0]
        first["values"] = []
        for index in range(256):
            sample = deepcopy(source_sample)
            watch = sample["watch"]
            watch[_selector_key(watch)] = f"r{index}"
            sample["typedValue"]["expression"] = f"r{index}"
            first["values"].append(sample)
        candidate["batches"] = [deepcopy(first) for _ in range(40)]
    before = deepcopy(candidate)

    with pytest.raises(contract.ReplayContractError) as error:
        contract.validate_physical_transcript(candidate)
    assert str(error.value) == expected_message
    assert candidate == before


@pytest.mark.parametrize(
    ("mutation", "expected_message"),
    (
        pytest.param(
            "root-collection",
            "physical transcript must be an object",
            id="root-collection",
        ),
        pytest.param("group-id-type", "groupId is invalid", id="group-id-type"),
        pytest.param(
            "session-device-name",
            "sessionId is invalid",
            id="session-device-name",
        ),
        pytest.param(
            "watch-kind",
            "replay watch kind is invalid",
            id="watch-kind",
        ),
        pytest.param(
            "captured-utc",
            "capturedAtUtc is invalid",
            id="captured-utc",
        ),
        pytest.param(
            "binding-git-dirty-type",
            "gitDirty is invalid",
            id="binding-git-dirty-type",
        ),
        pytest.param(
            "failed-status-shape",
            "replay failed sample is invalid",
            id="failed-status-shape",
        ),
    ),
)
def test_shared_physical_validator_rejects_additional_public_nested_variants(
    mutation: str, expected_message: str
) -> None:
    contract = _contract()
    candidate = _physical_transcript(_document("failed-before"))
    assert contract.validate_physical_transcript(candidate) == candidate

    if mutation == "root-collection":
        candidate = [candidate]
    elif mutation == "group-id-type":
        candidate["batches"][0]["groupId"] = None
    elif mutation == "session-device-name":
        candidate["binding"]["sessionId"] = "con"
    elif mutation == "watch-kind":
        candidate["batches"][0]["values"][0]["watch"]["kind"] = "other"
    elif mutation == "captured-utc":
        candidate["batches"][0]["capturedAtUtc"] = "1970-01-01T00:00:00.000000Z"
    elif mutation == "binding-git-dirty-type":
        candidate["binding"]["gitDirty"] = 1
    else:
        candidate["batches"][0]["values"][0]["status"] = "ERROR"

    before = deepcopy(candidate)
    with pytest.raises(contract.ReplayContractError) as error:
        contract.validate_physical_transcript(candidate)

    assert str(error.value) == expected_message
    assert candidate == before


@pytest.mark.parametrize(
    "value",
    (
        ("tuple",),
        {1: "non-string-key"},
        {"value": float("nan")},
        {"value": "e\u0301"},
    ),
)
def test_shared_physical_canonicalizer_rejects_unsafe_json_values(value: object) -> None:
    contract = _contract()
    before = value
    with pytest.raises(contract.ReplayContractError):
        contract.canonical_physical_json_bytes(value)
    assert value is before


def test_shared_physical_canonicalizer_rejects_cycles_without_mutating_input() -> None:
    contract = _contract()
    value: list[object] = []
    value.append(value)
    with pytest.raises(contract.ReplayContractError):
        contract.canonical_physical_json_bytes(value)
    assert value[0] is value


@pytest.mark.parametrize("case_name", tuple(_document_mutations(_document("failed-before"))))
def test_shared_and_monitor_reject_the_same_document_wire_mutations(
    case_name: str,
) -> None:
    contract = _contract()
    source = _document("failed-before")
    candidate = _document_mutations(source)[case_name]
    if case_name != "fixture-digest":
        assert candidate["fixture_sha256"] == _document_digest(candidate)
        assert candidate["fixture_sha256"] != source["fixture_sha256"]
    _run_target_sensitivity_oracle(
        _DOCUMENT_TARGET_TABLE,
        case_name,
        source,
        candidate,
    )
    if case_name in {"binding-extra", "binding-missing", "hash"}:
        assert all(batch["binding"] == candidate["binding"] for batch in candidate["batches"])
    if case_name in {"selector-whitespace", "selector-nfc", "selector-control"}:
        source_watch = source["batches"][0]["values"][0]["watch"]
        selector_field = _selector_key(source_watch)
        selector_kind = source_watch["kind"]
        projected = [
            sample["watch"][selector_field]
            for batch in candidate["batches"]
            for sample in batch["values"]
            if sample["watch"]["kind"] == selector_kind
        ]
        assert len(projected) >= 2
        assert set(projected) == {projected[0]}
    before = deepcopy(candidate)
    with pytest.raises(MonitorReplayError):
        MonitorReplayDocument.from_value(candidate)
    with pytest.raises(contract.ReplayContractError):
        contract.validate_replay_document(candidate)
    assert candidate == before


@pytest.mark.parametrize("role", ("failed-before", "fixed-after"))
def test_shared_and_monitor_reject_the_same_reference_wire_mutations(
    tmp_path: Path,
    role: str,
) -> None:
    contract = _contract()
    reference = _reference(tmp_path, role)
    for case_name, candidate in _reference_mutations(reference).items():
        if case_name not in {"unsigned-ref-digest", "reference-fixture-digest"}:
            assert candidate["run_ref_sha256"] == _reference_digest(candidate)
            assert candidate["run_ref_sha256"] != reference["run_ref_sha256"]
        _run_target_sensitivity_oracle(
            _REFERENCE_TARGET_TABLE,
            case_name,
            reference,
            candidate,
        )
        before = deepcopy(candidate)
        try:
            MonitorRunRef.from_value(candidate)
        except MonitorReplayError:
            pass
        else:
            pytest.fail(f"Monitor accepted reference mutation: {case_name}")
        with pytest.raises(contract.ReplayContractError):
            contract.validate_run_reference(candidate)
        assert candidate == before, case_name


@pytest.mark.parametrize(
    ("mutation", "expected_message"),
    (
        pytest.param(
            "replay-empty-batches",
            "replay document batches are invalid",
            id="replay-empty-batches",
        ),
        pytest.param(
            "replay-scheduled-order",
            "replay document scheduled times are not increasing",
            id="replay-scheduled-order",
        ),
        pytest.param(
            "replay-captured-order",
            "replay document captured times are not increasing",
            id="replay-captured-order",
        ),
        pytest.param(
            "reference-scenario-role",
            "monitor run reference scenario role is invalid",
            id="reference-scenario-role",
        ),
        pytest.param(
            "reference-execution-source",
            "monitor run reference execution source is invalid",
            id="reference-execution-source",
        ),
        pytest.param(
            "reference-run-identity",
            "monitor run reference operation and run IDs contradict",
            id="reference-run-identity",
        ),
    ),
)
def test_shared_public_replay_reference_rejects_recomputed_wire_semantics(
    mutation: str, expected_message: str
) -> None:
    contract = _contract()
    if mutation.startswith("replay-"):
        source = _document("failed-before")
        assert contract.validate_replay_document(source) == source
        candidate = deepcopy(source)
        if mutation == "replay-empty-batches":
            candidate["batches"] = []
        elif mutation == "replay-scheduled-order":
            first = candidate["batches"][0]
            second = candidate["batches"][1]
            second["scheduledUnixNs"] = first["scheduledUnixNs"]
            second["scheduledAtUtc"] = first["scheduledAtUtc"]
        else:
            first = candidate["batches"][0]
            second = candidate["batches"][1]
            first["capturedUnixNs"] = second["capturedUnixNs"]
            first["capturedAtUtc"] = second["capturedAtUtc"]
            first["latencyNs"] = first["capturedUnixNs"] - first["scheduledUnixNs"]
        _redigest_document(candidate)
    else:
        source = _physical_v2_reference()
        assert contract.validate_run_reference(source) == source
        candidate = deepcopy(source)
        if mutation == "reference-scenario-role":
            candidate["scenario_role"] = "other"
        elif mutation == "reference-execution-source":
            candidate["execution_source"] = "other"
        else:
            candidate["projected_run_id"] = "22222222-2222-4222-8222-222222222222"
        _redigest_reference(candidate)

    before = deepcopy(candidate)
    with pytest.raises(contract.ReplayContractError) as error:
        if mutation.startswith("replay-"):
            contract.validate_replay_document(candidate)
        else:
            contract.validate_run_reference(candidate)

    assert str(error.value) == expected_message
    assert candidate == before


@pytest.mark.parametrize("field", ("typedValue", "definition"))
def test_physical_typed_json_cumulative_string_budget_matches_monitor(
    field: str,
) -> None:
    contract = _contract()
    candidate = _physical_transcript(_document("failed-before"))
    sample = candidate["batches"][0]["values"][0]
    sample[field] = {"left": "a" * 700_000, "right": "b" * 700_000}
    if field == "typedValue":
        monitor_value = sample[field]
        monitor_definition = None
    else:
        monitor_value = sample["typedValue"]
        monitor_definition = sample[field]
    watch = WatchItem.from_dict(sample["watch"])

    with pytest.raises(ValueError):
        SampleValue(
            watch,
            "OK",
            typed_value=monitor_value,
            definition=monitor_definition,
        )
    with pytest.raises(contract.ReplayContractError):
        contract.validate_physical_transcript(candidate)


@pytest.mark.parametrize("field", ("typedValue", "definition"))
@pytest.mark.parametrize("depth", (27, 28, 32, 33))
def test_physical_typed_json_depth_matches_monitor(
    field: str,
    depth: int,
) -> None:
    contract = _contract()
    candidate = _physical_transcript(_document("failed-before"))
    sample = candidate["batches"][0]["values"][0]
    sample[field] = _deep_json(depth)
    if field == "typedValue":
        monitor_value = sample[field]
        monitor_definition = None
    else:
        monitor_value = sample["typedValue"]
        monitor_definition = sample[field]
    watch = WatchItem.from_dict(sample["watch"])

    if depth <= 32:
        SampleValue(
            watch,
            "OK",
            typed_value=monitor_value,
            definition=monitor_definition,
        )
        contract.validate_physical_transcript(candidate)
    else:
        with pytest.raises(ValueError):
            SampleValue(
                watch,
                "OK",
                typed_value=monitor_value,
                definition=monitor_definition,
            )
        with pytest.raises(contract.ReplayContractError):
            contract.validate_physical_transcript(candidate)


def test_physical_typed_json_node_budget_matches_monitor() -> None:
    contract = _contract()
    candidate = _physical_transcript(_document("failed-before"))
    sample = candidate["batches"][0]["values"][0]
    sample["typedValue"] = [0] * 10_000
    watch = WatchItem.from_dict(sample["watch"])

    with pytest.raises(ValueError):
        SampleValue(watch, "OK", typed_value=sample["typedValue"])
    with pytest.raises(contract.ReplayContractError):
        contract.validate_physical_transcript(candidate)


def test_physical_typed_json_signed_int64_boundary_matches_monitor() -> None:
    contract = _contract()
    accepted = _physical_transcript(_document("failed-before"))
    accepted_sample = accepted["batches"][0]["values"][0]
    accepted_sample["typedValue"] = {"minimum": -(1 << 63)}
    accepted_watch = WatchItem.from_dict(accepted_sample["watch"])
    SampleValue(accepted_watch, "OK", typed_value=accepted_sample["typedValue"])
    contract.validate_physical_transcript(accepted)

    rejected = _physical_transcript(_document("failed-before"))
    rejected_sample = rejected["batches"][0]["values"][0]
    rejected_sample["typedValue"] = {"below": -(1 << 63) - 1}
    rejected_watch = WatchItem.from_dict(rejected_sample["watch"])
    with pytest.raises(ValueError):
        SampleValue(rejected_watch, "OK", typed_value=rejected_sample["typedValue"])
    with pytest.raises(contract.ReplayContractError):
        contract.validate_physical_transcript(rejected)


@pytest.mark.parametrize(
    ("case_id", "entry", "expected_message"),
    (
        pytest.param(
            "M-CANONICAL-NONFINITE",
            "canonical_replay_json_bytes",
            "replay JSON number is not finite",
            id="M-CANONICAL-NONFINITE",
        ),
        pytest.param(
            "M-CANONICAL-STRING-BUDGET",
            "canonical_replay_json_bytes",
            "replay JSON string data exceeds its limit",
            id="M-CANONICAL-STRING-BUDGET",
        ),
        pytest.param(
            "M-CANONICAL-TUPLE",
            "canonical_replay_json_bytes",
            "replay JSON must not contain tuple containers",
            id="M-CANONICAL-TUPLE",
        ),
        pytest.param(
            "M-CANONICAL-MAPPING-CYCLE",
            "canonical_replay_json_bytes",
            "replay JSON contains a cycle",
            id="M-CANONICAL-MAPPING-CYCLE",
        ),
        pytest.param(
            "M-CANONICAL-NONSTRING-KEY",
            "canonical_replay_json_bytes",
            "replay JSON object keys must be strings",
            id="M-CANONICAL-NONSTRING-KEY",
        ),
        pytest.param(
            "M-CANONICAL-NFC-KEY",
            "canonical_replay_json_bytes",
            "replay JSON object keys must use NFC",
            id="M-CANONICAL-NFC-KEY",
        ),
        pytest.param(
            "M-CANONICAL-LIST-CYCLE",
            "canonical_replay_json_bytes",
            "replay JSON contains a cycle",
            id="M-CANONICAL-LIST-CYCLE",
        ),
        pytest.param(
            "M-CANONICAL-UNSUPPORTED",
            "canonical_replay_json_bytes",
            "replay JSON contains an unsupported value",
            id="M-CANONICAL-UNSUPPORTED",
        ),
        pytest.param(
            "M-REPLAY-BINDING-LABEL",
            "validate_replay_document",
            "replay binding labels are invalid",
            id="M-REPLAY-BINDING-LABEL",
        ),
        pytest.param(
            "M-REPLAY-WATCH-TYPE",
            "validate_replay_document",
            "replay watch is invalid",
            id="M-REPLAY-WATCH-TYPE",
        ),
        pytest.param(
            "M-REPLAY-FAILED-SAMPLE-SHAPE",
            "validate_replay_document",
            "replay failed sample is invalid",
            id="M-REPLAY-FAILED-SAMPLE-SHAPE",
        ),
        pytest.param(
            "M-REPLAY-SCHEMA",
            "validate_replay_document",
            "replay document schema is invalid",
            id="M-REPLAY-SCHEMA",
        ),
        pytest.param(
            "M-REPLAY-SOURCE",
            "validate_replay_document",
            "replay document source is invalid",
            id="M-REPLAY-SOURCE",
        ),
        pytest.param(
            "M-REPLAY-PHYSICAL-EVIDENCE",
            "validate_replay_document",
            "replay document physical evidence must be false",
            id="M-REPLAY-PHYSICAL-EVIDENCE",
        ),
        pytest.param(
            "M-REPLAY-ROLE",
            "validate_replay_document",
            "replay document scenario role is invalid",
            id="M-REPLAY-ROLE",
        ),
        pytest.param(
            "M-REPLAY-DUPLICATE-SELECTOR",
            "validate_replay_document",
            "replay document selectors are not unique",
            id="M-REPLAY-DUPLICATE-SELECTOR",
        ),
        pytest.param(
            "M-REFERENCE-GIT-HEAD",
            "validate_run_reference",
            "git_head is invalid",
            id="M-REFERENCE-GIT-HEAD",
        ),
        pytest.param(
            "M-REFERENCE-GIT-DIRTY-TYPE",
            "validate_run_reference",
            "git_dirty is invalid",
            id="M-REFERENCE-GIT-DIRTY-TYPE",
        ),
        pytest.param(
            "M-REFERENCE-EMPTY-DIGEST-LIST",
            "validate_run_reference",
            "projected batch digests are invalid",
            id="M-REFERENCE-EMPTY-DIGEST-LIST",
        ),
    ),
)
def test_public_replay_wire_remaining(
    case_id: str,
    entry: str,
    expected_message: str,
    tmp_path: Path,
) -> None:
    contract = _contract()

    if entry == "canonical_replay_json_bytes":
        source = _document("failed-before")
        source_before = deepcopy(source)
        assert contract.canonical_replay_json_bytes(source) == canonical_replay_json_bytes(
            source
        )
        candidate = deepcopy(source)

        if case_id == "M-CANONICAL-NONFINITE":
            nonfinite = float("nan")
            candidate["batches"][0]["actualRateHz"] = nonfinite
            with pytest.raises(contract.ReplayContractError) as error:
                contract.canonical_replay_json_bytes(candidate)
            assert candidate["batches"][0]["actualRateHz"] is nonfinite
            candidate["batches"][0]["actualRateHz"] = source["batches"][0]["actualRateHz"]
            assert candidate == source
        elif case_id == "M-CANONICAL-STRING-BUDGET":
            candidate["binding"]["targetDevice"] = "x" * (
                contract.MAX_REPLAY_JSON_STRING_CHARS + 1
            )
            candidate_before = deepcopy(candidate)
            with pytest.raises(contract.ReplayContractError) as error:
                contract.canonical_replay_json_bytes(candidate)
            assert candidate == candidate_before
        elif case_id == "M-CANONICAL-TUPLE":
            candidate["batches"][0]["values"] = tuple(candidate["batches"][0]["values"])
            candidate_before = deepcopy(candidate)
            with pytest.raises(contract.ReplayContractError) as error:
                contract.canonical_replay_json_bytes(candidate)
            assert candidate == candidate_before
        elif case_id == "M-CANONICAL-MAPPING-CYCLE":
            binding = candidate["binding"]
            binding["self"] = binding
            with pytest.raises(contract.ReplayContractError) as error:
                contract.canonical_replay_json_bytes(candidate)
            assert binding["self"] is binding
            del binding["self"]
            assert candidate == source
        elif case_id == "M-CANONICAL-NONSTRING-KEY":
            binding = candidate["binding"]
            binding[1] = "non-string-key"
            candidate_before = deepcopy(candidate)
            with pytest.raises(contract.ReplayContractError) as error:
                contract.canonical_replay_json_bytes(candidate)
            assert candidate == candidate_before
            del binding[1]
            assert candidate == source
        elif case_id == "M-CANONICAL-NFC-KEY":
            binding = candidate["binding"]
            nfc_key = "e\u0301"
            binding[nfc_key] = "decomposed-key"
            candidate_before = deepcopy(candidate)
            with pytest.raises(contract.ReplayContractError) as error:
                contract.canonical_replay_json_bytes(candidate)
            assert candidate == candidate_before
            del binding[nfc_key]
            assert candidate == source
        elif case_id == "M-CANONICAL-LIST-CYCLE":
            batches = candidate["batches"]
            batches.append(batches)
            with pytest.raises(contract.ReplayContractError) as error:
                contract.canonical_replay_json_bytes(candidate)
            assert batches[-1] is batches
            batches.pop()
            assert candidate == source
        elif case_id == "M-CANONICAL-UNSUPPORTED":
            unsupported = object()
            candidate["batches"][0]["actualRateHz"] = unsupported
            with pytest.raises(contract.ReplayContractError) as error:
                contract.canonical_replay_json_bytes(candidate)
            assert candidate["batches"][0]["actualRateHz"] is unsupported
            candidate["batches"][0]["actualRateHz"] = source["batches"][0]["actualRateHz"]
            assert candidate == source
        else:
            pytest.fail(f"unknown canonical replay wire case: {case_id}")

        assert type(error.value) is contract.ReplayContractError
        assert str(error.value) == expected_message
        assert source == source_before
        return

    if entry == "validate_replay_document":
        source = _document("failed-before")
        source_before = deepcopy(source)
        assert contract.validate_replay_document(source) == source
        candidate = deepcopy(source)

        if case_id == "M-REPLAY-BINDING-LABEL":
            _set_binding_field(candidate, "probeId", "replay:probe-v3")
        elif case_id == "M-REPLAY-WATCH-TYPE":
            candidate["batches"][0]["values"][0]["watch"] = None
        elif case_id == "M-REPLAY-FAILED-SAMPLE-SHAPE":
            candidate["batches"][0]["values"][0]["status"] = "ERROR"
        elif case_id == "M-REPLAY-SCHEMA":
            candidate["schema"] = "stm32-monitor-replay/other"
        elif case_id == "M-REPLAY-SOURCE":
            candidate["source"] = "other-replay-source"
        elif case_id == "M-REPLAY-PHYSICAL-EVIDENCE":
            candidate["physical_transport_evidence"] = True
        elif case_id == "M-REPLAY-ROLE":
            candidate["scenario_role"] = "other"
        elif case_id == "M-REPLAY-DUPLICATE-SELECTOR":
            for batch in candidate["batches"]:
                batch["values"][1]["watch"] = deepcopy(batch["values"][0]["watch"])
        else:
            pytest.fail(f"unknown replay document wire case: {case_id}")

        _redigest_public_document(contract, candidate)
        candidate_before = deepcopy(candidate)
        with pytest.raises(contract.ReplayContractError) as error:
            contract.validate_replay_document(candidate)
        assert type(error.value) is contract.ReplayContractError
        assert str(error.value) == expected_message
        assert candidate == candidate_before
        assert source == source_before
        return

    assert entry == "validate_run_reference"
    reference = _reference(tmp_path, "failed-before")
    reference_before = deepcopy(reference)
    assert contract.validate_run_reference(reference) == reference
    candidate = deepcopy(reference)

    if case_id == "M-REFERENCE-GIT-HEAD":
        candidate["git_head"] = "g" * 40
    elif case_id == "M-REFERENCE-GIT-DIRTY-TYPE":
        candidate["git_dirty"] = 1
    elif case_id == "M-REFERENCE-EMPTY-DIGEST-LIST":
        candidate["projected_batch_sha256s"] = []
    else:
        pytest.fail(f"unknown run reference wire case: {case_id}")

    _redigest_public_reference(contract, candidate)
    candidate_before = deepcopy(candidate)
    with pytest.raises(contract.ReplayContractError) as error:
        contract.validate_run_reference(candidate)
    assert type(error.value) is contract.ReplayContractError
    assert str(error.value) == expected_message
    assert candidate == candidate_before
    assert reference == reference_before


def test_public_replay_wire_accepts_legal_failed_sample() -> None:
    contract = _contract()
    source = _document("failed-before")
    source_before = deepcopy(source)
    assert contract.validate_replay_document(source) == source

    candidate = deepcopy(source)
    sample = candidate["batches"][0]["values"][0]
    sample["status"] = "ERROR"
    sample["typedValue"] = None
    sample["code"] = "MONITOR_READ_FAILED"
    _redigest_public_document(contract, candidate)
    candidate_before = deepcopy(candidate)

    validated = contract.validate_replay_document(candidate)

    assert validated == candidate
    assert validated is not candidate
    assert candidate == candidate_before
    assert source == source_before
