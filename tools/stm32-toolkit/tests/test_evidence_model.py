"""Behavioral contract tests for the canonical STM32 evidence model."""

from __future__ import annotations

import ast
from collections import Counter
from copy import deepcopy
import math
from pathlib import Path

import pytest

import stm32_toolkit.evidence as evidence_package
import stm32_toolkit.evidence.catalog as evidence_catalog
import stm32_toolkit.evidence.gc as evidence_gc
import stm32_toolkit.evidence.model as evidence_model
import stm32_toolkit.evidence.store as evidence_store
from stm32_toolkit.evidence.model import (
    ArtifactRef,
    EvidenceEnvelope,
    EvidenceIdentity,
    EvidenceIdentityContext,
    MAX_ARTIFACTS,
    MAX_ENVELOPE_BYTES,
    MAX_JSON_INTEGER,
    MAX_JSON_DEPTH,
    MAX_JSON_NODES,
    MAX_PARENTS,
    MAX_STRING_BYTES,
    calculate_evidence_id,
    canonical_json_bytes,
)


HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_C = "c" * 64
HASH_D = "d" * 64
HASH_E = "e" * 40
HASH_F = "f" * 64
GOLDEN_ID = "d928ebb8e9f7313abf6f85ba07be017ab876b0ee65e712ce08c691956d649a1f"
GOLDEN_BYTES = (
    b'{"artifacts":[{"kind":"log","media_type":"text/plain","relative_path":"logs/caf\xc3\xa9.txt",'
    b'"sha256":"1111111111111111111111111111111111111111111111111111111111111111",'
    b'"size_bytes":0}],"identity":{"build_id":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",'
    b'"elf_sha256":"cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",'
    b'"git_commit":"eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee","git_dirty":false,'
    b'"input_snapshot_sha256":"dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd",'
    b'"project_id":"123e4567-e89b-42d3-a456-426614174000","session_id":"session-01",'
    b'"target_device":"host:windows/amd64","workspace_id":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"},'
    b'"metadata":{"a":1,"\xce\xb1":"caf\xc3\xa9"},"operation":"fixture.test",'
    b'"parents":["ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",'
    b'"0000000000000000000000000000000000000000000000000000000000000000"],'
    b'"produced_at_utc":"2026-08-15T01:02:03.123456Z","schema":"stm32-evidence/1"}'
)


@pytest.fixture
def valid_envelope_dict() -> dict[str, object]:
    return {
        "schema": "stm32-evidence/1",
        "evidence_id": GOLDEN_ID,
        "identity": {
            "workspace_id": HASH_A,
            "project_id": "123e4567-e89b-42d3-a456-426614174000",
            "session_id": "session-01",
            "build_id": HASH_B,
            "elf_sha256": HASH_C,
            "target_device": "host:windows/amd64",
            "input_snapshot_sha256": HASH_D,
            "git_commit": HASH_E,
            "git_dirty": False,
        },
        "operation": "fixture.test",
        "produced_at_utc": "2026-08-15T01:02:03.123456Z",
        "parents": [HASH_F, "0" * 64],
        "artifacts": [
            {
                "sha256": "1" * 64,
                "size_bytes": 0,
                "relative_path": "logs/caf\u00e9.txt",
                "kind": "log",
                "media_type": "text/plain",
            }
        ],
        "metadata": {"\u03b1": "caf\u00e9", "a": 1},
    }


def test_envelope_id_is_canonical_content_digest_and_to_dict_is_fresh(valid_envelope_dict):
    """Changing object insertion order must not change the canonical evidence digest."""
    first = EvidenceEnvelope.from_dict(valid_envelope_dict)
    reordered = EvidenceEnvelope.from_dict(dict(reversed(valid_envelope_dict.items())))

    assert first.evidence_id == GOLDEN_ID
    assert reordered.evidence_id == GOLDEN_ID
    assert calculate_evidence_id(first) == GOLDEN_ID
    first_mapping = first.to_dict()
    second_mapping = first.to_dict()
    assert first_mapping is not second_mapping
    assert first_mapping["metadata"] is not second_mapping["metadata"]
    assert first_mapping["artifacts"] is not second_mapping["artifacts"]
    assert first_mapping == valid_envelope_dict


def test_canonical_json_bytes_match_hand_derived_utf8_golden_vector(valid_envelope_dict):
    """A serializer regression in ordering, NFC, separators, or JSON literals is observable."""
    envelope = EvidenceEnvelope.from_dict(valid_envelope_dict)

    encoded = canonical_json_bytes({key: value for key, value in envelope.to_dict().items() if key != "evidence_id"})

    assert encoded == GOLDEN_BYTES
    assert not encoded.startswith(b"\xef\xbb\xbf")
    assert b" " not in encoded
    assert b"\\u" not in encoded
    assert b"1.0" not in encoded
    assert list(envelope.parents) == [HASH_F, "0" * 64]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("workspace_id", "A" * 64),
        ("project_id", "123E4567-e89b-42d3-a456-426614174000"),
        ("session_id", "Session-01"),
        ("build_id", "build"),
        ("elf_sha256", "c" * 63),
        ("input_snapshot_sha256", "d" * 63),
        ("git_commit", "e" * 39),
        ("git_dirty", 0),
    ],
)
def test_identity_rejects_noncanonical_id_hash_or_boolean(field, value):
    """Weak identity validation could let ambiguous or false build provenance enter evidence."""
    identity = {
        "workspace_id": HASH_A,
        "project_id": "123e4567-e89b-42d3-a456-426614174000",
        "session_id": "session-01",
        "build_id": HASH_B,
        "elf_sha256": HASH_C,
        "target_device": "host:windows/amd64",
        "input_snapshot_sha256": HASH_D,
        "git_commit": HASH_E,
        "git_dirty": False,
    }
    identity[field] = value

    with pytest.raises(ValueError):
        EvidenceIdentity.from_dict(identity)


def test_identity_context_binds_only_runner_owned_hashes():
    """A caller-owned identity context binds the two Host digests supplied by discovery."""
    context = EvidenceIdentityContext(
        workspace_id="a" * 64,
        project_id="12345678-1234-5678-1234-567812345678",
        session_id="session-1",
        target_device="host:windows/amd64",
        input_snapshot_sha256="b" * 64,
        git_commit="c" * 40,
        git_dirty=False,
    )

    identity = context.bind(build_id="d" * 64, elf_sha256="e" * 64)

    assert identity == EvidenceIdentity(
        workspace_id="a" * 64,
        project_id="12345678-1234-5678-1234-567812345678",
        session_id="session-1",
        build_id="d" * 64,
        elf_sha256="e" * 64,
        target_device="host:windows/amd64",
        input_snapshot_sha256="b" * 64,
        git_commit="c" * 40,
        git_dirty=False,
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("workspace_id", "A" * 64),
        ("project_id", "123e4567-e89b-42d3-a456-426614174000".upper()),
        ("session_id", "Session-1"),
        ("target_device", ""),
        ("input_snapshot_sha256", "B" * 64),
        ("git_commit", "C" * 40),
        ("git_dirty", 0),
    ],
)
def test_identity_context_rejects_noncanonical_shared_fields(field, value):
    """Context validation must remain closed for every field shared with EvidenceIdentity."""
    context = {
        "workspace_id": HASH_A,
        "project_id": "123e4567-e89b-42d3-a456-426614174000",
        "session_id": "session-01",
        "target_device": "host:windows/amd64",
        "input_snapshot_sha256": HASH_D,
        "git_commit": HASH_E,
        "git_dirty": False,
    }
    context[field] = value

    with pytest.raises(ValueError):
        EvidenceIdentityContext(**context)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("size_bytes", True),
        ("size_bytes", 2 * 1024 * 1024 * 1024 + 1),
        ("sha256", "F" * 64),
        ("relative_path", "logs\\output.txt"),
        ("relative_path", "../output.txt"),
        ("relative_path", "/output.txt"),
        ("relative_path", "logs//output.txt"),
        ("relative_path", "logs/CON.txt"),
        ("relative_path", "logs/output. "),
        ("relative_path", "logs/output:stream.txt"),
    ],
)
def test_artifact_rejects_nonportable_path_hash_and_size(field, value):
    """Relaxing path or size validation would permit unaddressable or ambiguous objects."""
    artifact = {
        "sha256": "1" * 64,
        "size_bytes": 0,
        "relative_path": "logs/output.txt",
        "kind": "log",
        "media_type": "text/plain",
    }
    artifact[field] = value

    with pytest.raises(ValueError):
        ArtifactRef.from_dict(artifact)


@pytest.mark.parametrize(
    "alter",
    [
        lambda payload: payload.__setitem__("unexpected", None),
        lambda payload: payload.__setitem__("schema", "stm32-evidence/2"),
        lambda payload: payload.__setitem__("produced_at_utc", "2026-08-15T01:02:03Z"),
        lambda payload: payload.__setitem__("operation", ""),
        lambda payload: payload.__setitem__("metadata", []),
        lambda payload: payload.__setitem__("parents", [HASH_F] * (MAX_PARENTS + 1)),
        lambda payload: payload.__setitem__("artifacts", [payload["artifacts"][0]] * (MAX_ARTIFACTS + 1)),
    ],
)
def test_envelope_rejects_unknown_fields_wrong_types_and_contract_counts(valid_envelope_dict, alter):
    """Envelope boundaries reject additions and collection expansions before an ID is accepted."""
    payload = deepcopy(valid_envelope_dict)
    alter(payload)

    with pytest.raises(ValueError):
        EvidenceEnvelope.from_dict(payload)


def test_authoritative_decoder_rejects_bom_duplicate_noncanonical_order_and_non_nfc(valid_envelope_dict):
    """Equivalent-looking input bytes cannot become distinct authoritative evidence encodings."""
    canonical = EvidenceEnvelope.from_dict(valid_envelope_dict).to_json_bytes()
    duplicate = canonical.replace(b'"schema":"stm32-evidence/1"', b'"schema":"stm32-evidence/1","schema":"stm32-evidence/1"')
    reordered = b"{" + canonical[1:].replace(b'"artifacts"', b'"zz"', 1)
    decomposed = canonical.replace("caf\u00e9".encode("utf-8"), "cafe\u0301".encode("utf-8"))

    assert EvidenceEnvelope.from_json_bytes(canonical).to_json_bytes() == canonical
    for invalid in (b"\xef\xbb\xbf" + canonical, duplicate, reordered, decomposed, canonical + b"\n"):
        with pytest.raises(ValueError):
            EvidenceEnvelope.from_json_bytes(invalid)


@pytest.mark.parametrize("evidence_id", [0, None])
def test_authoritative_decoder_rejects_falsey_non_hash_evidence_id(valid_envelope_dict, evidence_id):
    """An explicit falsey ID must not become the direct-constructor default."""
    payload = deepcopy(valid_envelope_dict)
    payload["evidence_id"] = evidence_id

    with pytest.raises(ValueError):
        EvidenceEnvelope.from_json_bytes(canonical_json_bytes(payload))


def test_metadata_allows_canonical_bounded_json_control_characters():
    """Producer metadata may represent ordinary JSON content, including escaped newlines."""
    identity = EvidenceIdentity(
        workspace_id=HASH_A,
        project_id="123e4567-e89b-42d3-a456-426614174000",
        session_id="session-01",
        build_id=HASH_B,
        elf_sha256=HASH_C,
        target_device="host:windows/amd64",
        input_snapshot_sha256=HASH_D,
        git_commit=HASH_E,
        git_dirty=False,
    )

    envelope = EvidenceEnvelope(
        identity=identity,
        operation="fixture.message",
        produced_at_utc="2026-08-15T01:02:03.123456Z",
        parents=(),
        artifacts=(),
        metadata={"message": "line one\nline two"},
    )

    assert envelope.to_dict()["metadata"] == {"message": "line one\nline two"}


def test_direct_envelope_construction_requires_tuple_collections():
    """Collection order and immutability require tuples before the model is constructed."""
    identity = EvidenceIdentity(
        workspace_id=HASH_A,
        project_id="123e4567-e89b-42d3-a456-426614174000",
        session_id="session-01",
        build_id=HASH_B,
        elf_sha256=HASH_C,
        target_device="host:windows/amd64",
        input_snapshot_sha256=HASH_D,
        git_commit=HASH_E,
        git_dirty=False,
    )

    with pytest.raises(ValueError):
        EvidenceEnvelope(
            identity=identity,
            operation="fixture.test",
            produced_at_utc="2026-08-15T01:02:03.123456Z",
            parents={HASH_F},
            artifacts=(),
            metadata={},
        )


@pytest.mark.parametrize(
    "mutate",
    [
        lambda payload: payload.__setitem__("parents", tuple(payload["parents"])),
        lambda payload: payload.__setitem__("artifacts", tuple(payload["artifacts"])),
        lambda payload: payload.__setitem__("metadata", ("not", "an", "object")),
        lambda payload: payload.__setitem__("metadata", {"rows": ("not", "a", "JSON", "array")}),
    ],
)
def test_from_dict_rejects_tuple_containers_at_the_json_boundary(valid_envelope_dict, mutate):
    """Python tuples cannot cross the dictionary/authoritative-JSON boundary."""
    payload = deepcopy(valid_envelope_dict)
    mutate(payload)
    payload["evidence_id"] = calculate_evidence_id(payload)

    with pytest.raises(ValueError):
        EvidenceEnvelope.from_dict(payload)


def test_from_dict_rejects_deep_json_before_python_recursion(valid_envelope_dict):
    """The non-JSON-container preflight preserves the public depth-limit error."""
    nested: object = 0
    for _ in range(1_100):
        nested = [nested]
    payload = deepcopy(valid_envelope_dict)
    payload["metadata"] = {"nested": nested}

    with pytest.raises(ValueError):
        EvidenceEnvelope.from_dict(payload)


def test_direct_envelope_rejects_invalid_identity_artifact_and_oversized_bytes():
    """Constructor-only guards reject malformed frozen members before computing an envelope ID."""
    identity = EvidenceIdentity(
        workspace_id=HASH_A,
        project_id="123e4567-e89b-42d3-a456-426614174000",
        session_id="session-01",
        build_id=HASH_B,
        elf_sha256=HASH_C,
        target_device="host:windows/amd64",
        input_snapshot_sha256=HASH_D,
        git_commit=HASH_E,
        git_dirty=False,
    )
    arguments = {
        "operation": "fixture.test",
        "produced_at_utc": "2026-08-15T01:02:03.123456Z",
        "parents": (),
        "artifacts": (),
        "metadata": {},
    }

    with pytest.raises(ValueError):
        EvidenceEnvelope(identity=object(), **arguments)
    with pytest.raises(ValueError):
        EvidenceEnvelope(identity=identity, artifacts=("not-an-artifact",), **{key: value for key, value in arguments.items() if key != "artifacts"})
    with pytest.raises(ValueError):
        EvidenceEnvelope(
            identity=identity,
            **{key: value for key, value in arguments.items() if key != "metadata"},
            metadata={str(index): "x" * 60_000 for index in range(18)},
        )


def test_canonical_json_rejects_direct_duplicate_keys_and_integer_overflow():
    """Non-authoritative Python inputs cannot bypass duplicate-key or signed-integer limits."""
    class DuplicateKeys(dict[str, object]):
        def items(self):
            return [("same", 1), ("same", 2)]

    with pytest.raises(ValueError):
        canonical_json_bytes(DuplicateKeys())
    with pytest.raises(ValueError):
        canonical_json_bytes({"counter": MAX_JSON_INTEGER + 1})


def test_metadata_lists_thaw_freshly_and_decoder_requires_bytes(valid_envelope_dict):
    """Nested arrays are frozen/thawed without aliasing, and authority decoding accepts bytes only."""
    payload = deepcopy(valid_envelope_dict)
    payload["metadata"] = {"rows": [1, {"name": "one"}]}
    payload["evidence_id"] = calculate_evidence_id(payload)
    envelope = EvidenceEnvelope.from_dict(payload)
    first = envelope.to_dict()
    second = envelope.to_dict()

    assert first["metadata"] == {"rows": [1, {"name": "one"}]}
    assert first["metadata"]["rows"] is not second["metadata"]["rows"]
    with pytest.raises(ValueError):
        EvidenceEnvelope.from_json_bytes("not bytes")


def test_from_dict_requires_json_arrays_and_digest_accepts_only_envelopes_or_mappings(valid_envelope_dict):
    """Public parser and digest APIs keep their JSON boundary types closed."""
    payload = deepcopy(valid_envelope_dict)
    payload["parents"] = "not an array"

    with pytest.raises(ValueError):
        EvidenceEnvelope.from_dict(payload)
    assert calculate_evidence_id(valid_envelope_dict) == GOLDEN_ID
    with pytest.raises(ValueError):
        calculate_evidence_id([])


def test_artifact_path_rejects_controls_and_utf8_byte_overflow():
    """Portable artifact names cannot contain controls or exceed 512 encoded bytes."""
    base = {
        "sha256": "1" * 64,
        "size_bytes": 0,
        "relative_path": "logs/output.txt",
        "kind": "log",
        "media_type": "text/plain",
    }
    for path in ("logs/output\n.txt", "\u00e9" * 257):
        value = dict(base)
        value["relative_path"] = path
        with pytest.raises(ValueError):
            ArtifactRef.from_dict(value)


@pytest.mark.parametrize(
    "metadata",
    [
        {"fraction": 1.0},
        {"not_a_number": math.nan},
        {"too_deep": {"x": {"x": {"x": {"x": {"x": {"x": {"x": {"x": {"x": {"x": {"x": {"x": {"x": {"x": {"x": {"x": {"x": {"x": {"x": {"x": {"x": {"x": {"x": {"x": {"x": {"x": {"x": {"x": {"x": {"x": {"x": {"x": {"x": 0}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}}},
        },
        {"too_long": "x" * (MAX_STRING_BYTES + 1)},
        {"too_many_nodes": [0] * MAX_JSON_NODES},
    ],
)
def test_metadata_rejects_noncanonical_numbers_and_global_json_limits(valid_envelope_dict, metadata):
    """Generic producer metadata still shares one strict canonical JSON safety boundary."""
    payload = deepcopy(valid_envelope_dict)
    payload["metadata"] = metadata

    with pytest.raises(ValueError):
        EvidenceEnvelope.from_dict(payload)


def test_envelope_rejects_canonical_payload_larger_than_one_mebibyte(valid_envelope_dict):
    """Envelope size is checked separately from the per-string bound."""
    payload = deepcopy(valid_envelope_dict)
    payload["metadata"] = {str(index): "x" * 60_000 for index in range(18)}
    assert sum(len(value.encode("utf-8")) for value in payload["metadata"].values()) > MAX_ENVELOPE_BYTES

    with pytest.raises(ValueError):
        EvidenceEnvelope.from_dict(payload)


def test_metadata_validator_is_explicit_and_does_not_create_a_global_operation_registry(valid_envelope_dict):
    """A caller-provided producer contract may reject metadata without common-model operation guessing."""
    received: list[tuple[str, dict[str, object]]] = []

    def validator(operation: str, metadata: dict[str, object]) -> None:
        received.append((operation, metadata))
        if operation != "fixture.test" or set(metadata) != {"a", "\u03b1"}:
            raise ValueError("fixture producer contract failed")

    parsed = EvidenceEnvelope.from_dict(valid_envelope_dict, metadata_validator=validator)
    assert parsed.operation == "fixture.test"
    assert received == [("fixture.test", {"a": 1, "\u03b1": "caf\u00e9"})]


def test_t10_1a_evidence_validation_error_abi_is_closed_and_requires_two_arguments():
    """Defaults, open codes, mutable properties, or lossy ValueError behavior break the public ABI."""
    expected_codes = {
        "EVIDENCE_INVALID": "EVIDENCE_INVALID",
        "EVIDENCE_CORRUPT": "EVIDENCE_CORRUPT",
        "EVIDENCE_PATH_UNSAFE": "EVIDENCE_PATH_UNSAFE",
        "EVIDENCE_LIMIT_EXCEEDED": "EVIDENCE_LIMIT_EXCEEDED",
    }
    assert {
        name: getattr(evidence_model, name, None) for name in expected_codes
    } == expected_codes

    error_type = evidence_model.EvidenceValidationError
    for code in expected_codes.values():
        error = error_type(code, "closed evidence failure")
        assert isinstance(error, ValueError)
        assert error.code == code
        assert error.message == "closed evidence failure"
        assert error.args == ("closed evidence failure",)
        assert str(error) == "closed evidence failure"
        with pytest.raises(AttributeError):
            error.code = "EVIDENCE_INVALID"
        with pytest.raises(AttributeError):
            error.message = "changed"

    class StringSubclass(str):
        pass

    for arguments in ((), ("EVIDENCE_INVALID",)):
        with pytest.raises(TypeError):
            error_type(*arguments)
    for code in ("UNKNOWN", 1, StringSubclass("EVIDENCE_INVALID")):
        with pytest.raises(ValueError, match="unknown evidence validation error code"):
            error_type(code, "message")
    for message in (None, 1, StringSubclass("message")):
        with pytest.raises(TypeError, match="message must be a string"):
            error_type("EVIDENCE_INVALID", message)


def test_t10_1a_evidence_package_exports_exact_typed_error_boundary():
    """Missing, duplicated, or unrelated package exports would make the ABI incomplete or open."""
    accepted_exports = [
        "ArtifactRef",
        "EvidenceEnvelope",
        "EvidenceIdentity",
        "EvidenceIdentityContext",
        "EvidenceValidationError",
        "calculate_evidence_id",
        "canonical_json_bytes",
    ]
    added_exports = {
        "EVIDENCE_INVALID",
        "EVIDENCE_CORRUPT",
        "EVIDENCE_PATH_UNSAFE",
        "EVIDENCE_LIMIT_EXCEEDED",
        "GcStoreChangedError",
    }
    assert [
        name for name in evidence_package.__all__ if name not in added_exports
    ] == accepted_exports
    assert Counter(evidence_package.__all__) == Counter(
        [*accepted_exports, *added_exports]
    )
    for name in added_exports:
        expected_module = evidence_gc if name == "GcStoreChangedError" else evidence_model
        assert getattr(evidence_package, name) is getattr(expected_module, name)


def test_t10_1a_evidence_raise_inventory_is_exact_and_literal():
    """A missing, extra, reordered-shape, or wrongly classified raise site breaks the frozen ABI map."""
    expected = {
        "model.py": (43, {"EVIDENCE_INVALID": 30, "EVIDENCE_CORRUPT": 0, "EVIDENCE_PATH_UNSAFE": 4, "EVIDENCE_LIMIT_EXCEEDED": 9}),
        "store.py": (59, {"EVIDENCE_INVALID": 10, "EVIDENCE_CORRUPT": 9, "EVIDENCE_PATH_UNSAFE": 34, "EVIDENCE_LIMIT_EXCEEDED": 6}),
        "catalog.py": (19, {"EVIDENCE_INVALID": 14, "EVIDENCE_CORRUPT": 2, "EVIDENCE_PATH_UNSAFE": 3, "EVIDENCE_LIMIT_EXCEEDED": 0}),
        "gc.py": (33, {"EVIDENCE_INVALID": 8, "EVIDENCE_CORRUPT": 11, "EVIDENCE_PATH_UNSAFE": 13, "EVIDENCE_LIMIT_EXCEEDED": 1}),
    }
    module_paths = {
        "model.py": Path(evidence_model.__file__),
        "store.py": Path(evidence_store.__file__),
        "catalog.py": Path(evidence_catalog.__file__),
        "gc.py": Path(evidence_gc.__file__),
    }
    for name, (call_count, distribution) in expected.items():
        tree = ast.parse(module_paths[name].read_text(encoding="utf-8"), filename=name)
        calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "EvidenceValidationError"
        ]
        assert len(calls) == call_count
        assert all(len(node.args) == 2 and not node.keywords for node in calls)
        assert all(isinstance(node.args[0], ast.Name) for node in calls)
        observed = Counter(node.args[0].id for node in calls)
        assert {code: observed[code] for code in distribution} == distribution
