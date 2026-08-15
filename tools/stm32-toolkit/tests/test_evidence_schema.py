"""Schema boundary tests for canonical evidence envelopes."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError

from stm32_toolkit.evidence import ArtifactRef


ROOT_SCHEMA = Path("schemas/evidence-envelope.schema.json")
PACKAGED_SCHEMA = Path("tools/stm32-toolkit/src/stm32_toolkit/schemas/evidence-envelope.schema.json")


def _envelope() -> dict[str, object]:
    return {
        "schema": "stm32-evidence/1",
        "evidence_id": "0" * 64,
        "identity": {
            "workspace_id": "a" * 64,
            "project_id": "123e4567-e89b-42d3-a456-426614174000",
            "session_id": "session-01",
            "build_id": "b" * 64,
            "elf_sha256": "c" * 64,
            "target_device": "host:windows/amd64",
            "input_snapshot_sha256": "d" * 64,
            "git_commit": "e" * 40,
            "git_dirty": False,
        },
        "operation": "fixture.alpha",
        "produced_at_utc": "2026-08-15T01:02:03.123456Z",
        "parents": [],
        "artifacts": [],
        "metadata": {"result": "passed"},
    }


def _producer_schema(common: dict[str, object], operation: str) -> dict[str, object]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "allOf": [
            common,
            {
                "properties": {
                    "operation": {"const": operation},
                    "metadata": {
                        "type": "object",
                        "required": ["result"],
                        "additionalProperties": False,
                        "properties": {"result": {"enum": ["passed", "failed"]}},
                    },
                },
            },
        ],
    }


def test_root_and_packaged_evidence_schemas_are_byte_identical_and_closed():
    """Distribution must not alter the authoritative schema contract."""
    root_bytes = ROOT_SCHEMA.read_bytes()
    assert root_bytes == PACKAGED_SCHEMA.read_bytes()

    schema = json.loads(root_bytes)
    assert schema["$id"] == "https://stm32-toolkit.dev/schemas/evidence-envelope.schema.json"
    assert schema["required"] == ["schema", "evidence_id", "identity", "operation", "produced_at_utc", "parents", "artifacts", "metadata"]
    assert schema["additionalProperties"] is False
    assert schema["properties"]["metadata"] == {"type": "object"}
    assert schema["properties"]["parents"]["maxItems"] == 64
    assert schema["properties"]["artifacts"]["maxItems"] == 4096
    assert schema["$defs"]["artifact"]["additionalProperties"] is False
    assert schema["$defs"]["identity"]["additionalProperties"] is False


def test_common_schema_leaves_producer_operation_and_metadata_closed_by_composition():
    """A future producer owns its operation/metadata fields; the shared schema does not invent them."""
    common = json.loads(ROOT_SCHEMA.read_text(encoding="utf-8"))
    alpha = Draft202012Validator(_producer_schema(common, "fixture.alpha"))
    beta = Draft202012Validator(_producer_schema(common, "fixture.beta"))
    value = _envelope()

    alpha.validate(value)
    with pytest.raises(ValidationError):
        beta.validate(value)

    missing = _envelope()
    missing["metadata"] = {}
    with pytest.raises(ValidationError):
        alpha.validate(missing)

    extra = _envelope()
    extra["metadata"] = {"result": "passed", "unexpected": True}
    with pytest.raises(ValidationError):
        alpha.validate(extra)


def test_common_schema_leaves_utf8_byte_path_limit_to_the_canonical_model():
    """JSON Schema counts code points, so model validation completes the 512-byte contract."""
    validator = Draft202012Validator(json.loads(ROOT_SCHEMA.read_text(encoding="utf-8")))
    value = _envelope()
    relative_path = "\u00e9" * 257
    value["artifacts"] = [
        {
            "sha256": "1" * 64,
            "size_bytes": 0,
            "relative_path": relative_path,
            "kind": "log",
            "media_type": "text/plain",
        }
    ]

    validator.validate(value)
    with pytest.raises(ValueError):
        ArtifactRef.from_dict(value["artifacts"][0])

    relative_path_schema = validator.schema["$defs"]["artifact"]["properties"]["relative_path"]
    assert relative_path_schema["description"] == (
        "maxLength counts Unicode code points; the canonical model separately enforces "
        "the 512 UTF-8 byte limit."
    )


@pytest.mark.parametrize("relative_path", ["../outside.txt", "x" * 513])
def test_common_schema_enforces_the_artifact_posix_and_code_point_path_contract(relative_path):
    """Schema consumers still reject traversal and values over its safe code-point cap."""
    validator = Draft202012Validator(json.loads(ROOT_SCHEMA.read_text(encoding="utf-8")))
    value = _envelope()
    value["artifacts"] = [
        {
            "sha256": "1" * 64,
            "size_bytes": 0,
            "relative_path": relative_path,
            "kind": "log",
            "media_type": "text/plain",
        }
    ]

    with pytest.raises(ValidationError):
        validator.validate(value)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value.__setitem__("extra", None),
        lambda value: value["identity"].__setitem__("extra", None),
        lambda value: value["identity"].__setitem__("git_dirty", 0),
        lambda value: value.__setitem__("produced_at_utc", "2026-08-15T01:02:03Z"),
        lambda value: value.__setitem__("parents", ["f" * 64] * 65),
        lambda value: value.__setitem__("artifacts", [{"sha256": "1" * 64, "size_bytes": True, "relative_path": "log.txt", "kind": "log", "media_type": "text/plain"}]),
    ],
)
def test_common_schema_rejects_unknown_fields_and_noncanonical_contract_types(mutate):
    """Schema-level validation catches the visible closed-record boundary independently of Python."""
    validator = Draft202012Validator(json.loads(ROOT_SCHEMA.read_text(encoding="utf-8")))
    value = _envelope()
    mutate(value)

    with pytest.raises(ValidationError):
        validator.validate(value)
