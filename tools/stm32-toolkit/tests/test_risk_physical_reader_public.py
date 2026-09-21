from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

from stm32_toolkit.acceptance.recovery import (
    PHYSICAL_ATTEMPT_SCHEMA,
    PHYSICAL_SCENARIO_ID,
    PHYSICAL_SCENARIO_VERSION,
    PhysicalAcceptanceAttempt,
)
from stm32_toolkit.acceptance.recovery_workflows import (
    AcceptanceRecoveryContext,
    begin_acceptance_attempt,
    checkpoint_acceptance_attempt,
    resume_acceptance_attempt,
    show_acceptance_attempt,
)
from stm32_toolkit.evidence import (
    EvidenceEnvelope,
    EvidenceIdentity,
    canonical_json_bytes,
)
from stm32_toolkit.evidence.gc import RootRecord, get_root, put_root
from stm32_toolkit.evidence.store import EvidenceStore
from stm32_toolkit.paths import WorkspacePaths

# Reuse the established schema-3 Keil project writer.  The physical reader
# journey below uses only the public begin/checkpoint/show/resume APIs; the
# writer import is test fixture reuse, not a production seam.
from test_acceptance_physical_recovery import _write_physical_project

ATTEMPT_ID = "00000000-0000-4000-8000-000000000101"
PROJECT_ID = "00000000-0000-4000-8000-000000000102"
ROOT_TYPE = "acceptance-attempt"
ATTEMPT_OPERATION = "acceptance-attempt"
INTEGRITY_CODE = "ACCEPTANCE_ATTEMPT_EVIDENCE_INTEGRITY_FAILED"
IDENTITY_CODE = "ACCEPTANCE_ATTEMPT_IDENTITY_MISMATCH"
INTEGRITY_MESSAGE = "Acceptance attempt evidence failed integrity validation."
IDENTITY_MESSAGE = "Acceptance attempt identity does not match."


class _Variant:
    def __init__(
        self,
        name: str,
        expected_code: str,
        install: Callable[
            [
                EvidenceStore,
                dict[int, RootRecord],
                dict[int, EvidenceEnvelope],
                dict[int, PhysicalAcceptanceAttempt],
            ],
            None,
        ],
    ) -> None:
        self.name = name
        self.expected_code = expected_code
        self.install = install


def _utc_shift(value: str, seconds: int) -> str:
    parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ").replace(
        tzinfo=timezone.utc
    )
    return (parsed + timedelta(seconds=seconds)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _root_id(revision: int) -> str:
    return f"{ATTEMPT_ID}.{revision:08d}"


def _root_path(evidence: EvidenceStore, root_id: str) -> Path:
    filename = (
        hashlib.sha256(
            canonical_json_bytes({"root_type": ROOT_TYPE, "root_id": root_id})
        ).hexdigest()
        + ".json"
    )
    return evidence.root / "roots" / ROOT_TYPE / filename


def _file_snapshot(root: Path) -> dict[str, bytes]:
    if not root.exists():
        return {}
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def _restore_tree(root: Path, snapshot: Mapping[str, bytes]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    children = sorted(root.rglob("*"), key=lambda item: len(item.parts), reverse=True)
    for path in children:
        if path.is_file() or path.is_symlink():
            path.unlink()
        elif path.is_dir():
            path.rmdir()
    for relative, payload in snapshot.items():
        target = root / Path(relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)


def _persistence_snapshot(
    project_root: Path, data_root: Path
) -> tuple[dict[str, bytes], dict[str, bytes]]:
    return _file_snapshot(project_root), _file_snapshot(data_root)


def _assert_snapshot(root: Path, expected: Mapping[str, bytes]) -> None:
    assert _file_snapshot(root) == dict(expected)


def _result_wire(result: object) -> dict[str, object]:
    wire = getattr(result, "to_dict", lambda: None)()
    assert isinstance(wire, dict)
    return wire


def _assert_failure(result: object, operation: str, code: str) -> None:
    message = INTEGRITY_MESSAGE if code == INTEGRITY_CODE else IDENTITY_MESSAGE
    assert _result_wire(result) == {
        "protocol": "stm32-toolkit/1",
        "ok": False,
        "operation": operation,
        "code": code,
        "message": message,
        "data": None,
        "details": {},
    }


def _load_chain_records(
    evidence: EvidenceStore,
) -> tuple[
    dict[int, RootRecord],
    dict[int, EvidenceEnvelope],
    dict[int, PhysicalAcceptanceAttempt],
]:
    roots: dict[int, RootRecord] = {}
    envelopes: dict[int, EvidenceEnvelope] = {}
    attempts: dict[int, PhysicalAcceptanceAttempt] = {}
    for revision in (0, 1):
        root = get_root(evidence, ROOT_TYPE, _root_id(revision))
        envelope = evidence.get_envelope(root.manifest_id)
        raw_attempt = envelope.metadata.get("attempt")
        attempts[revision] = PhysicalAcceptanceAttempt.from_value(raw_attempt)
        roots[revision] = root
        envelopes[revision] = envelope
    return roots, envelopes, attempts


def _replace_root(
    evidence: EvidenceStore,
    old_root: RootRecord,
    envelope: EvidenceEnvelope,
    metadata: Mapping[str, object],
) -> None:
    evidence.put_envelope(envelope)
    path = _root_path(evidence, old_root.root_id)
    path.unlink()
    put_root(
        evidence,
        RootRecord(
            root_type=old_root.root_type,
            root_id=old_root.root_id,
            manifest_id=str(envelope.evidence_id),
            metadata=dict(metadata),
        ),
    )


def _attempt_with(
    baseline: PhysicalAcceptanceAttempt,
    **changes: object,
) -> PhysicalAcceptanceAttempt:
    payload = dict(baseline.to_dict())
    payload.update(changes)
    payload["checkpointId"] = hashlib.sha256(
        canonical_json_bytes(
            {key: value for key, value in payload.items() if key != "checkpointId"}
        )
    ).hexdigest()
    result = PhysicalAcceptanceAttempt.from_value(payload)
    assert result.schema == PHYSICAL_ATTEMPT_SCHEMA
    return result


def _envelope_with(
    baseline: EvidenceEnvelope,
    *,
    identity: EvidenceIdentity | None = None,
    produced_at_utc: str | None = None,
    parents: tuple[str, ...] | None = None,
    metadata: Mapping[str, object] | None = None,
) -> EvidenceEnvelope:
    return EvidenceEnvelope(
        identity=baseline.identity if identity is None else identity,
        operation=baseline.operation,
        produced_at_utc=(
            baseline.produced_at_utc if produced_at_utc is None else produced_at_utc
        ),
        parents=baseline.parents if parents is None else parents,
        artifacts=baseline.artifacts,
        metadata=baseline.metadata if metadata is None else metadata,
    )


def _attempt_envelope_metadata(attempt: PhysicalAcceptanceAttempt) -> dict[str, object]:
    return {"attempt": attempt.to_dict(), "attempt_sha256": attempt.checkpoint_id}


def _attempt_root_metadata(attempt: PhysicalAcceptanceAttempt) -> dict[str, object]:
    return {
        "attempt_sha256": attempt.checkpoint_id,
        "revision": attempt.revision,
        "workspace_id": attempt.workspace_id,
        "logical_project_id": attempt.logical_project_id,
    }


def _replace_attempt_revision(
    evidence: EvidenceStore,
    old_root: RootRecord,
    baseline_envelope: EvidenceEnvelope,
    attempt: PhysicalAcceptanceAttempt,
) -> None:
    envelope = _envelope_with(
        baseline_envelope,
        metadata=_attempt_envelope_metadata(attempt),
    )
    _replace_root(evidence, old_root, envelope, _attempt_root_metadata(attempt))


def _install_p1(
    evidence: EvidenceStore,
    roots: dict[int, RootRecord],
    envelopes: dict[int, EvidenceEnvelope],
    attempts: dict[int, PhysicalAcceptanceAttempt],
) -> None:
    metadata = dict(roots[0].metadata)
    metadata["revision"] = 1
    _replace_root(evidence, roots[0], envelopes[0], metadata)


def _install_p2(
    evidence: EvidenceStore,
    roots: dict[int, RootRecord],
    envelopes: dict[int, EvidenceEnvelope],
    attempts: dict[int, PhysicalAcceptanceAttempt],
) -> None:
    metadata = {"attempt": attempts[0].to_dict(), "attempt_sha256": "b" * 64}
    envelope = _envelope_with(envelopes[0], metadata=metadata)
    _replace_root(evidence, roots[0], envelope, roots[0].metadata)


def _install_p3(
    evidence: EvidenceStore,
    roots: dict[int, RootRecord],
    envelopes: dict[int, EvidenceEnvelope],
    attempts: dict[int, PhysicalAcceptanceAttempt],
) -> None:
    attempt = _attempt_with(attempts[1], previousCheckpointId="e" * 64)
    _replace_attempt_revision(evidence, roots[1], envelopes[1], attempt)


def _install_p4(
    evidence: EvidenceStore,
    roots: dict[int, RootRecord],
    envelopes: dict[int, EvidenceEnvelope],
    attempts: dict[int, PhysicalAcceptanceAttempt],
) -> None:
    envelope = _envelope_with(envelopes[1], parents=("f" * 64,))
    _replace_root(evidence, roots[1], envelope, roots[1].metadata)


def _install_p5(
    evidence: EvidenceStore,
    roots: dict[int, RootRecord],
    envelopes: dict[int, EvidenceEnvelope],
    attempts: dict[int, PhysicalAcceptanceAttempt],
) -> None:
    envelope = _envelope_with(
        envelopes[1],
        produced_at_utc=_utc_shift(attempts[1].updated_at_utc, 1),
    )
    _replace_root(evidence, roots[1], envelope, roots[1].metadata)


def _install_p6(
    evidence: EvidenceStore,
    roots: dict[int, RootRecord],
    envelopes: dict[int, EvidenceEnvelope],
    attempts: dict[int, PhysicalAcceptanceAttempt],
) -> None:
    attempt = _attempt_with(
        attempts[1],
        openedAtUtc=_utc_shift(attempts[0].opened_at_utc, -1),
    )
    _replace_attempt_revision(evidence, roots[1], envelopes[1], attempt)


def _install_p7(
    evidence: EvidenceStore,
    roots: dict[int, RootRecord],
    envelopes: dict[int, EvidenceEnvelope],
    attempts: dict[int, PhysicalAcceptanceAttempt],
) -> None:
    assert attempts[1].deadline_at_utc is not None
    attempt = _attempt_with(
        attempts[1],
        deadlineAtUtc=_utc_shift(attempts[1].deadline_at_utc, 1),
    )
    _replace_attempt_revision(evidence, roots[1], envelopes[1], attempt)


def _install_p8(
    evidence: EvidenceStore,
    roots: dict[int, RootRecord],
    envelopes: dict[int, EvidenceEnvelope],
    attempts: dict[int, PhysicalAcceptanceAttempt],
) -> None:
    identity = replace(
        envelopes[1].identity,
        session_id="t10-physical-reader-other",
    )
    envelope = _envelope_with(envelopes[1], identity=identity)
    _replace_root(evidence, roots[1], envelope, roots[1].metadata)


_VARIANTS = (
    _Variant("p1-root-revision", INTEGRITY_CODE, _install_p1),
    _Variant("p2-envelope-attempt-sha", INTEGRITY_CODE, _install_p2),
    _Variant("p3-previous-checkpoint", INTEGRITY_CODE, _install_p3),
    _Variant("p4-envelope-parents", INTEGRITY_CODE, _install_p4),
    _Variant("p5-produced-at", INTEGRITY_CODE, _install_p5),
    _Variant("p6-opened-at", INTEGRITY_CODE, _install_p6),
    # P7 is intentionally the rev1 deadline +1s semantic mismatch.  The
    # canonical links stay valid, so the public semantic reader reaches its
    # deadline formula guard rather than a model constructor or hash guard.
    _Variant("p7-deadline-plus-one-second", INTEGRITY_CODE, _install_p7),
    _Variant("p8-session-identity", IDENTITY_CODE, _install_p8),
)


def _build_public_prefix(
    tmp_path: Path,
) -> tuple[AcceptanceRecoveryContext, Path, Path, EvidenceStore]:
    project_root = tmp_path / "project"
    _write_physical_project(project_root)
    data_root = tmp_path / "data"
    session_id = "t10-physical-reader-public"
    context = AcceptanceRecoveryContext(
        project_root,
        data_root,
        session_id,
        clock=lambda: "2026-09-10T00:00:00.000000Z",
    )
    started = begin_acceptance_attempt(
        context,
        attempt_id=ATTEMPT_ID,
        scenario_id=PHYSICAL_SCENARIO_ID,
        scenario_version=PHYSICAL_SCENARIO_VERSION,
    )
    assert started.ok, _result_wire(started)
    checkpoint = checkpoint_acceptance_attempt(
        context,
        attempt_id=ATTEMPT_ID,
        expected_revision=0,
        stage="project-materialized",
    )
    assert checkpoint.ok, _result_wire(checkpoint)
    workspace = WorkspacePaths.from_roots(
        data_root,
        project_root,
        UUID(PROJECT_ID),
        session_id,
    )
    evidence = EvidenceStore(workspace.workspace_root / "evidence")
    return context, project_root, data_root, evidence


def test_public_physical_reader_refusals_restore_each_persisted_wire(
    tmp_path: Path,
) -> None:
    """Exercise P1-P6/P8 plus the rev1 deadline+1s public reader guards."""
    context, project_root, data_root, evidence = _build_public_prefix(tmp_path)
    baseline_show = _result_wire(
        show_acceptance_attempt(context, attempt_id=ATTEMPT_ID)
    )
    baseline_resume = _result_wire(
        resume_acceptance_attempt(context, attempt_id=ATTEMPT_ID)
    )
    assert baseline_show["ok"] is True
    assert baseline_resume["ok"] is True

    roots, envelopes, attempts = _load_chain_records(evidence)
    baseline_evidence = _file_snapshot(evidence.root)
    baseline_project, baseline_data = _persistence_snapshot(project_root, data_root)

    for variant in _VARIANTS:
        variant.install(evidence, roots, envelopes, attempts)
        corrupted_evidence = _file_snapshot(evidence.root)
        corrupted_project, corrupted_data = _persistence_snapshot(
            project_root, data_root
        )

        shown = show_acceptance_attempt(context, attempt_id=ATTEMPT_ID)
        _assert_failure(shown, "acceptance.attempt.show", variant.expected_code)
        _assert_snapshot(evidence.root, corrupted_evidence)
        _assert_snapshot(project_root, corrupted_project)
        _assert_snapshot(data_root, corrupted_data)

        resumed = resume_acceptance_attempt(context, attempt_id=ATTEMPT_ID)
        _assert_failure(resumed, "acceptance.attempt.resume", variant.expected_code)
        _assert_snapshot(evidence.root, corrupted_evidence)
        _assert_snapshot(project_root, corrupted_project)
        _assert_snapshot(data_root, corrupted_data)

        _restore_tree(evidence.root, baseline_evidence)
        _restore_tree(project_root, baseline_project)
        _restore_tree(data_root, baseline_data)
        _assert_snapshot(evidence.root, baseline_evidence)
        _assert_snapshot(project_root, baseline_project)
        _assert_snapshot(data_root, baseline_data)

        restored_show = show_acceptance_attempt(context, attempt_id=ATTEMPT_ID)
        restored_resume = resume_acceptance_attempt(context, attempt_id=ATTEMPT_ID)
        assert _result_wire(restored_show) == baseline_show
        assert _result_wire(restored_resume) == baseline_resume
        _assert_snapshot(evidence.root, baseline_evidence)
        _assert_snapshot(project_root, baseline_project)
        _assert_snapshot(data_root, baseline_data)
