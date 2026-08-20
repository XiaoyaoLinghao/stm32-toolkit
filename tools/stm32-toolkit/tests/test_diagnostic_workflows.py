from __future__ import annotations

import gc
import hashlib
import json
from dataclasses import replace
from pathlib import Path
import shutil
import tempfile
from types import SimpleNamespace
from uuid import UUID

import pytest

import stm32_toolkit.diagnostic_workflows as workflow_module
from stm32_toolkit.diagnostics import (
    DiagnosticSession,
    DiagnosticStore,
    EvidenceAssessment,
    Hypothesis,
    ObservationPlan,
    ObservationStep,
    calculate_assessment_id,
    calculate_plan_digest,
    reduce_event,
)
from stm32_toolkit.evidence import EVIDENCE_CORRUPT, EvidenceIdentity, EvidenceValidationError
from stm32_toolkit.evidence.gc import get_root
from stm32_toolkit.evidence.store import EvidenceStore
from stm32_toolkit.paths import WorkspacePaths
from stm32_toolkit.project_model import ProjectManifestError
from stm32_toolkit.testing.model import (
    TestCaseResult as CaseResult,
    TestRunManifest as RunManifest,
    TestProtocolError as ProtocolError,
    create_inventory,
    host_target_device,
)
from stm32_toolkit.testing.publication import TestRunPublisher as Publisher

from stm32_toolkit.diagnostic_workflows import (
    DiagnosticWorkflowContext,
    diagnostic_begin,
    diagnostic_show,
    diagnostic_start,
)


PROJECT_ID = UUID("12345678-1234-5678-1234-567812345678")
UTC_0 = "2026-08-21T12:00:00.000000Z"
UTC_1 = "2026-08-21T12:00:01.000000Z"


@pytest.fixture
def task_tmp() -> Path:
    path = Path(tempfile.mkdtemp(prefix="stm32tk-0603-diagnostic-workflows-", dir=r"C:\tmp"))
    try:
        yield path
    finally:
        gc.collect()
        shutil.rmtree(path, ignore_errors=False)


def _project_manifest() -> dict[str, object]:
    return {
        "schemaVersion": 3,
        "logicalProjectId": str(PROJECT_ID),
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
                "environment": {"allow": [], "values": {}},
            },
        },
    }


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("ascii")).hexdigest()


def _make_run(
    tmp_path: Path,
    *,
    state: str = "failed",
    identity_project_id: str = str(PROJECT_ID),
    identity_workspace_id: str | None = None,
) -> tuple[DiagnosticWorkflowContext, object, WorkspacePaths]:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / ".stm32-project.json").write_text(
        json.dumps(_project_manifest()), encoding="utf-8"
    )
    data_root = tmp_path / "data"
    context = DiagnosticWorkflowContext(project_root, data_root, "toolkit-session")
    workspace = WorkspacePaths.from_roots(data_root, project_root, PROJECT_ID, context.session_id)
    workspace.ensure()
    evidence = EvidenceStore(workspace.workspace_root / "evidence")

    raw_events = project_root / "raw-events.xml"
    stdout = project_root / "stdout.txt"
    stderr = project_root / "stderr.txt"
    raw_events.write_bytes(b"<testsuite><testcase name='failed'/></testsuite>")
    stdout.write_bytes(b"Host output\n")
    stderr.write_bytes(b"Host failure\n")
    raw = evidence.ingest_file(raw_events, kind="test-events", media_type="application/xml")
    out = evidence.ingest_file(stdout, kind="test-stdout", media_type="text/plain; charset=utf-8")
    err = evidence.ingest_file(stderr, kind="test-stderr", media_type="text/plain; charset=utf-8")
    identity = EvidenceIdentity(
        workspace_id=identity_workspace_id or workspace.workspace_id,
        project_id=identity_project_id,
        session_id="failed-test-run-session",
        build_id=_digest("host-build"),
        elf_sha256=_digest("host-tests"),
        target_device=host_target_device(),
        input_snapshot_sha256=_digest("project-inputs"),
        git_commit="a" * 40,
        git_dirty=False,
    )
    case_state = "failed" if state == "failed" else "error" if state == "error" else "passed"
    message = "assertion failed" if state == "failed" else "error" if state == "error" else None
    case = CaseResult("case-1", case_state, UTC_0, UTC_1, 1000, message, None, None)
    manifest = RunManifest(
        "stm32-test/1",
        f"run-{state}",
        "host",
        state,
        identity,
        None,
        (case,),
        UTC_0,
        UTC_1,
        1000,
        out,
        err,
        raw,
    )
    inventory = create_inventory("host", identity, ("case-1",), UTC_0)
    published = Publisher(
        evidence, project_root, workspace.session_root / "test-results"
    ).publish_host(manifest, inventory_digest=inventory.inventory_digest)
    return context, published, workspace


def _fresh_context(context: DiagnosticWorkflowContext) -> DiagnosticWorkflowContext:
    return DiagnosticWorkflowContext(
        Path(context.project_root), Path(context.data_root), str(context.session_id)
    )


def _begin_plan_session(
    context: DiagnosticWorkflowContext,
    published: object,
    *,
    prefix: str,
) -> str:
    started = diagnostic_start(
        _fresh_context(context),
        operation_id=f"{prefix}-start",
        failed_test_run_id=published.manifest.run_id,
    )
    diagnostic_session_id = started.to_dict()["data"]["session"]["diagnostic_session_id"]
    begun = diagnostic_begin(
        _fresh_context(context),
        operation_id=f"{prefix}-begin",
        diagnostic_session_id=diagnostic_session_id,
        expected_revision=1,
    )
    assert begun.ok is True
    return diagnostic_session_id


def _failed_case_plan_steps() -> list[dict[str, object]]:
    return [
        {
            "step_id": "failed-state",
            "selector": {"kind": "case-state", "case_id": "case-1"},
            "expected_value": "failed",
            "purpose": "bind the failed case state",
        },
        {
            "step_id": "failed-count",
            "selector": {"kind": "case-count", "state": "failed"},
            "expected_value": 1,
            "purpose": "bind the failed case count",
        },
    ]


def _prepared_assessment_session(
    context: DiagnosticWorkflowContext,
    published: object,
    *,
    prefix: str,
) -> tuple[str, str, str, str]:
    diagnostic_session_id = _begin_plan_session(context, published, prefix=prefix)
    first_hypothesis = workflow_module.diagnostic_add_hypothesis(
        _fresh_context(context),
        operation_id=f"{prefix}-hypothesis-one",
        diagnostic_session_id=diagnostic_session_id,
        expected_revision=2,
        statement="the failed case is the primary defect",
    )
    second_hypothesis = workflow_module.diagnostic_add_hypothesis(
        _fresh_context(context),
        operation_id=f"{prefix}-hypothesis-two",
        diagnostic_session_id=diagnostic_session_id,
        expected_revision=3,
        statement="the failed case count is misleading",
    )
    plan = workflow_module.diagnostic_add_plan(
        _fresh_context(context),
        operation_id=f"{prefix}-plan-add",
        diagnostic_session_id=diagnostic_session_id,
        expected_revision=4,
        steps=_failed_case_plan_steps(),
    )
    plan_id = plan.to_dict()["data"]["observation_plan"]["plan_id"]
    executed = workflow_module.diagnostic_run_plan(
        _fresh_context(context),
        operation_id=f"{prefix}-plan-run",
        diagnostic_session_id=diagnostic_session_id,
        expected_revision=5,
        plan_id=plan_id,
    )
    assert executed.ok is True
    return (
        diagnostic_session_id,
        first_hypothesis.to_dict()["data"]["hypothesis"]["hypothesis_id"],
        second_hypothesis.to_dict()["data"]["hypothesis"]["hypothesis_id"],
        plan_id,
    )


def test_failed_host_run_start_show_begin_survives_fresh_workflow_objects(task_tmp: Path) -> None:
    context, published, _workspace = _make_run(task_tmp)

    started = diagnostic_start(
        _fresh_context(context),
        operation_id="start-investigation",
        failed_test_run_id=published.manifest.run_id,
    )
    assert started.ok is True
    assert started.operation == "diagnostic.start"
    assert set(started.to_dict()["data"]) == {"session"}
    first_session = started.to_dict()["data"]["session"]
    assert first_session["revision"] == 1
    assert first_session["state"] == "OPEN"
    assert first_session["failed_test_run_id"] == published.manifest.run_id
    assert first_session["failed_evidence_id"] == str(published.envelope.evidence_id)
    assert first_session["identity"] == published.manifest.identity.to_dict()
    diagnostic_session_id = first_session["diagnostic_session_id"]

    shown = diagnostic_show(
        _fresh_context(context), diagnostic_session_id=diagnostic_session_id
    )
    assert shown.ok is True
    assert shown.operation == "diagnostic.show"
    assert set(shown.to_dict()["data"]) == {"session", "authoritative"}
    assert shown.to_dict()["data"]["authoritative"] is True
    assert shown.to_dict()["data"]["session"] == first_session

    begun = diagnostic_begin(
        _fresh_context(context),
        operation_id="begin-investigation",
        diagnostic_session_id=diagnostic_session_id,
        expected_revision=1,
    )
    assert begun.ok is True
    assert begun.operation == "diagnostic.begin"
    assert set(begun.to_dict()["data"]) == {"session"}
    assert begun.to_dict()["data"]["session"]["revision"] == 2
    assert begun.to_dict()["data"]["session"]["state"] == "INVESTIGATING"

    reloaded = diagnostic_show(
        _fresh_context(context), diagnostic_session_id=diagnostic_session_id
    )
    assert reloaded.ok is True
    assert reloaded.to_dict()["data"]["session"] == begun.to_dict()["data"]["session"]


def test_investigating_session_adds_competing_hypotheses_in_event_order(
    task_tmp: Path,
) -> None:
    context, published, _workspace = _make_run(task_tmp)
    started = diagnostic_start(
        _fresh_context(context),
        operation_id="hypothesis-start",
        failed_test_run_id=published.manifest.run_id,
    )
    diagnostic_session_id = started.to_dict()["data"]["session"]["diagnostic_session_id"]
    diagnostic_begin(
        _fresh_context(context),
        operation_id="hypothesis-begin",
        diagnostic_session_id=diagnostic_session_id,
        expected_revision=1,
    )

    first = workflow_module.diagnostic_add_hypothesis(
        _fresh_context(context),
        operation_id="hypothesis-one",
        diagnostic_session_id=diagnostic_session_id,
        expected_revision=2,
        statement="the host build emits an incompatible object",
    )
    assert first.ok is True
    assert first.operation == "diagnostic.hypothesis.add"
    assert set(first.to_dict()["data"]) == {"session", "hypothesis"}
    first_hypothesis = first.to_dict()["data"]["hypothesis"]
    assert set(first_hypothesis) == {
        "hypothesis_id",
        "statement",
        "status",
        "confidence_basis",
        "supporting",
        "refuting",
    }
    assert first_hypothesis["statement"] == "the host build emits an incompatible object"
    assert first_hypothesis["status"] == "open"
    assert first_hypothesis["confidence_basis"] == "unrated"
    assert first_hypothesis["supporting"] == []
    assert first_hypothesis["refuting"] == []

    second = workflow_module.diagnostic_add_hypothesis(
        _fresh_context(context),
        operation_id="hypothesis-two",
        diagnostic_session_id=diagnostic_session_id,
        expected_revision=3,
        statement="the test selector observes the wrong case",
        actor="ai-client",
    )
    assert second.ok is True
    second_hypothesis = second.to_dict()["data"]["hypothesis"]
    assert second_hypothesis["statement"] == "the test selector observes the wrong case"
    assert second_hypothesis["hypothesis_id"] != first_hypothesis["hypothesis_id"]

    shown = diagnostic_show(
        _fresh_context(context), diagnostic_session_id=diagnostic_session_id
    )
    assert shown.ok is True
    session = shown.to_dict()["data"]["session"]
    assert session["revision"] == 4
    assert [item["hypothesis_id"] for item in session["hypotheses"]] == [
        first_hypothesis["hypothesis_id"],
        second_hypothesis["hypothesis_id"],
    ]


def test_investigating_session_assesses_two_executed_observations(
    task_tmp: Path,
) -> None:
    context, published, workspace = _make_run(task_tmp)
    diagnostic_session_id = _begin_plan_session(context, published, prefix="assess")
    first_hypothesis_result = workflow_module.diagnostic_add_hypothesis(
        _fresh_context(context),
        operation_id="assess-hypothesis-one",
        diagnostic_session_id=diagnostic_session_id,
        expected_revision=2,
        statement="the failed case is the primary defect",
    )
    second_hypothesis_result = workflow_module.diagnostic_add_hypothesis(
        _fresh_context(context),
        operation_id="assess-hypothesis-two",
        diagnostic_session_id=diagnostic_session_id,
        expected_revision=3,
        statement="the failed case count is misleading",
    )
    first_hypothesis_id = first_hypothesis_result.to_dict()["data"]["hypothesis"]["hypothesis_id"]
    second_hypothesis_id = second_hypothesis_result.to_dict()["data"]["hypothesis"]["hypothesis_id"]
    added_plan = workflow_module.diagnostic_add_plan(
        _fresh_context(context),
        operation_id="assess-plan-add",
        diagnostic_session_id=diagnostic_session_id,
        expected_revision=4,
        steps=_failed_case_plan_steps(),
    )
    plan_id = added_plan.to_dict()["data"]["observation_plan"]["plan_id"]
    executed = workflow_module.diagnostic_run_plan(
        _fresh_context(context),
        operation_id="assess-plan-run",
        diagnostic_session_id=diagnostic_session_id,
        expected_revision=5,
        plan_id=plan_id,
    )
    assert executed.ok is True

    supporting = workflow_module.diagnostic_assess_hypothesis(
        _fresh_context(context),
        operation_id="assess-supporting",
        diagnostic_session_id=diagnostic_session_id,
        expected_revision=6,
        hypothesis_id=first_hypothesis_id,
        plan_id=plan_id,
        step_id="failed-state",
        polarity="supports",
        rationale="the failed case directly supports this hypothesis",
    )
    assert supporting.ok is True
    assert supporting.operation == "diagnostic.hypothesis.assess"
    supporting_data = supporting.to_dict()["data"]
    assert set(supporting_data) == {"session", "assessment"}
    supporting_assessment = supporting_data["assessment"]
    assert set(supporting_assessment) == {
        "assessment_id",
        "hypothesis_id",
        "plan_id",
        "step_id",
        "evidence_id",
        "selector",
        "observed_value",
        "polarity",
        "rationale",
    }
    assert supporting_assessment["hypothesis_id"] == first_hypothesis_id
    assert supporting_assessment["plan_id"] == plan_id
    assert supporting_assessment["step_id"] == "failed-state"
    assert supporting_assessment["evidence_id"] == str(published.envelope.evidence_id)
    assert supporting_assessment["selector"] == {"kind": "case-state", "case_id": "case-1"}
    assert supporting_assessment["observed_value"] == "failed"
    assert supporting_assessment["polarity"] == "supports"
    assert supporting_assessment["rationale"] == "the failed case directly supports this hypothesis"
    assert supporting_assessment["assessment_id"] == calculate_assessment_id(
        {key: value for key, value in supporting_assessment.items() if key != "assessment_id"}
    )

    refuting = workflow_module.diagnostic_assess_hypothesis(
        _fresh_context(context),
        operation_id="assess-refuting",
        diagnostic_session_id=diagnostic_session_id,
        expected_revision=7,
        hypothesis_id=second_hypothesis_id,
        plan_id=plan_id,
        step_id="failed-count",
        polarity="refutes",
        rationale="the count contradicts this alternative hypothesis",
    )
    assert refuting.ok is True
    refuting_data = refuting.to_dict()["data"]
    refuting_assessment = refuting_data["assessment"]
    assert refuting_assessment["hypothesis_id"] == second_hypothesis_id
    assert refuting_assessment["step_id"] == "failed-count"
    assert refuting_assessment["selector"] == {"kind": "case-count", "state": "failed"}
    assert refuting_assessment["observed_value"] == 1
    assert refuting_assessment["polarity"] == "refutes"
    assert refuting_assessment["assessment_id"] == calculate_assessment_id(
        {key: value for key, value in refuting_assessment.items() if key != "assessment_id"}
    )
    assert refuting_data["session"]["revision"] == 8
    assert refuting_data["session"]["hypotheses"][0]["status"] == "open"
    assert refuting_data["session"]["hypotheses"][0]["confidence_basis"] == "unrated"
    assert refuting_data["session"]["hypotheses"][0]["supporting"] == [supporting_assessment]
    assert refuting_data["session"]["hypotheses"][0]["refuting"] == []
    assert refuting_data["session"]["hypotheses"][1]["supporting"] == []
    assert refuting_data["session"]["hypotheses"][1]["refuting"] == [refuting_assessment]

    event = json.loads(
        (
            workspace.diagnostics_root
            / "sessions"
            / diagnostic_session_id
            / "events"
            / "00000006.json"
        ).read_text(encoding="utf-8")
    )
    assert event["event_type"] == "hypothesis.assessed"
    assert event["payload"] == {
        "request": {
            "hypothesis_id": first_hypothesis_id,
            "plan_id": plan_id,
            "step_id": "failed-state",
            "polarity": "supports",
            "rationale": "the failed case directly supports this hypothesis",
        },
        "result": {"assessment": supporting_assessment},
    }

    reloaded = diagnostic_show(
        _fresh_context(context), diagnostic_session_id=diagnostic_session_id
    )
    assert reloaded.ok is True
    assert reloaded.to_dict()["data"]["session"] == refuting_data["session"]
    encoded = json.dumps(refuting_data, sort_keys=True)
    for forbidden in ('"event":', '"appended":', 'workspace_root', 'stdout', 'stderr', 'raw-events.xml'):
        assert forbidden not in encoded
    refuting_data["assessment"]["observed_value"] = "mutated"
    refuting_data["session"]["hypotheses"][0]["status"] = "resolved"
    assert refuting.to_dict()["data"]["assessment"]["observed_value"] == 1
    assert refuting.to_dict()["data"]["session"]["hypotheses"][0]["status"] == "open"


def test_assessment_retry_and_conflicting_intents_are_store_authoritative(
    task_tmp: Path,
) -> None:
    context, published, workspace = _make_run(task_tmp)
    diagnostic_session_id, first_hypothesis_id, second_hypothesis_id, plan_id = (
        _prepared_assessment_session(context, published, prefix="retry-assess")
    )
    first = workflow_module.diagnostic_assess_hypothesis(
        _fresh_context(context),
        operation_id="retry-assess-operation",
        diagnostic_session_id=diagnostic_session_id,
        expected_revision=6,
        hypothesis_id=first_hypothesis_id,
        plan_id=plan_id,
        step_id="failed-state",
        polarity="supports",
        rationale="the first observation is direct evidence",
    )
    assert first.ok is True
    first_assessment = first.to_dict()["data"]["assessment"]
    advanced = workflow_module.diagnostic_add_hypothesis(
        _fresh_context(context),
        operation_id="retry-assess-advance",
        diagnostic_session_id=diagnostic_session_id,
        expected_revision=7,
        statement="a later hypothesis does not rewrite observations",
    )
    retry = workflow_module.diagnostic_assess_hypothesis(
        _fresh_context(context),
        operation_id="retry-assess-operation",
        diagnostic_session_id=diagnostic_session_id,
        expected_revision=8,
        hypothesis_id=first_hypothesis_id,
        plan_id=plan_id,
        step_id="failed-state",
        polarity="supports",
        rationale="the first observation is direct evidence",
    )
    assert retry.ok is True
    assert retry.to_dict()["data"]["assessment"] == first_assessment
    assert retry.to_dict()["data"]["session"] == advanced.to_dict()["data"]["session"]

    events_dir = workspace.diagnostics_root / "sessions" / diagnostic_session_id / "events"
    before = sorted(path.name for path in events_dir.iterdir())
    conflicts = [
        {
            "hypothesis_id": second_hypothesis_id,
            "plan_id": plan_id,
            "step_id": "failed-count",
            "polarity": "supports",
            "rationale": "different reference intent",
            "actor": "user",
        },
        {
            "hypothesis_id": first_hypothesis_id,
            "plan_id": plan_id,
            "step_id": "failed-state",
            "polarity": "refutes",
            "rationale": "different polarity intent",
            "actor": "tool",
        },
        {
            "hypothesis_id": first_hypothesis_id,
            "plan_id": plan_id,
            "step_id": "failed-state",
            "polarity": "supports",
            "rationale": "different rationale intent",
            "actor": "user",
        },
    ]
    for index, candidate in enumerate(conflicts):
        conflict = workflow_module.diagnostic_assess_hypothesis(
            _fresh_context(context),
            operation_id="retry-assess-operation",
            diagnostic_session_id=diagnostic_session_id,
            expected_revision=8,
            **candidate,
        )
        assert conflict.ok is False
        assert conflict.code == "DIAGNOSTIC_OPERATION_CONFLICT", index
        assert sorted(path.name for path in events_dir.iterdir()) == before

    stale = workflow_module.diagnostic_assess_hypothesis(
        _fresh_context(context),
        operation_id="retry-assess-stale",
        diagnostic_session_id=diagnostic_session_id,
        expected_revision=7,
        hypothesis_id=second_hypothesis_id,
        plan_id=plan_id,
        step_id="failed-count",
        polarity="refutes",
        rationale="a stale caller cannot append",
    )
    assert stale.ok is False
    assert stale.code == "DIAGNOSTIC_REVISION_CONFLICT"
    assert sorted(path.name for path in events_dir.iterdir()) == before


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        pytest.param({"hypothesis_id": "f" * 32}, "DIAGNOSTIC_PLAN_INVALID", id="hypothesis"),
        pytest.param({"plan_id": "0" * 64}, "DIAGNOSTIC_PLAN_INVALID", id="plan"),
        pytest.param({"step_id": "missing-step"}, "DIAGNOSTIC_PLAN_INVALID", id="step"),
        pytest.param({"polarity": "neutral"}, "DIAGNOSTIC_PLAN_INVALID", id="polarity"),
        pytest.param({"rationale": ""}, "DIAGNOSTIC_INVALID_EVENT", id="empty-rationale"),
        pytest.param({"rationale": "x" * (64 * 1024 + 1)}, "DIAGNOSTIC_LIMIT_EXCEEDED", id="large-rationale"),
        pytest.param({"actor": "robot"}, "DIAGNOSTIC_INVALID_EVENT", id="actor"),
        pytest.param({"expected_revision": -1}, "DIAGNOSTIC_REVISION_CONFLICT", id="revision"),
    ],
)
def test_assessment_rejects_malformed_references_and_rationale_without_append(
    task_tmp: Path, overrides: dict[str, object], code: str
) -> None:
    context, published, workspace = _make_run(task_tmp)
    diagnostic_session_id, first_hypothesis_id, _second_hypothesis_id, plan_id = (
        _prepared_assessment_session(context, published, prefix="invalid-assess")
    )
    arguments: dict[str, object] = {
        "operation_id": "invalid-assess-operation",
        "diagnostic_session_id": diagnostic_session_id,
        "expected_revision": 6,
        "hypothesis_id": first_hypothesis_id,
        "plan_id": plan_id,
        "step_id": "failed-state",
        "polarity": "supports",
        "rationale": "a valid explicit rationale",
        "actor": "user",
    }
    arguments.update(overrides)
    events_dir = workspace.diagnostics_root / "sessions" / diagnostic_session_id / "events"
    before = sorted(path.name for path in events_dir.iterdir())
    result = workflow_module.diagnostic_assess_hypothesis(
        _fresh_context(context),
        operation_id=arguments["operation_id"],  # type: ignore[arg-type]
        diagnostic_session_id=arguments["diagnostic_session_id"],  # type: ignore[arg-type]
        expected_revision=arguments["expected_revision"],  # type: ignore[arg-type]
        hypothesis_id=arguments["hypothesis_id"],  # type: ignore[arg-type]
        plan_id=arguments["plan_id"],  # type: ignore[arg-type]
        step_id=arguments["step_id"],  # type: ignore[arg-type]
        polarity=arguments["polarity"],  # type: ignore[arg-type]
        rationale=arguments["rationale"],  # type: ignore[arg-type]
        actor=arguments["actor"],  # type: ignore[arg-type]
    )
    assert result.ok is False
    assert result.code == code
    assert result.details == {}
    assert sorted(path.name for path in events_dir.iterdir()) == before


def test_assessment_rejects_missing_entities_state_and_result_without_append(
    task_tmp: Path,
) -> None:
    context, published, workspace = _make_run(task_tmp)
    started = diagnostic_start(
        _fresh_context(context),
        operation_id="open-assess-start",
        failed_test_run_id=published.manifest.run_id,
    )
    open_session_id = started.to_dict()["data"]["session"]["diagnostic_session_id"]
    open_result = workflow_module.diagnostic_assess_hypothesis(
        _fresh_context(context),
        operation_id="open-assess-operation",
        diagnostic_session_id=open_session_id,
        expected_revision=1,
        hypothesis_id="0" * 32,
        plan_id="0" * 64,
        step_id="step",
        polarity="supports",
        rationale="state rejects this before entity resolution",
    )
    assert open_result.ok is False
    assert open_result.code == "DIAGNOSTIC_INVALID_TRANSITION"
    assert len(
        tuple((workspace.diagnostics_root / "sessions" / open_session_id / "events").iterdir())
    ) == 1

    absent = workflow_module.diagnostic_assess_hypothesis(
        _fresh_context(context),
        operation_id="absent-assess-operation",
        diagnostic_session_id="f" * 32,
        expected_revision=0,
        hypothesis_id="0" * 32,
        plan_id="0" * 64,
        step_id="step",
        polarity="supports",
        rationale="the session is absent",
    )
    assert absent.ok is False
    assert absent.code == "DIAGNOSTIC_NOT_FOUND"

    diagnostic_session_id = _begin_plan_session(context, published, prefix="missing-assess")
    hypothesis = workflow_module.diagnostic_add_hypothesis(
        _fresh_context(context),
        operation_id="missing-assess-hypothesis",
        diagnostic_session_id=diagnostic_session_id,
        expected_revision=2,
        statement="a hypothesis without an executed result",
    )
    hypothesis_id = hypothesis.to_dict()["data"]["hypothesis"]["hypothesis_id"]
    added_plan = workflow_module.diagnostic_add_plan(
        _fresh_context(context),
        operation_id="missing-assess-plan",
        diagnostic_session_id=diagnostic_session_id,
        expected_revision=3,
        steps=_failed_case_plan_steps(),
    )
    plan_id = added_plan.to_dict()["data"]["observation_plan"]["plan_id"]
    missing_result = workflow_module.diagnostic_assess_hypothesis(
        _fresh_context(context),
        operation_id="missing-assess-operation",
        diagnostic_session_id=diagnostic_session_id,
        expected_revision=4,
        hypothesis_id=hypothesis_id,
        plan_id=plan_id,
        step_id="failed-state",
        polarity="supports",
        rationale="the plan has not executed yet",
    )
    assert missing_result.ok is False
    assert missing_result.code == "DIAGNOSTIC_PLAN_INVALID"
    assert len(
        tuple(
            (workspace.diagnostics_root / "sessions" / diagnostic_session_id / "events").iterdir()
        )
    ) == 4

    prepared_id, prepared_hypothesis_id, _second_id, prepared_plan_id = _prepared_assessment_session(
        context, published, prefix="missing-assess-entity"
    )
    before = sorted(
        path.name
        for path in (workspace.diagnostics_root / "sessions" / prepared_id / "events").iterdir()
    )
    missing_hypothesis = workflow_module.diagnostic_assess_hypothesis(
        _fresh_context(context),
        operation_id="missing-assess-hypothesis-operation",
        diagnostic_session_id=prepared_id,
        expected_revision=6,
        hypothesis_id="f" * 32,
        plan_id=prepared_plan_id,
        step_id="failed-state",
        polarity="supports",
        rationale="the hypothesis does not exist",
    )
    assert missing_hypothesis.ok is False
    assert missing_hypothesis.code == "DIAGNOSTIC_PLAN_INVALID"
    missing_plan = workflow_module.diagnostic_assess_hypothesis(
        _fresh_context(context),
        operation_id="missing-assess-plan-operation",
        diagnostic_session_id=prepared_id,
        expected_revision=6,
        hypothesis_id=prepared_hypothesis_id,
        plan_id="0" * 64,
        step_id="failed-state",
        polarity="supports",
        rationale="the plan does not exist",
    )
    assert missing_plan.ok is False
    assert missing_plan.code == "DIAGNOSTIC_PLAN_INVALID"
    missing_step = workflow_module.diagnostic_assess_hypothesis(
        _fresh_context(context),
        operation_id="missing-assess-step-operation",
        diagnostic_session_id=prepared_id,
        expected_revision=6,
        hypothesis_id=prepared_hypothesis_id,
        plan_id=prepared_plan_id,
        step_id="missing-step",
        polarity="supports",
        rationale="the step does not exist",
    )
    assert missing_step.ok is False
    assert missing_step.code == "DIAGNOSTIC_PLAN_INVALID"
    assert sorted(
        path.name
        for path in (workspace.diagnostics_root / "sessions" / prepared_id / "events").iterdir()
    ) == before


def test_assessment_duplicate_and_opposite_side_reuse_are_domain_rejected(
    task_tmp: Path,
) -> None:
    context, published, workspace = _make_run(task_tmp)
    diagnostic_session_id, first_hypothesis_id, second_hypothesis_id, plan_id = (
        _prepared_assessment_session(context, published, prefix="duplicate-assess")
    )
    first = workflow_module.diagnostic_assess_hypothesis(
        _fresh_context(context),
        operation_id="duplicate-assess-first",
        diagnostic_session_id=diagnostic_session_id,
        expected_revision=6,
        hypothesis_id=first_hypothesis_id,
        plan_id=plan_id,
        step_id="failed-state",
        polarity="supports",
        rationale="one explicit support",
    )
    assert first.ok is True
    first_assessment = first.to_dict()["data"]["assessment"]
    events_dir = workspace.diagnostics_root / "sessions" / diagnostic_session_id / "events"
    before = sorted(path.name for path in events_dir.iterdir())

    duplicate = workflow_module.diagnostic_assess_hypothesis(
        _fresh_context(context),
        operation_id="duplicate-assess-second",
        diagnostic_session_id=diagnostic_session_id,
        expected_revision=7,
        hypothesis_id=first_hypothesis_id,
        plan_id=plan_id,
        step_id="failed-state",
        polarity="supports",
        rationale="one explicit support",
    )
    assert duplicate.ok is False
    assert duplicate.code == "DIAGNOSTIC_PLAN_INVALID"
    assert sorted(path.name for path in events_dir.iterdir()) == before

    opposite = workflow_module.diagnostic_assess_hypothesis(
        _fresh_context(context),
        operation_id="duplicate-assess-opposite",
        diagnostic_session_id=diagnostic_session_id,
        expected_revision=7,
        hypothesis_id=first_hypothesis_id,
        plan_id=plan_id,
        step_id="failed-state",
        polarity="refutes",
        rationale="the same observation refutes this hypothesis",
    )
    assert opposite.ok is False
    assert opposite.code == "DIAGNOSTIC_PLAN_INVALID"
    assert sorted(path.name for path in events_dir.iterdir()) == before

    other_hypothesis = workflow_module.diagnostic_assess_hypothesis(
        _fresh_context(context),
        operation_id="duplicate-assess-other-hypothesis",
        diagnostic_session_id=diagnostic_session_id,
        expected_revision=7,
        hypothesis_id=second_hypothesis_id,
        plan_id=plan_id,
        step_id="failed-state",
        polarity="refutes",
        rationale="the same evidence is judged against another hypothesis",
    )
    assert other_hypothesis.ok is True
    assert other_hypothesis.to_dict()["data"]["assessment"]["evidence_id"] == first_assessment["evidence_id"]
    assert other_hypothesis.to_dict()["data"]["session"]["revision"] == 8


def test_assessment_collection_limit_rejects_without_persistent_append(
    task_tmp: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context, published, workspace = _make_run(task_tmp)
    diagnostic_session_id, first_hypothesis_id, _second_id, plan_id = (
        _prepared_assessment_session(context, published, prefix="limit-assess")
    )
    stored = DiagnosticStore(
        workspace.diagnostics_root,
        EvidenceStore(workspace.workspace_root / "evidence"),
    ).load(diagnostic_session_id)
    plan = stored.observation_plans[0]
    observation = stored.observation_results[0]
    assessments = tuple(
        EvidenceAssessment.new(
            hypothesis_id=first_hypothesis_id,
            plan_id=plan_id,
            step_id=observation.step_id,
            evidence_id=observation.evidence_id,
            selector=observation.selector,
            observed_value=observation.observed_value,
            polarity="supports",
            rationale=f"bounded assessment {index}",
        )
        for index in range(1024)
    )
    bounded_hypothesis = Hypothesis(
        first_hypothesis_id,
        stored.hypotheses[0].statement,
        "open",
        "unrated",
        assessments,
        (),
    )
    bounded_session = DiagnosticSession(
        diagnostic_session_id=stored.diagnostic_session_id,
        revision=stored.revision,
        state=stored.state,
        identity=stored.identity,
        failed_test_run_id=stored.failed_test_run_id,
        failed_evidence_id=stored.failed_evidence_id,
        event_head=stored.event_head,
        hypotheses=(bounded_hypothesis, stored.hypotheses[1]),
        observation_plans=stored.observation_plans,
        observation_results=stored.observation_results,
    )

    class LimitedStore:
        def __init__(self, session: DiagnosticSession) -> None:
            self.session = session
            self.append_calls = 0

        def load(self, _session_id: str) -> DiagnosticSession:
            return self.session

        def append(self, _session_id: str, event: object, *, expected_revision: int) -> object:
            self.append_calls += 1
            return reduce_event(self.session, event)  # type: ignore[arg-type]

    limited_store = LimitedStore(bounded_session)
    monkeypatch.setattr(
        workflow_module,
        "_diagnostic_store_factory",
        lambda _root, _evidence: limited_store,
    )
    events_dir = workspace.diagnostics_root / "sessions" / diagnostic_session_id / "events"
    before = sorted(path.name for path in events_dir.iterdir())
    result = workflow_module.diagnostic_assess_hypothesis(
        _fresh_context(context),
        operation_id="limit-assess-operation",
        diagnostic_session_id=diagnostic_session_id,
        expected_revision=6,
        hypothesis_id=first_hypothesis_id,
        plan_id=plan_id,
        step_id=observation.step_id,
        polarity="supports",
        rationale="the additional assessment exceeds the collection limit",
    )
    assert result.ok is False
    assert result.code == "DIAGNOSTIC_LIMIT_EXCEEDED"
    assert result.details == {}
    assert limited_store.append_calls == 1
    assert sorted(path.name for path in events_dir.iterdir()) == before


def test_unexpected_assessment_store_failure_propagates(
    task_tmp: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context, published, workspace = _make_run(task_tmp)
    diagnostic_session_id, first_hypothesis_id, _second_id, plan_id = (
        _prepared_assessment_session(context, published, prefix="unexpected-assess-store")
    )
    stored = DiagnosticStore(
        workspace.diagnostics_root,
        EvidenceStore(workspace.workspace_root / "evidence"),
    ).load(diagnostic_session_id)

    class ExplodingStore:
        def load(self, _session_id: str) -> DiagnosticSession:
            return stored

        def append(self, *_args: object, **_kwargs: object) -> object:
            raise RuntimeError("unexpected assessment append failure")

    monkeypatch.setattr(
        workflow_module,
        "_diagnostic_store_factory",
        lambda _root, _evidence: ExplodingStore(),
    )
    with pytest.raises(RuntimeError, match="unexpected assessment append failure"):
        workflow_module.diagnostic_assess_hypothesis(
            _fresh_context(context),
            operation_id="unexpected-assess-operation",
            diagnostic_session_id=diagnostic_session_id,
            expected_revision=6,
            hypothesis_id=first_hypothesis_id,
            plan_id=plan_id,
            step_id="failed-state",
            polarity="supports",
            rationale="the store error must remain visible to programmers",
        )


def test_investigating_session_freezes_failed_run_observation_plan(
    task_tmp: Path,
) -> None:
    context, published, workspace = _make_run(task_tmp)
    started = diagnostic_start(
        _fresh_context(context),
        operation_id="plan-start",
        failed_test_run_id=published.manifest.run_id,
    )
    diagnostic_session_id = started.to_dict()["data"]["session"]["diagnostic_session_id"]
    diagnostic_begin(
        _fresh_context(context),
        operation_id="plan-begin",
        diagnostic_session_id=diagnostic_session_id,
        expected_revision=1,
    )
    result = workflow_module.diagnostic_add_plan(
        _fresh_context(context),
        operation_id="plan-add",
        diagnostic_session_id=diagnostic_session_id,
        expected_revision=2,
        steps=_failed_case_plan_steps(),
    )
    assert result.ok is True
    assert result.operation == "diagnostic.plan.add"
    public = result.to_dict()
    assert set(public["data"]) == {"session", "observation_plan"}
    plan = public["data"]["observation_plan"]
    assert set(plan) == {
        "plan_id",
        "diagnostic_session_id",
        "created_revision",
        "steps",
        "digest",
    }
    assert plan["diagnostic_session_id"] == diagnostic_session_id
    assert plan["created_revision"] == 3
    assert plan["steps"] == _failed_case_plan_steps()
    expected_digest = calculate_plan_digest(
        {
            "diagnostic_session_id": diagnostic_session_id,
            "created_revision": 3,
            "steps": _failed_case_plan_steps(),
        }
    )
    assert plan["plan_id"] == expected_digest
    assert plan["digest"] == expected_digest
    assert public["data"]["session"]["revision"] == 3
    assert public["data"]["session"]["observation_plans"] == [plan]
    event = json.loads(
        (
            workspace.diagnostics_root
            / "sessions"
            / diagnostic_session_id
            / "events"
            / "00000002.json"
        ).read_text(encoding="utf-8")
    )
    assert event["event_type"] == "observation.plan_added"
    assert event["payload"] == {
        "request": {"steps": _failed_case_plan_steps()},
        "result": {"observation_plan": plan},
    }

    encoded = json.dumps(public, sort_keys=True)
    assert '"event":' not in encoded
    assert '"appended":' not in encoded
    assert '"workspace_root":' not in encoded
    assert '"stdout":' not in encoded
    public["data"]["observation_plan"]["steps"][0]["purpose"] = "mutated"
    public["data"]["session"]["observation_plans"][0]["steps"][0]["purpose"] = "mutated"
    assert result.to_dict()["data"]["observation_plan"]["steps"][0]["purpose"] == "bind the failed case state"
    assert (
        result.to_dict()["data"]["session"]["observation_plans"][0]["steps"][0]["purpose"]
        == "bind the failed case state"
    )


def test_plan_resolves_run_state_and_does_not_compare_expected_value(
    task_tmp: Path,
) -> None:
    context, published, _workspace = _make_run(task_tmp)
    diagnostic_session_id = _begin_plan_session(context, published, prefix="run-state-plan")
    result = workflow_module.diagnostic_add_plan(
        _fresh_context(context),
        operation_id="run-state-plan-add",
        diagnostic_session_id=diagnostic_session_id,
        expected_revision=2,
        steps=[
            {
                "step_id": "run-state",
                "selector": {"kind": "run-state"},
                "expected_value": "passed",
                "purpose": "compare the original run state later",
            }
        ],
    )
    assert result.ok is True
    assert result.to_dict()["data"]["observation_plan"]["steps"][0]["expected_value"] == "passed"


def test_failed_run_observation_plan_executes_ordered_results(
    task_tmp: Path,
) -> None:
    context, published, workspace = _make_run(task_tmp)
    diagnostic_session_id = _begin_plan_session(context, published, prefix="run-plan")
    steps = _failed_case_plan_steps()
    steps[1] = {**steps[1], "expected_value": 2}
    added = workflow_module.diagnostic_add_plan(
        _fresh_context(context),
        operation_id="run-plan-add",
        diagnostic_session_id=diagnostic_session_id,
        expected_revision=2,
        steps=steps,
    )
    plan = added.to_dict()["data"]["observation_plan"]

    result = workflow_module.diagnostic_run_plan(
        _fresh_context(context),
        operation_id="run-plan-execute",
        diagnostic_session_id=diagnostic_session_id,
        expected_revision=3,
        plan_id=plan["plan_id"],
    )

    assert result.ok is True
    assert result.operation == "diagnostic.plan.run"
    public = result.to_dict()
    assert set(public["data"]) == {"session", "observation_results"}
    expected_results = [
        {
            "plan_id": plan["plan_id"],
            "step_id": "failed-state",
            "evidence_id": published.envelope.evidence_id,
            "selector": {"kind": "case-state", "case_id": "case-1"},
            "observed_value": "failed",
            "expected_value": "failed",
            "matched": True,
        },
        {
            "plan_id": plan["plan_id"],
            "step_id": "failed-count",
            "evidence_id": published.envelope.evidence_id,
            "selector": {"kind": "case-count", "state": "failed"},
            "observed_value": 1,
            "expected_value": 2,
            "matched": False,
        },
    ]
    assert public["data"]["observation_results"] == expected_results
    assert public["data"]["session"]["revision"] == 4
    assert public["data"]["session"]["observation_results"] == expected_results
    encoded = json.dumps(public, sort_keys=True)
    for forbidden in ('"event":', '"appended":', 'stdout', 'stderr', 'raw-events.xml', 'workspace_root'):
        assert forbidden not in encoded
    public["data"]["observation_results"][0]["observed_value"] = "mutated"
    public["data"]["session"]["observation_results"][0]["observed_value"] = "mutated"
    assert result.to_dict()["data"]["observation_results"] == expected_results
    assert result.to_dict()["data"]["session"]["observation_results"] == expected_results

    event = json.loads(
        (
            workspace.diagnostics_root
            / "sessions"
            / diagnostic_session_id
            / "events"
            / "00000003.json"
        ).read_text(encoding="utf-8")
    )
    assert event["event_type"] == "observation.plan_executed"
    assert event["payload"] == {
        "request": {"plan_id": plan["plan_id"]},
        "result": {"observation_results": expected_results},
    }

    reloaded = diagnostic_show(
        _fresh_context(context), diagnostic_session_id=diagnostic_session_id
    )
    assert reloaded.ok is True
    assert reloaded.to_dict()["data"]["session"]["observation_results"] == expected_results


def test_plan_run_resolves_run_state_and_copies_expected_value(
    task_tmp: Path,
) -> None:
    context, published, _workspace = _make_run(task_tmp)
    diagnostic_session_id = _begin_plan_session(context, published, prefix="run-state-execute")
    steps = [
        {
            "step_id": "run-state-step",
            "selector": {"kind": "run-state"},
            "expected_value": "passed",
            "purpose": "compare the run state",
        }
    ]
    added = workflow_module.diagnostic_add_plan(
        _fresh_context(context),
        operation_id="run-state-execute-add",
        diagnostic_session_id=diagnostic_session_id,
        expected_revision=2,
        steps=steps,
    )
    plan_id = added.to_dict()["data"]["observation_plan"]["plan_id"]

    result = workflow_module.diagnostic_run_plan(
        _fresh_context(context),
        operation_id="run-state-execute-run",
        diagnostic_session_id=diagnostic_session_id,
        expected_revision=3,
        plan_id=plan_id,
    )

    assert result.ok is True
    observation = result.to_dict()["data"]["observation_results"][0]
    assert observation["selector"] == {"kind": "run-state"}
    assert observation["observed_value"] == "failed"
    assert observation["expected_value"] == "passed"
    assert observation["matched"] is False


def test_plan_run_retry_is_authoritative_and_conflicts_do_not_append(
    task_tmp: Path,
) -> None:
    context, published, workspace = _make_run(task_tmp)
    diagnostic_session_id = _begin_plan_session(context, published, prefix="retry-run")
    added = workflow_module.diagnostic_add_plan(
        _fresh_context(context),
        operation_id="retry-run-add",
        diagnostic_session_id=diagnostic_session_id,
        expected_revision=2,
        steps=_failed_case_plan_steps(),
    )
    plan = added.to_dict()["data"]["observation_plan"]
    first = workflow_module.diagnostic_run_plan(
        _fresh_context(context),
        operation_id="retry-run-execute",
        diagnostic_session_id=diagnostic_session_id,
        expected_revision=3,
        plan_id=plan["plan_id"],
    )
    first_data = first.to_dict()["data"]
    advanced = workflow_module.diagnostic_add_hypothesis(
        _fresh_context(context),
        operation_id="retry-run-advance",
        diagnostic_session_id=diagnostic_session_id,
        expected_revision=4,
        statement="the failed result remains bound",
    )
    retry = workflow_module.diagnostic_run_plan(
        _fresh_context(context),
        operation_id="retry-run-execute",
        diagnostic_session_id=diagnostic_session_id,
        expected_revision=5,
        plan_id=plan["plan_id"],
    )
    assert retry.ok is True
    assert retry.to_dict()["data"]["observation_results"] == first_data["observation_results"]
    assert retry.to_dict()["data"]["session"] == advanced.to_dict()["data"]["session"]

    second_plan_steps = [
        {
            "step_id": "second-run-plan",
            "selector": {"kind": "run-state"},
            "expected_value": "failed",
            "purpose": "a distinct candidate plan",
        }
    ]
    second_plan = workflow_module.diagnostic_add_plan(
        _fresh_context(context),
        operation_id="retry-run-second-plan",
        diagnostic_session_id=diagnostic_session_id,
        expected_revision=5,
        steps=second_plan_steps,
    )
    second_plan_id = second_plan.to_dict()["data"]["observation_plan"]["plan_id"]
    events_dir = workspace.diagnostics_root / "sessions" / diagnostic_session_id / "events"
    before = sorted(path.name for path in events_dir.iterdir())

    conflict = workflow_module.diagnostic_run_plan(
        _fresh_context(context),
        operation_id="retry-run-execute",
        diagnostic_session_id=diagnostic_session_id,
        expected_revision=6,
        plan_id=second_plan_id,
    )
    assert conflict.ok is False
    assert conflict.code == "DIAGNOSTIC_OPERATION_CONFLICT"
    assert sorted(path.name for path in events_dir.iterdir()) == before

    actor_conflict = workflow_module.diagnostic_run_plan(
        _fresh_context(context),
        operation_id="retry-run-execute",
        diagnostic_session_id=diagnostic_session_id,
        expected_revision=6,
        plan_id=plan["plan_id"],
        actor="user",
    )
    assert actor_conflict.ok is False
    assert actor_conflict.code == "DIAGNOSTIC_OPERATION_CONFLICT"
    assert sorted(path.name for path in events_dir.iterdir()) == before

    repeated = workflow_module.diagnostic_run_plan(
        _fresh_context(context),
        operation_id="retry-run-second-execute",
        diagnostic_session_id=diagnostic_session_id,
        expected_revision=6,
        plan_id=plan["plan_id"],
    )
    assert repeated.ok is False
    assert repeated.code == "DIAGNOSTIC_PLAN_INVALID"
    assert sorted(path.name for path in events_dir.iterdir()) == before

    stale = workflow_module.diagnostic_run_plan(
        _fresh_context(context),
        operation_id="retry-run-stale-execute",
        diagnostic_session_id=diagnostic_session_id,
        expected_revision=5,
        plan_id=second_plan_id,
    )
    assert stale.ok is False
    assert stale.code == "DIAGNOSTIC_REVISION_CONFLICT"
    assert sorted(path.name for path in events_dir.iterdir()) == before

    shown = diagnostic_show(
        _fresh_context(context), diagnostic_session_id=diagnostic_session_id
    )
    assert shown.ok is True
    assert len(shown.to_dict()["data"]["session"]["observation_results"]) == 2


def test_plan_run_checkpoint_keeps_failed_evidence_parent(task_tmp: Path) -> None:
    context, published, workspace = _make_run(task_tmp)
    diagnostic_session_id = _begin_plan_session(context, published, prefix="checkpoint-run")
    added = workflow_module.diagnostic_add_plan(
        _fresh_context(context),
        operation_id="checkpoint-run-add",
        diagnostic_session_id=diagnostic_session_id,
        expected_revision=2,
        steps=_failed_case_plan_steps(),
    )
    plan_id = added.to_dict()["data"]["observation_plan"]["plan_id"]
    result = workflow_module.diagnostic_run_plan(
        _fresh_context(context),
        operation_id="checkpoint-run-execute",
        diagnostic_session_id=diagnostic_session_id,
        expected_revision=3,
        plan_id=plan_id,
    )
    assert result.ok is True

    root = get_root(
        EvidenceStore(workspace.workspace_root / "evidence"),
        "diagnostic-session",
        f"{diagnostic_session_id}.00000004",
    )
    envelope = EvidenceStore(workspace.workspace_root / "evidence").get_envelope(root.manifest_id)
    previous_root = get_root(
        EvidenceStore(workspace.workspace_root / "evidence"),
        "diagnostic-session",
        f"{diagnostic_session_id}.00000003",
    )
    assert envelope.parents == (previous_root.manifest_id, str(published.envelope.evidence_id))


@pytest.mark.parametrize(
    ("kwargs", "code"),
    [
        pytest.param({"plan_id": "not-a-plan"}, "DIAGNOSTIC_PLAN_INVALID", id="plan-id"),
        pytest.param({"actor": "robot"}, "DIAGNOSTIC_INVALID_EVENT", id="actor"),
        pytest.param({"expected_revision": -1}, "DIAGNOSTIC_REVISION_CONFLICT", id="revision"),
    ],
)
def test_plan_run_rejects_malformed_request_without_append(
    task_tmp: Path, kwargs: dict[str, object], code: str
) -> None:
    context, published, workspace = _make_run(task_tmp)
    diagnostic_session_id = _begin_plan_session(context, published, prefix="malformed-run")
    added = workflow_module.diagnostic_add_plan(
        _fresh_context(context),
        operation_id="malformed-run-add",
        diagnostic_session_id=diagnostic_session_id,
        expected_revision=2,
        steps=_failed_case_plan_steps(),
    )
    arguments: dict[str, object] = {
        "operation_id": "malformed-run-execute",
        "diagnostic_session_id": diagnostic_session_id,
        "expected_revision": 3,
        "plan_id": added.to_dict()["data"]["observation_plan"]["plan_id"],
        "actor": "tool",
    }
    arguments.update(kwargs)
    events_dir = workspace.diagnostics_root / "sessions" / diagnostic_session_id / "events"
    before = sorted(path.name for path in events_dir.iterdir())
    result = workflow_module.diagnostic_run_plan(
        _fresh_context(context),
        operation_id=arguments["operation_id"],  # type: ignore[arg-type]
        diagnostic_session_id=arguments["diagnostic_session_id"],  # type: ignore[arg-type]
        expected_revision=arguments["expected_revision"],  # type: ignore[arg-type]
        plan_id=arguments["plan_id"],  # type: ignore[arg-type]
        actor=arguments["actor"],  # type: ignore[arg-type]
    )
    assert result.ok is False
    assert result.code == code
    assert result.details == {}
    assert sorted(path.name for path in events_dir.iterdir()) == before


def test_plan_run_rejects_missing_plan_open_and_absent_sessions(
    task_tmp: Path,
) -> None:
    context, published, workspace = _make_run(task_tmp)
    started = diagnostic_start(
        _fresh_context(context),
        operation_id="missing-run-start",
        failed_test_run_id=published.manifest.run_id,
    )
    open_session_id = started.to_dict()["data"]["session"]["diagnostic_session_id"]
    open_result = workflow_module.diagnostic_run_plan(
        _fresh_context(context),
        operation_id="open-run-execute",
        diagnostic_session_id=open_session_id,
        expected_revision=1,
        plan_id="0" * 64,
    )
    assert open_result.ok is False
    assert open_result.code == "DIAGNOSTIC_INVALID_TRANSITION"
    assert len(
        tuple(
            (workspace.diagnostics_root / "sessions" / open_session_id / "events").iterdir()
        )
    ) == 1

    diagnostic_session_id = _begin_plan_session(context, published, prefix="missing-plan-run")
    missing_plan = workflow_module.diagnostic_run_plan(
        _fresh_context(context),
        operation_id="missing-plan-execute",
        diagnostic_session_id=diagnostic_session_id,
        expected_revision=2,
        plan_id="0" * 64,
    )
    assert missing_plan.ok is False
    assert missing_plan.code == "DIAGNOSTIC_PLAN_INVALID"
    assert len(
        tuple(
            (workspace.diagnostics_root / "sessions" / diagnostic_session_id / "events").iterdir()
        )
    ) == 2

    absent = workflow_module.diagnostic_run_plan(
        _fresh_context(context),
        operation_id="absent-run-execute",
        diagnostic_session_id="f" * 32,
        expected_revision=0,
        plan_id="0" * 64,
    )
    assert absent.ok is False
    assert absent.code == "DIAGNOSTIC_NOT_FOUND"


@pytest.mark.parametrize("failure", ["test-run", "evidence"])
def test_plan_run_maps_missing_or_damaged_test_run_to_evidence_missing(
    task_tmp: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    context, published, workspace = _make_run(task_tmp)
    diagnostic_session_id = _begin_plan_session(context, published, prefix=f"missing-run-{failure}")
    added = workflow_module.diagnostic_add_plan(
        _fresh_context(context),
        operation_id=f"missing-run-add-{failure}",
        diagnostic_session_id=diagnostic_session_id,
        expected_revision=2,
        steps=_failed_case_plan_steps(),
    )
    plan_id = added.to_dict()["data"]["observation_plan"]["plan_id"]

    class BrokenRepository:
        def load(self, _run_id: str) -> object:
            if failure == "test-run":
                raise ProtocolError("TEST_PROTOCOL_INVALID", "damaged test run")
            raise EvidenceValidationError(EVIDENCE_CORRUPT, "damaged evidence")

    monkeypatch.setattr(workflow_module, "_repository_factory", lambda _evidence: BrokenRepository())
    events_dir = workspace.diagnostics_root / "sessions" / diagnostic_session_id / "events"
    result = workflow_module.diagnostic_run_plan(
        _fresh_context(context),
        operation_id=f"missing-run-execute-{failure}",
        diagnostic_session_id=diagnostic_session_id,
        expected_revision=3,
        plan_id=plan_id,
    )
    assert result.ok is False
    assert result.code == "DIAGNOSTIC_EVIDENCE_MISSING"
    assert result.details == {}
    assert sorted(path.name for path in events_dir.iterdir()) == [
        "00000000.json",
        "00000001.json",
        "00000002.json",
    ]


def test_plan_run_rejects_changed_evidence_identity_and_selector_without_partial_event(
    task_tmp: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context, published, workspace = _make_run(task_tmp)
    diagnostic_session_id = _begin_plan_session(context, published, prefix="changed-run")
    added = workflow_module.diagnostic_add_plan(
        _fresh_context(context),
        operation_id="changed-run-add",
        diagnostic_session_id=diagnostic_session_id,
        expected_revision=2,
        steps=_failed_case_plan_steps(),
    )
    plan_id = added.to_dict()["data"]["observation_plan"]["plan_id"]
    events_dir = workspace.diagnostics_root / "sessions" / diagnostic_session_id / "events"
    before = sorted(path.name for path in events_dir.iterdir())

    class ChangedEvidenceRepository:
        def load(self, _run_id: str) -> object:
            return SimpleNamespace(
                manifest=published.manifest,
                envelope=SimpleNamespace(
                    evidence_id="f" * 64,
                    identity=published.envelope.identity,
                ),
            )

    monkeypatch.setattr(workflow_module, "_repository_factory", lambda _evidence: ChangedEvidenceRepository())
    changed_evidence = workflow_module.diagnostic_run_plan(
        _fresh_context(context),
        operation_id="changed-evidence-run",
        diagnostic_session_id=diagnostic_session_id,
        expected_revision=3,
        plan_id=plan_id,
    )
    assert changed_evidence.ok is False
    assert changed_evidence.code == "DIAGNOSTIC_IDENTITY_MISMATCH"
    assert sorted(path.name for path in events_dir.iterdir()) == before

    changed_identity = replace(published.manifest.identity, build_id="f" * 64)

    class ChangedIdentityRepository:
        def load(self, _run_id: str) -> object:
            return SimpleNamespace(
                manifest=replace(published.manifest, identity=changed_identity),
                envelope=SimpleNamespace(
                    evidence_id=str(published.envelope.evidence_id),
                    identity=changed_identity,
                ),
            )

    monkeypatch.setattr(workflow_module, "_repository_factory", lambda _evidence: ChangedIdentityRepository())
    changed_identity_result = workflow_module.diagnostic_run_plan(
        _fresh_context(context),
        operation_id="changed-identity-run",
        diagnostic_session_id=diagnostic_session_id,
        expected_revision=3,
        plan_id=plan_id,
    )
    assert changed_identity_result.ok is False
    assert changed_identity_result.code == "DIAGNOSTIC_IDENTITY_MISMATCH"
    assert sorted(path.name for path in events_dir.iterdir()) == before

    class MissingCaseRepository:
        def load(self, _run_id: str) -> object:
            return SimpleNamespace(
                manifest=SimpleNamespace(
                    mode="host",
                    state="failed",
                    identity=published.manifest.identity,
                    cases=(),
                ),
                envelope=published.envelope,
            )

    monkeypatch.setattr(workflow_module, "_repository_factory", lambda _evidence: MissingCaseRepository())
    missing_case = workflow_module.diagnostic_run_plan(
        _fresh_context(context),
        operation_id="missing-case-run",
        diagnostic_session_id=diagnostic_session_id,
        expected_revision=3,
        plan_id=plan_id,
    )
    assert missing_case.ok is False
    assert missing_case.code == "DIAGNOSTIC_PLAN_INVALID"
    assert sorted(path.name for path in events_dir.iterdir()) == before


def test_unexpected_plan_run_repository_failure_propagates(
    task_tmp: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context, published, _workspace = _make_run(task_tmp)
    diagnostic_session_id = _begin_plan_session(context, published, prefix="unexpected-run-load")
    added = workflow_module.diagnostic_add_plan(
        _fresh_context(context),
        operation_id="unexpected-run-load-add",
        diagnostic_session_id=diagnostic_session_id,
        expected_revision=2,
        steps=_failed_case_plan_steps(),
    )
    plan_id = added.to_dict()["data"]["observation_plan"]["plan_id"]

    class Repository:
        def __init__(self, _store: EvidenceStore) -> None:
            pass

        def load(self, _run_id: str) -> object:
            raise RuntimeError("unexpected plan run repository failure")

    monkeypatch.setattr(workflow_module, "_repository_factory", Repository)
    with pytest.raises(RuntimeError, match="unexpected plan run repository failure"):
        workflow_module.diagnostic_run_plan(
            _fresh_context(context),
            operation_id="unexpected-run-load-execute",
            diagnostic_session_id=diagnostic_session_id,
            expected_revision=3,
            plan_id=plan_id,
        )


def test_unexpected_plan_run_store_failure_propagates(
    task_tmp: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context, published, workspace = _make_run(task_tmp)
    diagnostic_session_id = _begin_plan_session(context, published, prefix="unexpected-run-store")
    added = workflow_module.diagnostic_add_plan(
        _fresh_context(context),
        operation_id="unexpected-run-store-add",
        diagnostic_session_id=diagnostic_session_id,
        expected_revision=2,
        steps=_failed_case_plan_steps(),
    )
    plan_id = added.to_dict()["data"]["observation_plan"]["plan_id"]
    stored = DiagnosticStore(
        workspace.diagnostics_root,
        EvidenceStore(workspace.workspace_root / "evidence"),
    ).load(diagnostic_session_id)

    class ExplodingStore:
        def load(self, _session_id: str) -> DiagnosticSession:
            return stored

        def append(self, *_args: object, **_kwargs: object) -> object:
            raise RuntimeError("unexpected plan run append failure")

    monkeypatch.setattr(
        workflow_module,
        "_diagnostic_store_factory",
        lambda _root, _evidence: ExplodingStore(),
    )
    with pytest.raises(RuntimeError, match="unexpected plan run append failure"):
        workflow_module.diagnostic_run_plan(
            _fresh_context(context),
            operation_id="unexpected-run-store-execute",
            diagnostic_session_id=diagnostic_session_id,
            expected_revision=3,
            plan_id=plan_id,
        )


def test_plan_retry_returns_accepted_plan_after_session_advances(
    task_tmp: Path,
) -> None:
    context, published, workspace = _make_run(task_tmp)
    diagnostic_session_id = _begin_plan_session(context, published, prefix="retry-plan")
    steps = _failed_case_plan_steps()
    first = workflow_module.diagnostic_add_plan(
        _fresh_context(context),
        operation_id="retry-plan-add",
        diagnostic_session_id=diagnostic_session_id,
        expected_revision=2,
        steps=steps,
    )
    first_plan = first.to_dict()["data"]["observation_plan"]
    advanced = workflow_module.diagnostic_add_hypothesis(
        _fresh_context(context),
        operation_id="retry-plan-advance",
        diagnostic_session_id=diagnostic_session_id,
        expected_revision=3,
        statement="the failed case remains the authoritative signal",
    )
    retry = workflow_module.diagnostic_add_plan(
        _fresh_context(context),
        operation_id="retry-plan-add",
        diagnostic_session_id=diagnostic_session_id,
        expected_revision=3,
        steps=steps,
    )
    assert retry.ok is True
    assert retry.to_dict()["data"]["observation_plan"] == first_plan
    assert retry.to_dict()["data"]["session"] == advanced.to_dict()["data"]["session"]

    conflicting_steps = [dict(item) for item in steps]
    conflicting_steps[0] = {**conflicting_steps[0], "purpose": "different intent"}
    conflict = workflow_module.diagnostic_add_plan(
        _fresh_context(context),
        operation_id="retry-plan-add",
        diagnostic_session_id=diagnostic_session_id,
        expected_revision=4,
        steps=conflicting_steps,
    )
    assert conflict.ok is False
    assert conflict.code == "DIAGNOSTIC_OPERATION_CONFLICT"
    actor_conflict = workflow_module.diagnostic_add_plan(
        _fresh_context(context),
        operation_id="retry-plan-add",
        diagnostic_session_id=diagnostic_session_id,
        expected_revision=4,
        steps=steps,
        actor="tool",
    )
    assert actor_conflict.ok is False
    assert actor_conflict.code == "DIAGNOSTIC_OPERATION_CONFLICT"

    before = sorted(
        path.name
        for path in (
            workspace.diagnostics_root / "sessions" / diagnostic_session_id / "events"
        ).iterdir()
    )
    stale = workflow_module.diagnostic_add_plan(
        _fresh_context(context),
        operation_id="retry-plan-stale",
        diagnostic_session_id=diagnostic_session_id,
        expected_revision=3,
        steps=steps,
    )
    assert stale.ok is False
    assert stale.code == "DIAGNOSTIC_REVISION_CONFLICT"
    assert sorted(
        path.name
        for path in (
            workspace.diagnostics_root / "sessions" / diagnostic_session_id / "events"
        ).iterdir()
    ) == before


@pytest.mark.parametrize(
    ("steps", "code"),
    [
        pytest.param([], "DIAGNOSTIC_PLAN_INVALID", id="empty"),
        pytest.param((), "DIAGNOSTIC_INVALID_EVENT", id="tuple"),
        pytest.param(
            [
                {
                    "step_id": "unknown-selector",
                    "selector": {"kind": "unknown"},
                    "expected_value": "failed",
                    "purpose": "invalid selector",
                }
            ],
            "DIAGNOSTIC_PLAN_INVALID",
            id="unknown-selector",
        ),
        pytest.param(
            [
                {
                    "step_id": "extra-selector",
                    "selector": {"kind": "run-state", "extra": True},
                    "expected_value": "failed",
                    "purpose": "extra selector field",
                }
            ],
            "DIAGNOSTIC_INVALID_EVENT",
            id="extra-selector-field",
        ),
        pytest.param(
            [
                {
                    "step_id": "extra-step",
                    "selector": {"kind": "run-state"},
                    "expected_value": "failed",
                    "purpose": "extra step field",
                    "unexpected": True,
                }
            ],
            "DIAGNOSTIC_INVALID_EVENT",
            id="extra-step-field",
        ),
        pytest.param(
            [
                {
                    "step_id": "duplicate",
                    "selector": {"kind": "run-state"},
                    "expected_value": "failed",
                    "purpose": "first duplicate",
                },
                {
                    "step_id": "duplicate",
                    "selector": {"kind": "case-count", "state": "failed"},
                    "expected_value": 1,
                    "purpose": "second duplicate",
                },
            ],
            "DIAGNOSTIC_PLAN_INVALID",
            id="duplicate-step",
        ),
        pytest.param(
            [
                {
                    "step_id": "missing-case",
                    "selector": {"kind": "case-state", "case_id": "missing"},
                    "expected_value": "failed",
                    "purpose": "missing case",
                }
            ],
            "DIAGNOSTIC_PLAN_INVALID",
            id="missing-case",
        ),
        pytest.param(
            [
                {
                    "step_id": "wrong-run-value",
                    "selector": {"kind": "run-state"},
                    "expected_value": 1,
                    "purpose": "wrong expected type",
                }
            ],
            "DIAGNOSTIC_PLAN_INVALID",
            id="wrong-run-value",
        ),
        pytest.param(
            [
                {
                    "step_id": "wrong-count-value",
                    "selector": {"kind": "case-count", "state": "failed"},
                    "expected_value": "1",
                    "purpose": "wrong expected type",
                }
            ],
            "DIAGNOSTIC_PLAN_INVALID",
            id="wrong-count-value",
        ),
    ],
)
def test_plan_rejects_invalid_steps_without_append(
    task_tmp: Path, steps: object, code: str
) -> None:
    context, published, workspace = _make_run(task_tmp)
    diagnostic_session_id = _begin_plan_session(context, published, prefix="invalid-plan")
    events_dir = workspace.diagnostics_root / "sessions" / diagnostic_session_id / "events"
    before = sorted(path.name for path in events_dir.iterdir())
    result = workflow_module.diagnostic_add_plan(
        _fresh_context(context),
        operation_id="invalid-plan-add",
        diagnostic_session_id=diagnostic_session_id,
        expected_revision=2,
        steps=steps,  # type: ignore[arg-type]
    )
    assert result.ok is False
    assert result.code == code
    assert result.details == {}
    assert sorted(path.name for path in events_dir.iterdir()) == before


def test_plan_rejects_more_than_64_steps_without_append(task_tmp: Path) -> None:
    context, published, workspace = _make_run(task_tmp)
    diagnostic_session_id = _begin_plan_session(context, published, prefix="step-limit-plan")
    steps = [
        {
            "step_id": f"step-{index}",
            "selector": {"kind": "run-state"},
            "expected_value": "failed",
            "purpose": "bounded plan step",
        }
        for index in range(65)
    ]
    result = workflow_module.diagnostic_add_plan(
        _fresh_context(context),
        operation_id="step-limit-plan-add",
        diagnostic_session_id=diagnostic_session_id,
        expected_revision=2,
        steps=steps,
    )
    assert result.ok is False
    assert result.code == "DIAGNOSTIC_LIMIT_EXCEEDED"
    assert len(
        tuple(
            (
                workspace.diagnostics_root
                / "sessions"
                / diagnostic_session_id
                / "events"
            ).iterdir()
        )
    ) == 2


@pytest.mark.parametrize("failure", ["test-run", "evidence"])
def test_plan_maps_missing_or_damaged_test_run_to_evidence_missing(
    task_tmp: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    context, published, workspace = _make_run(task_tmp)
    diagnostic_session_id = _begin_plan_session(context, published, prefix=f"missing-plan-{failure}")

    class BrokenRepository:
        def load(self, _run_id: str) -> object:
            if failure == "test-run":
                raise ProtocolError("TEST_PROTOCOL_INVALID", "damaged test run")
            raise EvidenceValidationError(EVIDENCE_CORRUPT, "damaged evidence")

    monkeypatch.setattr(workflow_module, "_repository_factory", lambda _evidence: BrokenRepository())
    events_dir = workspace.diagnostics_root / "sessions" / diagnostic_session_id / "events"
    result = workflow_module.diagnostic_add_plan(
        _fresh_context(context),
        operation_id=f"missing-plan-add-{failure}",
        diagnostic_session_id=diagnostic_session_id,
        expected_revision=2,
        steps=_failed_case_plan_steps(),
    )
    assert result.ok is False
    assert result.code == "DIAGNOSTIC_EVIDENCE_MISSING"
    assert result.details == {}
    assert sorted(path.name for path in events_dir.iterdir()) == [
        "00000000.json",
        "00000001.json",
    ]


def test_unexpected_plan_repository_failure_propagates(
    task_tmp: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context, published, _workspace = _make_run(task_tmp)
    diagnostic_session_id = _begin_plan_session(context, published, prefix="unexpected-load-plan")

    class Repository:
        def __init__(self, _store: EvidenceStore) -> None:
            pass

        def load(self, _run_id: str) -> object:
            raise RuntimeError("unexpected plan repository failure")

    monkeypatch.setattr(workflow_module, "_repository_factory", Repository)
    with pytest.raises(RuntimeError, match="unexpected plan repository failure"):
        workflow_module.diagnostic_add_plan(
            _fresh_context(context),
            operation_id="unexpected-load-plan-add",
            diagnostic_session_id=diagnostic_session_id,
            expected_revision=2,
            steps=_failed_case_plan_steps(),
        )


def test_plan_maps_changed_evidence_id_to_identity_mismatch(
    task_tmp: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context, published, workspace = _make_run(task_tmp)
    diagnostic_session_id = _begin_plan_session(context, published, prefix="changed-evidence-plan")

    class ChangedEvidenceRepository:
        def load(self, _run_id: str) -> object:
            return SimpleNamespace(
                manifest=published.manifest,
                envelope=SimpleNamespace(
                    evidence_id="f" * 64,
                    identity=published.envelope.identity,
                ),
            )

    monkeypatch.setattr(
        workflow_module,
        "_repository_factory",
        lambda _evidence: ChangedEvidenceRepository(),
    )
    result = workflow_module.diagnostic_add_plan(
        _fresh_context(context),
        operation_id="changed-evidence-plan-add",
        diagnostic_session_id=diagnostic_session_id,
        expected_revision=2,
        steps=_failed_case_plan_steps(),
    )
    assert result.ok is False
    assert result.code == "DIAGNOSTIC_IDENTITY_MISMATCH"
    assert result.details == {}
    assert len(
        tuple(
            (
                workspace.diagnostics_root
                / "sessions"
                / diagnostic_session_id
                / "events"
            ).iterdir()
        )
    ) == 2


def test_plan_maps_changed_test_run_identity_to_identity_mismatch(
    task_tmp: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context, published, workspace = _make_run(task_tmp)
    diagnostic_session_id = _begin_plan_session(context, published, prefix="changed-identity-plan")
    changed_identity = replace(published.manifest.identity, build_id="f" * 64)

    class ChangedIdentityRepository:
        def load(self, _run_id: str) -> object:
            return SimpleNamespace(
                manifest=replace(published.manifest, identity=changed_identity),
                envelope=SimpleNamespace(
                    evidence_id=str(published.envelope.evidence_id),
                    identity=changed_identity,
                ),
            )

    monkeypatch.setattr(
        workflow_module,
        "_repository_factory",
        lambda _evidence: ChangedIdentityRepository(),
    )
    result = workflow_module.diagnostic_add_plan(
        _fresh_context(context),
        operation_id="changed-identity-plan-add",
        diagnostic_session_id=diagnostic_session_id,
        expected_revision=2,
        steps=_failed_case_plan_steps(),
    )
    assert result.ok is False
    assert result.code == "DIAGNOSTIC_IDENTITY_MISMATCH"
    assert result.details == {}
    assert len(
        tuple(
            (
                workspace.diagnostics_root
                / "sessions"
                / diagnostic_session_id
                / "events"
            ).iterdir()
        )
    ) == 2


def test_plan_rejects_nonfailed_test_run_before_append(
    task_tmp: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context, published, workspace = _make_run(task_tmp)
    diagnostic_session_id = _begin_plan_session(context, published, prefix="wrong-state-plan")

    class WrongStateRepository:
        def load(self, _run_id: str) -> object:
            return SimpleNamespace(
                manifest=replace(published.manifest, mode="target"),
                envelope=published.envelope,
            )

    monkeypatch.setattr(
        workflow_module,
        "_repository_factory",
        lambda _evidence: WrongStateRepository(),
    )
    result = workflow_module.diagnostic_add_plan(
        _fresh_context(context),
        operation_id="wrong-state-plan-add",
        diagnostic_session_id=diagnostic_session_id,
        expected_revision=2,
        steps=_failed_case_plan_steps(),
    )
    assert result.ok is False
    assert result.code == "DIAGNOSTIC_INVALID_EVENT"
    assert len(
        tuple(
            (
                workspace.diagnostics_root
                / "sessions"
                / diagnostic_session_id
                / "events"
            ).iterdir()
        )
    ) == 2


def test_plan_rejects_open_session_without_append(task_tmp: Path) -> None:
    context, published, workspace = _make_run(task_tmp)
    started = diagnostic_start(
        _fresh_context(context),
        operation_id="open-plan-start",
        failed_test_run_id=published.manifest.run_id,
    )
    diagnostic_session_id = started.to_dict()["data"]["session"]["diagnostic_session_id"]
    result = workflow_module.diagnostic_add_plan(
        _fresh_context(context),
        operation_id="open-plan-add",
        diagnostic_session_id=diagnostic_session_id,
        expected_revision=1,
        steps=_failed_case_plan_steps(),
    )
    assert result.ok is False
    assert result.code == "DIAGNOSTIC_INVALID_TRANSITION"
    assert len(
        tuple(
            (
                workspace.diagnostics_root
                / "sessions"
                / diagnostic_session_id
                / "events"
            ).iterdir()
        )
    ) == 1


@pytest.mark.parametrize(
    ("kwargs", "code"),
    [
        pytest.param({"operation_id": "Bad"}, "DIAGNOSTIC_INVALID_EVENT", id="operation"),
        pytest.param({"actor": "robot"}, "DIAGNOSTIC_INVALID_EVENT", id="actor"),
        pytest.param({"expected_revision": -1}, "DIAGNOSTIC_REVISION_CONFLICT", id="revision"),
        pytest.param(
            {"diagnostic_session_id": "not-a-session"},
            "DIAGNOSTIC_INVALID_EVENT",
            id="session-id",
        ),
        pytest.param(
            {"diagnostic_session_id": "f" * 32},
            "DIAGNOSTIC_NOT_FOUND",
            id="missing-session",
        ),
    ],
)
def test_plan_rejects_malformed_public_inputs(
    task_tmp: Path, kwargs: dict[str, object], code: str
) -> None:
    context, published, _workspace = _make_run(task_tmp)
    diagnostic_session_id = _begin_plan_session(context, published, prefix="malformed-plan")
    arguments: dict[str, object] = {
        "operation_id": "valid-plan-add",
        "diagnostic_session_id": diagnostic_session_id,
        "expected_revision": 2,
        "steps": _failed_case_plan_steps(),
        "actor": "user",
    }
    arguments.update(kwargs)
    result = workflow_module.diagnostic_add_plan(
        _fresh_context(context),
        operation_id=arguments["operation_id"],  # type: ignore[arg-type]
        diagnostic_session_id=arguments["diagnostic_session_id"],  # type: ignore[arg-type]
        expected_revision=arguments["expected_revision"],  # type: ignore[arg-type]
        steps=arguments["steps"],  # type: ignore[arg-type]
        actor=arguments["actor"],  # type: ignore[arg-type]
    )
    assert result.ok is False
    assert result.code == code
    assert result.details == {}


def test_plan_collection_limit_rejects_65th_plan_without_persistent_append(
    task_tmp: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context, published, workspace = _make_run(task_tmp)
    diagnostic_session_id = _begin_plan_session(context, published, prefix="plan-limit")
    stored = DiagnosticStore(
        workspace.diagnostics_root,
        EvidenceStore(workspace.workspace_root / "evidence"),
    ).load(diagnostic_session_id)
    plans: list[ObservationPlan] = []
    for index in range(64):
        step = ObservationStep(
            f"bounded-{index}",
            {"kind": "run-state"},
            "failed",
            "bounded plan",
        )
        fields = {
            "diagnostic_session_id": diagnostic_session_id,
            "created_revision": index + 3,
            "steps": [step.to_dict()],
        }
        digest = calculate_plan_digest(fields)
        plans.append(
            ObservationPlan(
                digest,
                diagnostic_session_id,
                index + 3,
                (step,),
                digest,
            )
        )
    bounded_session = DiagnosticSession(
        diagnostic_session_id=stored.diagnostic_session_id,
        revision=stored.revision,
        state=stored.state,
        identity=stored.identity,
        failed_test_run_id=stored.failed_test_run_id,
        failed_evidence_id=stored.failed_evidence_id,
        event_head=stored.event_head,
        hypotheses=(),
        observation_plans=tuple(plans),
        observation_results=(),
    )

    class LimitedStore:
        def __init__(self, session: DiagnosticSession) -> None:
            self.session = session
            self.append_calls = 0

        def load(self, _session_id: str) -> DiagnosticSession:
            return self.session

        def append(self, _session_id: str, event: object, *, expected_revision: int) -> object:
            self.append_calls += 1
            return reduce_event(self.session, event)  # type: ignore[arg-type]

    limited_store = LimitedStore(bounded_session)
    monkeypatch.setattr(
        workflow_module,
        "_diagnostic_store_factory",
        lambda _root, _evidence: limited_store,
    )
    result = workflow_module.diagnostic_add_plan(
        _fresh_context(context),
        operation_id="plan-limit-add",
        diagnostic_session_id=diagnostic_session_id,
        expected_revision=2,
        steps=[
            {
                "step_id": "overflow",
                "selector": {"kind": "run-state"},
                "expected_value": "failed",
                "purpose": "overflow plan",
            }
        ],
    )
    assert result.ok is False
    assert result.code == "DIAGNOSTIC_LIMIT_EXCEEDED"
    assert result.details == {}
    assert limited_store.append_calls == 1
    assert len(bounded_session.observation_plans) == 64
    assert len(
        tuple(
            (
                workspace.diagnostics_root
                / "sessions"
                / diagnostic_session_id
                / "events"
            ).iterdir()
        )
    ) == 2


def test_unexpected_plan_append_failure_propagates(
    task_tmp: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context, published, workspace = _make_run(task_tmp)
    diagnostic_session_id = _begin_plan_session(context, published, prefix="unexpected-plan")
    stored = DiagnosticStore(
        workspace.diagnostics_root,
        EvidenceStore(workspace.workspace_root / "evidence"),
    ).load(diagnostic_session_id)

    class ExplodingStore:
        def load(self, _session_id: str) -> DiagnosticSession:
            return stored

        def append(self, *_args: object, **_kwargs: object) -> object:
            raise RuntimeError("unexpected plan append failure")

    monkeypatch.setattr(
        workflow_module,
        "_diagnostic_store_factory",
        lambda _root, _evidence: ExplodingStore(),
    )
    with pytest.raises(RuntimeError, match="unexpected plan append failure"):
        workflow_module.diagnostic_add_plan(
            _fresh_context(context),
            operation_id="unexpected-plan-add",
            diagnostic_session_id=diagnostic_session_id,
            expected_revision=2,
            steps=_failed_case_plan_steps(),
        )
    assert len(
        tuple(
            (
                workspace.diagnostics_root
                / "sessions"
                / diagnostic_session_id
                / "events"
            ).iterdir()
        )
    ) == 2


def test_hypothesis_retry_returns_accepted_event_after_session_advances(
    task_tmp: Path,
) -> None:
    context, published, workspace = _make_run(task_tmp)
    started = diagnostic_start(
        _fresh_context(context),
        operation_id="retry-hypothesis-start",
        failed_test_run_id=published.manifest.run_id,
    )
    diagnostic_session_id = started.to_dict()["data"]["session"]["diagnostic_session_id"]
    diagnostic_begin(
        _fresh_context(context),
        operation_id="retry-hypothesis-begin",
        diagnostic_session_id=diagnostic_session_id,
        expected_revision=1,
    )
    first = workflow_module.diagnostic_add_hypothesis(
        _fresh_context(context),
        operation_id="retry-hypothesis-one",
        diagnostic_session_id=diagnostic_session_id,
        expected_revision=2,
        statement="the linker output is incomplete",
    )
    first_hypothesis = first.to_dict()["data"]["hypothesis"]
    advanced = workflow_module.diagnostic_add_hypothesis(
        _fresh_context(context),
        operation_id="retry-hypothesis-two",
        diagnostic_session_id=diagnostic_session_id,
        expected_revision=3,
        statement="the case inventory is stale",
    )

    retry = workflow_module.diagnostic_add_hypothesis(
        _fresh_context(context),
        operation_id="retry-hypothesis-one",
        diagnostic_session_id=diagnostic_session_id,
        expected_revision=3,
        statement="the linker output is incomplete",
    )
    assert retry.ok is True
    assert retry.to_dict()["data"]["hypothesis"] == first_hypothesis
    assert retry.to_dict()["data"]["session"] == advanced.to_dict()["data"]["session"]

    conflicting_statement = workflow_module.diagnostic_add_hypothesis(
        _fresh_context(context),
        operation_id="retry-hypothesis-one",
        diagnostic_session_id=diagnostic_session_id,
        expected_revision=4,
        statement="a different explanation",
    )
    assert conflicting_statement.ok is False
    assert conflicting_statement.code == "DIAGNOSTIC_OPERATION_CONFLICT"
    conflicting_actor = workflow_module.diagnostic_add_hypothesis(
        _fresh_context(context),
        operation_id="retry-hypothesis-one",
        diagnostic_session_id=diagnostic_session_id,
        expected_revision=4,
        statement="the linker output is incomplete",
        actor="tool",
    )
    assert conflicting_actor.ok is False
    assert conflicting_actor.code == "DIAGNOSTIC_OPERATION_CONFLICT"

    events_dir = workspace.diagnostics_root / "sessions" / diagnostic_session_id / "events"
    assert sorted(path.name for path in events_dir.iterdir()) == [
        "00000000.json",
        "00000001.json",
        "00000002.json",
        "00000003.json",
    ]


def test_hypothesis_stale_revision_conflict_does_not_append(
    task_tmp: Path,
) -> None:
    context, published, workspace = _make_run(task_tmp)
    started = diagnostic_start(
        _fresh_context(context),
        operation_id="stale-hypothesis-start",
        failed_test_run_id=published.manifest.run_id,
    )
    diagnostic_session_id = started.to_dict()["data"]["session"]["diagnostic_session_id"]
    diagnostic_begin(
        _fresh_context(context),
        operation_id="stale-hypothesis-begin",
        diagnostic_session_id=diagnostic_session_id,
        expected_revision=1,
    )
    accepted = workflow_module.diagnostic_add_hypothesis(
        _fresh_context(context),
        operation_id="stale-hypothesis-accepted",
        diagnostic_session_id=diagnostic_session_id,
        expected_revision=2,
        statement="the linker output is incomplete",
    )
    assert accepted.ok is True

    events_dir = workspace.diagnostics_root / "sessions" / diagnostic_session_id / "events"
    before = sorted(path.name for path in events_dir.iterdir())
    stale = workflow_module.diagnostic_add_hypothesis(
        _fresh_context(context),
        operation_id="stale-hypothesis-different-operation",
        diagnostic_session_id=diagnostic_session_id,
        expected_revision=2,
        statement="the case inventory is stale",
    )
    assert stale.ok is False
    assert stale.code == "DIAGNOSTIC_REVISION_CONFLICT"
    assert stale.details == {}
    assert sorted(path.name for path in events_dir.iterdir()) == before


@pytest.mark.parametrize(
    ("statement", "code", "message"),
    [
        pytest.param(
            "", "DIAGNOSTIC_INVALID_EVENT", "event/model/operation intent is invalid", id="empty"
        ),
        pytest.param(
            123, "DIAGNOSTIC_INVALID_EVENT", "event/model/operation intent is invalid", id="non-string"
        ),
        pytest.param(
            "x" * (64 * 1024 + 1),
            "DIAGNOSTIC_LIMIT_EXCEEDED",
            "a diagnostic collection or byte limit is exceeded",
            id="over-limit",
        ),
    ],
)
def test_hypothesis_statement_limits_use_closed_failures(
    task_tmp: Path, statement: object, code: str, message: str
) -> None:
    context, published, _workspace = _make_run(task_tmp)
    started = diagnostic_start(
        _fresh_context(context),
        operation_id="statement-limit-start",
        failed_test_run_id=published.manifest.run_id,
    )
    diagnostic_session_id = started.to_dict()["data"]["session"]["diagnostic_session_id"]
    diagnostic_begin(
        _fresh_context(context),
        operation_id="statement-limit-begin",
        diagnostic_session_id=diagnostic_session_id,
        expected_revision=1,
    )

    result = workflow_module.diagnostic_add_hypothesis(
        _fresh_context(context),
        operation_id="statement-limit-add",
        diagnostic_session_id=diagnostic_session_id,
        expected_revision=2,
        statement=statement,  # type: ignore[arg-type]
    )

    assert result.ok is False
    assert result.code == code
    assert result.message == message
    assert result.details == {}
    public = json.dumps(result.to_dict(), sort_keys=True)
    assert "x" * 128 not in public
    shown = diagnostic_show(
        _fresh_context(context), diagnostic_session_id=diagnostic_session_id
    )
    assert shown.to_dict()["data"]["session"]["revision"] == 2
    assert shown.to_dict()["data"]["session"]["hypotheses"] == []


def test_hypothesis_requires_investigating_and_valid_request_shape(task_tmp: Path) -> None:
    context, published, _workspace = _make_run(task_tmp)
    started = diagnostic_start(
        _fresh_context(context),
        operation_id="validation-start",
        failed_test_run_id=published.manifest.run_id,
    )
    diagnostic_session_id = started.to_dict()["data"]["session"]["diagnostic_session_id"]

    open_result = workflow_module.diagnostic_add_hypothesis(
        _fresh_context(context),
        operation_id="open-hypothesis",
        diagnostic_session_id=diagnostic_session_id,
        expected_revision=1,
        statement="not yet investigating",
    )
    assert open_result.ok is False
    assert open_result.code == "DIAGNOSTIC_INVALID_TRANSITION"
    assert open_result.details == {}

    diagnostic_begin(
        _fresh_context(context),
        operation_id="validation-begin",
        diagnostic_session_id=diagnostic_session_id,
        expected_revision=1,
    )
    invalid_requests = [
        {
            "operation_id": "bad id",
            "diagnostic_session_id": diagnostic_session_id,
            "expected_revision": 2,
            "statement": "valid statement",
            "actor": "user",
            "code": "DIAGNOSTIC_INVALID_EVENT",
        },
        {
            "operation_id": "bad-actor",
            "diagnostic_session_id": diagnostic_session_id,
            "expected_revision": 2,
            "statement": "valid statement",
            "actor": "robot",
            "code": "DIAGNOSTIC_INVALID_EVENT",
        },
        {
            "operation_id": "bad-session",
            "diagnostic_session_id": "not-a-session",
            "expected_revision": 2,
            "statement": "valid statement",
            "actor": "user",
            "code": "DIAGNOSTIC_INVALID_EVENT",
        },
        {
            "operation_id": "bad-revision",
            "diagnostic_session_id": diagnostic_session_id,
            "expected_revision": -1,
            "statement": "valid statement",
            "actor": "user",
            "code": "DIAGNOSTIC_REVISION_CONFLICT",
        },
    ]
    for request in invalid_requests:
        result = workflow_module.diagnostic_add_hypothesis(
            _fresh_context(context),
            operation_id=request["operation_id"],
            diagnostic_session_id=request["diagnostic_session_id"],
            expected_revision=request["expected_revision"],
            statement=request["statement"],
            actor=request["actor"],
        )
        assert result.ok is False
        assert result.code == request["code"]
        assert result.details == {}

    shown = diagnostic_show(
        _fresh_context(context), diagnostic_session_id=diagnostic_session_id
    )
    assert shown.to_dict()["data"]["session"]["revision"] == 2
    assert shown.to_dict()["data"]["session"]["hypotheses"] == []


def test_hypothesis_rejects_wrong_session_and_identity_bindings(
    task_tmp: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context, published, workspace = _make_run(task_tmp)
    started = diagnostic_start(
        _fresh_context(context),
        operation_id="binding-start",
        failed_test_run_id=published.manifest.run_id,
    )
    diagnostic_session_id = started.to_dict()["data"]["session"]["diagnostic_session_id"]
    diagnostic_begin(
        _fresh_context(context),
        operation_id="binding-begin",
        diagnostic_session_id=diagnostic_session_id,
        expected_revision=1,
    )

    missing = workflow_module.diagnostic_add_hypothesis(
        _fresh_context(context),
        operation_id="missing-session",
        diagnostic_session_id="f" * 32,
        expected_revision=2,
        statement="missing session",
    )
    assert missing.ok is False
    assert missing.code == "DIAGNOSTIC_NOT_FOUND"

    wrong_model = SimpleNamespace(
        schema_version=3,
        logical_project_id=UUID("87654321-4321-8765-4321-876543218765"),
    )
    monkeypatch.setattr(workflow_module, "_load_project_model", lambda _root: wrong_model)
    monkeypatch.setattr(
        workflow_module,
        "_workspace_paths_factory",
        lambda *_args: workspace,
    )
    wrong_project = workflow_module.diagnostic_add_hypothesis(
        _fresh_context(context),
        operation_id="wrong-project",
        diagnostic_session_id=diagnostic_session_id,
        expected_revision=2,
        statement="wrong project",
    )
    assert wrong_project.ok is False
    assert wrong_project.code == "DIAGNOSTIC_IDENTITY_MISMATCH"

    monkeypatch.setattr(
        workflow_module,
        "_load_project_model",
        lambda _root: SimpleNamespace(schema_version=3, logical_project_id=PROJECT_ID),
    )
    monkeypatch.setattr(
        workflow_module,
        "_workspace_paths_factory",
        lambda *_args: replace(workspace, workspace_id="f" * 64),
    )
    wrong_workspace = workflow_module.diagnostic_add_hypothesis(
        _fresh_context(context),
        operation_id="wrong-workspace",
        diagnostic_session_id=diagnostic_session_id,
        expected_revision=2,
        statement="wrong workspace",
    )
    assert wrong_workspace.ok is False
    assert wrong_workspace.code == "DIAGNOSTIC_IDENTITY_MISMATCH"

    monkeypatch.undo()
    shown = diagnostic_show(
        _fresh_context(context), diagnostic_session_id=diagnostic_session_id
    )
    assert shown.to_dict()["data"]["session"]["revision"] == 2
    assert shown.to_dict()["data"]["session"]["hypotheses"] == []


def test_hypothesis_result_is_closed_json_snapshot(task_tmp: Path) -> None:
    context, published, _workspace = _make_run(task_tmp)
    started = diagnostic_start(
        _fresh_context(context),
        operation_id="snapshot-hypothesis-start",
        failed_test_run_id=published.manifest.run_id,
    )
    diagnostic_session_id = started.to_dict()["data"]["session"]["diagnostic_session_id"]
    diagnostic_begin(
        _fresh_context(context),
        operation_id="snapshot-hypothesis-begin",
        diagnostic_session_id=diagnostic_session_id,
        expected_revision=1,
    )
    result = workflow_module.diagnostic_add_hypothesis(
        _fresh_context(context),
        operation_id="snapshot-hypothesis-add",
        diagnostic_session_id=diagnostic_session_id,
        expected_revision=2,
        statement="the test command selected an old binary",
    )

    encoded = json.dumps(result.to_dict(), sort_keys=True)
    assert '"event":' not in encoded
    assert '"appended":' not in encoded
    assert '"workspace_root":' not in encoded
    assert '"stdout":' not in encoded
    public = result.to_dict()
    public["data"]["hypothesis"]["statement"] = "mutated"
    public["data"]["session"]["hypotheses"][0]["statement"] = "mutated"
    assert result.to_dict()["data"]["hypothesis"]["statement"] == "the test command selected an old binary"
    assert result.to_dict()["data"]["session"]["hypotheses"][0]["statement"] == "the test command selected an old binary"


def test_hypothesis_collection_limit_rejects_257th_without_append(
    task_tmp: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context, published, workspace = _make_run(task_tmp)
    started = diagnostic_start(
        _fresh_context(context),
        operation_id="limit-hypothesis-start",
        failed_test_run_id=published.manifest.run_id,
    )
    diagnostic_session_id = started.to_dict()["data"]["session"]["diagnostic_session_id"]
    diagnostic_begin(
        _fresh_context(context),
        operation_id="limit-hypothesis-begin",
        diagnostic_session_id=diagnostic_session_id,
        expected_revision=1,
    )

    stored = DiagnosticStore(
        workspace.diagnostics_root,
        EvidenceStore(workspace.workspace_root / "evidence"),
    ).load(diagnostic_session_id)
    full_hypotheses = tuple(
        Hypothesis(f"{index:032x}", f"bounded hypothesis {index}", "open", "unrated", (), ())
        for index in range(256)
    )
    bounded_session = DiagnosticSession(
        diagnostic_session_id=stored.diagnostic_session_id,
        revision=stored.revision,
        state=stored.state,
        identity=stored.identity,
        failed_test_run_id=stored.failed_test_run_id,
        failed_evidence_id=stored.failed_evidence_id,
        event_head=stored.event_head,
        hypotheses=full_hypotheses,
        observation_plans=(),
        observation_results=(),
    )

    class LimitedStore:
        def __init__(self, session: DiagnosticSession) -> None:
            self.session = session
            self.append_calls = 0

        def load(self, _session_id: str) -> DiagnosticSession:
            return self.session

        def append(self, _session_id: str, event: object, *, expected_revision: int) -> object:
            self.append_calls += 1
            return reduce_event(self.session, event)  # type: ignore[arg-type]

    limited_store = LimitedStore(bounded_session)
    monkeypatch.setattr(
        workflow_module,
        "_diagnostic_store_factory",
        lambda _root, _evidence: limited_store,
    )

    rejected = workflow_module.diagnostic_add_hypothesis(
        _fresh_context(context),
        operation_id="limit-hypothesis-256",
        diagnostic_session_id=diagnostic_session_id,
        expected_revision=258,
        statement="the 257th hypothesis must not be stored",
    )
    assert rejected.ok is False
    assert rejected.code == "DIAGNOSTIC_LIMIT_EXCEEDED"
    assert rejected.details == {}
    assert limited_store.append_calls == 1
    assert len(bounded_session.hypotheses) == 256
    events_dir = workspace.diagnostics_root / "sessions" / diagnostic_session_id / "events"
    assert len(tuple(events_dir.iterdir())) == 2


def test_unexpected_hypothesis_append_failure_is_not_remapped(
    task_tmp: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context, published, workspace = _make_run(task_tmp)
    started = diagnostic_start(
        _fresh_context(context),
        operation_id="unexpected-hypothesis-start",
        failed_test_run_id=published.manifest.run_id,
    )
    diagnostic_session_id = started.to_dict()["data"]["session"]["diagnostic_session_id"]
    diagnostic_begin(
        _fresh_context(context),
        operation_id="unexpected-hypothesis-begin",
        diagnostic_session_id=diagnostic_session_id,
        expected_revision=1,
    )

    class ExplodingStore:
        def __init__(self, root: Path, evidence: EvidenceStore) -> None:
            self.delegate = DiagnosticStore(root, evidence)

        def load(self, session_id: str) -> DiagnosticSession:
            return self.delegate.load(session_id)

        def append(self, *_args: object, **_kwargs: object) -> object:
            raise RuntimeError("unexpected append failure")

    monkeypatch.setattr(workflow_module, "_diagnostic_store_factory", ExplodingStore)
    with pytest.raises(RuntimeError, match="unexpected append failure"):
        workflow_module.diagnostic_add_hypothesis(
            _fresh_context(context),
            operation_id="unexpected-hypothesis-add",
            diagnostic_session_id=diagnostic_session_id,
            expected_revision=2,
            statement="this error must propagate",
        )
    events_dir = workspace.diagnostics_root / "sessions" / diagnostic_session_id / "events"
    assert len(tuple(events_dir.iterdir())) == 2


def test_start_and_begin_retries_are_store_authoritative(task_tmp: Path) -> None:
    context, published, workspace = _make_run(task_tmp)
    first = diagnostic_start(
        _fresh_context(context),
        operation_id="retry-start",
        failed_test_run_id=published.manifest.run_id,
    )
    diagnostic_session_id = first.to_dict()["data"]["session"]["diagnostic_session_id"]
    begun = diagnostic_begin(
        _fresh_context(context),
        operation_id="retry-begin",
        diagnostic_session_id=diagnostic_session_id,
        expected_revision=1,
    )

    start_retry = diagnostic_start(
        _fresh_context(context),
        operation_id="retry-start",
        failed_test_run_id=published.manifest.run_id,
    )
    assert start_retry.ok is True
    assert start_retry.to_dict()["data"]["session"] == begun.to_dict()["data"]["session"]

    begin_retry = diagnostic_begin(
        _fresh_context(context),
        operation_id="retry-begin",
        diagnostic_session_id=diagnostic_session_id,
        expected_revision=1,
    )
    assert begin_retry.ok is True
    assert begin_retry.to_dict()["data"]["session"] == begun.to_dict()["data"]["session"]

    conflicting_start = diagnostic_start(
        _fresh_context(context),
        operation_id="retry-start",
        failed_test_run_id=published.manifest.run_id,
        actor="tool",
    )
    assert conflicting_start.ok is False
    assert conflicting_start.code == "DIAGNOSTIC_OPERATION_CONFLICT"

    conflicting_begin = diagnostic_begin(
        _fresh_context(context),
        operation_id="retry-begin",
        diagnostic_session_id=diagnostic_session_id,
        expected_revision=1,
        actor="tool",
    )
    assert conflicting_begin.ok is False
    assert conflicting_begin.code == "DIAGNOSTIC_OPERATION_CONFLICT"

    stale = diagnostic_begin(
        _fresh_context(context),
        operation_id="different-begin",
        diagnostic_session_id=diagnostic_session_id,
        expected_revision=1,
    )
    assert stale.ok is False
    assert stale.code == "DIAGNOSTIC_REVISION_CONFLICT"
    invalid_transition = diagnostic_begin(
        _fresh_context(context),
        operation_id="invalid-transition",
        diagnostic_session_id=diagnostic_session_id,
        expected_revision=2,
    )
    assert invalid_transition.ok is False
    assert invalid_transition.code == "DIAGNOSTIC_INVALID_TRANSITION"
    events_dir = workspace.diagnostics_root / "sessions" / diagnostic_session_id / "events"
    assert sorted(path.name for path in events_dir.iterdir()) == [
        "00000000.json",
        "00000001.json",
    ]


@pytest.mark.parametrize("state", ["passed", "error"])
def test_start_rejects_nonfailed_terminal_host_runs_without_diagnostic_event(
    task_tmp: Path, state: str
) -> None:
    context, published, workspace = _make_run(task_tmp, state=state)

    result = diagnostic_start(
        _fresh_context(context),
        operation_id=f"reject-{state}",
        failed_test_run_id=published.manifest.run_id,
    )

    assert result.ok is False
    assert result.code == "DIAGNOSTIC_INVALID_EVENT"
    sessions = workspace.diagnostics_root / "sessions"
    assert not sessions.exists() or not any(sessions.rglob("*.json"))


@pytest.mark.parametrize("damage", ["missing", "corrupt"])
def test_start_projects_missing_or_corrupt_test_run_to_evidence_missing(
    task_tmp: Path, damage: str
) -> None:
    context, published, workspace = _make_run(task_tmp)
    root_path = next((workspace.workspace_root / "evidence" / "roots" / "test-run").glob("*.json"))
    if damage == "missing":
        root_path.unlink()
    else:
        root_path.write_bytes(b"not-json")

    result = diagnostic_start(
        _fresh_context(context),
        operation_id=f"missing-{damage}",
        failed_test_run_id=published.manifest.run_id,
    )

    assert result.ok is False
    assert result.code == "DIAGNOSTIC_EVIDENCE_MISSING"
    sessions = workspace.diagnostics_root / "sessions"
    assert not sessions.exists() or not any(sessions.rglob("*.json"))


@pytest.mark.parametrize("damage", ["envelope", "artifact"])
def test_start_projects_missing_test_run_objects_to_evidence_missing(
    task_tmp: Path, damage: str
) -> None:
    context, published, workspace = _make_run(task_tmp)
    evidence_root = workspace.workspace_root / "evidence"
    if damage == "envelope":
        (evidence_root / "manifests" / f"{published.envelope.evidence_id}.json").unlink()
    else:
        artifact_path = evidence_root.joinpath(*published.manifest_artifact.relative_path.split("/"))
        artifact_path.unlink()

    result = diagnostic_start(
        _fresh_context(context),
        operation_id=f"missing-object-{damage}",
        failed_test_run_id=published.manifest.run_id,
    )

    assert result.ok is False
    assert result.code == "DIAGNOSTIC_EVIDENCE_MISSING"
    sessions = workspace.diagnostics_root / "sessions"
    assert not sessions.exists() or not any(sessions.rglob("*.json"))


@pytest.mark.parametrize(
    ("identity_project_id", "identity_workspace_id"),
    [("87654321-4321-8765-4321-876543218765", None), (str(PROJECT_ID), "f" * 64)],
)
def test_start_rejects_project_or_workspace_identity_mismatch(
    task_tmp: Path, identity_project_id: str, identity_workspace_id: str | None
) -> None:
    context, published, workspace = _make_run(
        task_tmp,
        identity_project_id=identity_project_id,
        identity_workspace_id=identity_workspace_id,
    )

    result = diagnostic_start(
        _fresh_context(context),
        operation_id="wrong-identity",
        failed_test_run_id=published.manifest.run_id,
    )

    assert result.ok is False
    assert result.code == "DIAGNOSTIC_IDENTITY_MISMATCH"
    sessions = workspace.diagnostics_root / "sessions"
    assert not sessions.exists() or not any(sessions.rglob("*.json"))


def test_later_toolkit_session_can_reload_and_begin_same_workspace(task_tmp: Path) -> None:
    context, published, _workspace = _make_run(task_tmp)
    started = diagnostic_start(
        _fresh_context(context),
        operation_id="later-session-start",
        failed_test_run_id=published.manifest.run_id,
    )
    diagnostic_session_id = started.to_dict()["data"]["session"]["diagnostic_session_id"]
    later_context = DiagnosticWorkflowContext(
        context.project_root, context.data_root, "later-toolkit-session"
    )

    shown = diagnostic_show(later_context, diagnostic_session_id=diagnostic_session_id)
    assert shown.ok is True
    assert shown.to_dict()["data"]["authoritative"] is True
    begun = diagnostic_begin(
        later_context,
        operation_id="later-session-begin",
        diagnostic_session_id=diagnostic_session_id,
        expected_revision=1,
    )
    assert begun.ok is True
    assert begun.to_dict()["data"]["session"]["state"] == "INVESTIGATING"


def test_invalid_context_ids_actor_and_revision_use_closed_diagnostic_failures(
    task_tmp: Path,
) -> None:
    context, published, _workspace = _make_run(task_tmp)
    assert diagnostic_start(
        _fresh_context(context), operation_id="bad id", failed_test_run_id=published.manifest.run_id
    ).code == "DIAGNOSTIC_INVALID_EVENT"
    assert diagnostic_start(
        _fresh_context(context), operation_id="bad-actor", failed_test_run_id=published.manifest.run_id, actor="robot"
    ).code == "DIAGNOSTIC_INVALID_EVENT"
    assert diagnostic_start(
        _fresh_context(context), operation_id="bad-run", failed_test_run_id="../outside"
    ).code == "DIAGNOSTIC_INVALID_EVENT"
    assert diagnostic_show(
        _fresh_context(context), diagnostic_session_id="not-a-diagnostic-session"
    ).code == "DIAGNOSTIC_INVALID_EVENT"
    assert diagnostic_begin(
        _fresh_context(context),
        operation_id="bad-revision",
        diagnostic_session_id="f" * 32,
        expected_revision=-1,
    ).code == "DIAGNOSTIC_REVISION_CONFLICT"
    assert diagnostic_begin(
        _fresh_context(context),
        operation_id="bad-context",
        diagnostic_session_id="f" * 32,
        expected_revision=1,
        actor="robot",
    ).code == "DIAGNOSTIC_INVALID_EVENT"
    malformed = DiagnosticWorkflowContext("not-a-path", context.data_root, context.session_id)  # type: ignore[arg-type]
    assert diagnostic_show(malformed, diagnostic_session_id="f" * 32).code == "DIAGNOSTIC_IDENTITY_MISMATCH"


def test_workflow_results_are_closed_json_snapshots(task_tmp: Path) -> None:
    context, published, _workspace = _make_run(task_tmp)
    result = diagnostic_start(
        _fresh_context(context),
        operation_id="snapshot-start",
        failed_test_run_id=published.manifest.run_id,
    )
    encoded = json.dumps(result.to_dict(), sort_keys=True)
    assert "diagnostics" not in encoded
    public = result.to_dict()
    public["data"]["session"]["state"] = "MUTATED"
    assert result.to_dict()["data"]["session"]["state"] == "OPEN"


@pytest.mark.parametrize(
    "failure",
    [
        EvidenceValidationError(EVIDENCE_CORRUPT, "damaged"),
        ProtocolError("TEST_PROTOCOL_INVALID", "malformed"),
        OSError("unavailable"),
        TypeError("wrong type"),
    ],
)
def test_start_projects_typed_repository_load_failures(
    task_tmp: Path, monkeypatch: pytest.MonkeyPatch, failure: BaseException
) -> None:
    context, published, _workspace = _make_run(task_tmp)

    class Repository:
        def __init__(self, _store: EvidenceStore) -> None:
            pass

        def load(self, _run_id: str) -> object:
            raise failure

    monkeypatch.setattr(workflow_module, "_repository_factory", Repository)
    result = workflow_module.diagnostic_start(
        _fresh_context(context),
        operation_id="typed-load-failure",
        failed_test_run_id=published.manifest.run_id,
    )

    assert result.ok is False
    assert result.code == "DIAGNOSTIC_EVIDENCE_MISSING"
    assert result.details == {}
    assert result.message == "required TestRun evidence is absent or damaged"


def test_unexpected_repository_programmer_failure_is_not_remapped(
    task_tmp: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context, published, _workspace = _make_run(task_tmp)

    class Repository:
        def __init__(self, _store: EvidenceStore) -> None:
            pass

        def load(self, _run_id: str) -> object:
            raise RuntimeError("programmer failure")

    monkeypatch.setattr(workflow_module, "_repository_factory", Repository)
    with pytest.raises(RuntimeError, match="programmer failure"):
        workflow_module.diagnostic_start(
            _fresh_context(context),
            operation_id="unexpected-load-failure",
            failed_test_run_id=published.manifest.run_id,
        )


def test_start_rejects_wrong_mode_before_store_create(
    task_tmp: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context, published, workspace = _make_run(task_tmp)

    class Repository:
        def __init__(self, _store: EvidenceStore) -> None:
            pass

        def load(self, _run_id: str) -> object:
            return SimpleNamespace(
                manifest=SimpleNamespace(
                    mode="target", state="failed", identity=published.manifest.identity
                ),
                envelope=published.envelope,
            )

    monkeypatch.setattr(workflow_module, "_repository_factory", Repository)
    result = workflow_module.diagnostic_start(
        _fresh_context(context),
        operation_id="wrong-mode",
        failed_test_run_id=published.manifest.run_id,
    )

    assert result.ok is False
    assert result.code == "DIAGNOSTIC_INVALID_EVENT"
    sessions = workspace.diagnostics_root / "sessions"
    assert not sessions.exists() or not any(sessions.rglob("*.json"))


def test_project_manifest_failure_projects_to_identity_mismatch(
    task_tmp: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context, _published, _workspace = _make_run(task_tmp)

    def fail(_root: Path) -> object:
        raise ProjectManifestError("PROJECT_JSON_INVALID", "invalid", {})

    monkeypatch.setattr(workflow_module, "_load_project_model", fail)
    result = workflow_module.diagnostic_show(
        _fresh_context(context), diagnostic_session_id="f" * 32
    )
    assert result.ok is False
    assert result.code == "DIAGNOSTIC_IDENTITY_MISMATCH"
    assert result.details == {}
