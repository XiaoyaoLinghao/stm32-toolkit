"""Public fail-closed boundaries for diagnostic-store root and chain authority."""

from __future__ import annotations

from pathlib import Path

import pytest

from stm32_toolkit.diagnostics import (
    DIAGNOSTIC_CHAIN_CORRUPT,
    DIAGNOSTIC_INVALID_EVENT,
    DIAGNOSTIC_NOT_FOUND,
    DiagnosticValidationError,
    canonical_diagnostic_json_bytes,
    create_event,
)
from stm32_toolkit.diagnostics.store import DiagnosticStore
from stm32_toolkit.evidence.store import EvidenceStore

from test_diagnostic_store import (
    FAILED_EVIDENCE_ID,
    SID,
    UTC,
    _authority_snapshot,
    _created,
    _created_for,
    _event,
    _failed_evidence,
    _started,
)


CHAIN_CORRUPT_MESSAGE = "event/checkpoint/root chain is missing or contradictory"


def _created_store(tmp_path: Path) -> tuple[DiagnosticStore, EvidenceStore, Path]:
    evidence = EvidenceStore(tmp_path / "evidence")
    failed_evidence_id = _failed_evidence(evidence, tmp_path)
    root = tmp_path / "diagnostics"
    store = DiagnosticStore(root, evidence)
    store.create(_created(failed_evidence_id))
    return store, evidence, root


@pytest.mark.parametrize(
    "operation",
    [
        "append",
        "resolve-operation",
        "resolve-accepted-operation",
        "load-durable",
    ],
)
def test_absent_root_operations_report_not_found_without_creating_authority(
    tmp_path: Path, operation: str
) -> None:
    evidence = EvidenceStore(tmp_path / "evidence")
    diagnostics_root = tmp_path / "diagnostics"
    store = DiagnosticStore(diagnostics_root, evidence)
    created = _created()
    before = _authority_snapshot(diagnostics_root, evidence.root)

    with pytest.raises(DiagnosticValidationError) as error:
        if operation == "append":
            store.append(SID, _started(created), expected_revision=1)
        elif operation == "resolve-operation":
            store.resolve_operation(
                SID,
                "absent-root-op",
                event_type="investigation.started",
                actor="user",
                request={},
            )
        elif operation == "resolve-accepted-operation":
            store.resolve_accepted_operation(
                SID,
                "absent-root-op",
                event_type="investigation.started",
                actor="user",
            )
        else:
            store.load_durable(SID)

    assert error.value.code == DIAGNOSTIC_NOT_FOUND
    assert not diagnostics_root.exists()
    assert _authority_snapshot(diagnostics_root, evidence.root) == before


@pytest.mark.parametrize("layout", ["empty-root", "sessions-only", "lock-only"])
def test_incomplete_root_read_refusal_preserves_layout(
    tmp_path: Path, layout: str
) -> None:
    evidence = EvidenceStore(tmp_path / "evidence")
    diagnostics_root = tmp_path / "diagnostics"
    diagnostics_root.mkdir()
    if layout == "sessions-only":
        (diagnostics_root / "sessions").mkdir()
    elif layout == "lock-only":
        (diagnostics_root / ".diagnostic.lock").write_bytes(b"\0")
    store = DiagnosticStore(diagnostics_root, evidence)
    before = _authority_snapshot(diagnostics_root, evidence.root)

    with pytest.raises(DiagnosticValidationError) as error:
        store.load(SID)

    assert error.value.code == DIAGNOSTIC_CHAIN_CORRUPT
    assert str(error.value) == CHAIN_CORRUPT_MESSAGE
    assert _authority_snapshot(diagnostics_root, evidence.root) == before


def test_read_path_rejects_two_byte_lock_without_repair(tmp_path: Path) -> None:
    store, evidence, diagnostics_root = _created_store(tmp_path)
    lock = diagnostics_root / ".diagnostic.lock"
    lock.write_bytes(b"xx")
    before = _authority_snapshot(diagnostics_root, evidence.root)

    with pytest.raises(DiagnosticValidationError) as error:
        store.load(SID)

    assert error.value.code == DIAGNOSTIC_CHAIN_CORRUPT
    assert str(error.value) == CHAIN_CORRUPT_MESSAGE
    assert lock.read_bytes() == b"xx"
    assert _authority_snapshot(diagnostics_root, evidence.root) == before


def _creation_intent_root(tmp_path: Path) -> Path:
    diagnostics_root = tmp_path / "diagnostics"
    diagnostics_root.mkdir()
    (diagnostics_root / ".diagnostic.lock").write_bytes(b"\0")
    events = diagnostics_root / "sessions" / SID / "events"
    events.mkdir(parents=True)
    return events


@pytest.mark.parametrize("case", ["wrong-event-type", "foreign-session-binding"])
def test_creation_intent_refuses_non_creation_event_zero(
    tmp_path: Path, case: str
) -> None:
    evidence = EvidenceStore(tmp_path / "evidence")
    events = _creation_intent_root(tmp_path)
    if case == "wrong-event-type":
        event = _event(
            sequence=0,
            event_type="investigation.started",
            request={},
            result={},
            operation_id="intent-wrong-type",
        )
    else:
        event = _created_for("a" * 32, "intent-foreign-session", FAILED_EVIDENCE_ID)
    (events / "00000000.json").write_bytes(
        canonical_diagnostic_json_bytes(event.to_dict())
    )
    store = DiagnosticStore(tmp_path / "diagnostics", evidence)
    before = _authority_snapshot(tmp_path / "diagnostics", evidence.root)

    with pytest.raises(DiagnosticValidationError) as error:
        store.load_creation_intent(SID)

    assert error.value.code == DIAGNOSTIC_CHAIN_CORRUPT
    assert str(error.value) == CHAIN_CORRUPT_MESSAGE
    assert _authority_snapshot(tmp_path / "diagnostics", evidence.root) == before


def test_creation_intent_refuses_after_prepare_crash_prefix(tmp_path: Path) -> None:
    evidence = EvidenceStore(tmp_path / "evidence")
    failed_evidence_id = _failed_evidence(evidence, tmp_path)
    diagnostics_root = tmp_path / "diagnostics"
    fired = False

    def inject(point: str) -> None:
        nonlocal fired
        if point == "session.after_prepare" and not fired:
            fired = True
            raise RuntimeError("crash after prepare")

    store = DiagnosticStore(diagnostics_root, evidence, fault_injector=inject)
    with pytest.raises(RuntimeError, match="^crash after prepare$"):
        store.create(_created(failed_evidence_id))
    assert fired is True
    events = diagnostics_root / "sessions" / SID / "events"
    assert events.is_dir()
    assert not list(events.iterdir())

    reader = DiagnosticStore(diagnostics_root, EvidenceStore(evidence.root))
    before = _authority_snapshot(diagnostics_root, evidence.root)
    with pytest.raises(DiagnosticValidationError) as intent_error:
        reader.load_creation_intent(SID)
    assert intent_error.value.code == DIAGNOSTIC_CHAIN_CORRUPT
    with pytest.raises(DiagnosticValidationError) as load_error:
        reader.load(SID)
    assert load_error.value.code == DIAGNOSTIC_CHAIN_CORRUPT
    assert _authority_snapshot(diagnostics_root, evidence.root) == before


@pytest.mark.parametrize(
    "case",
    ["repeated-creation", "wrong-prior-digest", "repeated-investigation-start"],
)
def test_load_rejects_model_valid_events_that_break_chain_semantics(
    tmp_path: Path, case: str
) -> None:
    evidence = EvidenceStore(tmp_path / "evidence")
    failed_evidence_id = _failed_evidence(evidence, tmp_path)
    diagnostics_root = tmp_path / "diagnostics"
    store = DiagnosticStore(diagnostics_root, evidence)
    created = _created(failed_evidence_id)
    store.create(created)
    events = diagnostics_root / "sessions" / SID / "events"

    if case == "repeated-creation":
        illegal = create_event(
            diagnostic_session_id=SID,
            operation_id="illegal-transition-created",
            sequence=1,
            revision_before=1,
            event_type="session.created",
            occurred_at_utc=UTC,
            actor="user",
            previous_digest=created.digest,
            payload=created.to_dict()["payload"],
        )
    elif case == "wrong-prior-digest":
        illegal = create_event(
            diagnostic_session_id=SID,
            operation_id="illegal-transition-digest",
            sequence=1,
            revision_before=1,
            event_type="investigation.started",
            occurred_at_utc=UTC,
            actor="user",
            previous_digest="0" * 64,
            payload={"request": {}, "result": {}},
        )
    else:
        started = _started(created)
        store.append(SID, started, expected_revision=1)
        illegal = create_event(
            diagnostic_session_id=SID,
            operation_id="illegal-transition-state",
            sequence=2,
            revision_before=2,
            event_type="investigation.started",
            occurred_at_utc=UTC,
            actor="user",
            previous_digest=started.digest,
            payload={"request": {}, "result": {}},
        )

    (events / f"{illegal.sequence:08d}.json").write_bytes(
        canonical_diagnostic_json_bytes(illegal.to_dict())
    )
    before = _authority_snapshot(diagnostics_root, evidence.root)
    with pytest.raises(DiagnosticValidationError) as error:
        store.load(SID)

    assert error.value.code == DIAGNOSTIC_CHAIN_CORRUPT
    assert str(error.value) == CHAIN_CORRUPT_MESSAGE
    assert _authority_snapshot(diagnostics_root, evidence.root) == before


@pytest.mark.parametrize(
    "request_payload",
    [{"x": object()}, {"x": float("nan")}],
    ids=["unsupported-object", "nan"],
)
def test_operation_request_canonicalization_refusal_precedes_root_layout(
    tmp_path: Path, request_payload: dict[str, object]
) -> None:
    evidence = EvidenceStore(tmp_path / "evidence")
    diagnostics_root = tmp_path / "diagnostics"
    diagnostics_root.mkdir()
    store = DiagnosticStore(diagnostics_root, evidence)
    before = _authority_snapshot(diagnostics_root, evidence.root)

    with pytest.raises(DiagnosticValidationError) as error:
        store.resolve_operation(
            SID,
            "canonicalization-op",
            event_type="investigation.started",
            actor="user",
            request=request_payload,
        )

    assert error.value.code == DIAGNOSTIC_INVALID_EVENT
    assert _authority_snapshot(diagnostics_root, evidence.root) == before
