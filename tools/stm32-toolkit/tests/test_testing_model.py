"""Contract tests for the common STM32 test protocol."""

from __future__ import annotations

from dataclasses import fields
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

from jsonschema import Draft202012Validator
import pytest

from stm32_toolkit.evidence import ArtifactRef, EvidenceIdentity, canonical_json_bytes
from stm32_toolkit.testing.model import (
    CASE_STATES,
    MAX_FRAME_PAYLOAD_BYTES,
    MAX_RUN_STREAM_BYTES,
    RUN_STATES,
    TestCaseResult as CaseResult,
    TestInventory as Inventory,
    TestProtocolError as ProtocolError,
    TestRunManifest as RunManifest,
    calculate_host_build_inventory_digest,
    calculate_host_test_executable_inventory_digest,
    calculate_inventory_digest,
    create_inventory,
    host_target_device,
    validate_host_identity,
)
from stm32_toolkit.testing.protocol import assemble_test_run, validate_event_payload


HASH = {
    name: sha256(name.encode("ascii")).hexdigest()
    for name in (
        "workspace",
        "host-build-inventory",
        "host-test-executable-inventory",
        "snapshot",
        "raw-events",
    )
}
UTC_0 = "2026-08-16T00:00:00.000000Z"
UTC_1 = "2026-08-16T00:00:01.000000Z"
UTC_2 = "2026-08-16T00:00:02.000000Z"


def _identity(*, target_device: str = "host:windows/amd64") -> EvidenceIdentity:
    return EvidenceIdentity(
        workspace_id=HASH["workspace"],
        project_id="123e4567-e89b-42d3-a456-426614174000",
        session_id="session-0601-t07",
        build_id=HASH["host-build-inventory"],
        elf_sha256=HASH["host-test-executable-inventory"],
        target_device=target_device,
        input_snapshot_sha256=HASH["snapshot"],
        git_commit="a" * 40,
        git_dirty=False,
    )


def _artifact(kind: str = "test-events") -> ArtifactRef:
    return ArtifactRef(
        sha256=HASH["raw-events"],
        size_bytes=123,
        relative_path=f"objects/{HASH['raw-events'][:2]}/{HASH['raw-events']}",
        kind=kind,
        media_type="application/xml",
    )


def _inventory() -> Inventory:
    return create_inventory(
        mode="host",
        identity=_identity(),
        case_ids=("zeta", "éclair"),
        discovered_at_utc=UTC_0,
        executable_inventory=(
            {"case_id": "éclair", "command": ["build/éclair.exe"]},
            {"case_id": "zeta", "command": ["build/zeta.exe", "--unit"]},
        ),
    )


def test_exact_models_states_limits_and_utf8_inventory_order_are_frozen():
    """Adding fields/states or sorting by locale would change the wire contract."""
    inventory = _inventory()

    assert RUN_STATES == (
        "discovered", "running", "passed", "failed", "error", "cancelled"
    )
    assert CASE_STATES == ("passed", "failed", "skipped", "error", "timeout")
    assert MAX_FRAME_PAYLOAD_BYTES == 16 * 1024
    assert MAX_RUN_STREAM_BYTES == 64 * 1024 * 1024
    assert [field.name for field in fields(CaseResult)] == [
        "case_id", "state", "started_at_utc", "ended_at_utc", "duration_ms",
        "message", "stdout", "stderr",
    ]
    assert [field.name for field in fields(Inventory)] == [
        "mode", "identity", "case_ids", "inventory_digest", "discovered_at_utc",
    ]
    assert [field.name for field in fields(RunManifest)] == [
        "schema", "run_id", "mode", "state", "identity", "transport", "cases",
        "started_at_utc", "ended_at_utc", "duration_ms", "stdout", "stderr", "raw_events",
    ]
    assert inventory.case_ids == ("zeta", "éclair")
    assert inventory.inventory_digest == calculate_inventory_digest(
        "host", inventory.identity, inventory.case_ids,
        executable_inventory=(
            {"case_id": "éclair", "command": ["build/éclair.exe"]},
            {"case_id": "zeta", "command": ["build/zeta.exe", "--unit"]},
        ),
    )


def test_inventory_rejects_duplicates_empty_unsorted_and_unbound_digest():
    """An ambiguous or silently reordered inventory must never become authoritative."""
    for case_ids, digest in (
        ((), "0" * 64),
        (("same", "same"), "0" * 64),
        (("éclair", "zeta"), "0" * 64),
        (("zeta", "éclair"), "not-a-digest"),
    ):
        with pytest.raises(ProtocolError):
            Inventory("host", _identity(), case_ids, digest, UTC_0)

    with pytest.raises(ProtocolError) as caught:
        create_inventory("host", _identity(), (), UTC_0)
    assert caught.value.code == "TEST_NO_CASES"


def test_host_identity_is_exact_and_never_uses_placeholder_firmware_hashes():
    """Host evidence must identify the real OS/architecture and real inventories."""
    assert host_target_device(system="Windows", architecture="AMD64") == "host:windows/amd64"
    assert host_target_device(system="Linux", architecture="aarch64") == "host:linux/arm64"
    validate_host_identity(_identity(), system="Windows", architecture="AMD64")

    for identity in (
        _identity(target_device="host:windows/x86"),
        EvidenceIdentity(**{**_identity().to_dict(), "build_id": "0" * 64}),
        EvidenceIdentity(**{**_identity().to_dict(), "elf_sha256": "0" * 64}),
    ):
        with pytest.raises(ProtocolError) as caught:
            validate_host_identity(identity, system="Windows", architecture="AMD64")
        assert caught.value.code == "TEST_IDENTITY_MISMATCH"


def test_event_state_machine_records_incomplete_cases_and_rejects_illegal_transitions():
    """A started case cannot disappear or receive two terminal outcomes."""
    inventory = _inventory()
    events = (
        (0, "run_start", {
            "run_id": "run-1", "started_at_utc": UTC_0,
            "case_ids": ["zeta", "éclair"], "inventory_digest": inventory.inventory_digest,
        }),
        (1, "case_start", {"case_id": "zeta", "started_at_utc": UTC_0}),
        (2, "case_result", {
            "case_id": "zeta", "state": "passed", "ended_at_utc": UTC_1,
            "duration_ms": 1000, "message": None, "stdout": None, "stderr": None,
        }),
        (3, "case_start", {"case_id": "éclair", "started_at_utc": UTC_1}),
        (4, "run_end", {
            "state": "error", "ended_at_utc": UTC_2, "duration_ms": 2000,
            "inventory_digest": inventory.inventory_digest,
            "build_id": inventory.identity.build_id,
            "elf_sha256": inventory.identity.elf_sha256,
            "target_device": inventory.identity.target_device,
            "counts": {"passed": 1, "failed": 0, "skipped": 0, "error": 1, "timeout": 0},
            "event_stream_digest": HASH["raw-events"],
        }),
    )

    manifest = assemble_test_run(
        inventory, events, exit_code=None, raw_events=_artifact(), transport="rtt"
    )

    assert manifest.state == "error"
    assert [(case.case_id, case.state) for case in manifest.cases] == [
        ("zeta", "passed"), ("éclair", "error")
    ]
    assert manifest.cases[1].message == "case ended without a terminal result"

    duplicate_terminal = events[:3] + (events[2],) + events[3:]
    with pytest.raises(ProtocolError) as caught:
        assemble_test_run(
            inventory, duplicate_terminal, exit_code=None,
            raw_events=_artifact(), transport="rtt",
        )
    assert caught.value.code == "TEST_EVENT_SEQUENCE_INVALID"


def test_cancelled_run_remains_cancelled_while_incomplete_case_is_recorded_as_error():
    """Cancellation is a terminal run state, not a way to hide an incomplete selected case."""
    inventory = create_inventory("target", _identity(), ("one",), UTC_0)
    events = (
        (0, "run_start", {
            "run_id": "run-cancelled", "started_at_utc": UTC_0,
            "case_ids": ["one"], "inventory_digest": inventory.inventory_digest,
        }),
        (1, "run_end", {
            "state": "cancelled", "ended_at_utc": UTC_1, "duration_ms": 1000,
            "inventory_digest": inventory.inventory_digest,
            "build_id": inventory.identity.build_id,
            "elf_sha256": inventory.identity.elf_sha256,
            "target_device": inventory.identity.target_device,
            "counts": {"passed": 0, "failed": 0, "skipped": 0, "error": 1, "timeout": 0},
            "event_stream_digest": HASH["raw-events"],
        }),
    )

    manifest = assemble_test_run(
        inventory, events, exit_code=None, raw_events=_artifact(), transport="uart"
    )

    assert manifest.state == "cancelled"
    assert [(case.case_id, case.state) for case in manifest.cases] == [("one", "error")]


@pytest.mark.parametrize(
    ("case_state", "run_state", "exit_code"),
    [("failed", "failed", 0), ("passed", "passed", 1)],
)
def test_exit_code_cannot_override_or_contradict_terminal_events(
    case_state: str, run_state: str, exit_code: int,
):
    """A process/status disagreement cannot be represented as a passing run."""
    inventory = create_inventory("host", _identity(), ("one",), UTC_0)
    counts = {state: int(state == case_state) for state in CASE_STATES}
    events = (
        (0, "run_start", {
            "run_id": "run-1", "started_at_utc": UTC_0,
            "case_ids": ["one"], "inventory_digest": inventory.inventory_digest,
        }),
        (1, "case_start", {"case_id": "one", "started_at_utc": UTC_0}),
        (2, "case_result", {
            "case_id": "one", "state": case_state, "ended_at_utc": UTC_1,
            "duration_ms": 1000, "message": None, "stdout": None, "stderr": None,
        }),
        (3, "run_end", {
            "state": run_state, "ended_at_utc": UTC_1, "duration_ms": 1000,
            "inventory_digest": inventory.inventory_digest,
            "build_id": inventory.identity.build_id,
            "elf_sha256": inventory.identity.elf_sha256,
            "target_device": inventory.identity.target_device,
            "counts": counts, "event_stream_digest": HASH["raw-events"],
        }),
    )

    with pytest.raises(ProtocolError) as caught:
        assemble_test_run(
            inventory, events, exit_code=exit_code,
            raw_events=_artifact(), transport=None,
        )
    assert caught.value.code == "TEST_EXIT_MISMATCH"


def test_event_payloads_are_closed_per_kind_and_artifacts_are_typed():
    """Unknown payload members and non-ArtifactRef output cannot cross the protocol."""
    valid = {"case_id": "one", "started_at_utc": UTC_0}
    assert validate_event_payload("case_start", valid) == valid
    with pytest.raises(ProtocolError):
        validate_event_payload("case_start", {**valid, "extra": True})
    with pytest.raises(ProtocolError):
        CaseResult("one", "passed", UTC_0, UTC_1, 1000, None, "stdout", None)


def test_schema_mirrors_compile_and_close_every_event_payload():
    """Schema drift or an open payload object would permit a second wire contract."""
    repo = Path(__file__).resolve().parents[3]
    root_schema = repo / "schemas/stm32-test.schema.json"
    packaged_schema = (
        repo / "tools/stm32-toolkit/src/stm32_toolkit/schemas/stm32-test.schema.json"
    )

    assert root_schema.read_bytes() == packaged_schema.read_bytes()
    schema = json.loads(root_schema.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    assert schema["$defs"]["testCaseResult"]["additionalProperties"] is False
    assert schema["$defs"]["testInventory"]["additionalProperties"] is False
    assert schema["$defs"]["testRunManifest"]["additionalProperties"] is False
    assert schema["$defs"]["testRunManifest"]["properties"]["cases"]["minItems"] == 1
    assert "pattern" in schema["$defs"]["artifact"]["properties"]["relative_path"]
    for kind in ("inventory", "runStart", "caseStart", "caseResult", "runEnd", "log"):
        assert schema["$defs"][f"{kind}Payload"]["additionalProperties"] is False
    assert schema["$defs"]["frame"]["properties"]["kind"]["enum"] == [1, 2, 3, 4, 5, 6]
    assert schema["$defs"]["frame"]["properties"]["payload_length"]["maximum"] == 16384


@pytest.mark.parametrize(
    "make_invalid",
    [
        lambda: CaseResult("", "passed", UTC_0, UTC_1, 1, None, None, None),
        lambda: CaseResult("e\u0301", "passed", UTC_0, UTC_1, 1, None, None, None),
        lambda: CaseResult("x" * 65537, "passed", UTC_0, UTC_1, 1, None, None, None),
        lambda: CaseResult("one", "unknown", UTC_0, UTC_1, 1, None, None, None),
        lambda: CaseResult("one", "passed", "not-utc", UTC_1, 1, None, None, None),
        lambda: CaseResult("one", "passed", UTC_1, UTC_0, 1, None, None, None),
        lambda: CaseResult("one", "passed", UTC_0, UTC_1, True, None, None, None),
        lambda: CaseResult("one", "passed", UTC_0, UTC_1, 1, "", None, None),
    ],
)
def test_case_model_rejects_each_ambiguous_scalar_boundary(make_invalid):
    """Malformed IDs, clocks, state, duration, and messages cannot enter a result."""
    with pytest.raises(ProtocolError):
        make_invalid()


def test_model_serializers_emit_fresh_json_shapes_with_real_artifact_refs():
    """Serialization must preserve the exact public records without Python objects."""
    artifact = _artifact()
    case = CaseResult("one", "failed", UTC_0, UTC_1, 1000, "failure", artifact, artifact)
    inventory = create_inventory("target", _identity(), ("one",), UTC_0)
    manifest = RunManifest(
        "stm32-test/1", "run-1", "target", "failed", inventory.identity, "uart",
        (case,), UTC_0, UTC_1, 1000, artifact, artifact, artifact,
    )

    assert case.to_dict()["stdout"] == artifact.to_dict()
    assert inventory.to_dict()["case_ids"] == ["one"]
    serialized = manifest.to_dict()
    assert serialized["cases"] == [case.to_dict()]
    assert serialized["raw_events"] == artifact.to_dict()


def test_inventory_digest_rejects_malformed_executable_material_and_identity():
    """Host command changes are digest material only when their shape exactly matches cases."""
    invalid = (
        ("invalid", _identity(), ("one",), ()),
        ("host", object(), ("one",), ()),
        ("host", _identity(), (), ()),
        ("host", _identity(), ("one", "one"), ()),
        ("host", _identity(), ("one",), ({"case_id": "one"},)),
        ("host", _identity(), ("one",), ({"case_id": "one", "command": []},)),
        ("host", _identity(), ("one",), ({"case_id": "two", "command": ["two.exe"]},)),
    )
    for mode, identity, cases, executables in invalid:
        with pytest.raises(ProtocolError):
            calculate_inventory_digest(
                mode, identity, cases, executable_inventory=executables
            )
    with pytest.raises(ProtocolError):
        create_inventory("host", _identity(), (1,), UTC_0)


def test_host_build_and_executable_identity_digests_use_canonical_ordered_inventories():
    """Host build/ELF identity slots bind real canonical inventories, never firmware placeholders."""
    executables = (
        {"case_id": "éclair", "command": ["build/éclair.exe"]},
        {"case_id": "zeta", "command": ["build/zeta.exe", "--unit"]},
    )

    assert calculate_host_build_inventory_digest(
        "b", "t", ("unit", "fast"), executables
    ) == "836215876c1b310d81809c52ae229c494650fc36aa5e77a9a5238f5702eb39bc"
    assert calculate_host_test_executable_inventory_digest(
        reversed(executables)
    ) == "87449cd252db1eda6b7a10b6f8256227610a10b86d06200df8694b3aa3f48e4e"
    for invalid in ((), ({"case_id": "one"},), ({"case_id": "one", "command": []},)):
        with pytest.raises(ProtocolError):
            calculate_host_test_executable_inventory_digest(invalid)
    with pytest.raises(ProtocolError):
        calculate_host_build_inventory_digest("b", "t", ("unit", "unit"), executables)


def test_manifest_rejects_every_unbound_or_noncanonical_member():
    """A manifest cannot weaken schema, identity, case, time, or stream bindings."""
    artifact = _artifact()
    case = CaseResult("one", "passed", UTC_0, UTC_1, 1000, None, None, None)
    arguments = [
        "stm32-test/1", "run-1", "host", "passed", _identity(), None,
        (case,), UTC_0, UTC_1, 1000, None, None, artifact,
    ]
    mutations = {
        0: "stm32-test/2",
        1: "UPPER",
        2: "other",
        4: object(),
        6: [case],
        7: UTC_2,
        8: "2025-08-16T00:00:00.000000Z",
        12: "not-an-artifact",
    }
    for index, value in mutations.items():
        changed = list(arguments)
        changed[index] = value
        with pytest.raises(ProtocolError):
            RunManifest(*changed)

    duplicate = list(arguments)
    duplicate[6] = (case, case)
    with pytest.raises(ProtocolError):
        RunManifest(*duplicate)
    empty = list(arguments)
    empty[6] = ()
    with pytest.raises(ProtocolError):
        RunManifest(*empty)
    huge = ArtifactRef(
        sha256="1" * 64, size_bytes=64 * 1024 * 1024 + 1,
        relative_path="objects/huge", kind="events", media_type="application/octet-stream",
    )
    too_large = list(arguments)
    too_large[12] = huge
    with pytest.raises(ProtocolError) as caught:
        RunManifest(*too_large)
    assert caught.value.code == "TEST_STREAM_TOO_LARGE"


def test_all_six_event_payload_shapes_accept_only_their_real_members():
    """Every target event kind has one independently validated closed payload."""
    artifact = _artifact().to_dict()
    payloads = {
        "inventory": {
            "mode": "target", "identity": _identity().to_dict(), "case_ids": ["one"],
            "inventory_digest": HASH["raw-events"], "discovered_at_utc": UTC_0,
        },
        "run_start": {
            "run_id": "run-1", "started_at_utc": UTC_0, "case_ids": ["one"],
            "inventory_digest": HASH["raw-events"],
        },
        "case_start": {"case_id": "one", "started_at_utc": UTC_0},
        "case_result": {
            "case_id": "one", "state": "error", "ended_at_utc": UTC_1,
            "duration_ms": 1000, "message": "failed", "stdout": artifact, "stderr": None,
        },
        "run_end": {
            "state": "error", "ended_at_utc": UTC_1, "duration_ms": 1000,
            "inventory_digest": HASH["raw-events"], "build_id": _identity().build_id,
            "elf_sha256": _identity().elf_sha256, "target_device": _identity().target_device,
            "counts": {"passed": 0, "failed": 0, "skipped": 0, "error": 1, "timeout": 0},
            "event_stream_digest": HASH["raw-events"],
        },
        "log": {"timestamp_utc": UTC_0, "stream": "stderr", "message": "line"},
    }
    for kind, payload in payloads.items():
        assert validate_event_payload(kind, payload) == payload


@pytest.mark.parametrize(
    ("kind", "mutate"),
    [
        ("unknown", lambda value: value),
        ("inventory", lambda value: value.__setitem__("mode", "other")),
        ("inventory", lambda value: value.__setitem__("identity", {})),
        ("run_start", lambda value: value.__setitem__("case_ids", [])),
        ("run_start", lambda value: value.__setitem__("case_ids", ["one", "one"])),
        ("case_result", lambda value: value.__setitem__("state", "unknown")),
        ("case_result", lambda value: value.__setitem__("duration_ms", True)),
        ("case_result", lambda value: value.__setitem__("stdout", {"bad": True})),
        ("case_result", lambda value: value.__setitem__("stderr", "bad")),
        ("run_end", lambda value: value.__setitem__("state", "running")),
        ("run_end", lambda value: value.__setitem__("inventory_digest", "bad")),
        ("run_end", lambda value: value.__setitem__("counts", {"passed": 1})),
        ("log", lambda value: value.__setitem__("stream", "log")),
        ("log", lambda value: value.__setitem__("timestamp_utc", "bad")),
    ],
)
def test_event_payload_scalar_and_collection_corruption_is_rejected(kind, mutate):
    """Each malformed native payload is rejected at the first protocol boundary."""
    base = {
        "inventory": {
            "mode": "target", "identity": _identity().to_dict(), "case_ids": ["one"],
            "inventory_digest": HASH["raw-events"], "discovered_at_utc": UTC_0,
        },
        "run_start": {
            "run_id": "run-1", "started_at_utc": UTC_0, "case_ids": ["one"],
            "inventory_digest": HASH["raw-events"],
        },
        "case_result": {
            "case_id": "one", "state": "passed", "ended_at_utc": UTC_1,
            "duration_ms": 1, "message": None, "stdout": None, "stderr": None,
        },
        "run_end": {
            "state": "passed", "ended_at_utc": UTC_1, "duration_ms": 1,
            "inventory_digest": HASH["raw-events"], "build_id": _identity().build_id,
            "elf_sha256": _identity().elf_sha256, "target_device": _identity().target_device,
            "counts": {"passed": 1, "failed": 0, "skipped": 0, "error": 0, "timeout": 0},
            "event_stream_digest": HASH["raw-events"],
        },
        "log": {"timestamp_utc": UTC_0, "stream": "stdout", "message": "line"},
        "unknown": {},
    }
    payload = deepcopy(base[kind])
    mutate(payload)
    with pytest.raises(ProtocolError):
        validate_event_payload(kind, payload)


def test_event_payload_rejects_empty_and_noncanonical_time_and_accepts_artifact_object():
    """Decoded events retain canonical time/text while internal assembly may use ArtifactRef."""
    for payload in (
        {"timestamp_utc": UTC_0, "stream": "stdout", "message": ""},
        {"timestamp_utc": "2026-08-16T00:00:00.0Z", "stream": "stdout", "message": "line"},
    ):
        with pytest.raises(ProtocolError):
            validate_event_payload("log", payload)
    payload = {
        "case_id": "one", "state": "passed", "ended_at_utc": UTC_1,
        "duration_ms": 1, "message": None, "stdout": _artifact(), "stderr": None,
    }
    assert validate_event_payload("case_result", payload) == payload


def test_run_assembly_rejects_misplaced_unknown_and_unbound_events():
    """Sequence, selection, terminal, identity, and summary mutations are all observable."""
    inventory = create_inventory("host", _identity(), ("one",), UTC_0)
    start = (0, "run_start", {
        "run_id": "run-1", "started_at_utc": UTC_0, "case_ids": ["one"],
        "inventory_digest": inventory.inventory_digest,
    })
    case_start = (1, "case_start", {"case_id": "one", "started_at_utc": UTC_0})
    case_result = (2, "case_result", {
        "case_id": "one", "state": "passed", "ended_at_utc": UTC_1,
        "duration_ms": 1000, "message": None, "stdout": None, "stderr": None,
    })
    end_payload = {
        "state": "passed", "ended_at_utc": UTC_1, "duration_ms": 1000,
        "inventory_digest": inventory.inventory_digest, "build_id": inventory.identity.build_id,
        "elf_sha256": inventory.identity.elf_sha256,
        "target_device": inventory.identity.target_device,
        "counts": {"passed": 1, "failed": 0, "skipped": 0, "error": 0, "timeout": 0},
        "event_stream_digest": HASH["raw-events"],
    }
    valid = (start, case_start, case_result, (3, "run_end", end_payload))
    malformed_streams = [
        (),
        ((1, "run_start", start[2]),),
        ((0, "case_start", case_start[2]),),
        (start, (1, "case_start", {"case_id": "other", "started_at_utc": UTC_0})),
        (start, case_start, case_start),
        (start, (1, "case_result", case_result[2])),
        (start, (1, "inventory", {
            "mode": "host", "identity": inventory.identity.to_dict(), "case_ids": ["one"],
            "inventory_digest": inventory.inventory_digest, "discovered_at_utc": UTC_0,
        })),
        (start,),
    ]
    for stream in malformed_streams:
        with pytest.raises(ProtocolError):
            assemble_test_run(
                inventory, stream, exit_code=None, raw_events=_artifact(), transport=None
            )

    for field, value in (
        ("inventory_digest", "1" * 64),
        ("build_id", "1" * 64),
        ("state", "failed"),
    ):
        changed = dict(end_payload)
        changed[field] = value
        with pytest.raises(ProtocolError):
            assemble_test_run(
                inventory, (*valid[:3], (3, "run_end", changed)),
                exit_code=None, raw_events=_artifact(), transport=None,
            )

    with pytest.raises(ProtocolError):
        assemble_test_run(
            inventory, valid, exit_code=True, raw_events=_artifact(), transport=None
        )
