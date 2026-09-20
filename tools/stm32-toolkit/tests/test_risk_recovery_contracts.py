from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from uuid import UUID

import pytest

import test_acceptance_physical_recovery as physical_fixtures
import test_diagnostic_store as diagnostic_fixtures
import test_vs08b_scenarios as completion_fixtures
from stm32_toolkit.acceptance.recovery_workflows import (
    resume_acceptance_attempt,
    show_acceptance_attempt,
)
from stm32_toolkit.diagnostic_workflows import (
    DiagnosticWorkflowContext,
    diagnostic_show_verification,
)
from stm32_toolkit.diagnostics import (
    DIAGNOSTIC_CHAIN_CORRUPT,
    DIAGNOSTIC_EVIDENCE_MISSING,
    DIAGNOSTIC_NOT_FOUND,
    DiagnosticStore,
    DiagnosticValidationError,
)
from stm32_toolkit.evidence import EvidenceEnvelope, canonical_json_bytes
from stm32_toolkit.evidence.gc import RootRecord, get_root, put_root
from stm32_toolkit.evidence.store import EvidenceStore
from stm32_toolkit.paths import WorkspacePaths


def _bytes_snapshot(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def _root_file(evidence: EvidenceStore, root_type: str, root_id: str) -> Path:
    key_digest = hashlib.sha256(
        canonical_json_bytes({"root_type": root_type, "root_id": root_id})
    ).hexdigest()
    return evidence.root / "roots" / root_type / f"{key_digest}.json"


@pytest.mark.parametrize("variant", ["missing-root", "regular-file", "missing-evidence"])
def test_diagnostic_store_availability_and_durable_read_modes(
    tmp_path: Path,
    variant: str,
) -> None:
    session_id = diagnostic_fixtures.SID
    if variant == "missing-root":
        diagnostics_root = tmp_path / "d"
        store = DiagnosticStore(diagnostics_root, EvidenceStore(tmp_path / "e"))
        before = _bytes_snapshot(tmp_path)
        with pytest.raises(DiagnosticValidationError) as error:
            store.load_creation_intent(session_id)
        assert error.value.code == DIAGNOSTIC_NOT_FOUND
        assert error.value.message == "session does not exist"
        assert not diagnostics_root.exists()
        assert _bytes_snapshot(tmp_path) == before
        return

    if variant == "regular-file":
        diagnostics_root = tmp_path / "d"
        sentinel = b"diagnostics-root-sentinel"
        diagnostics_root.write_bytes(sentinel)
        store = DiagnosticStore(diagnostics_root, EvidenceStore(tmp_path / "e"))
        before = _bytes_snapshot(tmp_path)
        with pytest.raises(DiagnosticValidationError) as error:
            store.load_creation_intent(session_id)
        assert error.value.code == DIAGNOSTIC_CHAIN_CORRUPT
        assert error.value.message == "event/checkpoint/root chain is missing or contradictory"
        assert diagnostics_root.read_bytes() == sentinel
        assert _bytes_snapshot(tmp_path) == before
        return

    origin = tmp_path / "o"
    origin.mkdir()
    origin_evidence = EvidenceStore(origin / "e")
    failed_evidence_id = diagnostic_fixtures._failed_evidence(origin_evidence, origin)
    origin_store = DiagnosticStore(origin / "d", origin_evidence)
    created = diagnostic_fixtures._created_target(failed_evidence_id)
    created_record = origin_store.create(created)
    origin_before = _bytes_snapshot(origin)

    clone = tmp_path / "c"
    shutil.copytree(origin, clone)
    clone_evidence = EvidenceStore(clone / "e")
    clone_store = DiagnosticStore(clone / "d", clone_evidence)
    failed_envelope = clone_evidence.get_envelope(failed_evidence_id)
    manifest_path = clone_evidence.root / "manifests" / f"{failed_evidence_id}.json"
    object_path = clone_evidence.root / failed_envelope.artifacts[0].relative_path
    manifest_path.unlink()
    object_path.unlink()
    clone_before = _bytes_snapshot(clone)

    durable = clone_store.load_durable(session_id)
    assert durable.to_dict() == created_record.session.to_dict()
    with pytest.raises(DiagnosticValidationError) as error:
        clone_store.load(session_id)
    assert error.value.code == DIAGNOSTIC_EVIDENCE_MISSING
    assert error.value.message == "required TestRun evidence is absent or damaged"
    assert _bytes_snapshot(clone) == clone_before
    assert _bytes_snapshot(origin) == origin_before


def test_diagnostic_show_verification_rejects_missing_analysis_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        project_root,
        data_root,
        runtime_session_id,
        diagnostic_session_id,
        _verification_plan,
        publication,
        _after_run,
    ) = completion_fixtures._prepare_completion_graph(tmp_path, monkeypatch)
    project_before = _bytes_snapshot(project_root)
    data_before = _bytes_snapshot(data_root)

    clone_data = tmp_path / "c"
    shutil.copytree(data_root, clone_data)
    clone_workspace = WorkspacePaths.from_roots(
        clone_data,
        project_root,
        completion_fixtures.PROJECT_ID,
        runtime_session_id,
    )
    clone_evidence = EvidenceStore(clone_workspace.workspace_root / "evidence")
    analysis_id = str(publication.analysis_result.analysis_id)
    analysis_root = get_root(clone_evidence, "monitor-analysis", analysis_id)
    analysis_root_path = _root_file(clone_evidence, analysis_root.root_type, analysis_root.root_id)
    assert analysis_root_path.read_bytes() == canonical_json_bytes(analysis_root.to_dict())
    analysis_root_path.unlink()
    clone_before = _bytes_snapshot(clone_data)

    context = DiagnosticWorkflowContext(project_root, clone_data, runtime_session_id)
    result = diagnostic_show_verification(
        context,
        diagnostic_session_id=diagnostic_session_id,
    )
    assert result.to_dict() == {
        "protocol": "stm32-toolkit/1",
        "ok": False,
        "operation": "diagnostic.verification.show",
        "code": DIAGNOSTIC_CHAIN_CORRUPT,
        "message": "event/checkpoint/root chain is missing or contradictory",
        "data": None,
        "details": {},
    }
    assert _bytes_snapshot(clone_data) == clone_before
    assert _bytes_snapshot(project_root) == project_before
    assert _bytes_snapshot(data_root) == data_before


def test_acceptance_recovery_unknown_schema_dispatch_is_read_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context, _diagnostic, _diagnostic_id = physical_fixtures._prepare_public_physical_attempt(
        tmp_path,
        monkeypatch,
        through_revision=1,
    )
    project_before = _bytes_snapshot(context.project_root)
    data_before = _bytes_snapshot(context.data_root)

    clone_data = tmp_path / "c"
    shutil.copytree(context.data_root, clone_data)
    clone_workspace = WorkspacePaths.from_roots(
        clone_data,
        context.project_root,
        UUID(physical_fixtures.PROJECT_ID),
        context.session_id,
    )
    clone_evidence = EvidenceStore(clone_workspace.workspace_root / "evidence")
    root_id = f"{physical_fixtures.ATTEMPT_ID}.00000000"
    root = get_root(clone_evidence, "acceptance-attempt", root_id)
    envelope = clone_evidence.get_envelope(root.manifest_id)
    metadata = dict(envelope.metadata)
    attempt = dict(metadata["attempt"])
    attempt["schema"] = "stm32-acceptance-attempt/unknown"
    metadata["attempt"] = attempt
    replacement = EvidenceEnvelope(
        identity=envelope.identity,
        operation=envelope.operation,
        produced_at_utc=envelope.produced_at_utc,
        parents=envelope.parents,
        artifacts=envelope.artifacts,
        metadata=metadata,
    )
    clone_evidence.put_envelope(replacement)
    root_path = _root_file(clone_evidence, root.root_type, root.root_id)
    root_path.unlink()
    put_root(
        clone_evidence,
        RootRecord(root.root_type, root.root_id, str(replacement.evidence_id), root.metadata),
    )
    clone_before = _bytes_snapshot(clone_data)

    clone_context = type(context)(
        context.project_root,
        clone_data,
        context.session_id,
        clock=context.clock,
    )
    for operation, caller in (
        ("acceptance.attempt.show", show_acceptance_attempt),
        ("acceptance.attempt.resume", resume_acceptance_attempt),
    ):
        result = caller(clone_context, attempt_id=physical_fixtures.ATTEMPT_ID)
        assert result.to_dict() == {
            "protocol": "stm32-toolkit/1",
            "ok": False,
            "operation": operation,
            "code": "ACCEPTANCE_ATTEMPT_EVIDENCE_INTEGRITY_FAILED",
            "message": "Acceptance attempt evidence failed integrity validation.",
            "data": None,
            "details": {},
        }
        assert _bytes_snapshot(clone_data) == clone_before

    assert _bytes_snapshot(context.project_root) == project_before
    assert _bytes_snapshot(context.data_root) == data_before
