from __future__ import annotations

import asyncio
import gc
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from uuid import UUID

import pytest

import stm32_toolkit.testing_workflows as testing_workflows
from stm32_toolkit.diagnostics import (
    DiagnosticEvent,
    calculate_event_digest,
    canonical_diagnostic_json_bytes,
)
from stm32_toolkit.evidence.gc import get_root
from stm32_toolkit.evidence.store import EvidenceStore
from stm32_toolkit.mcp_server import create_server
from stm32_toolkit.paths import WorkspacePaths
from stm32_toolkit.testing.host import HostTestRunner


PROJECT_ID = UUID("12345678-1234-5678-1234-567812345678")
PROJECT_ID_TEXT = str(PROJECT_ID)
SESSION_ID = "a" * 32
SNAPSHOT_SHA = "b" * 64
GIT_HEAD = "c" * 40


def _project_manifest(environment: dict[str, str]) -> dict[str, object]:
    return {
        "schemaVersion": 3,
        "logicalProjectId": PROJECT_ID_TEXT,
        "generatedBy": {"tool": "stm32-toolkit", "version": "0.6.0"},
        "project": {"name": "firmware", "origin": "manual"},
        "target": {"device": "STM32F429ZGTx", "core": "cortex-m4"},
        "framework": {"type": "spl", "version": None},
        "build": {
            "sources": ["App/main.c"],
            "includePaths": [],
            "defines": [],
            "compileOptions": [],
            "assemblySources": [],
            "presets": [],
            "elf": "build-fw/firmware.elf",
        },
        "memory": {"source": "manual", "regions": []},
        "debug": {"backend": "pyocd", "target": "stm32f429zgtx", "svd": None},
        "generation": {
            "cubeMxIoc": None,
            "managedManifest": ".stm32-toolkit/generated-files.json",
            "generatedDirectories": [],
            "userDirectories": [],
        },
        "testing": {
            "host": {
                "buildPreset": "host-build",
                "ctestPreset": "host-tests",
                "labels": [],
                "timeout_seconds": 30,
                "environment": {"allow": list(environment), "values": environment},
            },
            "target": {
                "executable": "build/test/firmware-tests.elf",
                "timeout_seconds": 120,
                "transport": {
                    "kind": "memory-mailbox",
                    "options": {"address": 0x20010000, "size": 4096},
                },
            },
        },
    }


def _write_fake_host_tool(path: Path) -> None:
    path.write_text(
        r'''
import json
from pathlib import Path
import sys

mode, *argv = sys.argv[1:]
if mode == "cmake":
    raise SystemExit(0)
if "--show-only=json-v1" in argv:
    print(json.dumps({
        "backtraceGraph": {"commands": [], "files": [], "nodes": []},
        "kind": "ctestInfo",
        "tests": [
            {"command": ["<REPOSITORY_ROOT>/build/passes.exe"], "name": "passes", "properties": []},
            {"command": ["<REPOSITORY_ROOT>/build/fails.exe"], "name": "fails", "properties": []},
        ],
        "version": {"major": 1, "minor": 0},
    }))
    raise SystemExit(0)
selection = argv[argv.index("--tests-information") + 1]
output = Path(argv[argv.index("--output-junit") + 1])
if selection.endswith(",2"):
    output.write_text(
        '<testsuite tests="1" failures="1" disabled="0" skipped="0">'
        '<testcase name="fails" classname="fails" time="0" status="fail">'
        '<failure message="Failed"/><properties/><system-out></system-out>'
        '</testcase></testsuite>',
        encoding="utf-8",
    )
    print("Test project <REPOSITORY_ROOT>/build")
    print("    Start 1: fails")
    print("1/1 Test #1: fails ......................***Failed    0.01 sec")
    print("0% tests passed, 1 tests failed out of 1")
else:
    raise SystemExit(2)
print("fake stderr", file=sys.stderr)
raise SystemExit(1)
''',
        encoding="utf-8",
    )


def _project_snapshot(project_root: Path) -> tuple[tuple[str, bytes], ...]:
    return tuple(
        sorted(
            (
                path.relative_to(project_root).as_posix(),
                path.read_bytes(),
            )
            for path in project_root.rglob("*")
            if path.is_file()
        )
    )


def _call_registered_tool(
    project_root: Path,
    data_root: Path,
    tool_name: str,
    arguments: dict[str, object] | None = None,
) -> dict[str, object]:
    server = create_server(project_root, data_root, SESSION_ID)
    try:
        _content, result = asyncio.run(
            server.call_tool(tool_name, arguments if arguments is not None else {})
        )
        assert isinstance(result, dict)
        return result
    finally:
        del server
        gc.collect()


def _operation_data(result: dict[str, object], operation: str) -> dict[str, object]:
    assert result["ok"] is True
    assert result["operation"] == operation
    data = result["data"]
    assert isinstance(data, dict)
    return data


def _drop(value: object) -> None:
    del value
    gc.collect()


def test_registered_fastmcp_failed_host_run_survives_full_diagnostic_replay(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    data_root = tmp_path / "data"
    scenario_root = tmp_path / "scenario"
    scenario_root.mkdir()
    fake_host_tool = scenario_root / "fake-host-tool.py"
    _write_fake_host_tool(fake_host_tool)
    junit_source = scenario_root / "unused-junit.xml"
    junit_source.write_text("<testsuite/>", encoding="utf-8")
    results_root = tmp_path / "unused-results"
    environment = {
        "SCENARIO_DIR": str(scenario_root),
        "JUNIT_SOURCE": str(junit_source),
        "RESULTS_ROOT": str(results_root),
    }
    (project_root / ".stm32-project.json").write_text(
        json.dumps(_project_manifest(environment)), encoding="utf-8"
    )
    (project_root / "App").mkdir()
    (project_root / "App" / "main.c").write_bytes(b"int main(void) { return 0; }\n")
    before_project = _project_snapshot(project_root)

    runner_count = 0

    def runner_factory(**kwargs: object) -> HostTestRunner:
        nonlocal runner_count
        runner_count += 1
        return HostTestRunner(
            **kwargs,
            cmake_executable=(sys.executable, str(fake_host_tool), "cmake"),
            ctest_executable=(sys.executable, str(fake_host_tool), "ctest"),
        )

    monkeypatch.setattr(testing_workflows, "_host_runner_factory", runner_factory)
    monkeypatch.setattr(
        testing_workflows,
        "_snapshot_project_inputs",
        lambda _model: SimpleNamespace(sha256=SNAPSHOT_SHA),
    )
    monkeypatch.setattr(
        testing_workflows,
        "_git_evidence",
        lambda _root: SimpleNamespace(head=GIT_HEAD, dirty=False),
    )

    discovered_result = _call_registered_tool(
        project_root, data_root, "stm32_test_host_discover"
    )
    discovered_data = _operation_data(discovered_result, "test.host.discover")
    inventory = discovered_data["inventory"]
    assert isinstance(inventory, dict)
    assert set(inventory["case_ids"]) == {"passes", "fails"}
    assert len(inventory["case_ids"]) == 2
    inventory_digest = inventory["inventory_digest"]
    assert isinstance(inventory_digest, str)
    _drop(discovered_result)

    run_result = _call_registered_tool(
        project_root,
        data_root,
        "stm32_test_host_run",
        {"inventoryDigest": inventory_digest, "caseIds": ["fails"]},
    )
    run_data = _operation_data(run_result, "test.host.run")
    run_summary = run_data["run"]
    assert isinstance(run_summary, dict)
    assert run_summary["state"] == "failed"
    assert run_summary["case_counts"] == {
        "passed": 0,
        "failed": 1,
        "skipped": 0,
        "error": 0,
        "timeout": 0,
    }
    run_id = run_summary["run_id"]
    failed_evidence_id = run_data["evidence_id"]
    assert isinstance(run_id, str)
    assert isinstance(failed_evidence_id, str)
    assert len(failed_evidence_id) == 64
    _drop(run_result)
    assert runner_count == 2

    start_result = _call_registered_tool(
        project_root,
        data_root,
        "stm32_diagnostic_start",
        {"operationId": "e2e-start", "failedTestRunId": run_id},
    )
    start_data = _operation_data(start_result, "diagnostic.start")
    start_session = start_data["session"]
    assert isinstance(start_session, dict)
    assert start_session["state"] == "OPEN"
    assert start_session["revision"] == 1
    assert start_session["failed_evidence_id"] == failed_evidence_id
    diagnostic_session_id = start_session["diagnostic_session_id"]
    assert isinstance(diagnostic_session_id, str)
    assert len(diagnostic_session_id) == 32
    session_identity = start_session["identity"]
    assert isinstance(session_identity, dict)
    _drop(start_result)

    begin_result = _call_registered_tool(
        project_root,
        data_root,
        "stm32_diagnostic_begin",
        {
            "operationId": "e2e-begin",
            "diagnosticSessionId": diagnostic_session_id,
            "expectedRevision": 1,
        },
    )
    begin_data = _operation_data(begin_result, "diagnostic.begin")
    assert begin_data["session"]["revision"] == 2
    _drop(begin_result)

    first_hypothesis_result = _call_registered_tool(
        project_root,
        data_root,
        "stm32_diagnostic_hypothesis_add",
        {
            "operationId": "e2e-hypothesis-one",
            "diagnosticSessionId": diagnostic_session_id,
            "expectedRevision": 2,
            "statement": "the selected case is the failing root cause",
        },
    )
    first_hypothesis_data = _operation_data(
        first_hypothesis_result, "diagnostic.hypothesis.add"
    )
    first_hypothesis = first_hypothesis_data["hypothesis"]
    assert isinstance(first_hypothesis, dict)
    first_hypothesis_id = first_hypothesis["hypothesis_id"]
    assert isinstance(first_hypothesis_id, str)
    _drop(first_hypothesis_result)

    second_hypothesis_result = _call_registered_tool(
        project_root,
        data_root,
        "stm32_diagnostic_hypothesis_add",
        {
            "operationId": "e2e-hypothesis-two",
            "diagnosticSessionId": diagnostic_session_id,
            "expectedRevision": 3,
            "statement": "the failed case count is incidental",
        },
    )
    second_hypothesis_data = _operation_data(
        second_hypothesis_result, "diagnostic.hypothesis.add"
    )
    second_hypothesis = second_hypothesis_data["hypothesis"]
    assert isinstance(second_hypothesis, dict)
    second_hypothesis_id = second_hypothesis["hypothesis_id"]
    assert isinstance(second_hypothesis_id, str)
    _drop(second_hypothesis_result)

    steps = [
        {
            "step_id": "failed-case",
            "selector": {"kind": "case-state", "case_id": "fails"},
            "expected_value": "failed",
            "purpose": "confirm the selected case failed",
        },
        {
            "step_id": "failed-count",
            "selector": {"kind": "case-count", "state": "failed"},
            "expected_value": 1,
            "purpose": "confirm exactly one case failed",
        },
    ]
    plan_result = _call_registered_tool(
        project_root,
        data_root,
        "stm32_diagnostic_plan_add",
        {
            "operationId": "e2e-plan-add",
            "diagnosticSessionId": diagnostic_session_id,
            "expectedRevision": 4,
            "steps": steps,
        },
    )
    plan_data = _operation_data(plan_result, "diagnostic.plan.add")
    plan = plan_data["observation_plan"]
    assert isinstance(plan, dict)
    plan_id = plan["plan_id"]
    assert isinstance(plan_id, str)
    assert len(plan_id) == 64
    assert plan["steps"] == steps
    _drop(plan_result)

    run_plan_result = _call_registered_tool(
        project_root,
        data_root,
        "stm32_diagnostic_plan_run",
        {
            "operationId": "e2e-plan-run",
            "diagnosticSessionId": diagnostic_session_id,
            "expectedRevision": 5,
            "planId": plan_id,
        },
    )
    run_plan_data = _operation_data(run_plan_result, "diagnostic.plan.run")
    observation_results = run_plan_data["observation_results"]
    assert isinstance(observation_results, list)
    assert len(observation_results) == 2
    assert observation_results[0]["step_id"] == "failed-case"
    assert observation_results[0]["observed_value"] == "failed"
    assert observation_results[0]["expected_value"] == "failed"
    assert observation_results[0]["matched"] is True
    assert observation_results[1]["step_id"] == "failed-count"
    assert observation_results[1]["observed_value"] == 1
    assert observation_results[1]["expected_value"] == 1
    assert observation_results[1]["matched"] is True
    assert all(item["evidence_id"] == failed_evidence_id for item in observation_results)
    _drop(run_plan_result)

    first_assessment_result = _call_registered_tool(
        project_root,
        data_root,
        "stm32_diagnostic_hypothesis_assess",
        {
            "operationId": "e2e-assess-one",
            "diagnosticSessionId": diagnostic_session_id,
            "expectedRevision": 6,
            "hypothesisId": first_hypothesis_id,
            "planId": plan_id,
            "stepId": "failed-case",
            "polarity": "supports",
            "rationale": "the failed selected case supports the first hypothesis",
        },
    )
    first_assessment_data = _operation_data(
        first_assessment_result, "diagnostic.hypothesis.assess"
    )
    first_assessment = first_assessment_data["assessment"]
    assert isinstance(first_assessment, dict)
    first_assessment_id = first_assessment["assessment_id"]
    assert isinstance(first_assessment_id, str)
    _drop(first_assessment_result)

    second_assessment_result = _call_registered_tool(
        project_root,
        data_root,
        "stm32_diagnostic_hypothesis_assess",
        {
            "operationId": "e2e-assess-two",
            "diagnosticSessionId": diagnostic_session_id,
            "expectedRevision": 7,
            "hypothesisId": second_hypothesis_id,
            "planId": plan_id,
            "stepId": "failed-count",
            "polarity": "refutes",
            "rationale": "the failed count refutes the competing hypothesis",
        },
    )
    second_assessment_data = _operation_data(
        second_assessment_result, "diagnostic.hypothesis.assess"
    )
    second_assessment = second_assessment_data["assessment"]
    assert isinstance(second_assessment, dict)
    second_assessment_id = second_assessment["assessment_id"]
    assert isinstance(second_assessment_id, str)
    _drop(second_assessment_result)

    show_result = _call_registered_tool(
        project_root,
        data_root,
        "stm32_diagnostic_show",
        {"diagnosticSessionId": diagnostic_session_id},
    )
    show_data = _operation_data(show_result, "diagnostic.show")
    assert show_data["authoritative"] is True
    shown_session = show_data["session"]
    assert isinstance(shown_session, dict)
    assert shown_session["revision"] == 8
    assert shown_session["state"] == "INVESTIGATING"
    assert shown_session["identity"] == session_identity
    assert shown_session["failed_evidence_id"] == failed_evidence_id
    hypotheses = shown_session["hypotheses"]
    plans = shown_session["observation_plans"]
    shown_results = shown_session["observation_results"]
    assert isinstance(hypotheses, list)
    assert isinstance(plans, list)
    assert isinstance(shown_results, list)
    assert len(hypotheses) == 2
    assert len(plans) == 1
    assert len(shown_results) == 2
    assert len(hypotheses[0]["supporting"]) == 1
    assert hypotheses[0]["supporting"][0]["assessment_id"] == first_assessment_id
    assert hypotheses[0]["refuting"] == []
    assert hypotheses[1]["supporting"] == []
    assert len(hypotheses[1]["refuting"]) == 1
    assert hypotheses[1]["refuting"][0]["assessment_id"] == second_assessment_id
    assert all(item["evidence_id"] == failed_evidence_id for item in shown_results)
    assert all(
        assessment["evidence_id"] == failed_evidence_id
        for hypothesis in hypotheses
        for assessment in hypothesis["supporting"] + hypothesis["refuting"]
    )
    _drop(show_result)

    workspace = WorkspacePaths.from_roots(
        data_root, project_root, PROJECT_ID, SESSION_ID
    )
    evidence = EvidenceStore(workspace.workspace_root / "evidence")
    events_dir = workspace.diagnostics_root / "sessions" / diagnostic_session_id / "events"
    event_paths = sorted(events_dir.glob("*.json"))
    assert [path.name for path in event_paths] == [
        f"{sequence:08d}.json" for sequence in range(8)
    ]
    event_types = [
        "session.created",
        "investigation.started",
        "hypothesis.added",
        "hypothesis.added",
        "observation.plan_added",
        "observation.plan_executed",
        "hypothesis.assessed",
        "hypothesis.assessed",
    ]
    checkpoint_manifest_ids: list[str] = []
    previous_digest: str | None = None
    for sequence, (event_path, expected_type) in enumerate(zip(event_paths, event_types)):
        event_bytes = event_path.read_bytes()
        document = json.loads(event_bytes.decode("utf-8"))
        assert canonical_diagnostic_json_bytes(document) == event_bytes
        event = DiagnosticEvent.from_value(document)
        assert event.sequence == sequence
        assert event.revision_before == sequence
        assert event.event_type == expected_type
        assert event.previous_digest == previous_digest
        assert event.digest == calculate_event_digest(document)
        previous_digest = event.digest

        revision = sequence + 1
        checkpoint_root = get_root(
            evidence, "diagnostic-session", f"{diagnostic_session_id}.{revision:08d}"
        )
        checkpoint_manifest_ids.append(checkpoint_root.manifest_id)
        checkpoint_envelope = evidence.get_envelope(checkpoint_root.manifest_id)
        expected_parents: list[str] = []
        if sequence:
            expected_parents.append(checkpoint_manifest_ids[sequence - 1])
        if expected_type in {
            "session.created",
            "observation.plan_executed",
            "hypothesis.assessed",
        }:
            expected_parents.append(failed_evidence_id)
        assert checkpoint_envelope.parents == tuple(expected_parents)
        assert checkpoint_envelope.operation == "diagnostic-event"
        assert checkpoint_envelope.identity.to_dict() == session_identity
        assert checkpoint_envelope.metadata == {
            "diagnostic_session_id": diagnostic_session_id,
            "sequence": sequence,
            "revision": revision,
            "event_digest": event.digest,
        }
        assert len(checkpoint_envelope.artifacts) == 1
        assert (
            evidence.read_artifact(
                checkpoint_envelope.artifacts[0], maximum_bytes=1024 * 1024
            )
            == event_bytes
        )
        assert checkpoint_root.metadata == {
            "diagnostic_session_id": diagnostic_session_id,
            "revision": revision,
            "state": "OPEN" if revision == 1 else "INVESTIGATING",
            "event_digest": event.digest,
        }

    failed_root = get_root(evidence, "test-run", run_id)
    failed_envelope = evidence.get_envelope(failed_root.manifest_id)
    assert failed_root.manifest_id == failed_evidence_id
    assert failed_root.metadata == {"mode": "host", "state": "failed"}
    assert failed_envelope.operation == "host-test-run"
    assert failed_envelope.parents == ()
    assert failed_envelope.identity.to_dict() == session_identity
    assert {artifact.kind for artifact in failed_envelope.artifacts} == {
        "test-manifest",
        "test-events",
        "test-stdout",
        "test-stderr",
    }
    for artifact in failed_envelope.artifacts:
        artifact_bytes = evidence.read_artifact(artifact, maximum_bytes=1024 * 1024)
        assert hashlib.sha256(artifact_bytes).hexdigest() == artifact.sha256

    assert _project_snapshot(project_root) == before_project
