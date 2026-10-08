"""Public acceptance readers over the genuine VS10-A archived graph.

The archive is historical input, not new physical evidence.  These checks keep
the original project and archive read-only, use a byte-exact run-owned data copy,
and exercise only the public show/resume readers.
"""

from __future__ import annotations

import json
import os
import shutil
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

import pytest
import test_risk_continuation_archive_reader as archive_fixture
from stm32_toolkit.acceptance.recovery_workflows import (
    AcceptanceRecoveryContext,
    resume_acceptance_attempt,
    show_acceptance_attempt,
)
from stm32_toolkit.evidence import canonical_json_bytes
from stm32_toolkit.evidence.store import EvidenceStore
from stm32_toolkit.paths import WorkspacePaths
from stm32_toolkit.project_model import load_project_model

_PROJECT_ROOT_ENV = "STM32TK_VS10A_PROJECT_ROOT"
_EXPECTED_PROJECT_ROOT = Path(r"D:\codex-tmp\t10-d3-fw")
_PROJECT_ID = "4ea7b7c3-2ed9-51ae-bf7d-4b55a23bad6c"
_WORKSPACE_ID = "d7b137149685154d159f2f0ded85852248e4a2de1fe2813a788aa9bb54c2fd74"
_SESSION_ID = "vs10a-t10-d3-20260914-01"
_COMPLETED_ATTEMPT_ID = "ee7b50a4-22f5-4547-99ed-344582bcb853"
_IN_PROGRESS_ATTEMPT_ID = "13093342-58d9-41b7-b78d-f4b86dc7bafa"
_IN_PROGRESS_DEADLINE = "2026-09-17T08:42:49.371973Z"
_INTEGRITY_CODE = "ACCEPTANCE_ATTEMPT_EVIDENCE_INTEGRITY_FAILED"
_INTEGRITY_MESSAGE = "Acceptance attempt evidence failed integrity validation."

TreeSnapshot = archive_fixture.TreeSnapshot


@dataclass(frozen=True)
class ReaderCase:
    source_public_data: Path
    source_snapshot: TreeSnapshot
    public_data: Path
    project_root: Path
    project_manifest: Path
    project_manifest_bytes: bytes
    context: AcceptanceRecoveryContext
    evidence: EvidenceStore


def _configured_project_root() -> Path:
    configured = os.environ.get(_PROJECT_ROOT_ENV)
    if not configured:
        pytest.fail(f"set {_PROJECT_ROOT_ENV} to the pinned original project")
    project_root = Path(configured).resolve(strict=True)
    if project_root != _EXPECTED_PROJECT_ROOT.resolve(strict=True):
        pytest.fail("the configured project is not the pinned VS10-A original project")
    model = load_project_model(project_root)
    if model.schema_version != 3 or str(model.logical_project_id) != _PROJECT_ID:
        pytest.fail("the pinned original project model identity does not match VS10-A")
    return project_root


def _load_case(tmp_path: Path) -> ReaderCase:
    _, source_public_data = archive_fixture._archive_paths()
    source_snapshot = archive_fixture._snapshot(source_public_data)
    public_data = tmp_path / "public-data"
    shutil.copytree(source_public_data, public_data)
    assert archive_fixture._snapshot(public_data) == source_snapshot

    project_root = _configured_project_root()
    model = load_project_model(project_root)
    archived_project = archive_fixture._project_root(public_data)
    workspace = WorkspacePaths.from_roots(
        public_data,
        project_root,
        UUID(str(model.logical_project_id)),
        _SESSION_ID,
    )
    assert workspace.workspace_id == _WORKSPACE_ID
    assert workspace.workspace_root.resolve() == archived_project.resolve()
    evidence = EvidenceStore(workspace.workspace_root / "evidence")
    project_manifest = project_root / ".stm32-project.json"
    assert project_manifest.is_file()
    return ReaderCase(
        source_public_data=source_public_data,
        source_snapshot=source_snapshot,
        public_data=public_data,
        project_root=project_root,
        project_manifest=project_manifest,
        project_manifest_bytes=project_manifest.read_bytes(),
        context=AcceptanceRecoveryContext(
            project_root=project_root,
            data_root=public_data,
            session_id=_SESSION_ID,
        ),
        evidence=evidence,
    )


def _wire(result: object) -> dict[str, object]:
    wire = getattr(result, "to_dict", lambda: None)()
    assert isinstance(wire, dict)
    assert wire["protocol"] == "stm32-toolkit/1"
    return wire


def _assert_success(wire: Mapping[str, object], operation: str) -> dict[str, object]:
    assert wire["ok"] is True
    assert wire["operation"] == operation
    assert wire["code"] == "OK"
    assert wire["message"] == ""
    assert wire["details"] == {}
    data = wire["data"]
    assert isinstance(data, dict)
    return data


def _assert_integrity_refusal(wire: Mapping[str, object], operation: str) -> None:
    assert wire == {
        "protocol": "stm32-toolkit/1",
        "ok": False,
        "operation": operation,
        "code": _INTEGRITY_CODE,
        "message": _INTEGRITY_MESSAGE,
        "data": None,
        "details": {},
    }


def _assert_project_and_archive_unchanged(case: ReaderCase) -> None:
    assert case.project_manifest.read_bytes() == case.project_manifest_bytes
    assert archive_fixture._snapshot(case.source_public_data) == case.source_snapshot


def _attempt_root_path(case: ReaderCase, attempt_id: str, revision: int) -> Path:
    root_id = f"{attempt_id}.{revision:08d}"
    return archive_fixture._public_root_path(
        case.evidence, "acceptance-attempt", root_id
    )


def test_archived_completed_acceptance_show_and_resume_are_read_only(
    tmp_path: Path,
) -> None:
    case = _load_case(tmp_path)
    baseline = archive_fixture._snapshot(case.public_data)

    before_show = archive_fixture._snapshot(case.public_data)
    shown = _wire(
        show_acceptance_attempt(case.context, attempt_id=_COMPLETED_ATTEMPT_ID)
    )
    shown_data = _assert_success(shown, "acceptance.attempt.show")
    assert archive_fixture._snapshot(case.public_data) == before_show

    before_resume = archive_fixture._snapshot(case.public_data)
    resumed = _wire(
        resume_acceptance_attempt(case.context, attempt_id=_COMPLETED_ATTEMPT_ID)
    )
    resumed_data = _assert_success(resumed, "acceptance.attempt.resume")
    assert archive_fixture._snapshot(case.public_data) == before_resume

    assert shown_data["authoritative"] is True
    assert resumed_data["authoritative"] is True
    assert shown_data["attempt"] == resumed_data["attempt"]
    attempt = shown_data["attempt"]
    assert isinstance(attempt, dict)
    assert attempt["attemptId"] == _COMPLETED_ATTEMPT_ID
    assert attempt["revision"] == 1
    assert attempt["status"] == "COMPLETED"
    assert attempt["stage"] == "target-fix-verified"
    assert resumed_data["nextStage"] is None
    assert resumed_data["authorizationRequired"] is False
    assert resumed_data["actionDigest"] is None
    assert resumed_data["timedOut"] is False
    assert isinstance(resumed_data["recoveryPolicy"], dict)
    assert archive_fixture._snapshot(case.public_data) == baseline
    _assert_project_and_archive_unchanged(case)


def test_archived_in_progress_acceptance_show_and_resume_report_current_timeout(
    tmp_path: Path,
) -> None:
    case = _load_case(tmp_path)
    baseline = archive_fixture._snapshot(case.public_data)

    shown = _wire(
        show_acceptance_attempt(case.context, attempt_id=_IN_PROGRESS_ATTEMPT_ID)
    )
    shown_data = _assert_success(shown, "acceptance.attempt.show")
    resumed = _wire(
        resume_acceptance_attempt(case.context, attempt_id=_IN_PROGRESS_ATTEMPT_ID)
    )
    resumed_data = _assert_success(resumed, "acceptance.attempt.resume")

    assert shown_data["authoritative"] is True
    assert resumed_data["authoritative"] is True
    assert shown_data["attempt"] == resumed_data["attempt"]
    attempt = shown_data["attempt"]
    assert isinstance(attempt, dict)
    assert attempt["attemptId"] == _IN_PROGRESS_ATTEMPT_ID
    assert attempt["revision"] == 0
    assert attempt["status"] == "IN_PROGRESS"
    assert attempt["stage"] == "verification-pending"
    assert attempt["deadlineAtUtc"] == _IN_PROGRESS_DEADLINE
    assert resumed_data["nextStage"] == "target-fix-verified"
    assert resumed_data["authorizationRequired"] is False
    assert resumed_data["actionDigest"] is None
    assert resumed_data["timedOut"] is True
    assert isinstance(resumed_data["recoveryPolicy"], dict)
    assert archive_fixture._snapshot(case.public_data) == baseline
    _assert_project_and_archive_unchanged(case)


def test_archived_acceptance_root_corruption_refuses_without_write_then_restores(
    tmp_path: Path,
) -> None:
    case = _load_case(tmp_path)
    baseline = archive_fixture._snapshot(case.public_data)
    root_path = _attempt_root_path(case, _COMPLETED_ATTEMPT_ID, 1)
    original_root = root_path.read_bytes()
    root_value = json.loads(original_root.decode("utf-8"))
    assert isinstance(root_value, dict)
    metadata = root_value.get("metadata")
    assert isinstance(metadata, dict)
    original_attempt_sha = metadata.get("attempt_sha256")
    assert isinstance(original_attempt_sha, str)
    metadata["attempt_sha256"] = (
        "0" * 64 if original_attempt_sha != "0" * 64 else "1" * 64
    )
    root_path.write_bytes(canonical_json_bytes(root_value))
    corrupted = archive_fixture._snapshot(case.public_data)

    refused_show = _wire(
        show_acceptance_attempt(case.context, attempt_id=_COMPLETED_ATTEMPT_ID)
    )
    _assert_integrity_refusal(refused_show, "acceptance.attempt.show")
    assert archive_fixture._snapshot(case.public_data) == corrupted
    refused_resume = _wire(
        resume_acceptance_attempt(case.context, attempt_id=_COMPLETED_ATTEMPT_ID)
    )
    _assert_integrity_refusal(refused_resume, "acceptance.attempt.resume")
    assert archive_fixture._snapshot(case.public_data) == corrupted

    root_path.write_bytes(original_root)
    assert archive_fixture._snapshot(case.public_data) == baseline
    restored_show = _wire(
        show_acceptance_attempt(case.context, attempt_id=_COMPLETED_ATTEMPT_ID)
    )
    restored_resume = _wire(
        resume_acceptance_attempt(case.context, attempt_id=_COMPLETED_ATTEMPT_ID)
    )
    restored_show_data = _assert_success(restored_show, "acceptance.attempt.show")
    restored_resume_data = _assert_success(restored_resume, "acceptance.attempt.resume")
    assert restored_show_data["attempt"] == restored_resume_data["attempt"]
    assert archive_fixture._snapshot(case.public_data) == baseline
    _assert_project_and_archive_unchanged(case)
