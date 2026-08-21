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
    value["batches"][0]["sequence"] = True
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
    value["batches"][0]["groupId"] = f"{group_id[:-1]}A"
    _redigest_document(value)
    cases["uuid"] = value

    value = fresh()
    _set_binding_field(value, "buildId", "g" * 64)
    _redigest_document(value)
    cases["hash"] = value

    value = fresh()
    value["batches"][0]["groupRevision"] = 0
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
    origin_run_id = value["origin_run_id"]
    value["origin_run_id"] = f"{origin_run_id[:-1]}A"
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
