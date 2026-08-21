from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest

import stm32_toolkit.diagnostic_workflows as diagnostic_workflows
import stm32_toolkit.testing_workflows as testing_workflows
from stm32_toolkit.diagnostic_workflows import (
    DiagnosticWorkflowContext,
    diagnostic_add_hypothesis,
    diagnostic_begin,
    diagnostic_show,
    diagnostic_start,
)
from stm32_toolkit.evidence import EVIDENCE_CORRUPT, EvidenceValidationError
from stm32_toolkit.evidence.store import EvidenceStore
from stm32_toolkit.paths import WorkspacePaths
from stm32_toolkit.testing.replay import load_target_replay_fixture


FIXTURES = Path(__file__).parent / "fixtures" / "vs03" / "target"
PROJECT_ID = UUID("123e4567-e89b-42d3-a456-426614174000")


def _install_model(
    monkeypatch: pytest.MonkeyPatch,
    project_id: UUID = PROJECT_ID,
) -> None:
    model = SimpleNamespace(
        schema_version=3,
        logical_project_id=project_id,
        testing=SimpleNamespace(host=None, target=object()),
    )
    monkeypatch.setattr(testing_workflows, "_load_project_model", lambda _root: model)
    monkeypatch.setattr(diagnostic_workflows, "_load_project_model", lambda _root: model)


def _contexts(tmp_path: Path) -> tuple[testing_workflows.TestingWorkflowContext, DiagnosticWorkflowContext]:
    project = tmp_path / "project"
    project.mkdir()
    data = tmp_path / "data"
    return (
        testing_workflows.TestingWorkflowContext(project, data, "replay-session"),
        DiagnosticWorkflowContext(project, data, "replay-session"),
    )


def _fresh_diagnostic_context(context: DiagnosticWorkflowContext) -> DiagnosticWorkflowContext:
    return DiagnosticWorkflowContext(
        Path(context.project_root), Path(context.data_root), str(context.session_id)
    )


def _replay_and_open_session(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> tuple[DiagnosticWorkflowContext, str, object, WorkspacePaths]:
    testing_context, diagnostic_context = _contexts(tmp_path)
    _install_model(monkeypatch)
    replay = testing_workflows.target_replay_run(
        testing_context,
        "vs03-failed-before",
        FIXTURES / "failed-before.json",
        FIXTURES / "failed-before.hex",
    )
    assert replay.ok is True

    started = diagnostic_start(
        _fresh_diagnostic_context(diagnostic_context),
        operation_id="diagnostic.start",
        failed_test_run_id="vs03-failed-before",
        failed_run_mode="target",
    )
    assert started.ok is True
    session_id = started.data["session"]["diagnostic_session_id"]
    begun = diagnostic_begin(
        _fresh_diagnostic_context(diagnostic_context),
        operation_id="diagnostic.begin",
        diagnostic_session_id=session_id,
        expected_revision=1,
    )
    assert begun.ok is True
    added = diagnostic_add_hypothesis(
        _fresh_diagnostic_context(diagnostic_context),
        operation_id="diagnostic.hypothesis.add",
        diagnostic_session_id=session_id,
        expected_revision=2,
        statement="the replayed failed run identifies the faulty behavior",
    )
    assert added.ok is True
    workspace = WorkspacePaths.from_roots(
        diagnostic_context.data_root,
        diagnostic_context.project_root,
        PROJECT_ID,
        diagnostic_context.session_id,
    )
    return diagnostic_context, session_id, replay, workspace


def _tree_snapshot(root: Path) -> tuple[tuple[str, bytes | None], ...]:
    if not root.exists():
        return ()
    entries: list[tuple[str, bytes | None]] = []
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        relative = path.relative_to(root).as_posix()
        entries.append((relative, path.read_bytes() if path.is_file() else None))
    return tuple(entries)


def _authority_snapshot(workspace: WorkspacePaths) -> tuple[object, object]:
    return (
        _tree_snapshot(workspace.diagnostics_root),
        _tree_snapshot(workspace.workspace_root / "evidence" / "roots"),
    )


def _target_test_run_root(workspace: WorkspacePaths) -> Path:
    roots = tuple((workspace.workspace_root / "evidence" / "roots" / "test-run").glob("*.json"))
    assert len(roots) == 1
    return roots[0]


def test_target_replay_diagnostic_session_reloads_with_origin_authority(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    testing_context, diagnostic_context = _contexts(tmp_path)
    _install_model(monkeypatch)
    replay = testing_workflows.target_replay_run(
        testing_context,
        "vs03-failed-before",
        FIXTURES / "failed-before.json",
        FIXTURES / "failed-before.hex",
    )
    origin_workspace_id = replay.data["run"]["identity"]["workspace_id"]
    started = diagnostic_start(
        _fresh_diagnostic_context(diagnostic_context),
        operation_id="diagnostic.start",
        failed_test_run_id="vs03-failed-before",
        failed_run_mode="target",
    )
    assert replay.ok is True
    assert started.ok is True and started.data["session"]["state"] == "OPEN"
    session_id = started.data["session"]["diagnostic_session_id"]
    begun = diagnostic_begin(
        _fresh_diagnostic_context(diagnostic_context),
        operation_id="diagnostic.begin",
        diagnostic_session_id=session_id,
        expected_revision=1,
    )
    assert begun.ok is True and begun.data["session"]["state"] == "INVESTIGATING"
    added = diagnostic_add_hypothesis(
        _fresh_diagnostic_context(diagnostic_context),
        operation_id="diagnostic.hypothesis.add",
        diagnostic_session_id=session_id,
        expected_revision=2,
        statement="the replayed failed run identifies the faulty behavior",
    )
    assert added.ok is True
    shown = diagnostic_show(
        _fresh_diagnostic_context(diagnostic_context), diagnostic_session_id=session_id
    )
    assert shown.ok is True
    assert shown.data["session"]["identity"]["workspace_id"] == origin_workspace_id
    assert origin_workspace_id != WorkspacePaths.from_roots(
        diagnostic_context.data_root,
        diagnostic_context.project_root,
        PROJECT_ID,
    ).workspace_id


def test_target_replay_start_rejects_foreign_project_without_mutation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    foreign_project_id = UUID("ffffffff-ffff-4fff-8fff-ffffffffffff")
    testing_context, diagnostic_context = _contexts(tmp_path)
    _install_model(monkeypatch, foreign_project_id)
    replay = testing_workflows.target_replay_run(
        testing_context,
        "vs03-failed-before",
        FIXTURES / "failed-before.json",
        FIXTURES / "failed-before.hex",
    )
    assert replay.ok is True
    workspace = WorkspacePaths.from_roots(
        diagnostic_context.data_root,
        diagnostic_context.project_root,
        foreign_project_id,
        diagnostic_context.session_id,
    )
    before = _authority_snapshot(workspace)
    started = diagnostic_start(
        _fresh_diagnostic_context(diagnostic_context),
        operation_id="diagnostic.start.foreign-project",
        failed_test_run_id="vs03-failed-before",
        failed_run_mode="target",
    )
    after = _authority_snapshot(workspace)
    assert started.ok is False
    assert started.code == "INCOMPATIBLE_IDENTITY"
    assert after == before


@pytest.mark.parametrize(
    ("failure", "expected_code"),
    (
        ("missing", "EVIDENCE_INTEGRITY_FAILURE"),
        ("provider", "ENVIRONMENT_FAILURE"),
    ),
)
def test_target_replay_start_classifies_repository_failures(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    failure: str,
    expected_code: str,
) -> None:
    testing_context, diagnostic_context = _contexts(tmp_path)
    _install_model(monkeypatch)
    replay = testing_workflows.target_replay_run(
        testing_context,
        "vs03-failed-before",
        FIXTURES / "failed-before.json",
        FIXTURES / "failed-before.hex",
    )
    assert replay.ok is True
    workspace = WorkspacePaths.from_roots(
        diagnostic_context.data_root,
        diagnostic_context.project_root,
        PROJECT_ID,
        diagnostic_context.session_id,
    )

    class FailingRepository:
        def __init__(self, _evidence_store: object) -> None:
            pass

        def load(self, _run_id: str) -> object:
            if failure == "missing":
                raise FileNotFoundError("immutable TestRun material is missing")
            raise OSError("evidence provider is unavailable")

    monkeypatch.setattr(diagnostic_workflows, "_repository_factory", FailingRepository)
    before = _authority_snapshot(workspace)
    started = diagnostic_start(
        _fresh_diagnostic_context(diagnostic_context),
        operation_id=f"diagnostic.start.{failure}",
        failed_test_run_id="vs03-failed-before",
        failed_run_mode="target",
    )
    after = _authority_snapshot(workspace)
    assert started.ok is False
    assert started.code == expected_code
    assert after == before


def test_target_replay_real_repository_provider_failure_is_environment_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    testing_context, diagnostic_context = _contexts(tmp_path)
    _install_model(monkeypatch)
    replay = testing_workflows.target_replay_run(
        testing_context,
        "vs03-failed-before",
        FIXTURES / "failed-before.json",
        FIXTURES / "failed-before.hex",
    )
    assert replay.ok is True
    workspace = WorkspacePaths.from_roots(
        diagnostic_context.data_root,
        diagnostic_context.project_root,
        PROJECT_ID,
        diagnostic_context.session_id,
    )

    def provider_failure(
        _store: EvidenceStore, _artifact: object, *, maximum_bytes: int
    ) -> bytes:
        raise OSError("evidence provider is unavailable")

    monkeypatch.setattr(EvidenceStore, "read_artifact", provider_failure)
    before = _authority_snapshot(workspace)
    started = diagnostic_start(
        _fresh_diagnostic_context(diagnostic_context),
        operation_id="diagnostic.start.target-provider-real",
        failed_test_run_id="vs03-failed-before",
        failed_run_mode="target",
    )
    after = _authority_snapshot(workspace)
    assert started.ok is False
    assert started.code == "ENVIRONMENT_FAILURE"
    assert after == before


def test_target_replay_start_missing_published_root_is_integrity_failure_without_mutation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    testing_context, diagnostic_context = _contexts(tmp_path)
    _install_model(monkeypatch)
    replay = testing_workflows.target_replay_run(
        testing_context,
        "vs03-failed-before",
        FIXTURES / "failed-before.json",
        FIXTURES / "failed-before.hex",
    )
    assert replay.ok is True
    workspace = WorkspacePaths.from_roots(
        diagnostic_context.data_root,
        diagnostic_context.project_root,
        PROJECT_ID,
        diagnostic_context.session_id,
    )
    _target_test_run_root(workspace).unlink()
    before = _authority_snapshot(workspace)
    started = diagnostic_start(
        _fresh_diagnostic_context(diagnostic_context),
        operation_id="diagnostic.start.target-missing-root",
        failed_test_run_id="vs03-failed-before",
        failed_run_mode="target",
    )
    after = _authority_snapshot(workspace)
    assert started.ok is False
    assert started.code == "EVIDENCE_INTEGRITY_FAILURE"
    assert after == before


def test_default_host_repository_corruption_keeps_legacy_failure_projection(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _testing_context, diagnostic_context = _contexts(tmp_path)
    _install_model(monkeypatch)

    class CorruptRepository:
        def __init__(self, _evidence_store: object) -> None:
            pass

        def load(self, _run_id: str) -> object:
            raise EvidenceValidationError(EVIDENCE_CORRUPT, "corrupt")

    monkeypatch.setattr(diagnostic_workflows, "_repository_factory", CorruptRepository)
    workspace = WorkspacePaths.from_roots(
        diagnostic_context.data_root,
        diagnostic_context.project_root,
        PROJECT_ID,
        diagnostic_context.session_id,
    )
    before = _authority_snapshot(workspace)
    started = diagnostic_start(
        _fresh_diagnostic_context(diagnostic_context),
        operation_id="diagnostic.start.host-corrupt",
        failed_test_run_id="host-failed-run",
    )
    after = _authority_snapshot(workspace)
    assert started.ok is False
    assert started.code == "DIAGNOSTIC_EVIDENCE_MISSING"
    assert started.message == "required TestRun evidence is absent or damaged"
    assert started.details == {}
    assert after == before


def test_invalid_failed_run_mode_is_rejected_before_repository_access_without_mutation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _testing_context, diagnostic_context = _contexts(tmp_path)
    _install_model(monkeypatch)

    class ForbiddenRepository:
        def __init__(self, _evidence_store: object) -> None:
            pass

        def load(self, _run_id: str) -> object:
            raise AssertionError("invalid mode must be rejected before repository access")

    monkeypatch.setattr(diagnostic_workflows, "_repository_factory", ForbiddenRepository)
    workspace = WorkspacePaths.from_roots(
        diagnostic_context.data_root,
        diagnostic_context.project_root,
        PROJECT_ID,
        diagnostic_context.session_id,
    )
    before = _authority_snapshot(workspace)
    started = diagnostic_start(
        _fresh_diagnostic_context(diagnostic_context),
        operation_id="diagnostic.start.invalid-mode",
        failed_test_run_id="vs03-failed-before",
        failed_run_mode="invalid",  # type: ignore[arg-type]
    )
    after = _authority_snapshot(workspace)
    assert started.ok is False
    assert started.code == "DIAGNOSTIC_INVALID_EVENT"
    assert after == before


def test_target_mode_rejects_host_record_without_mutation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    testing_context, diagnostic_context = _contexts(tmp_path)
    _install_model(monkeypatch)
    replay = testing_workflows.target_replay_run(
        testing_context,
        "vs03-failed-before",
        FIXTURES / "failed-before.json",
        FIXTURES / "failed-before.hex",
    )
    assert replay.ok is True
    original_factory = diagnostic_workflows._repository_factory

    class HostRecordRepository:
        def __init__(self, evidence_store: object) -> None:
            self._repository = original_factory(evidence_store)

        def load(self, run_id: str) -> object:
            published = self._repository.load(run_id)
            return replace(
                published,
                manifest=replace(published.manifest, mode="host", transport=None),
            )

    monkeypatch.setattr(diagnostic_workflows, "_repository_factory", HostRecordRepository)
    workspace = WorkspacePaths.from_roots(
        diagnostic_context.data_root,
        diagnostic_context.project_root,
        PROJECT_ID,
        diagnostic_context.session_id,
    )
    before = _authority_snapshot(workspace)
    started = diagnostic_start(
        _fresh_diagnostic_context(diagnostic_context),
        operation_id="diagnostic.start.target-host-record",
        failed_test_run_id="vs03-failed-before",
        failed_run_mode="target",
    )
    after = _authority_snapshot(workspace)
    assert started.ok is False
    assert started.code == "EVIDENCE_INTEGRITY_FAILURE"
    assert after == before


def test_default_host_mode_rejects_target_record_without_mutation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    testing_context, diagnostic_context = _contexts(tmp_path)
    _install_model(monkeypatch)
    replay = testing_workflows.target_replay_run(
        testing_context,
        "vs03-failed-before",
        FIXTURES / "failed-before.json",
        FIXTURES / "failed-before.hex",
    )
    assert replay.ok is True
    workspace = WorkspacePaths.from_roots(
        diagnostic_context.data_root,
        diagnostic_context.project_root,
        PROJECT_ID,
        diagnostic_context.session_id,
    )
    before = _authority_snapshot(workspace)
    started = diagnostic_start(
        _fresh_diagnostic_context(diagnostic_context),
        operation_id="diagnostic.start.host-target-record",
        failed_test_run_id="vs03-failed-before",
    )
    after = _authority_snapshot(workspace)
    assert started.ok is False
    assert started.code == "DIAGNOSTIC_INVALID_EVENT"
    assert after == before


def test_target_alias_show_uses_durable_mode_after_published_root_is_deleted(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    testing_context, diagnostic_context = _contexts(tmp_path)
    _install_model(monkeypatch)
    origin_workspace_id = load_target_replay_fixture(
        FIXTURES / "failed-before.json", FIXTURES / "failed-before.hex"
    ).descriptor.identity.workspace_id
    original_factory = WorkspacePaths.from_roots

    def alias_factory(
        data_root: Path,
        project_root: Path,
        logical_project_id: UUID,
        session_id: str | None = None,
    ) -> WorkspacePaths:
        actual = original_factory(data_root, project_root, logical_project_id, session_id)
        return replace(actual, workspace_id=origin_workspace_id)

    monkeypatch.setattr(testing_workflows.WorkspacePaths, "from_roots", alias_factory)
    monkeypatch.setattr(diagnostic_workflows, "_workspace_paths_factory", alias_factory)
    replay = testing_workflows.target_replay_run(
        testing_context,
        "vs03-failed-before",
        FIXTURES / "failed-before.json",
        FIXTURES / "failed-before.hex",
    )
    assert replay.ok is True
    started = diagnostic_start(
        _fresh_diagnostic_context(diagnostic_context),
        operation_id="diagnostic.start.alias-missing-root",
        failed_test_run_id="vs03-failed-before",
        failed_run_mode="target",
    )
    assert started.ok is True
    session_id = started.data["session"]["diagnostic_session_id"]
    workspace = original_factory(
        diagnostic_context.data_root,
        diagnostic_context.project_root,
        PROJECT_ID,
        diagnostic_context.session_id,
    )
    _target_test_run_root(workspace).unlink()
    before = _authority_snapshot(workspace)
    shown = diagnostic_show(
        _fresh_diagnostic_context(diagnostic_context), diagnostic_session_id=session_id
    )
    after = _authority_snapshot(workspace)
    assert shown.ok is False
    assert shown.code == "EVIDENCE_INTEGRITY_FAILURE"
    assert after == before


def test_target_replay_alias_workspace_is_legal_for_start_and_show(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    testing_context, diagnostic_context = _contexts(tmp_path)
    _install_model(monkeypatch)
    origin_workspace_id = load_target_replay_fixture(
        FIXTURES / "failed-before.json", FIXTURES / "failed-before.hex"
    ).descriptor.identity.workspace_id
    original_factory = WorkspacePaths.from_roots

    def alias_factory(
        data_root: Path,
        project_root: Path,
        logical_project_id: UUID,
        session_id: str | None = None,
    ) -> WorkspacePaths:
        actual = original_factory(data_root, project_root, logical_project_id, session_id)
        return replace(actual, workspace_id=origin_workspace_id)

    monkeypatch.setattr(testing_workflows.WorkspacePaths, "from_roots", alias_factory)
    monkeypatch.setattr(diagnostic_workflows, "_workspace_paths_factory", alias_factory)
    replay = testing_workflows.target_replay_run(
        testing_context,
        "vs03-failed-before",
        FIXTURES / "failed-before.json",
        FIXTURES / "failed-before.hex",
    )
    assert replay.ok is True
    started = diagnostic_start(
        _fresh_diagnostic_context(diagnostic_context),
        operation_id="diagnostic.start.alias",
        failed_test_run_id="vs03-failed-before",
        failed_run_mode="target",
    )
    assert started.ok is True
    shown = diagnostic_show(
        _fresh_diagnostic_context(diagnostic_context),
        diagnostic_session_id=started.data["session"]["diagnostic_session_id"],
    )
    assert shown.ok is True
    assert shown.data["session"]["identity"]["workspace_id"] == origin_workspace_id


def _tamper_published(kind: str, published: object) -> object:
    manifest = published.manifest
    root = published.root
    if kind == "foreign_manifest_identity":
        foreign = replace(manifest.identity, workspace_id="f" * 64)
        return replace(published, manifest=replace(manifest, identity=foreign))
    if kind == "physical_flag":
        metadata = dict(root.metadata)
        metadata["physical_transport_evidence"] = True
        return replace(published, root=replace(root, metadata=metadata))
    if kind == "non_replay_transport":
        return replace(published, manifest=replace(manifest, transport="physical"))
    if kind == "wrong_origin_metadata":
        metadata = dict(root.metadata)
        metadata["origin_workspace_id"] = "a" * 64
        return replace(published, root=replace(root, metadata=metadata))
    if kind == "wrong_current_import_metadata":
        metadata = dict(root.metadata)
        metadata["import_workspace_id"] = "b" * 64
        return replace(published, root=replace(root, metadata=metadata))
    raise AssertionError(f"unknown tamper kind: {kind}")


@pytest.mark.parametrize(
    ("kind", "expected_code"),
    (
        ("foreign_manifest_identity", "INCOMPATIBLE_IDENTITY"),
        ("physical_flag", "EVIDENCE_INTEGRITY_FAILURE"),
        ("non_replay_transport", "EVIDENCE_INTEGRITY_FAILURE"),
        ("wrong_origin_metadata", "EVIDENCE_INTEGRITY_FAILURE"),
        ("wrong_current_import_metadata", "EVIDENCE_INTEGRITY_FAILURE"),
    ),
)
def test_target_replay_authority_rejects_foreign_or_contradictory_records_without_mutation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    kind: str,
    expected_code: str,
) -> None:
    diagnostic_context, session_id, _replay, workspace = _replay_and_open_session(
        monkeypatch, tmp_path
    )
    original_factory = diagnostic_workflows._repository_factory

    class TamperedRepository:
        def __init__(self, evidence_store: object) -> None:
            self._repository = original_factory(evidence_store)

        def load(self, run_id: str) -> object:
            return _tamper_published(kind, self._repository.load(run_id))

    monkeypatch.setattr(diagnostic_workflows, "_repository_factory", TamperedRepository)
    before = _authority_snapshot(workspace)
    shown = diagnostic_show(
        _fresh_diagnostic_context(diagnostic_context), diagnostic_session_id=session_id
    )
    after = _authority_snapshot(workspace)
    assert shown.ok is False
    assert shown.code == expected_code
    assert after == before
