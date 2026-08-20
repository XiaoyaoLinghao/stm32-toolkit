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
from stm32_toolkit.diagnostics import DiagnosticSession, DiagnosticStore, Hypothesis, reduce_event
from stm32_toolkit.evidence import EVIDENCE_CORRUPT, EvidenceIdentity, EvidenceValidationError
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
