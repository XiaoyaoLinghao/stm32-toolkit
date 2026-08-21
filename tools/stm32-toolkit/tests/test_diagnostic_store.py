from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import shutil
import tempfile
import threading
import time

import pytest

from stm32_toolkit.diagnostics import (
    DIAGNOSTIC_CHAIN_CORRUPT,
    DIAGNOSTIC_EVIDENCE_MISSING,
    DIAGNOSTIC_LIMIT_EXCEEDED,
    DIAGNOSTIC_REVISION_CONFLICT,
    DIAGNOSTIC_OPERATION_CONFLICT,
    DiagnosticEvent,
    DiagnosticValidationError,
    canonical_diagnostic_json_bytes,
    create_event,
)
from stm32_toolkit.diagnostics.store import DiagnosticStore
from stm32_toolkit.evidence import (
    ArtifactRef,
    EvidenceEnvelope,
    EvidenceIdentity,
)
from stm32_toolkit.evidence.gc import RootRecord, get_root, put_root
from stm32_toolkit.evidence.store import EvidenceStore
import stm32_toolkit.diagnostics.store as store_module


IDENTITY = EvidenceIdentity(
    workspace_id="a" * 64,
    project_id="12345678-1234-5678-1234-567812345678",
    session_id="toolkit-session",
    build_id="b" * 64,
    elf_sha256="c" * 64,
    target_device="host:windows/amd64",
    input_snapshot_sha256="d" * 64,
    git_commit="e" * 40,
    git_dirty=False,
)
SID = "f" * 32
FAILED_EVIDENCE_ID = "0" * 64
UTC = "2026-08-21T12:00:00.000000Z"


@pytest.fixture
def tmp_path():
    path = Path(tempfile.mkdtemp(prefix="stm32tk-0600-diagnostic-store-", dir=r"C:\tmp"))
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=False)


def _event(
    *,
    sequence: int,
    event_type: str,
    request: dict[str, object],
    result: dict[str, object],
    previous_digest: str | None = None,
    operation_id: str | None = None,
) -> DiagnosticEvent:
    return create_event(
        diagnostic_session_id=SID,
        operation_id=operation_id or f"op-{sequence}",
        sequence=sequence,
        revision_before=sequence,
        event_type=event_type,
        occurred_at_utc=UTC,
        actor="user",
        previous_digest=previous_digest,
        payload={"request": request, "result": result},
    )


def _failed_evidence(store: EvidenceStore, source_root: Path) -> str:
    source = source_root / "failed-run.json"
    source.write_bytes(b"failed run evidence")
    artifact = store.ingest_file(source, kind="test-run", media_type="application/json")
    envelope = EvidenceEnvelope(
        identity=IDENTITY,
        operation="test-run",
        produced_at_utc=UTC,
        parents=(),
        artifacts=(artifact,),
        metadata={"run": "failed"},
    )
    store.put_envelope(envelope)
    return str(envelope.evidence_id)


def _created(failed_evidence_id: str = FAILED_EVIDENCE_ID) -> DiagnosticEvent:
    return _event(
        sequence=0,
        event_type="session.created",
        request={"failed_test_run_id": "run-1"},
        result={"failed_evidence_id": failed_evidence_id, "identity": IDENTITY.to_dict()},
        operation_id="create-op",
    )


def _created_target(failed_evidence_id: str = FAILED_EVIDENCE_ID) -> DiagnosticEvent:
    return _event(
        sequence=0,
        event_type="session.created",
        request={"failed_test_run_id": "run-1", "failed_run_mode": "target"},
        result={"failed_evidence_id": failed_evidence_id, "identity": IDENTITY.to_dict()},
        operation_id="create-op",
    )


def _created_for(session_id: str, operation_id: str, failed_evidence_id: str) -> DiagnosticEvent:
    return create_event(
        diagnostic_session_id=session_id,
        operation_id=operation_id,
        sequence=0,
        revision_before=0,
        event_type="session.created",
        occurred_at_utc=UTC,
        actor="user",
        previous_digest=None,
        payload={
            "request": {"failed_test_run_id": "run-1"},
            "result": {"failed_evidence_id": failed_evidence_id, "identity": IDENTITY.to_dict()},
        },
    )


def _started(created: DiagnosticEvent, *, operation_id: str = "begin-op") -> DiagnosticEvent:
    return _event(
        sequence=1,
        event_type="investigation.started",
        request={},
        result={},
        previous_digest=created.digest,
        operation_id=operation_id,
    )


def test_create_append_and_reload_publishes_exact_event_checkpoints_and_roots(tmp_path: Path) -> None:
    evidence = EvidenceStore(tmp_path / "evidence")
    failed_evidence_id = _failed_evidence(evidence, tmp_path)
    store = DiagnosticStore(tmp_path / "diagnostics", evidence)
    created = _created(failed_evidence_id)

    created_record = store.create(created)
    started = _started(created)
    started_record = store.append(SID, started, expected_revision=1)

    assert created_record.appended is True
    assert started_record.appended is True
    assert started_record.session.revision == 2
    assert store.load(SID).to_dict() == started_record.session.to_dict()

    events_dir = tmp_path / "diagnostics" / "sessions" / SID / "events"
    for event, revision, parents in (
        (created, 1, (failed_evidence_id,)),
        (started, 2, (get_root(evidence, "diagnostic-session", f"{SID}.00000001").manifest_id,)),
    ):
        event_path = events_dir / f"{event.sequence:08d}.json"
        assert event_path.read_bytes() == canonical_diagnostic_json_bytes(event.to_dict())
        checkpoint_root = get_root(evidence, "diagnostic-session", f"{SID}.{revision:08d}")
        checkpoint_envelope = evidence.get_envelope(checkpoint_root.manifest_id)
        assert checkpoint_envelope.parents == parents
        assert checkpoint_envelope.metadata == {
            "diagnostic_session_id": SID,
            "sequence": event.sequence,
            "revision": revision,
            "event_digest": event.digest,
        }
        assert evidence.read_artifact(
            checkpoint_envelope.artifacts[0], maximum_bytes=1024 * 1024
        ) == event_path.read_bytes()

    event_path = events_dir / "00000001.json"
    root = get_root(evidence, "diagnostic-session", f"{SID}.00000002")
    envelope = evidence.get_envelope(root.manifest_id)
    assert envelope.operation == "diagnostic-event"
    assert envelope.identity == IDENTITY
    created_root = get_root(evidence, "diagnostic-session", f"{SID}.00000001")
    assert envelope.parents == (created_root.manifest_id,)
    assert envelope.metadata == {
        "diagnostic_session_id": SID,
        "sequence": 1,
        "revision": 2,
        "event_digest": started.digest,
    }
    assert len(envelope.artifacts) == 1
    assert envelope.artifacts[0].kind == "diagnostic-event"
    assert envelope.artifacts[0].media_type == "application/json"
    assert evidence.read_artifact(envelope.artifacts[0], maximum_bytes=1024 * 1024) == event_path.read_bytes()
    assert root.metadata == {
        "diagnostic_session_id": SID,
        "revision": 2,
        "state": "INVESTIGATING",
        "event_digest": started.digest,
    }


def test_retry_returns_original_event_and_current_session_without_appending(tmp_path: Path) -> None:
    evidence = EvidenceStore(tmp_path / "evidence")
    failed_evidence_id = _failed_evidence(evidence, tmp_path)
    store = DiagnosticStore(tmp_path / "diagnostics", evidence)
    created = _created(failed_evidence_id)
    first = store.create(created)
    store.append(SID, _started(created), expected_revision=1)

    retry = store.create(created)
    assert retry.appended is False
    assert retry.event == first.event == created
    assert retry.session.revision == 2
    assert len(list((tmp_path / "diagnostics" / "sessions" / SID / "events").iterdir())) == 2

    conflicting = _event(
        sequence=0,
        event_type="session.created",
        request={"failed_test_run_id": "different-run"},
        result={"failed_evidence_id": failed_evidence_id, "identity": IDENTITY.to_dict()},
        operation_id="create-op",
    )
    with pytest.raises(DiagnosticValidationError) as error:
        store.create(conflicting)
    assert error.value.code == DIAGNOSTIC_OPERATION_CONFLICT


@pytest.mark.parametrize("phase", ["event.after_publish", "artifact.after_ingest", "envelope.after_publish", "root.after_publish"])
def test_load_repairs_one_interrupted_publication_phase(tmp_path: Path, phase: str) -> None:
    evidence = EvidenceStore(tmp_path / "evidence")
    failed_evidence_id = _failed_evidence(evidence, tmp_path)
    fired = False

    def inject(point: str) -> None:
        nonlocal fired
        if point == phase and not fired:
            fired = True
            raise RuntimeError("interrupted")

    store = DiagnosticStore(tmp_path / "diagnostics", evidence, fault_injector=inject)
    with pytest.raises(RuntimeError, match="interrupted"):
        store.create(_created(failed_evidence_id))
    assert fired is True

    recovered = DiagnosticStore(tmp_path / "diagnostics", EvidenceStore(evidence.root))
    assert recovered.load(SID).revision == 1
    assert get_root(evidence, "diagnostic-session", f"{SID}.00000001").metadata["event_digest"] == _created(failed_evidence_id).digest


def test_existing_checkpoint_contradiction_fails_closed(tmp_path: Path) -> None:
    evidence = EvidenceStore(tmp_path / "evidence")
    failed_evidence_id = _failed_evidence(evidence, tmp_path)
    store = DiagnosticStore(tmp_path / "diagnostics", evidence)
    store.create(_created(failed_evidence_id))
    event_path = tmp_path / "diagnostics" / "sessions" / SID / "events" / "00000000.json"
    document = json.loads(event_path.read_text(encoding="utf-8"))
    document["payload"]["request"]["failed_test_run_id"] = "mutated"
    # Keep bytes canonical but make the immutable event no longer match its checkpoint.
    event_path.write_bytes(canonical_diagnostic_json_bytes(document))
    with pytest.raises(DiagnosticValidationError) as error:
        store.load(SID)
    assert error.value.code == DIAGNOSTIC_CHAIN_CORRUPT


def test_load_absent_is_read_only_and_missing_evidence_is_typed(tmp_path: Path) -> None:
    evidence = EvidenceStore(tmp_path / "evidence")
    diagnostics_root = tmp_path / "diagnostics"
    store = DiagnosticStore(diagnostics_root, evidence)
    with pytest.raises(DiagnosticValidationError) as error:
        store.load(SID)
    assert error.value.code == "DIAGNOSTIC_NOT_FOUND"
    assert not diagnostics_root.exists()

    with pytest.raises(DiagnosticValidationError) as error:
        store.create(_created())
    assert error.value.code == DIAGNOSTIC_EVIDENCE_MISSING


def test_creation_intent_query_is_bounded_and_does_not_dereference_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    evidence = EvidenceStore(tmp_path / "evidence")
    failed_evidence_id = _failed_evidence(evidence, tmp_path)
    store = DiagnosticStore(tmp_path / "diagnostics", evidence)
    store.create(_created_target(failed_evidence_id))

    def forbidden_evidence_read(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("creation intent must not dereference Evidence")

    monkeypatch.setattr(evidence, "get_envelope", forbidden_evidence_read)
    assert store.load_creation_intent(SID) == "target"


def test_load_preserves_provider_oserror_as_evidence_missing_cause(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    evidence = EvidenceStore(tmp_path / "evidence")
    failed_evidence_id = _failed_evidence(evidence, tmp_path)
    store = DiagnosticStore(tmp_path / "diagnostics", evidence)
    store.create(_created(failed_evidence_id))

    def provider_failure(*_args: object, **_kwargs: object) -> object:
        raise OSError("Evidence provider unavailable")

    monkeypatch.setattr(evidence, "get_envelope", provider_failure)
    with pytest.raises(DiagnosticValidationError) as error:
        store.load(SID)
    assert error.value.code == DIAGNOSTIC_EVIDENCE_MISSING
    cause = error.value.__cause__
    assert isinstance(cause, OSError)
    assert str(cause) == "Evidence provider unavailable"


def test_append_retry_returns_accepted_event_after_session_advanced(tmp_path: Path) -> None:
    evidence = EvidenceStore(tmp_path / "evidence")
    failed_evidence_id = _failed_evidence(evidence, tmp_path)
    store = DiagnosticStore(tmp_path / "diagnostics", evidence)
    created = _created(failed_evidence_id)
    store.create(created)
    started = _started(created)
    first = store.append(SID, started, expected_revision=1)
    retry = store.append(SID, started, expected_revision=1)
    assert retry.appended is False
    assert retry.event == first.event == started
    assert retry.session.revision == 2
    hypothesis = {
        "hypothesis_id": "1" * 32,
        "statement": "different intent",
        "status": "open",
        "confidence_basis": "unrated",
        "supporting": [],
        "refuting": [],
    }
    conflicting = create_event(
        diagnostic_session_id=SID,
        operation_id=started.operation_id,
        sequence=2,
        revision_before=2,
        event_type="hypothesis.added",
        occurred_at_utc=UTC,
        actor="user",
        previous_digest=started.digest,
        payload={"request": {"statement": hypothesis["statement"]}, "result": {"hypothesis": hypothesis}},
    )
    with pytest.raises(DiagnosticValidationError) as error:
        store.append(SID, conflicting, expected_revision=2)
    assert error.value.code == DIAGNOSTIC_OPERATION_CONFLICT


@pytest.mark.parametrize("expected_revision", [0, 2])
def test_stale_or_future_revision_appends_nothing(tmp_path: Path, expected_revision: int) -> None:
    evidence = EvidenceStore(tmp_path / "evidence")
    failed_evidence_id = _failed_evidence(evidence, tmp_path)
    store = DiagnosticStore(tmp_path / "diagnostics", evidence)
    created = _created(failed_evidence_id)
    store.create(created)
    started = _started(created, operation_id=f"begin-{expected_revision}")
    with pytest.raises(DiagnosticValidationError) as error:
        store.append(SID, started, expected_revision=expected_revision)
    assert error.value.code == DIAGNOSTIC_REVISION_CONFLICT
    assert store.load(SID).revision == 1
    assert list((tmp_path / "diagnostics" / "sessions" / SID / "events").iterdir()) == [
        tmp_path / "diagnostics" / "sessions" / SID / "events" / "00000000.json"
    ]


@pytest.mark.parametrize("mutation", ["missing", "extra", "noncanonical", "hard-link"])
def test_event_layout_contradictions_fail_closed(tmp_path: Path, mutation: str) -> None:
    evidence = EvidenceStore(tmp_path / "evidence")
    failed_evidence_id = _failed_evidence(evidence, tmp_path)
    store = DiagnosticStore(tmp_path / "diagnostics", evidence)
    store.create(_created(failed_evidence_id))
    events_dir = tmp_path / "diagnostics" / "sessions" / SID / "events"
    event_path = events_dir / "00000000.json"
    if mutation == "missing":
        event_path.unlink()
    elif mutation == "extra":
        (events_dir / "unexpected.txt").write_bytes(b"unexpected")
    elif mutation == "noncanonical":
        event_path.write_bytes(b" " + event_path.read_bytes())
    else:
        os.link(event_path, tmp_path / "event-hard-link.json")
    with pytest.raises(DiagnosticValidationError) as error:
        store.load(SID)
    assert error.value.code == DIAGNOSTIC_CHAIN_CORRUPT


def test_damaged_checkpoint_root_fails_without_rewriting_it(tmp_path: Path) -> None:
    evidence = EvidenceStore(tmp_path / "evidence")
    failed_evidence_id = _failed_evidence(evidence, tmp_path)
    store = DiagnosticStore(tmp_path / "diagnostics", evidence)
    store.create(_created(failed_evidence_id))
    root_path = next((evidence.root / "roots" / "diagnostic-session").glob("*.json"))
    original = root_path.read_bytes()
    document = json.loads(original)
    document["metadata"]["state"] = "INVESTIGATING"
    root_path.write_bytes(canonical_diagnostic_json_bytes(document))
    damaged = root_path.read_bytes()
    with pytest.raises(DiagnosticValidationError) as error:
        store.load(SID)
    assert error.value.code == DIAGNOSTIC_CHAIN_CORRUPT
    assert root_path.read_bytes() == damaged


@pytest.mark.parametrize("missing_kind", ["artifact", "envelope", "root"])
def test_missing_checkpoint_publication_is_repaired_from_the_event(tmp_path: Path, missing_kind: str) -> None:
    evidence = EvidenceStore(tmp_path / "evidence")
    failed_evidence_id = _failed_evidence(evidence, tmp_path)
    store = DiagnosticStore(tmp_path / "diagnostics", evidence)
    created = _created(failed_evidence_id)
    store.create(created)
    root = get_root(evidence, "diagnostic-session", f"{SID}.00000001")
    envelope = evidence.get_envelope(root.manifest_id)
    artifact_path = evidence.root.joinpath(*envelope.artifacts[0].relative_path.split("/"))
    manifest_path = evidence.root / "manifests" / f"{envelope.evidence_id}.json"
    root_path = next((evidence.root / "roots" / "diagnostic-session").glob("*.json"))
    if missing_kind == "artifact":
        artifact_path.unlink()
    elif missing_kind == "envelope":
        manifest_path.unlink()
    else:
        root_path.unlink()
    assert store.load(SID).revision == 1
    assert evidence.get_envelope(root.manifest_id) == envelope
    assert get_root(evidence, "diagnostic-session", f"{SID}.00000001") == root


def test_concurrent_appends_serialize_one_revision(tmp_path: Path) -> None:
    evidence = EvidenceStore(tmp_path / "evidence")
    failed_evidence_id = _failed_evidence(evidence, tmp_path)
    first_store = DiagnosticStore(tmp_path / "diagnostics", evidence)
    created = _created(failed_evidence_id)
    first_store.create(created)
    event_a = _started(created, operation_id="begin-a")
    event_b = _started(created, operation_id="begin-b")

    def append(event: DiagnosticEvent):
        return DiagnosticStore(tmp_path / "diagnostics", EvidenceStore(evidence.root)).append(
            SID, event, expected_revision=1
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(append, event) for event in (event_a, event_b)]
        results: list[object] = []
        for future in futures:
            try:
                results.append(future.result())
            except DiagnosticValidationError as error:
                results.append(error)
    successes = [result for result in results if not isinstance(result, Exception)]
    failures = [result for result in results if isinstance(result, DiagnosticValidationError)]
    assert len(successes) == 1
    assert len(failures) == 1
    assert failures[0].code == DIAGNOSTIC_REVISION_CONFLICT


def test_store_waits_for_lock_before_inspecting_prepublication_session_layout(tmp_path: Path) -> None:
    evidence = EvidenceStore(tmp_path / "evidence")
    failed_evidence_id = _failed_evidence(evidence, tmp_path)
    prepared = threading.Event()
    release = threading.Event()
    paused = True

    def inject(point: str) -> None:
        nonlocal paused
        if point == "session.after_prepare" and paused:
            paused = False
            prepared.set()
            assert release.wait(timeout=10)

    first_store = DiagnosticStore(tmp_path / "diagnostics", evidence, fault_injector=inject)
    created = _created(failed_evidence_id)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(first_store.create, created)
        assert prepared.wait(timeout=10)
        second = pool.submit(
            DiagnosticStore(tmp_path / "diagnostics", EvidenceStore(evidence.root)).load,
            SID,
        )
        time.sleep(0.2)
        assert not second.done()
        release.set()
        assert first.result(timeout=10).session.revision == 1
        assert second.result(timeout=10).revision == 1


def test_create_retry_validates_every_workspace_session_before_returning(tmp_path: Path) -> None:
    evidence = EvidenceStore(tmp_path / "evidence")
    failed_evidence_id = _failed_evidence(evidence, tmp_path)
    store = DiagnosticStore(tmp_path / "diagnostics", evidence)
    first_sid = "e" * 32
    first = _created_for(first_sid, "workspace-create", failed_evidence_id)
    second_sid = SID
    store.create(first)

    # Construct a canonical later session through the public Evidence APIs, but
    # give its session.created event the earlier workspace operation ID.
    duplicate = _created_for(second_sid, first.operation_id, failed_evidence_id)
    second_events_dir = tmp_path / "diagnostics" / "sessions" / second_sid / "events"
    second_events_dir.mkdir(parents=True)
    second_event_path = second_events_dir / "00000000.json"
    second_event_path.write_bytes(canonical_diagnostic_json_bytes(duplicate.to_dict()))
    artifact = evidence.ingest_file(second_event_path, kind="diagnostic-event", media_type="application/json")
    envelope = EvidenceEnvelope(
        identity=IDENTITY,
        operation="diagnostic-event",
        produced_at_utc=duplicate.occurred_at_utc,
        parents=(failed_evidence_id,),
        artifacts=(artifact,),
        metadata={
            "diagnostic_session_id": second_sid,
            "sequence": 0,
            "revision": 1,
            "event_digest": duplicate.digest,
        },
    )
    evidence.put_envelope(envelope)
    put_root(
        evidence,
        RootRecord(
            root_type="diagnostic-session",
            root_id=f"{second_sid}.00000001",
            manifest_id=str(envelope.evidence_id),
            metadata={
                "diagnostic_session_id": second_sid,
                "revision": 1,
                "state": "OPEN",
                "event_digest": duplicate.digest,
            },
        ),
    )
    event_bytes = second_event_path.read_bytes()
    roots_directory = evidence.root / "roots" / "diagnostic-session"
    root_bytes = {path.name: path.read_bytes() for path in roots_directory.glob("*.json")}
    with pytest.raises(DiagnosticValidationError) as error:
        store.create(first)
    assert error.value.code == DIAGNOSTIC_CHAIN_CORRUPT
    assert second_event_path.read_bytes() == event_bytes
    assert {path.name: path.read_bytes() for path in roots_directory.glob("*.json")} == root_bytes


def test_create_operation_scope_ignores_later_event_operation_ids(tmp_path: Path) -> None:
    evidence = EvidenceStore(tmp_path / "evidence")
    failed_evidence_id = _failed_evidence(evidence, tmp_path)
    store = DiagnosticStore(tmp_path / "diagnostics", evidence)
    created_a = _created(failed_evidence_id)
    store.create(created_a)
    shared_operation = _started(created_a, operation_id="shared-operation")
    store.append(SID, shared_operation, expected_revision=1)

    session_b = "e" * 32
    created_b = _created_for(session_b, "shared-operation", failed_evidence_id)
    record = store.create(created_b)

    assert record.appended is True
    assert store.load(SID).revision == 2
    assert store.load(session_b).revision == 1


def test_session_limit_is_checked_without_creating_a_new_session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    evidence = EvidenceStore(tmp_path / "evidence")
    failed_evidence_id = _failed_evidence(evidence, tmp_path)
    store = DiagnosticStore(tmp_path / "diagnostics", evidence)
    store.create(_created(failed_evidence_id))
    monkeypatch.setattr(store_module, "_MAX_SESSIONS", 1)
    second_sid = "e" * 32
    events_dir = tmp_path / "diagnostics" / "sessions" / SID / "events"
    event_bytes = {path.name: path.read_bytes() for path in events_dir.glob("*.json")}
    roots_directory = evidence.root / "roots" / "diagnostic-session"
    root_bytes = {path.name: path.read_bytes() for path in roots_directory.glob("*.json")}
    with pytest.raises(DiagnosticValidationError) as error:
        store.create(_created_for(second_sid, "second-create", failed_evidence_id))
    assert error.value.code == DIAGNOSTIC_LIMIT_EXCEEDED
    assert not (tmp_path / "diagnostics" / "sessions" / second_sid).exists()
    assert {path.name: path.read_bytes() for path in events_dir.glob("*.json")} == event_bytes
    assert {path.name: path.read_bytes() for path in roots_directory.glob("*.json")} == root_bytes
    assert store.load(SID).revision == 1


def test_event_limit_is_checked_without_creating_a_new_event(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    evidence = EvidenceStore(tmp_path / "evidence")
    failed_evidence_id = _failed_evidence(evidence, tmp_path)
    store = DiagnosticStore(tmp_path / "diagnostics", evidence)
    created = _created(failed_evidence_id)
    store.create(created)
    monkeypatch.setattr(store_module, "MAX_EVENTS", 1)
    started = _started(created, operation_id="limit-begin")
    roots_directory = evidence.root / "roots" / "diagnostic-session"
    root_bytes = {path.name: path.read_bytes() for path in roots_directory.glob("*.json")}
    events_dir = tmp_path / "diagnostics" / "sessions" / SID / "events"
    event_bytes = {path.name: path.read_bytes() for path in events_dir.glob("*.json")}
    with pytest.raises(DiagnosticValidationError) as error:
        store.append(SID, started, expected_revision=1)
    assert error.value.code == DIAGNOSTIC_LIMIT_EXCEEDED
    assert sorted(path.name for path in events_dir.iterdir()) == ["00000000.json"]
    assert {path.name: path.read_bytes() for path in events_dir.glob("*.json")} == event_bytes
    assert {path.name: path.read_bytes() for path in roots_directory.glob("*.json")} == root_bytes
    assert store.load(SID).revision == 1


def test_event_redirect_is_rejected_without_root_mutation(tmp_path: Path) -> None:
    evidence = EvidenceStore(tmp_path / "evidence")
    failed_evidence_id = _failed_evidence(evidence, tmp_path)
    store = DiagnosticStore(tmp_path / "diagnostics", evidence)
    store.create(_created(failed_evidence_id))
    event_path = tmp_path / "diagnostics" / "sessions" / SID / "events" / "00000000.json"
    redirect_target = tmp_path / "redirect-target.json"
    redirect_target.write_bytes(event_path.read_bytes())
    try:
        event_path.unlink()
        os.symlink(redirect_target, event_path)
    except (OSError, NotImplementedError) as error:
        pytest.skip(f"Windows symlink creation unavailable: {error}")
    roots_directory = evidence.root / "roots" / "diagnostic-session"
    root_bytes = {path.name: path.read_bytes() for path in roots_directory.glob("*.json")}
    with pytest.raises(DiagnosticValidationError) as error:
        store.load(SID)
    assert error.value.code == DIAGNOSTIC_CHAIN_CORRUPT
    assert event_path.is_symlink()
    assert {path.name: path.read_bytes() for path in roots_directory.glob("*.json")} == root_bytes
