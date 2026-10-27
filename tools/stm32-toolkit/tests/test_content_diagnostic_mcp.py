"""MCP-edge contract tests for the optional Monitor snapshot provenance pair.

The registered ``stm32_diagnostic_plan_add`` tool must accept the legacy Git
reference and the complete snapshot reference while rejecting every partial,
explicit-null, mixed, extra or unknown pair value before any workflow effect.
The same contract must hold for existing ``DiagnosticMonitorRunRef`` instances:
``model_copy`` results and mutated models may not smuggle an explicit null past
the serializer, which omits the pair for a legacy reference.
"""

from __future__ import annotations

import asyncio
from copy import deepcopy
from pathlib import Path

import pytest
from mcp.server.fastmcp.exceptions import ToolError
from pydantic import ValidationError as PydanticValidationError

import stm32_toolkit.mcp_server as mcp_mod
from stm32_toolkit.mcp_server import (
    DiagnosticMonitorRunRef,
    DiagnosticObservationStep,
    create_server,
)
from stm32_toolkit.monitor_replay_contract import (
    ReplayContractError,
    validate_run_reference,
)
from test_diagnostic_mcp import (
    DIAGNOSTIC_SESSION_ID,
    OPERATION_ID,
    PHYSICAL_FACT_STEP,
    PHYSICAL_MONITOR_REF,
    _redigest_monitor_reference,
    _resolve_schema,
    _runtime,
    _schemas,
    _tree_snapshot,
    _v2_failed_before_step,
)

SNAPSHOT_MONITOR_REF: dict[str, object] = deepcopy(PHYSICAL_MONITOR_REF)
SNAPSHOT_MONITOR_REF.update(
    {
        "git_head": None,
        "git_dirty": None,
        "source_baseline": "input-snapshot-v1",
        "git_evidence": {
            "status": "unavailable",
            "code": "BUILD_GIT_INVALID",
            "rule": "head",
        },
    }
)
_redigest_monitor_reference(SNAPSHOT_MONITOR_REF)

REFERENCE_FIELDS = frozenset(
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
        "source_baseline",
        "git_evidence",
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
        "projected_batch_sha256s",
        "transcript_evidence_id",
        "run_ref_sha256",
        "source_record_sha256",
    }
)
PAIR_FIELDS = frozenset({"source_baseline", "git_evidence"})


def _plan_add_wire(step: dict[str, object]) -> dict[str, object]:
    return {
        "operationId": OPERATION_ID,
        "diagnosticSessionId": DIAGNOSTIC_SESSION_ID,
        "expectedRevision": 4,
        "steps": [step],
    }


def _physical_step(kind: str, reference: dict[str, object]) -> dict[str, object]:
    step = (
        _v2_failed_before_step()
        if kind == "physical-monitor-fact/2"
        else deepcopy(PHYSICAL_FACT_STEP)
    )
    selector = step["selector"]
    assert isinstance(selector, dict)
    selector["monitor_run_ref"] = deepcopy(reference)
    return step


def _schema_variants(schema: dict[str, object]) -> list[dict[str, object]]:
    variants = schema.get("anyOf") or schema.get("oneOf")
    assert isinstance(variants, list)
    return [item for item in variants if isinstance(item, dict)]


def _schema_types(schema: dict[str, object]) -> set[object]:
    return {item.get("type") for item in _schema_variants(schema)}


def _validated(reference: dict[str, object]) -> DiagnosticMonitorRunRef:
    return DiagnosticMonitorRunRef.model_validate(deepcopy(reference))


def _malformed_reference(case_id: str) -> dict[str, object]:
    if case_id == "raw-partial":
        reference = deepcopy(SNAPSHOT_MONITOR_REF)
        reference.pop("git_evidence")
    elif case_id == "explicit-null-pair":
        reference = deepcopy(PHYSICAL_MONITOR_REF)
        reference["source_baseline"] = None
        reference["git_evidence"] = None
    elif case_id == "explicit-null-baseline":
        reference = deepcopy(PHYSICAL_MONITOR_REF)
        reference["source_baseline"] = None
    elif case_id == "mixed-git-and-snapshot":
        reference = deepcopy(SNAPSHOT_MONITOR_REF)
        reference["git_head"] = "e" * 40
    elif case_id == "extra-evidence-key":
        reference = deepcopy(SNAPSHOT_MONITOR_REF)
        evidence = reference["git_evidence"]
        assert isinstance(evidence, dict)
        reference["git_evidence"] = {**evidence, "extra": "x"}
    elif case_id == "unknown-evidence-rule":
        reference = deepcopy(SNAPSHOT_MONITOR_REF)
        evidence = reference["git_evidence"]
        assert isinstance(evidence, dict)
        reference["git_evidence"] = {**evidence, "rule": "index"}
    else:
        raise AssertionError(f"unhandled malformed case: {case_id}")
    _redigest_monitor_reference(reference)
    return reference


def test_registered_plan_add_schema_closes_the_optional_pair(tmp_path: Path) -> None:
    add = _schemas(tmp_path)["stm32_diagnostic_plan_add"]
    steps = _resolve_schema(add["properties"]["steps"]["items"], add)
    selector = _resolve_schema(steps["properties"]["selector"], add)
    resolved = [_resolve_schema(item, add) for item in _schema_variants(selector)]
    physical_v2 = next(
        item
        for item in resolved
        if "monitor_run_ref" in item["properties"]
        and "continuation_evidence_id" not in item["properties"]
    )
    reference = _resolve_schema(physical_v2["properties"]["monitor_run_ref"], add)
    properties = reference["properties"]
    assert isinstance(properties, dict)
    required = set(reference["required"])

    assert reference["additionalProperties"] is False
    assert set(properties) == REFERENCE_FIELDS
    assert required == REFERENCE_FIELDS - PAIR_FIELDS
    for key in ("source_baseline", "git_evidence"):
        assert properties[key]["default"] is None
        assert "null" in _schema_types(properties[key])
    for key in ("git_head", "git_dirty", "svd_sha256"):
        assert key in required
        assert "null" in _schema_types(properties[key])


@pytest.mark.parametrize(
    ("kind", "snapshot"),
    [
        ("physical-monitor-fact/1", False),
        ("physical-monitor-fact/2", False),
        ("physical-monitor-fact/1", True),
        ("physical-monitor-fact/2", True),
    ],
    ids=["legacy-v1", "legacy-v2", "snapshot-v1", "snapshot-v2"],
)
def test_registered_plan_add_forwards_the_exact_physical_reference(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    kind: str,
    snapshot: bool,
) -> None:
    runtime = _runtime(tmp_path)
    server = create_server(runtime.project_root, runtime.data_root, runtime.session_id)
    calls: list[tuple[object, ...]] = []

    async def helper(*args: object) -> dict[str, object]:
        calls.append(args)
        return {"tool": "plan-add"}

    monkeypatch.setattr(mcp_mod, "tool_diagnostic_add_plan_for_request", helper)

    reference = SNAPSHOT_MONITOR_REF if snapshot else PHYSICAL_MONITOR_REF
    step = _physical_step(kind, reference)
    wire = _plan_add_wire(step)
    wire_before = deepcopy(wire)

    _content, result = asyncio.run(server.call_tool("stm32_diagnostic_plan_add", wire))

    assert result == {"tool": "plan-add"}
    assert len(calls) == 1
    assert calls[0][0].project_root == runtime.project_root
    assert calls[0][2:] == (
        OPERATION_ID,
        DIAGNOSTIC_SESSION_ID,
        4,
        [step],
        "user",
    )
    forwarded_step = calls[0][5][0]
    assert forwarded_step == step
    forwarded_reference = forwarded_step["selector"]["monitor_run_ref"]
    assert forwarded_reference == reference
    assert set(forwarded_reference) == set(reference)
    assert forwarded_reference["svd_sha256"] is None
    if snapshot:
        assert forwarded_reference["source_baseline"] == "input-snapshot-v1"
        assert forwarded_reference["git_evidence"] == {
            "status": "unavailable",
            "code": "BUILD_GIT_INVALID",
            "rule": "head",
        }
        assert forwarded_reference["git_head"] is None
        assert forwarded_reference["git_dirty"] is None
    else:
        assert not (PAIR_FIELDS & set(forwarded_reference))
        assert forwarded_reference["git_head"] == "e" * 40
        assert forwarded_reference["git_dirty"] is False
    assert wire == wire_before


@pytest.mark.parametrize(
    "case_id",
    [
        "raw-partial",
        "explicit-null-pair",
        "explicit-null-baseline",
        "mixed-git-and-snapshot",
        "extra-evidence-key",
        "unknown-evidence-rule",
    ],
)
def test_registered_plan_add_rejects_malformed_pair_before_effects(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    case_id: str,
) -> None:
    runtime = _runtime(tmp_path)
    server = create_server(runtime.project_root, runtime.data_root, runtime.session_id)
    calls: list[tuple[object, ...]] = []

    async def helper(*args: object) -> dict[str, object]:
        calls.append(args)
        return {"tool": "plan-add"}

    monkeypatch.setattr(mcp_mod, "tool_diagnostic_add_plan_for_request", helper)
    project_before = _tree_snapshot(runtime.project_root)
    data_before = _tree_snapshot(runtime.data_root)

    reference = _malformed_reference(case_id)
    # The shared replay contract is the single owner of these rules.
    with pytest.raises(ReplayContractError):
        validate_run_reference(reference)

    selector = deepcopy(PHYSICAL_FACT_STEP)
    selector_data = selector["selector"]
    assert isinstance(selector_data, dict)
    selector_data["monitor_run_ref"] = reference
    wire = _plan_add_wire(selector)
    wire_before = deepcopy(wire)

    with pytest.raises(ToolError) as error:
        asyncio.run(server.call_tool("stm32_diagnostic_plan_add", wire))

    assert "monitor run reference violates replay contract" in str(error.value)
    assert calls == []
    assert wire == wire_before
    assert _tree_snapshot(runtime.project_root) == project_before
    assert _tree_snapshot(runtime.data_root) == data_before


@pytest.mark.parametrize(
    "reference",
    [PHYSICAL_MONITOR_REF, SNAPSHOT_MONITOR_REF],
    ids=["legacy", "snapshot"],
)
def test_valid_instance_roundtrips_through_the_shared_contract(
    reference: dict[str, object],
) -> None:
    expected = deepcopy(reference)
    instance = DiagnosticMonitorRunRef.model_validate(deepcopy(expected))
    assert instance.model_dump(mode="python", by_alias=True) == expected

    revalidated = DiagnosticMonitorRunRef.model_validate(instance)
    dumped = revalidated.model_dump(mode="python", by_alias=True)

    assert dumped == expected
    assert set(dumped) == set(expected)
    assert dumped["svd_sha256"] is None
    if "source_baseline" in expected:
        assert dumped["source_baseline"] == "input-snapshot-v1"
        assert dumped["git_evidence"] == expected["git_evidence"]
        assert dumped["git_head"] is None
        assert dumped["git_dirty"] is None
    else:
        # Only the absent default pair may be omitted from a legacy reference.
        assert not (PAIR_FIELDS & set(dumped))
        assert dumped["git_head"] == "e" * 40
        assert dumped["git_dirty"] is False


@pytest.mark.parametrize(
    "case_id",
    [
        "copy-explicit-null-baseline",
        "assignment-explicit-null-pair",
        "copy-partial-snapshot",
        "copy-mixed-git-head",
    ],
)
def test_explicit_or_partial_pair_on_existing_instances_fails_before_use(
    case_id: str,
) -> None:
    if case_id == "copy-explicit-null-baseline":
        mutated = _validated(PHYSICAL_MONITOR_REF).model_copy(
            update={"source_baseline": None}
        )
        assert "source_baseline" in mutated.model_fields_set
        dumped = mutated.model_dump(mode="python", by_alias=True)
        # Only absent default pair keys are omitted; an explicit null stays.
        assert dumped["source_baseline"] is None
        assert "git_evidence" not in dumped
    elif case_id == "assignment-explicit-null-pair":
        mutated = _validated(PHYSICAL_MONITOR_REF)
        mutated.source_baseline = None
        mutated.git_evidence = None
        assert PAIR_FIELDS <= mutated.model_fields_set
        dumped = mutated.model_dump(mode="python", by_alias=True)
        assert PAIR_FIELDS <= set(dumped)
        assert dumped["source_baseline"] is None
        assert dumped["git_evidence"] is None
    elif case_id == "copy-partial-snapshot":
        mutated = _validated(SNAPSHOT_MONITOR_REF).model_copy(
            update={"git_evidence": None}
        )
        assert "git_evidence" in mutated.model_fields_set
        dumped = mutated.model_dump(mode="python", by_alias=True)
        assert dumped["git_evidence"] is None
        assert dumped["source_baseline"] == "input-snapshot-v1"
    else:
        mutated = _validated(SNAPSHOT_MONITOR_REF).model_copy(
            update={"git_head": "e" * 40}
        )
        assert mutated.model_dump(mode="python", by_alias=True)["git_head"] == "e" * 40

    with pytest.raises(PydanticValidationError) as error:
        DiagnosticMonitorRunRef.model_validate(mutated)
    assert "monitor run reference violates replay contract" in str(error.value)


@pytest.mark.parametrize(
    "reference",
    [PHYSICAL_MONITOR_REF, SNAPSHOT_MONITOR_REF],
    ids=["legacy", "snapshot"],
)
def test_nested_instance_reference_is_accepted_when_valid(
    reference: dict[str, object],
) -> None:
    expected = deepcopy(reference)
    step = deepcopy(PHYSICAL_FACT_STEP)
    selector = step["selector"]
    assert isinstance(selector, dict)
    selector["monitor_run_ref"] = _validated(expected)

    decoded = DiagnosticObservationStep.model_validate(step)

    assert decoded.selector.monitor_run_ref.model_dump(
        mode="python", by_alias=True
    ) == expected


def test_nested_mutated_instance_reference_is_revalidated() -> None:
    mutated = _validated(PHYSICAL_MONITOR_REF).model_copy(
        update={"source_baseline": None}
    )
    step = deepcopy(PHYSICAL_FACT_STEP)
    selector = step["selector"]
    assert isinstance(selector, dict)
    selector["monitor_run_ref"] = mutated

    with pytest.raises(PydanticValidationError) as error:
        DiagnosticObservationStep.model_validate(step)
    assert "monitor run reference violates replay contract" in str(error.value)
