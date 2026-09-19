from __future__ import annotations

from dataclasses import fields, replace
from hashlib import sha256
import json
from pathlib import Path
from uuid import UUID

import pytest

from stm32_monitor.history import MAX_HISTORY_BATCHES, HistoryPage, HistoryQuery, HistoryStore
from stm32_monitor.models import ObservationBinding, SampleBatch, SampleValue, WatchItem
from stm32_monitor.protocol import ProtocolResult
from stm32_monitor.replay import (
    EVIDENCE_INTEGRITY_FAILURE,
    ENVIRONMENT_FAILURE,
    MONITOR_REPLAY_INVALID,
    MONITOR_PHYSICAL_INVALID,
    OPERATION_CONFLICT,
    MonitorReplayError,
    MonitorRunRef,
    MonitorRunRefV2,
    canonical_replay_json_bytes,
    publish_physical_monitor_run,
    load_monitor_run_reference,
)
from stm32_toolkit.evidence import EvidenceEnvelope, EvidenceIdentity
from stm32_toolkit.evidence.model import canonical_json_bytes
from stm32_toolkit.evidence.store import EvidenceStore
from stm32_toolkit.paths import WorkspacePaths
from stm32_toolkit.diagnostic_workflows import (
    DiagnosticWorkflowContext,
    diagnostic_show,
    diagnostic_start,
)
from stm32_toolkit.testing.model import TestCaseResult as _TestCaseResult
from stm32_toolkit.testing.model import TestRunManifest as _TestRunManifest
from stm32_toolkit.testing.model import calculate_inventory_digest as _calculate_inventory_digest
from stm32_toolkit.testing.publication import TestRunPublisher as _TestRunPublisher


def _physical_v2_candidate() -> dict[str, object]:
    project_id = "123e4567-e89b-42d3-a456-426614174000"
    workspace_id = "a" * 64
    session_id = "physical-session"
    run_id = "11111111-1111-4111-8111-111111111111"
    payload: dict[str, object] = {
        "schema": "stm32-monitor-run-ref/2",
        "operation_id": run_id,
        "scenario_role": "failed-before",
        "execution_source": "physical",
        "physical_transport_evidence": True,
        "origin_workspace_id": workspace_id,
        "import_workspace_id": workspace_id,
        "logical_project_id": project_id,
        "origin_session_id": session_id,
        "projected_session_id": session_id,
        "origin_run_id": run_id,
        "projected_run_id": run_id,
        "target_device": "stm32:stm32f429zi",
        "probe_id": sha256(b"probe/serial/01").hexdigest(),
        "physical_target": "stm32f429zi",
        "build_id": "b" * 64,
        "elf_sha256": "c" * 64,
        "input_snapshot_sha256": "d" * 64,
        "git_head": "e" * 40,
        "git_dirty": False,
        "flash_session_id": "flash-session-01",
        "lease_id": "lease-01",
        "dwarf_sha256": "f" * 64,
        "svd_sha256": None,
        "group_id": "22222222-2222-4222-8222-222222222222",
        "group_revision": 1,
        "start_sequence": 0,
        "end_sequence_exclusive": 2,
        "start_captured_unix_ns": 1_700_000_000_000_000_000,
        "end_captured_unix_ns_exclusive": 1_700_000_000_002_000_000,
        "source_record_sha256": "1" * 64,
        "projected_batch_sha256s": ["2" * 64, "3" * 64],
        "transcript_evidence_id": "4" * 64,
        "run_ref_sha256": "0" * 64,
    }
    payload["run_ref_sha256"] = sha256(
        canonical_json_bytes(
            {key: value for key, value in payload.items() if key != "run_ref_sha256"}
        )
    ).hexdigest()
    return payload


def test_physical_v2_reference_uses_source_record_and_forbids_v1_fixture() -> None:
    payload = _physical_v2_candidate()

    reference = MonitorRunRef.from_value(payload)

    assert reference.schema == "stm32-monitor-run-ref/2"
    assert isinstance(reference, MonitorRunRefV2)
    assert reference.to_dict() == payload
    assert "source_record_sha256" in reference.to_dict()
    assert "fixture_sha256" not in reference.to_dict()


def test_failed_physical_target_diagnostic_starts_and_reloads_bound_session(
    tmp_path: Path,
) -> None:
    paths, evidence, test_run_id, raw_probe, monitor_run_id, _group_id = _physical_context(tmp_path)
    _publish_physical_test_run(
        paths,
        evidence,
        test_run_id=test_run_id,
        raw_probe=raw_probe,
        monitor_run_id=monitor_run_id,
    )
    context = DiagnosticWorkflowContext(paths.project_root, paths.data_root, paths.session_id)
    started = diagnostic_start(
        context,
        operation_id="physical-diagnostic-start",
        failed_test_run_id=test_run_id,
        failed_run_mode="target",
    )
    assert started.ok, started.to_dict()
    session = started.data["session"]
    assert session["failed_run_mode"] == "target"
    reloaded = diagnostic_show(
        DiagnosticWorkflowContext(paths.project_root, paths.data_root, paths.session_id),
        diagnostic_session_id=session["diagnostic_session_id"],
    )
    assert reloaded.ok, reloaded.to_dict()
    assert reloaded.data["session"]["failed_run_mode"] == "target"


def test_physical_target_diagnostic_rejects_foreign_current_session_before_create(
    tmp_path: Path,
) -> None:
    paths, evidence, test_run_id, raw_probe, monitor_run_id, _group_id = _physical_context(tmp_path)
    _publish_physical_test_run(
        paths,
        evidence,
        test_run_id=test_run_id,
        raw_probe=raw_probe,
        monitor_run_id=monitor_run_id,
        session_id="foreign-physical-session",
    )

    context = DiagnosticWorkflowContext(paths.project_root, paths.data_root, paths.session_id)
    result = diagnostic_start(
        context,
        operation_id="physical-foreign-session-start",
        failed_test_run_id=test_run_id,
        failed_run_mode="target",
    )

    assert result.ok is False
    assert result.code == "INCOMPATIBLE_IDENTITY"
    sessions = paths.diagnostics_root / "sessions"
    assert not sessions.exists() or not any(sessions.rglob("*.json"))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("probe_id", "replay:probe-v2"),
        ("target_device", "replay"),
        ("physical_target", "replay:non-physical"),
        ("flash_session_id", "replay"),
        ("lease_id", "replay:lease"),
    ],
)
def test_physical_v2_reference_rejects_replay_hardware_labels(
    field: str,
    value: str,
) -> None:
    payload = _physical_v2_candidate()
    payload[field] = value
    payload["run_ref_sha256"] = sha256(
        canonical_json_bytes(
            {key: value for key, value in payload.items() if key != "run_ref_sha256"}
        )
    ).hexdigest()

    with pytest.raises(MonitorReplayError):
        MonitorRunRef.from_value(payload)


def test_public_run_reference_union_rejects_replay_v2_discriminator() -> None:
    payload = _physical_v2_candidate()
    payload.update(
        {
            "execution_source": "replay",
            "physical_transport_evidence": False,
            "probe_id": "replay:probe-v2",
            "physical_target": "replay:non-physical",
            "flash_session_id": "replay:no-flash",
            "lease_id": "replay:no-lease",
        }
    )
    payload["run_ref_sha256"] = sha256(
        canonical_json_bytes(
            {key: value for key, value in payload.items() if key != "run_ref_sha256"}
        )
    ).hexdigest()

    with pytest.raises(MonitorReplayError):
        MonitorRunRef.from_value(payload)


@pytest.mark.parametrize(
    "case",
    ["v2-direct-schema", "v2-parser-existing-instance"],
    ids=("v2-direct-schema", "v2-parser-existing-instance"),
)
def test_public_physical_v2_constructor_parser_boundary_matrix(case: str) -> None:
    payload = _physical_v2_candidate()
    reference = MonitorRunRefV2.from_value(payload)
    before = reference.to_dict()

    if case == "v2-direct-schema":
        values = {item.name: getattr(reference, item.name) for item in fields(reference)}
        values["schema"] = "stm32-monitor-run-ref/1"
        with pytest.raises(MonitorReplayError) as error:
            MonitorRunRefV2(**values)
        assert error.value.code == MONITOR_REPLAY_INVALID
        assert error.value.args == ("monitor run reference schema is invalid",)
    else:
        returned = MonitorRunRefV2.from_value(reference)
        assert returned is reference
        assert returned.to_dict() == before == payload

    assert reference.to_dict() == before


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("source_record_sha256", "invalid"),
        ("git_head", "g" * 40),
        ("git_dirty", 1),
        ("group_revision", 0),
        ("start_sequence", True),
        ("end_captured_unix_ns_exclusive", 0),
        ("projected_batch_sha256s", ["invalid"]),
        ("transcript_evidence_id", "invalid"),
    ],
)
def test_public_physical_v2_reference_rejects_invalid_identity_and_windows(
    field: str,
    replacement: object,
) -> None:
    payload = _physical_v2_candidate()
    payload[field] = replacement
    payload["run_ref_sha256"] = sha256(
        canonical_json_bytes(
            {key: value for key, value in payload.items() if key != "run_ref_sha256"}
        )
    ).hexdigest()

    with pytest.raises(MonitorReplayError):
        MonitorRunRefV2.from_value(payload)


def _physical_context(tmp_path: Path) -> tuple[WorkspacePaths, EvidenceStore, str, str, UUID, UUID]:
    project = tmp_path / "project"
    project.mkdir()
    (project / ".stm32-project.json").write_text(
        json.dumps(
            {
                "schemaVersion": 3,
                "logicalProjectId": "123e4567-e89b-42d3-a456-426614174000",
                "generatedBy": {"tool": "stm32-toolkit", "version": "0.6"},
                "project": {"name": "physical-monitor", "origin": "manual"},
                "target": {"device": "stm32:stm32f429zi", "core": "cortex-m4"},
                "framework": {"type": "bare-metal", "version": None},
                "build": {
                    "sources": [],
                    "includePaths": [],
                    "defines": [],
                    "compileOptions": [],
                    "assemblySources": [],
                    "presets": [],
                    "elf": None,
                },
                "memory": {"source": "manual", "regions": []},
                "debug": {"backend": "pyocd", "target": "board:fixture-01", "svd": None},
                "generation": {
                    "cubeMxIoc": None,
                    "managedManifest": ".stm32-toolkit/generated-files.json",
                    "generatedDirectories": [],
                    "userDirectories": [],
                },
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    paths = WorkspacePaths.from_roots(
        tmp_path / "state",
        project,
        UUID("123e4567-e89b-42d3-a456-426614174000"),
        "physical-monitor",
    )
    evidence = EvidenceStore(paths.workspace_root / "evidence")
    test_run_id = "physical-test-run-01"
    monitor_run_id = UUID("11111111-1111-4111-8111-111111111111")
    group_id = UUID("22222222-2222-4222-8222-222222222222")
    return paths, evidence, test_run_id, "probe/serial/01", monitor_run_id, group_id


def _publish_physical_test_run(
    paths: WorkspacePaths,
    evidence: EvidenceStore,
    *,
    test_run_id: str,
    raw_probe: str,
    monitor_run_id: UUID,
    state: str = "failed",
    build_id: str = "b" * 64,
    elf_sha256: str = "c" * 64,
    input_snapshot_sha256: str = "d" * 64,
    git_head: str = "e" * 40,
    session_id: str | None = None,
    case_id: str = "case.counter",
    inventory_digest: str | None = None,
    lease_id: str = "lease-01",
) -> None:
    assert state in {"failed", "passed"}
    case_state = state
    run_session_id = paths.session_id if session_id is None else session_id
    identity = EvidenceIdentity(
        workspace_id=paths.workspace_id,
        project_id="123e4567-e89b-42d3-a456-426614174000",
        session_id=run_session_id,
        build_id=build_id,
        elf_sha256=elf_sha256,
        target_device="stm32:stm32f429zi",
        input_snapshot_sha256=input_snapshot_sha256,
        git_commit=git_head,
        git_dirty=False,
    )
    stored_inventory_digest = (
        _calculate_inventory_digest("target", identity, (case_id,))
        if inventory_digest is None
        else inventory_digest
    )
    raw_source = paths.project_root / "events.bin"
    raw_source.write_bytes(b"physical-events")
    raw_events = evidence.ingest_file(
        raw_source,
        kind="test-events",
        media_type="application/vnd.stm32.target-events",
    )
    manifest = _TestRunManifest(
        "stm32-test/1",
        test_run_id,
        "target",
        state,
        identity,
        "semihosting",
        (
            _TestCaseResult(
                case_id,
                case_state,
                "2026-08-22T00:00:00.000000Z",
                "2026-08-22T00:00:00.001000Z",
                1 if state == "failed" else 0,
                "expected failure" if state == "failed" else None,
                None,
                None,
            ),
        ),
        "2026-08-22T00:00:00.000000Z",
        "2026-08-22T00:00:00.001000Z",
        1,
        None,
        None,
        raw_events,
    )
    manifest_source = paths.project_root / "manifest.json"
    manifest_source.write_bytes(canonical_json_bytes(manifest.to_dict()))
    manifest_artifact = evidence.ingest_file(
        manifest_source,
        kind="test-manifest",
        media_type="application/json",
    )
    digest = sha256(b"physical-action").hexdigest()
    envelope = EvidenceEnvelope(
        identity=identity,
        operation="target-test-physical",
        produced_at_utc=manifest.ended_at_utc,
        parents=(),
        artifacts=(manifest_artifact, raw_events),
        metadata={
            "action_digest": digest,
            "execution_source": "physical",
            "flash_session_id": "flash-session-01",
            "import_session_id": run_session_id,
            "import_workspace_id": paths.workspace_id,
            "intent_digest": digest,
            "inventory_digest": stored_inventory_digest,
            "lease_id": lease_id,
            "origin_session_id": run_session_id,
            "origin_workspace_id": paths.workspace_id,
            "physical_transport_evidence": True,
            "probe_id": sha256(raw_probe.encode("utf-8")).hexdigest(),
            "target_id": identity.target_device,
            "transport_config_digest": "2" * 64,
        },
    )
    evidence.put_envelope(envelope)
    _TestRunPublisher(
        evidence,
        paths.project_root,
        paths.data_root / "results",
    ).publish_target_physical(manifest, envelope)


def _append_physical_history(
    paths: WorkspacePaths,
    raw_probe: str,
    monitor_run_id: UUID,
    group_id: UUID,
    *,
    scenario_role: str = "failed-before",
    value_offset: int = 0,
    build_id: str = "b" * 64,
    elf_sha256: str = "c" * 64,
    input_snapshot_sha256: str = "d" * 64,
    git_head: str = "e" * 40,
    lease_id: str = "lease-01",
) -> tuple[SampleBatch, ...]:
    binding = ObservationBinding(
        workspace_id=paths.workspace_id,
        logical_project_id="123e4567-e89b-42d3-a456-426614174000",
        session_id=paths.session_id,
        probe_id=raw_probe,
        target_device="stm32:stm32f429zi",
        physical_target="board:fixture-01",
        build_id=build_id,
        elf_sha256=elf_sha256,
        input_snapshot_sha256=input_snapshot_sha256,
        git_head=git_head,
        git_dirty=False,
        flash_session_id="flash-session-01",
        lease_id=lease_id,
        dwarf_sha256="f" * 64,
        svd_sha256=None,
    )
    batches = tuple(
        SampleBatch(
            binding=binding,
            group_id=group_id,
            group_revision=1,
            run_id=monitor_run_id,
            sequence=sequence,
            scheduled_unix_ns=1_700_000_000_000_000_000 + sequence * 1_000_000,
            captured_unix_ns=1_700_000_000_000_000_100 + sequence * 1_000_000,
            latency_ns=100,
            actual_rate_hz=1000.0,
            subscriber_drops=0,
            history_drops=0,
            deadline_drops=0,
            values=(
                SampleValue(
                    WatchItem.variable("counter"),
                    "OK",
                    typed_value={"type": "uint32", "value": sequence + value_offset},
                ),
            ),
        )
        for sequence in range(2)
    )
    history = HistoryStore(paths)
    try:
        appended = history.append_batches(batches)
        assert appended.ok, appended.to_dict()
    finally:
        history.close()
    return batches


def _append_large_physical_history(
    paths: WorkspacePaths,
    raw_probe: str,
    monitor_run_id: UUID,
    group_id: UUID,
    *,
    batch_count: int = 40,
    values_per_batch: int = 250,
    definition_chars: int = 256,
) -> tuple[SampleBatch, ...]:
    binding = ObservationBinding(
        workspace_id=paths.workspace_id,
        logical_project_id="123e4567-e89b-42d3-a456-426614174000",
        session_id=paths.session_id,
        probe_id=raw_probe,
        target_device="stm32:stm32f429zi",
        physical_target="board:fixture-01",
        build_id="b" * 64,
        elf_sha256="c" * 64,
        input_snapshot_sha256="d" * 64,
        git_head="e" * 40,
        git_dirty=False,
        flash_session_id="flash-session-01",
        lease_id="lease-01",
        dwarf_sha256="f" * 64,
        svd_sha256=None,
    )
    watches = tuple(
        WatchItem.variable(f"counter-{index:03d}")
        for index in range(values_per_batch)
    )
    batches = tuple(
        SampleBatch(
            binding=binding,
            group_id=group_id,
            group_revision=1,
            run_id=monitor_run_id,
            sequence=sequence,
            scheduled_unix_ns=1_700_000_000_000_000_000 + sequence * 1_000_000,
            captured_unix_ns=1_700_000_000_000_000_100 + sequence * 1_000_000,
            latency_ns=100,
            actual_rate_hz=1000.0,
            subscriber_drops=0,
            history_drops=0,
            deadline_drops=0,
            values=tuple(
                SampleValue(
                    watch,
                    "OK",
                    typed_value={"type": "uint32", "value": sequence * values_per_batch + index},
                    definition={"description": "x" * definition_chars},
                )
                for index, watch in enumerate(watches)
            ),
        )
        for sequence in range(batch_count)
    )
    history = HistoryStore(paths)
    try:
        for offset in range(0, len(batches), MAX_HISTORY_BATCHES):
            appended = history.append_batches(
                batches[offset : offset + MAX_HISTORY_BATCHES]
            )
            assert appended.ok, appended.to_dict()
    finally:
        history.close()
    return batches


def test_physical_large_history_reassembles_cursor_fragments_and_allows_over_one_mib(
    tmp_path: Path,
) -> None:
    paths, evidence, test_run_id, raw_probe, monitor_run_id, group_id = _physical_context(tmp_path)
    _publish_physical_test_run(
        paths,
        evidence,
        test_run_id=test_run_id,
        raw_probe=raw_probe,
        monitor_run_id=monitor_run_id,
    )
    batches = _append_large_physical_history(paths, raw_probe, monitor_run_id, group_id)
    request = {
        "scenario_role": "failed-before",
        "test_run_id": test_run_id,
        "run_id": str(monitor_run_id),
        "group_id": str(group_id),
        "start_sequence": 0,
        "end_sequence_exclusive": 40,
        "start_captured_unix_ns": batches[0].captured_unix_ns,
        "end_captured_unix_ns_exclusive": batches[-1].captured_unix_ns + 1,
        "probe_id": raw_probe,
    }

    reference = publish_physical_monitor_run(paths, evidence, **request)

    transcript_root = json.loads(
        _monitor_root_files(evidence, "monitor-run")[0].read_bytes().decode("utf-8")
    )
    transcript_manifest = json.loads(
        (
            evidence.root
            / "manifests"
            / f"{transcript_root['manifest_id']}.json"
        ).read_bytes().decode("utf-8")
    )
    transcript_artifact = transcript_manifest["artifacts"][0]
    transcript_bytes = (
        evidence.root / transcript_artifact["relative_path"]
    ).read_bytes()
    assert len(transcript_bytes) > 1024 * 1024
    assert load_monitor_run_reference(
        paths,
        EvidenceStore(evidence.root),
        str(monitor_run_id),
    ) == reference


@pytest.mark.parametrize(
    ("mutation", "expected_message"),
    (
        (
            "reordered",
            "physical Monitor history fragments are reordered or incomplete",
        ),
        (
            "metadata",
            "physical Monitor history fragment metadata changed",
        ),
        (
            "gap",
            "physical Monitor history fragments have a gap or overlap",
        ),
        (
            "chain",
            "physical Monitor history sample chain is invalid",
        ),
    ),
    ids=("reordered", "metadata", "gap", "chain"),
)
def test_physical_history_fragment_discontinuities_reject_before_roots(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
    expected_message: str,
) -> None:
    from stm32_monitor import replay as replay_module

    def prepare(root: Path):
        root.mkdir()
        paths, evidence, test_run_id, raw_probe, monitor_run_id, group_id = _physical_context(root)
        _publish_physical_test_run(
            paths,
            evidence,
            test_run_id=test_run_id,
            raw_probe=raw_probe,
            monitor_run_id=monitor_run_id,
        )
        batches = _append_large_physical_history(
            paths,
            raw_probe,
            monitor_run_id,
            group_id,
            batch_count=(
                1
                if mutation in {"metadata", "gap"}
                else 3
                if mutation == "reordered"
                else 2
            ),
            values_per_batch=2,
        )
        request = {
            "scenario_role": "failed-before",
            "test_run_id": test_run_id,
            "run_id": str(monitor_run_id),
            "group_id": str(group_id),
            "start_sequence": batches[0].sequence,
            "end_sequence_exclusive": batches[-1].sequence + 1,
            "start_captured_unix_ns": batches[0].captured_unix_ns,
            "end_captured_unix_ns_exclusive": batches[-1].captured_unix_ns + 1,
            "probe_id": raw_probe,
        }
        return paths, evidence, monitor_run_id, request

    def evidence_snapshot(evidence: EvidenceStore) -> tuple[tuple[str, bytes], ...]:
        return tuple(
            sorted(
                (
                    path.relative_to(evidence.root).as_posix(),
                    path.read_bytes(),
                )
                for path in evidence.root.rglob("*")
                if path.is_file()
            )
        )

    baseline_paths, baseline_evidence, baseline_run_id, baseline_request = prepare(
        tmp_path / "baseline"
    )
    baseline_reference = publish_physical_monitor_run(
        baseline_paths,
        baseline_evidence,
        **baseline_request,
    )
    assert len(_monitor_root_files(baseline_evidence, "monitor-run")) == 1
    assert len(_monitor_root_files(baseline_evidence, "monitor-run-ref")) == 1
    assert load_monitor_run_reference(
        baseline_paths,
        EvidenceStore(baseline_evidence.root),
        str(baseline_run_id),
    ) == baseline_reference

    paths, evidence, monitor_run_id, request = prepare(tmp_path / "mutation")
    before_tree = evidence_snapshot(evidence)
    original_query = replay_module.HistoryStore.query_history
    query_calls = 0

    def mutated_query(history: HistoryStore, query: HistoryQuery):
        nonlocal query_calls
        query_calls += 1
        effective_query = (
            replace(query, limit=1)
            if mutation in {"reordered", "metadata", "gap"}
            else query
        )
        result = original_query(history, effective_query)
        assert result.ok and result.data is not None
        page = result.data
        changed_page = page
        if mutation == "reordered" and query_calls == 5:
            assert len(page.batches) == 1
            changed_page = HistoryPage.create(
                (replace(page.batches[0], sequence=0),),
                next_cursor=page.next_cursor,
            )
        elif mutation == "metadata" and query_calls == 2:
            assert len(page.batches) == 1
            changed_page = HistoryPage.create(
                (replace(page.batches[0], latency_ns=page.batches[0].latency_ns + 1),),
                next_cursor=page.next_cursor,
            )
        elif mutation == "gap" and query_calls == 2:
            assert len(page.batches) == 1
            changed_page = HistoryPage.create(
                (replace(page.batches[0], start_ordinal=0),),
                next_cursor=page.next_cursor,
            )
        elif mutation == "chain":
            assert query_calls == 1
            assert len(page.batches) == 2
            second = page.batches[1]
            changed_values = (
                replace(second.values[0], watch=WatchItem.variable("other")),
                *second.values[1:],
            )
            changed_page = HistoryPage.create(
                (page.batches[0], replace(second, values=changed_values)),
                next_cursor=page.next_cursor,
            )
        return ProtocolResult(
            ok=True,
            operation=result.operation,
            code=result.code,
            message=result.message,
            data=changed_page,
            details=result.details,
        )

    monkeypatch.setattr(
        replay_module.HistoryStore,
        "query_history",
        mutated_query,
    )
    with pytest.raises(MonitorReplayError) as error:
        publish_physical_monitor_run(paths, evidence, **request)

    assert error.value.code == "INCOMPATIBLE_IDENTITY"
    assert error.value.message == expected_message
    assert query_calls >= 1
    assert _monitor_root_files(evidence, "monitor-run") == ()
    assert _monitor_root_files(evidence, "monitor-run-ref") == ()
    assert _monitor_manifest_operations(evidence) == ()
    assert evidence_snapshot(evidence) == before_tree


def test_physical_history_allows_more_fragments_than_reconstructed_batch_limit(
    tmp_path: Path,
) -> None:
    paths, evidence, test_run_id, raw_probe, monitor_run_id, group_id = _physical_context(tmp_path)
    _publish_physical_test_run(
        paths,
        evidence,
        test_run_id=test_run_id,
        raw_probe=raw_probe,
        monitor_run_id=monitor_run_id,
    )
    batches = _append_large_physical_history(
        paths,
        raw_probe,
        monitor_run_id,
        group_id,
        batch_count=1024,
        values_per_batch=9,
    )
    pages = []
    history = HistoryStore(paths)
    try:
        cursor = None
        while True:
            result = history.query_history(
                HistoryQuery(
                    session_id=paths.session_id,
                    start_ns=batches[0].captured_unix_ns,
                    end_ns=batches[-1].captured_unix_ns + 1,
                    limit=10_000,
                    cursor=cursor,
                    run_id=monitor_run_id,
                    group_id=group_id,
                )
            )
            assert result.ok and result.data is not None
            pages.append(result.data)
            if result.data.next_cursor is None:
                break
            cursor = result.data.next_cursor
    finally:
        history.close()
    assert sum(page.value_count for page in pages) == 9_216
    assert sum(len(page.batches) for page in pages) == 1_025

    reference = publish_physical_monitor_run(
        paths,
        evidence,
        scenario_role="failed-before",
        test_run_id=test_run_id,
        run_id=str(monitor_run_id),
        group_id=str(group_id),
        start_sequence=0,
        end_sequence_exclusive=1024,
        start_captured_unix_ns=batches[0].captured_unix_ns,
        end_captured_unix_ns_exclusive=batches[-1].captured_unix_ns + 1,
        probe_id=raw_probe,
    )
    assert load_monitor_run_reference(paths, EvidenceStore(evidence.root), str(monitor_run_id)) == reference


def test_physical_history_allows_monitor_bounded_typed_strings(
    tmp_path: Path,
) -> None:
    paths, evidence, test_run_id, raw_probe, monitor_run_id, group_id = _physical_context(tmp_path)
    _publish_physical_test_run(
        paths,
        evidence,
        test_run_id=test_run_id,
        raw_probe=raw_probe,
        monitor_run_id=monitor_run_id,
    )
    binding = ObservationBinding(
        workspace_id=paths.workspace_id,
        logical_project_id="123e4567-e89b-42d3-a456-426614174000",
        session_id=paths.session_id,
        probe_id=raw_probe,
        target_device="stm32:stm32f429zi",
        physical_target="board:fixture-01",
        build_id="b" * 64,
        elf_sha256="c" * 64,
        input_snapshot_sha256="d" * 64,
        git_head="e" * 40,
        git_dirty=False,
        flash_session_id="flash-session-01",
        lease_id="lease-01",
        dwarf_sha256="f" * 64,
        svd_sha256=None,
    )
    typed_payload = "x" * 70_000
    batches = tuple(
        SampleBatch(
            binding=binding,
            group_id=group_id,
            group_revision=1,
            run_id=monitor_run_id,
            sequence=sequence,
            scheduled_unix_ns=1_700_000_000_000_000_000 + sequence * 1_000_000,
            captured_unix_ns=1_700_000_000_000_000_100 + sequence * 1_000_000,
            latency_ns=100,
            actual_rate_hz=1000.0,
            subscriber_drops=0,
            history_drops=0,
            deadline_drops=0,
            values=(
                SampleValue(
                    WatchItem.variable("large-string"),
                    "OK",
                    typed_value={"payload": typed_payload},
                ),
            ),
        )
        for sequence in range(2)
    )
    history = HistoryStore(paths)
    try:
        appended = history.append_batches(batches)
        assert appended.ok, appended.to_dict()
    finally:
        history.close()

    reference = publish_physical_monitor_run(
        paths,
        evidence,
        scenario_role="failed-before",
        test_run_id=test_run_id,
        run_id=str(monitor_run_id),
        group_id=str(group_id),
        start_sequence=0,
        end_sequence_exclusive=2,
        start_captured_unix_ns=batches[0].captured_unix_ns,
        end_captured_unix_ns_exclusive=batches[-1].captured_unix_ns + 1,
        probe_id=raw_probe,
    )
    assert load_monitor_run_reference(paths, EvidenceStore(evidence.root), str(monitor_run_id)) == reference


def test_physical_history_rejects_more_reconstructed_batches_before_root_writes(
    tmp_path: Path,
) -> None:
    paths, evidence, test_run_id, raw_probe, monitor_run_id, group_id = _physical_context(tmp_path)
    _publish_physical_test_run(
        paths,
        evidence,
        test_run_id=test_run_id,
        raw_probe=raw_probe,
        monitor_run_id=monitor_run_id,
    )
    batches = _append_large_physical_history(
        paths,
        raw_probe,
        monitor_run_id,
        group_id,
        batch_count=1025,
        values_per_batch=1,
        definition_chars=0,
    )

    with pytest.raises(MonitorReplayError) as failure:
        publish_physical_monitor_run(
            paths,
            evidence,
            scenario_role="failed-before",
            test_run_id=test_run_id,
            run_id=str(monitor_run_id),
            group_id=str(group_id),
            start_sequence=0,
            end_sequence_exclusive=1025,
            start_captured_unix_ns=batches[0].captured_unix_ns,
            end_captured_unix_ns_exclusive=batches[-1].captured_unix_ns + 1,
            probe_id=raw_probe,
        )

    assert failure.value.code == "INCOMPATIBLE_IDENTITY"
    assert _monitor_root_files(evidence, "monitor-run") == ()
    assert _monitor_root_files(evidence, "monitor-run-ref") == ()


def test_physical_history_window_publishes_and_fresh_loads_v2_reference(tmp_path: Path) -> None:
    paths, evidence, test_run_id, raw_probe, monitor_run_id, group_id = _physical_context(tmp_path)
    _publish_physical_test_run(
        paths,
        evidence,
        test_run_id=test_run_id,
        raw_probe=raw_probe,
        monitor_run_id=monitor_run_id,
    )
    binding = ObservationBinding(
        workspace_id=paths.workspace_id,
        logical_project_id="123e4567-e89b-42d3-a456-426614174000",
        session_id=paths.session_id,
        probe_id=raw_probe,
        target_device="stm32:stm32f429zi",
        physical_target="board:fixture-01",
        build_id="b" * 64,
        elf_sha256="c" * 64,
        input_snapshot_sha256="d" * 64,
        git_head="e" * 40,
        git_dirty=False,
        flash_session_id="flash-session-01",
        lease_id="lease-01",
        dwarf_sha256="f" * 64,
        svd_sha256=None,
    )
    batches = tuple(
        SampleBatch(
            binding=binding,
            group_id=group_id,
            group_revision=1,
            run_id=monitor_run_id,
            sequence=sequence,
            scheduled_unix_ns=1_700_000_000_000_000_000 + sequence * 1_000_000,
            captured_unix_ns=1_700_000_000_000_000_100 + sequence * 1_000_000,
            latency_ns=100,
            actual_rate_hz=1000.0,
            subscriber_drops=0,
            history_drops=0,
            deadline_drops=0,
            values=(
                SampleValue(
                    WatchItem.variable("counter"),
                    "OK",
                    typed_value={"type": "uint32", "value": sequence},
                ),
            ),
        )
        for sequence in range(2)
    )
    history = HistoryStore(paths)
    try:
        appended = history.append_batches(batches)
        assert appended.ok, appended.to_dict()
    finally:
        history.close()

    reference = publish_physical_monitor_run(
        paths,
        evidence,
        scenario_role="failed-before",
        test_run_id=test_run_id,
        run_id=str(monitor_run_id),
        group_id=str(group_id),
        start_sequence=0,
        end_sequence_exclusive=2,
        start_captured_unix_ns=batches[0].captured_unix_ns,
        end_captured_unix_ns_exclusive=batches[-1].captured_unix_ns + 1,
        probe_id=raw_probe,
    )

    assert reference.schema == "stm32-monitor-run-ref/2"
    assert reference.execution_source == "physical"
    assert reference.physical_transport_evidence is True
    assert reference.probe_id == sha256(raw_probe.encode("utf-8")).hexdigest()
    assert raw_probe not in canonical_json_bytes(reference.to_dict()).decode("utf-8")
    for durable_json in (paths.workspace_root / "evidence").rglob("*.json"):
        assert raw_probe.encode("utf-8") not in durable_json.read_bytes()
    fresh = load_monitor_run_reference(
        WorkspacePaths.from_roots(
            paths.data_root,
            paths.project_root,
            UUID("123e4567-e89b-42d3-a456-426614174000"),
            paths.session_id,
        ),
        EvidenceStore(paths.workspace_root / "evidence"),
        str(monitor_run_id),
    )
    assert fresh == reference


def test_physical_publication_accepts_sequential_leases_and_retains_each_authority(
    tmp_path: Path,
) -> None:
    paths, evidence, test_run_id, raw_probe, monitor_run_id, group_id = _physical_context(tmp_path)
    target_lease_id = "target-lease-01"
    monitor_lease_id = "monitor-lease-01"
    _publish_physical_test_run(
        paths,
        evidence,
        test_run_id=test_run_id,
        raw_probe=raw_probe,
        monitor_run_id=monitor_run_id,
        lease_id=target_lease_id,
    )
    target_root_files = tuple((evidence.root / "roots" / "test-run").glob("*.json"))
    assert len(target_root_files) == 1
    target_root_path = target_root_files[0]
    target_root_before = target_root_path.read_bytes()
    request = _physical_request(
        paths,
        raw_probe,
        monitor_run_id,
        group_id,
        test_run_id,
        monitor_lease_id=monitor_lease_id,
    )

    reference = publish_physical_monitor_run(paths, evidence, **request)

    assert reference.lease_id == monitor_lease_id
    assert load_monitor_run_reference(
        paths,
        EvidenceStore(evidence.root),
        str(monitor_run_id),
    ).lease_id == monitor_lease_id
    assert target_root_path.read_bytes() == target_root_before
    assert json.loads(target_root_before.decode("utf-8"))["metadata"]["lease_id"] == target_lease_id


def test_physical_cli_is_a_thin_sanitized_workflow_adapter(tmp_path: Path, monkeypatch) -> None:
    from stm32_monitor import cli as cli_module

    paths, evidence, _test_run_id, raw_probe, monitor_run_id, group_id = _physical_context(tmp_path)
    candidate = MonitorRunRefV2.from_value(_physical_v2_candidate())
    calls: list[dict[str, object]] = []

    def publish(*args, **kwargs):
        calls.append(kwargs)
        return candidate

    monkeypatch.setattr(cli_module, "_load_context", lambda arguments: (paths, evidence))
    monkeypatch.setattr(cli_module, "publish_physical_monitor_run", publish)
    output = __import__("io").StringIO()

    code = cli_module.main(
        [
            "physical",
            "publish",
            "--project",
            str(paths.project_root),
            "--data-root",
            str(paths.data_root),
            "--session-id",
            paths.session_id,
            "--scenario-role",
            "failed-before",
            "--test-run-id",
            "physical-test-run-01",
            "--run-id",
            str(monitor_run_id),
            "--group-id",
            str(group_id),
            "--start-sequence",
            "0",
            "--end-sequence-exclusive",
            "2",
            "--start-captured-unix-ns",
            "1700000000000000100",
            "--end-captured-unix-ns-exclusive",
            "1700000000001000101",
            "--probe-id",
            raw_probe,
            "--json",
        ],
        _stdout=output,
    )

    assert code == 0
    assert len(calls) == 1
    assert calls[0]["probe_id"] == raw_probe
    assert json.loads(output.getvalue())["data"]["monitor_run_ref"]["schema"] == "stm32-monitor-run-ref/2"
    assert raw_probe not in output.getvalue()


def test_physical_cli_preserves_operation_conflict(tmp_path: Path, monkeypatch) -> None:
    from stm32_monitor import cli as cli_module

    paths, evidence, _test_run_id, raw_probe, monitor_run_id, group_id = _physical_context(tmp_path)

    monkeypatch.setattr(cli_module, "_load_context", lambda arguments: (paths, evidence))
    monkeypatch.setattr(
        cli_module,
        "publish_physical_monitor_run",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            MonitorReplayError(OPERATION_CONFLICT, "operation conflict")
        ),
    )
    output = __import__("io").StringIO()

    code = cli_module.main(
        [
            "physical",
            "publish",
            "--project",
            str(paths.project_root),
            "--data-root",
            str(paths.data_root),
            "--session-id",
            paths.session_id,
            "--scenario-role",
            "failed-before",
            "--test-run-id",
            "physical-test-run-01",
            "--run-id",
            str(monitor_run_id),
            "--group-id",
            str(group_id),
            "--start-sequence",
            "0",
            "--end-sequence-exclusive",
            "2",
            "--start-captured-unix-ns",
            "1700000000000000100",
            "--end-captured-unix-ns-exclusive",
            "1700000000001000101",
            "--probe-id",
            raw_probe,
            "--json",
        ],
        _stdout=output,
    )

    assert code == 1
    assert json.loads(output.getvalue())["code"] == OPERATION_CONFLICT


def test_complete_reference_intent_conflict_precedes_history_query(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from stm32_monitor import replay as replay_module

    paths, evidence, test_run_id, raw_probe, monitor_run_id, group_id = _physical_context(tmp_path)
    _publish_physical_test_run(
        paths,
        evidence,
        test_run_id=test_run_id,
        raw_probe=raw_probe,
        monitor_run_id=monitor_run_id,
    )
    request = _physical_request(
        paths,
        raw_probe,
        monitor_run_id,
        group_id,
        test_run_id,
    )
    publish_physical_monitor_run(paths, evidence, **request)

    def query_must_not_run(*args, **kwargs):
        raise AssertionError("changed complete-reference intent queried live History")

    monkeypatch.setattr(replay_module.HistoryStore, "query_history", query_must_not_run)
    with pytest.raises(MonitorReplayError) as conflict:
        publish_physical_monitor_run(
            paths,
            EvidenceStore(evidence.root),
            **{**request, "scenario_role": "fixed-after"},
        )
    assert conflict.value.code == OPERATION_CONFLICT
    assert _monitor_root_files(evidence, "monitor-run")
    assert _monitor_root_files(evidence, "monitor-run-ref")


def test_physical_transcript_size_limit_fails_before_durable_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from stm32_monitor import replay as replay_module

    paths, evidence, test_run_id, raw_probe, monitor_run_id, group_id = _physical_context(tmp_path)
    _publish_physical_test_run(
        paths,
        evidence,
        test_run_id=test_run_id,
        raw_probe=raw_probe,
        monitor_run_id=monitor_run_id,
    )
    request = _physical_request(
        paths,
        raw_probe,
        monitor_run_id,
        group_id,
        test_run_id,
    )
    monkeypatch.setattr(replay_module, "MAX_PHYSICAL_TRANSCRIPT_BYTES", 1)

    with pytest.raises(MonitorReplayError) as failure:
        publish_physical_monitor_run(paths, evidence, **request)

    assert failure.value.code == MONITOR_PHYSICAL_INVALID
    assert _monitor_root_files(evidence, "monitor-run") == ()
    assert _monitor_root_files(evidence, "monitor-run-ref") == ()
    assert _monitor_manifest_operations(evidence) == ()


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("scenario_role", "fixed-after"),
        ("target_device", "stm32:stm32f411"),
        ("probe_id", sha256(b"other-probe").hexdigest()),
        ("git_dirty", True),
        ("group_revision", 2),
    ],
)
def test_physical_loader_rejects_coherent_reference_field_drift(
    tmp_path: Path,
    field: str,
    replacement: object,
) -> None:
    paths, evidence, test_run_id, raw_probe, monitor_run_id, group_id = _physical_context(tmp_path)
    _publish_physical_test_run(
        paths,
        evidence,
        test_run_id=test_run_id,
        raw_probe=raw_probe,
        monitor_run_id=monitor_run_id,
    )
    request = _physical_request(
        paths,
        raw_probe,
        monitor_run_id,
        group_id,
        test_run_id,
    )
    original = publish_physical_monitor_run(paths, evidence, **request)
    payload = original.to_dict()
    payload[field] = replacement
    payload["run_ref_sha256"] = sha256(
        canonical_json_bytes(
            {key: value for key, value in payload.items() if key != "run_ref_sha256"}
        )
    ).hexdigest()
    candidate = MonitorRunRefV2.from_value(payload)

    reference_root_path = _monitor_root_files(evidence, "monitor-run-ref")[0]
    reference_root = json.loads(reference_root_path.read_bytes().decode("utf-8"))
    original_envelope = evidence.get_envelope(reference_root["manifest_id"])
    reference_source = tmp_path / f"drifted-{field}.json"
    reference_bytes = canonical_json_bytes(candidate.to_dict())
    reference_source.write_bytes(reference_bytes)
    reference_artifact = evidence.ingest_file(
        reference_source,
        kind="monitor-run-ref",
        media_type="application/json",
    )
    reference_metadata = dict(original_envelope.metadata)
    reference_metadata["run_ref_sha256"] = candidate.run_ref_sha256
    reference_metadata["scenario_role"] = candidate.scenario_role
    reference_metadata["source_record_sha256"] = candidate.source_record_sha256
    replacement_envelope = EvidenceEnvelope(
        identity=original_envelope.identity,
        operation=original_envelope.operation,
        produced_at_utc=original_envelope.produced_at_utc,
        parents=original_envelope.parents,
        artifacts=(reference_artifact,),
        metadata=reference_metadata,
    )
    evidence.put_envelope(replacement_envelope)
    reference_root["manifest_id"] = str(replacement_envelope.evidence_id)
    reference_root["metadata"] = reference_metadata
    reference_root_path.write_bytes(canonical_json_bytes(reference_root))

    with pytest.raises(MonitorReplayError) as failure:
        load_monitor_run_reference(paths, EvidenceStore(evidence.root), str(monitor_run_id))
    assert failure.value.code == EVIDENCE_INTEGRITY_FAILURE


def _monitor_root_files(evidence: EvidenceStore, root_type: str) -> tuple[Path, ...]:
    directory = evidence.root / "roots" / root_type
    return tuple(directory.glob("*.json")) if directory.exists() else ()


def _physical_evidence_state(evidence: EvidenceStore) -> dict[str, bytes]:
    return {
        str(path.relative_to(evidence.root)): path.read_bytes()
        for path in evidence.root.rglob("*")
        if path.is_file()
    }


def _replace_persisted_physical_transcript(
    tmp_path: Path,
    evidence: EvidenceStore,
    reference: MonitorRunRefV2,
    mutation: str,
) -> None:
    transcript_root_path = _monitor_root_files(evidence, "monitor-run")[0]
    reference_root_path = _monitor_root_files(evidence, "monitor-run-ref")[0]
    transcript_root = json.loads(transcript_root_path.read_bytes().decode("utf-8"))
    reference_root = json.loads(reference_root_path.read_bytes().decode("utf-8"))
    stored_transcript = evidence.get_envelope(transcript_root["manifest_id"])
    original_raw = evidence.read_artifact(
        stored_transcript.artifacts[0],
        maximum_bytes=64 * 1024 * 1024,
    )
    if mutation == "bom":
        mutated_raw = b"\xef\xbb\xbf" + original_raw
    elif mutation == "duplicate-key":
        canonical_raw = original_raw[:-1] if original_raw.endswith(b"\n") else original_raw
        assert canonical_raw.endswith(b"}")
        mutated_raw = (
            canonical_raw[:-1]
            + b',"schema":"stm32-monitor-physical-transcript/1",'
            b'"schema":"stm32-monitor-physical-transcript/1"}'
        )
    elif mutation == "noncanonical":
        mutated_raw = original_raw + b"\n"
    elif mutation == "scalar-root":
        mutated_raw = b"[]"
    else:
        raise AssertionError(f"unknown physical transcript mutation: {mutation}")

    source_digest = sha256(mutated_raw).hexdigest()
    transcript_source = tmp_path / f"physical-transcript-{mutation}.json"
    transcript_source.write_bytes(mutated_raw)
    transcript_artifact = evidence.ingest_file(
        transcript_source,
        kind="monitor-physical-transcript",
        media_type="application/json",
    )
    transcript_metadata = dict(stored_transcript.metadata)
    transcript_metadata["source_record_sha256"] = source_digest
    replacement_transcript = EvidenceEnvelope(
        identity=stored_transcript.identity,
        operation=stored_transcript.operation,
        produced_at_utc=stored_transcript.produced_at_utc,
        parents=stored_transcript.parents,
        artifacts=(transcript_artifact,),
        metadata=transcript_metadata,
    )
    evidence.put_envelope(replacement_transcript)

    reference_payload = reference.to_dict()
    reference_payload["source_record_sha256"] = source_digest
    reference_payload["transcript_evidence_id"] = str(replacement_transcript.evidence_id)
    unsigned_reference = {
        key: value
        for key, value in reference_payload.items()
        if key != "run_ref_sha256"
    }
    reference_payload["run_ref_sha256"] = sha256(
        canonical_replay_json_bytes(unsigned_reference)
    ).hexdigest()
    updated_reference = MonitorRunRefV2.from_value(reference_payload)

    stored_reference = evidence.get_envelope(reference_root["manifest_id"])
    reference_source = tmp_path / f"physical-reference-{mutation}.json"
    reference_source.write_bytes(canonical_replay_json_bytes(updated_reference.to_dict()))
    reference_artifact = evidence.ingest_file(
        reference_source,
        kind="monitor-run-ref",
        media_type="application/json",
    )
    reference_metadata = dict(stored_reference.metadata)
    reference_metadata["source_record_sha256"] = updated_reference.source_record_sha256
    reference_metadata["run_ref_sha256"] = updated_reference.run_ref_sha256
    replacement_reference = EvidenceEnvelope(
        identity=stored_reference.identity,
        operation=stored_reference.operation,
        produced_at_utc=stored_reference.produced_at_utc,
        parents=(str(replacement_transcript.evidence_id),),
        artifacts=(reference_artifact,),
        metadata=reference_metadata,
    )
    evidence.put_envelope(replacement_reference)

    transcript_root["manifest_id"] = str(replacement_transcript.evidence_id)
    transcript_root_metadata = dict(transcript_root["metadata"])
    transcript_root_metadata["source_record_sha256"] = updated_reference.source_record_sha256
    transcript_root_metadata["run_ref_sha256"] = updated_reference.run_ref_sha256
    transcript_root["metadata"] = transcript_root_metadata
    transcript_root_path.write_bytes(canonical_json_bytes(transcript_root))

    reference_root["manifest_id"] = str(replacement_reference.evidence_id)
    reference_root["metadata"] = reference_metadata
    reference_root_path.write_bytes(canonical_json_bytes(reference_root))


def _monitor_manifest_operations(evidence: EvidenceStore) -> tuple[str, ...]:
    directory = evidence.root / "manifests"
    if not directory.exists():
        return ()
    operations: list[str] = []
    for path in directory.glob("*.json"):
        document = json.loads(path.read_bytes().decode("utf-8"))
        operation = document.get("operation")
        if operation in {"monitor-physical-window", "monitor-run-ref"}:
            operations.append(operation)
    return tuple(sorted(operations))


def _physical_request(
    paths: WorkspacePaths,
    raw_probe: str,
    monitor_run_id: UUID,
    group_id: UUID,
    test_run_id: str,
    *,
    monitor_lease_id: str = "lease-01",
) -> dict[str, object]:
    batches = _append_physical_history(
        paths,
        raw_probe,
        monitor_run_id,
        group_id,
        lease_id=monitor_lease_id,
    )
    return {
        "scenario_role": "failed-before",
        "test_run_id": test_run_id,
        "run_id": str(monitor_run_id),
        "group_id": str(group_id),
        "start_sequence": 0,
        "end_sequence_exclusive": 2,
        "start_captured_unix_ns": batches[0].captured_unix_ns,
        "end_captured_unix_ns_exclusive": batches[-1].captured_unix_ns + 1,
        "probe_id": raw_probe,
    }


@pytest.mark.parametrize(
    ("fault_point", "occurrence", "transcript_root", "reference_root", "operations"),
    [
        ("artifact.after_publish", 1, False, False, ()),
        ("manifest.after_publish", 1, False, False, ("monitor-physical-window",)),
        ("gc-root.after_publish", 1, True, False, ("monitor-physical-window",)),
        (
            "artifact.after_publish",
            2,
            True,
            False,
            ("monitor-physical-window",),
        ),
        (
            "manifest.after_publish",
            2,
            True,
            False,
            ("monitor-physical-window", "monitor-run-ref"),
        ),
        (
            "gc-root.after_publish",
            2,
            True,
            True,
            ("monitor-physical-window", "monitor-run-ref"),
        ),
    ],
)
def test_physical_provider_fault_retains_only_valid_prefix_and_retry_resumes(
    tmp_path: Path,
    fault_point: str,
    occurrence: int,
    transcript_root: bool,
    reference_root: bool,
    operations: tuple[str, ...],
) -> None:
    paths, evidence, test_run_id, raw_probe, monitor_run_id, group_id = _physical_context(tmp_path)
    _publish_physical_test_run(
        paths,
        evidence,
        test_run_id=test_run_id,
        raw_probe=raw_probe,
        monitor_run_id=monitor_run_id,
    )
    request = _physical_request(
        paths,
        raw_probe,
        monitor_run_id,
        group_id,
        test_run_id,
    )
    seen = 0

    def inject(point: str) -> None:
        nonlocal seen
        if point == fault_point:
            seen += 1
            if seen == occurrence:
                raise OSError("injected provider failure")

    faulty = EvidenceStore(evidence.root, fault_injector=inject)
    with pytest.raises(MonitorReplayError) as failure:
        publish_physical_monitor_run(paths, faulty, **request)
    assert failure.value.code == ENVIRONMENT_FAILURE
    assert bool(_monitor_root_files(faulty, "monitor-run")) is transcript_root
    assert bool(_monitor_root_files(faulty, "monitor-run-ref")) is reference_root
    assert _monitor_manifest_operations(faulty) == operations

    retry = publish_physical_monitor_run(
        paths,
        EvidenceStore(evidence.root),
        **request,
    )
    assert retry.schema == "stm32-monitor-run-ref/2"
    assert _monitor_root_files(evidence, "monitor-run")
    assert _monitor_root_files(evidence, "monitor-run-ref")
    assert load_monitor_run_reference(
        paths,
        EvidenceStore(evidence.root),
        str(monitor_run_id),
    ) == retry


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [("malformed", EVIDENCE_INTEGRITY_FAILURE), ("contradictory", OPERATION_CONFLICT)],
)
def test_physical_malformed_or_contradictory_prefix_fails_closed(
    tmp_path: Path,
    mutation: str,
    expected_code: str,
) -> None:
    paths, evidence, test_run_id, raw_probe, monitor_run_id, group_id = _physical_context(tmp_path)
    _publish_physical_test_run(
        paths,
        evidence,
        test_run_id=test_run_id,
        raw_probe=raw_probe,
        monitor_run_id=monitor_run_id,
    )
    request = _physical_request(
        paths,
        raw_probe,
        monitor_run_id,
        group_id,
        test_run_id,
    )
    seen = 0

    def inject(point: str) -> None:
        nonlocal seen
        if point == "gc-root.after_publish":
            seen += 1
            if seen == 1:
                raise OSError("injected provider failure")

    faulty = EvidenceStore(evidence.root, fault_injector=inject)
    with pytest.raises(MonitorReplayError) as interrupted:
        publish_physical_monitor_run(paths, faulty, **request)
    assert interrupted.value.code == ENVIRONMENT_FAILURE
    root_path = _monitor_root_files(evidence, "monitor-run")[0]
    if mutation == "malformed":
        root_path.write_bytes(b"{}")
    else:
        root = json.loads(root_path.read_bytes().decode("utf-8"))
        root["manifest_id"] = "0" * 64
        root_path.write_bytes(canonical_json_bytes(root))

    with pytest.raises(MonitorReplayError) as failure:
        publish_physical_monitor_run(
            paths,
            EvidenceStore(evidence.root),
            **request,
        )
    assert failure.value.code == expected_code
    assert _monitor_root_files(evidence, "monitor-run-ref") == ()


def test_physical_publication_retry_is_idempotent_and_window_drift_conflicts(
    tmp_path: Path,
) -> None:
    paths, evidence, test_run_id, raw_probe, monitor_run_id, group_id = _physical_context(tmp_path)
    _publish_physical_test_run(
        paths,
        evidence,
        test_run_id=test_run_id,
        raw_probe=raw_probe,
        monitor_run_id=monitor_run_id,
    )
    batches = _append_physical_history(paths, raw_probe, monitor_run_id, group_id)
    request = dict(
        scenario_role="failed-before",
        test_run_id=test_run_id,
        run_id=str(monitor_run_id),
        group_id=str(group_id),
        start_sequence=0,
        end_sequence_exclusive=2,
        start_captured_unix_ns=batches[0].captured_unix_ns,
        end_captured_unix_ns_exclusive=batches[-1].captured_unix_ns + 1,
        probe_id=raw_probe,
    )
    first = publish_physical_monitor_run(paths, evidence, **request)
    retry = publish_physical_monitor_run(paths, EvidenceStore(paths.workspace_root / "evidence"), **request)
    assert retry == first
    before_transcript = _monitor_root_files(evidence, "monitor-run")
    before_reference = _monitor_root_files(evidence, "monitor-run-ref")

    with pytest.raises(MonitorReplayError) as conflict:
        publish_physical_monitor_run(
            paths,
            evidence,
            **{
                **request,
                "end_captured_unix_ns_exclusive": request["end_captured_unix_ns_exclusive"] + 1,
            },
        )
    assert conflict.value.code == OPERATION_CONFLICT
    assert _monitor_root_files(evidence, "monitor-run") == before_transcript
    assert _monitor_root_files(evidence, "monitor-run-ref") == before_reference


def test_physical_probe_hash_mismatch_fails_before_monitor_root_writes(tmp_path: Path) -> None:
    paths, evidence, test_run_id, raw_probe, monitor_run_id, group_id = _physical_context(tmp_path)
    _publish_physical_test_run(
        paths,
        evidence,
        test_run_id=test_run_id,
        raw_probe=raw_probe,
        monitor_run_id=monitor_run_id,
    )
    batches = _append_physical_history(paths, raw_probe, monitor_run_id, group_id)

    with pytest.raises(MonitorReplayError) as mismatch:
        publish_physical_monitor_run(
            paths,
            evidence,
            scenario_role="failed-before",
            test_run_id=test_run_id,
            run_id=str(monitor_run_id),
            group_id=str(group_id),
            start_sequence=0,
            end_sequence_exclusive=2,
            start_captured_unix_ns=batches[0].captured_unix_ns,
            end_captured_unix_ns_exclusive=batches[-1].captured_unix_ns + 1,
            probe_id="probe/serial/other",
        )
    assert mismatch.value.code == "INCOMPATIBLE_IDENTITY"
    assert _monitor_root_files(evidence, "monitor-run") == ()
    assert _monitor_root_files(evidence, "monitor-run-ref") == ()


def test_physical_history_raw_selector_mismatch_fails_before_root_writes(tmp_path: Path) -> None:
    paths, evidence, test_run_id, raw_probe, monitor_run_id, group_id = _physical_context(tmp_path)
    _publish_physical_test_run(
        paths,
        evidence,
        test_run_id=test_run_id,
        raw_probe=raw_probe,
        monitor_run_id=monitor_run_id,
    )
    batches = _append_physical_history(
        paths,
        "probe/serial/history-drift",
        monitor_run_id,
        group_id,
    )

    with pytest.raises(MonitorReplayError) as mismatch:
        publish_physical_monitor_run(
            paths,
            evidence,
            scenario_role="failed-before",
            test_run_id=test_run_id,
            run_id=str(monitor_run_id),
            group_id=str(group_id),
            start_sequence=0,
            end_sequence_exclusive=2,
            start_captured_unix_ns=batches[0].captured_unix_ns,
            end_captured_unix_ns_exclusive=batches[-1].captured_unix_ns + 1,
            probe_id=raw_probe,
        )
    assert mismatch.value.code == "INCOMPATIBLE_IDENTITY"
    assert _monitor_root_files(evidence, "monitor-run") == ()
    assert _monitor_root_files(evidence, "monitor-run-ref") == ()


def test_physical_corrupt_transcript_artifact_fails_closed(tmp_path: Path) -> None:
    paths, evidence, test_run_id, raw_probe, monitor_run_id, group_id = _physical_context(tmp_path)
    _publish_physical_test_run(
        paths,
        evidence,
        test_run_id=test_run_id,
        raw_probe=raw_probe,
        monitor_run_id=monitor_run_id,
    )
    request = _physical_request(
        paths,
        raw_probe,
        monitor_run_id,
        group_id,
        test_run_id,
    )
    reference = publish_physical_monitor_run(paths, evidence, **request)
    transcript_root = json.loads(
        _monitor_root_files(evidence, "monitor-run")[0].read_bytes().decode("utf-8")
    )
    transcript_manifest = json.loads(
        (
            evidence.root
            / "manifests"
            / f"{transcript_root['manifest_id']}.json"
        ).read_bytes().decode("utf-8")
    )
    artifact = transcript_manifest["artifacts"][0]
    artifact_path = evidence.root / artifact["relative_path"]
    artifact_path.write_bytes(b"corrupt-transcript")

    with pytest.raises(MonitorReplayError) as failure:
        load_monitor_run_reference(
            paths,
            EvidenceStore(evidence.root),
            str(monitor_run_id),
        )
    assert failure.value.code == EVIDENCE_INTEGRITY_FAILURE
    assert reference.schema == "stm32-monitor-run-ref/2"
    assert _monitor_root_files(evidence, "monitor-run-ref")


@pytest.mark.parametrize(
    ("storage_code", "expected_code"),
    [
        ("MONITOR_STORAGE_BUSY", ENVIRONMENT_FAILURE),
        ("MONITOR_STORAGE_CORRUPT", EVIDENCE_INTEGRITY_FAILURE),
    ],
)
def test_physical_history_provider_failure_is_mapped_before_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    storage_code: str,
    expected_code: str,
) -> None:
    from stm32_monitor import replay as replay_module

    paths, evidence, test_run_id, raw_probe, monitor_run_id, group_id = _physical_context(tmp_path)
    _publish_physical_test_run(
        paths,
        evidence,
        test_run_id=test_run_id,
        raw_probe=raw_probe,
        monitor_run_id=monitor_run_id,
    )
    request = _physical_request(
        paths,
        raw_probe,
        monitor_run_id,
        group_id,
        test_run_id,
    )
    failure = ProtocolResult(
        ok=False,
        operation="history.query",
        code=storage_code,
        message="history provider failure",
        data=None,
    )
    monkeypatch.setattr(replay_module.HistoryStore, "query_history", lambda self, query: failure)

    with pytest.raises(MonitorReplayError) as error:
        publish_physical_monitor_run(paths, evidence, **request)

    assert error.value.code == expected_code
    assert _monitor_root_files(evidence, "monitor-run") == ()
    assert _monitor_root_files(evidence, "monitor-run-ref") == ()


def test_physical_history_provider_repeated_cursor_is_integrity_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from stm32_monitor import replay as replay_module

    paths, evidence, test_run_id, raw_probe, monitor_run_id, group_id = _physical_context(tmp_path)
    _publish_physical_test_run(
        paths,
        evidence,
        test_run_id=test_run_id,
        raw_probe=raw_probe,
        monitor_run_id=monitor_run_id,
    )
    request = _physical_request(
        paths,
        raw_probe,
        monitor_run_id,
        group_id,
        test_run_id,
    )
    original_query = replay_module.HistoryStore.query_history
    first_page = None

    def repeated_page(history: HistoryStore, query: HistoryQuery):
        nonlocal first_page
        if first_page is None:
            result = original_query(history, replace(query, limit=1))
            assert result.ok and result.data is not None
            first_page = result.data
        return ProtocolResult(
            ok=True,
            operation="history.query",
            code="OK",
            message="",
            data=first_page,
        )

    monkeypatch.setattr(replay_module.HistoryStore, "query_history", repeated_page)
    with pytest.raises(MonitorReplayError) as error:
        publish_physical_monitor_run(paths, evidence, **request)

    assert error.value.code == EVIDENCE_INTEGRITY_FAILURE
    assert _monitor_root_files(evidence, "monitor-run") == ()
    assert _monitor_root_files(evidence, "monitor-run-ref") == ()


def test_physical_history_provider_wrong_page_shape_is_integrity_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from stm32_monitor import replay as replay_module

    paths, evidence, test_run_id, raw_probe, monitor_run_id, group_id = _physical_context(tmp_path)
    _publish_physical_test_run(
        paths,
        evidence,
        test_run_id=test_run_id,
        raw_probe=raw_probe,
        monitor_run_id=monitor_run_id,
    )
    request = _physical_request(
        paths,
        raw_probe,
        monitor_run_id,
        group_id,
        test_run_id,
    )
    monkeypatch.setattr(
        replay_module.HistoryStore,
        "query_history",
        lambda self, query: ProtocolResult(
            ok=True,
            operation="history.query",
            code="OK",
            message="",
            data={"batches": (), "next_cursor": None},
        ),
    )

    with pytest.raises(MonitorReplayError) as error:
        publish_physical_monitor_run(paths, evidence, **request)

    assert error.value.code == EVIDENCE_INTEGRITY_FAILURE
    assert _monitor_root_files(evidence, "monitor-run") == ()
    assert _monitor_root_files(evidence, "monitor-run-ref") == ()


def test_physical_test_run_provider_failure_is_sanitized_before_history_publish(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from stm32_monitor import replay as replay_module

    paths, evidence, test_run_id, raw_probe, monitor_run_id, group_id = _physical_context(tmp_path)
    _publish_physical_test_run(
        paths,
        evidence,
        test_run_id=test_run_id,
        raw_probe=raw_probe,
        monitor_run_id=monitor_run_id,
    )
    request = _physical_request(
        paths,
        raw_probe,
        monitor_run_id,
        group_id,
        test_run_id,
    )
    monkeypatch.setattr(
        replay_module.TestRunRepository,
        "load",
        lambda self, run_id: (_ for _ in ()).throw(OSError("provider path leaked")),
    )

    with pytest.raises(MonitorReplayError) as error:
        publish_physical_monitor_run(paths, evidence, **request)

    assert error.value.code == ENVIRONMENT_FAILURE
    assert "provider path leaked" not in error.value.message
    assert _monitor_root_files(evidence, "monitor-run") == ()
    assert _monitor_root_files(evidence, "monitor-run-ref") == ()


@pytest.mark.parametrize(
    ("operation_id", "expected_code"),
    [
        ("not-a-uuid", MONITOR_PHYSICAL_INVALID),
        ("11111111-1111-4111-8111-111111111111", EVIDENCE_INTEGRITY_FAILURE),
    ],
)
def test_public_physical_loader_rejects_invalid_or_absent_authority(
    tmp_path: Path,
    operation_id: str,
    expected_code: str,
) -> None:
    paths, evidence, _test_run_id, _raw_probe, _monitor_run_id, _group_id = _physical_context(tmp_path)

    with pytest.raises(MonitorReplayError) as error:
        load_monitor_run_reference(paths, evidence, operation_id)

    assert error.value.code == expected_code


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("operation", "wrong-operation"),
        ("parents", []),
        ("artifacts", []),
    ],
)
def test_physical_loader_rejects_persisted_reference_envelope_drift(
    tmp_path: Path,
    field: str,
    replacement: object,
) -> None:
    paths, evidence, test_run_id, raw_probe, monitor_run_id, group_id = _physical_context(tmp_path)
    _publish_physical_test_run(
        paths,
        evidence,
        test_run_id=test_run_id,
        raw_probe=raw_probe,
        monitor_run_id=monitor_run_id,
    )
    request = _physical_request(
        paths,
        raw_probe,
        monitor_run_id,
        group_id,
        test_run_id,
    )
    publish_physical_monitor_run(paths, evidence, **request)
    reference_root = json.loads(_monitor_root_files(evidence, "monitor-run-ref")[0].read_bytes().decode("utf-8"))
    manifest_path = evidence.root / "manifests" / f"{reference_root['manifest_id']}.json"
    manifest = json.loads(manifest_path.read_bytes().decode("utf-8"))
    manifest[field] = replacement
    manifest_path.write_bytes(canonical_json_bytes(manifest))

    with pytest.raises(MonitorReplayError) as error:
        load_monitor_run_reference(paths, EvidenceStore(evidence.root), str(monitor_run_id))

    assert error.value.code == EVIDENCE_INTEGRITY_FAILURE


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("scenario_role", "other"),
        ("run_id", "not-a-uuid"),
        ("start_sequence", True),
        ("end_sequence_exclusive", 0),
        ("probe_id", " probe/serial/01"),
    ],
)
def test_public_physical_request_validation_precedes_provider_access(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    value: object,
) -> None:
    from stm32_monitor import replay as replay_module

    paths, evidence, test_run_id, raw_probe, monitor_run_id, group_id = _physical_context(tmp_path)
    _publish_physical_test_run(
        paths,
        evidence,
        test_run_id=test_run_id,
        raw_probe=raw_probe,
        monitor_run_id=monitor_run_id,
    )
    request = _physical_request(
        paths,
        raw_probe,
        monitor_run_id,
        group_id,
        test_run_id,
    )
    request[field] = value
    monkeypatch.setattr(
        replay_module.TestRunRepository,
        "load",
        lambda self, run_id: pytest.fail("invalid public request reached TestRun provider"),
    )
    monkeypatch.setattr(
        replay_module.HistoryStore,
        "query_history",
        lambda self, query: pytest.fail("invalid public request reached History provider"),
    )

    with pytest.raises(MonitorReplayError) as error:
        publish_physical_monitor_run(paths, evidence, **request)

    assert error.value.code == MONITOR_PHYSICAL_INVALID
    assert _monitor_root_files(evidence, "monitor-run") == ()
    assert _monitor_root_files(evidence, "monitor-run-ref") == ()


def test_physical_history_empty_public_page_fails_before_monitor_roots(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from stm32_monitor import replay as replay_module

    paths, evidence, test_run_id, raw_probe, monitor_run_id, group_id = _physical_context(tmp_path)
    _publish_physical_test_run(
        paths,
        evidence,
        test_run_id=test_run_id,
        raw_probe=raw_probe,
        monitor_run_id=monitor_run_id,
    )
    request = _physical_request(
        paths,
        raw_probe,
        monitor_run_id,
        group_id,
        test_run_id,
    )
    page = HistoryPage.create((), next_cursor=None)
    calls: list[HistoryQuery] = []

    def empty_page(history: HistoryStore, query: HistoryQuery):
        calls.append(query)
        return ProtocolResult(
            ok=True,
            operation="history.query",
            code="OK",
            message="",
            data=page,
        )

    monkeypatch.setattr(replay_module.HistoryStore, "query_history", empty_page)
    with pytest.raises(MonitorReplayError) as error:
        publish_physical_monitor_run(paths, evidence, **request)

    assert error.value.code == "INCOMPATIBLE_IDENTITY"
    assert calls
    assert _monitor_root_files(evidence, "monitor-run") == ()
    assert _monitor_root_files(evidence, "monitor-run-ref") == ()


def test_physical_history_sequence_window_contradiction_fails_before_monitor_roots(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from stm32_monitor import replay as replay_module

    paths, evidence, test_run_id, raw_probe, monitor_run_id, group_id = _physical_context(tmp_path)
    _publish_physical_test_run(
        paths,
        evidence,
        test_run_id=test_run_id,
        raw_probe=raw_probe,
        monitor_run_id=monitor_run_id,
    )
    request = _physical_request(
        paths,
        raw_probe,
        monitor_run_id,
        group_id,
        test_run_id,
    )
    history = HistoryStore(paths)
    try:
        result = history.query_history(
            HistoryQuery(
                session_id=paths.session_id,
                start_ns=0,
                end_ns=(1 << 63) - 1,
                limit=10_000,
                run_id=monitor_run_id,
                group_id=group_id,
            )
        )
    finally:
        history.close()
    assert result.ok and result.data is not None
    shifted = tuple(replace(item, sequence=item.sequence + 1) for item in result.data.batches)
    page = HistoryPage.create(shifted, next_cursor=None)
    calls: list[HistoryQuery] = []

    def shifted_page(history: HistoryStore, query: HistoryQuery):
        calls.append(query)
        return ProtocolResult(
            ok=True,
            operation="history.query",
            code="OK",
            message="",
            data=page,
        )

    monkeypatch.setattr(replay_module.HistoryStore, "query_history", shifted_page)
    with pytest.raises(MonitorReplayError) as error:
        publish_physical_monitor_run(paths, evidence, **request)

    assert error.value.code == "INCOMPATIBLE_IDENTITY"
    assert calls
    assert _monitor_root_files(evidence, "monitor-run") == ()
    assert _monitor_root_files(evidence, "monitor-run-ref") == ()


def test_physical_history_time_window_contradiction_fails_before_monitor_roots(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from stm32_monitor import replay as replay_module

    paths, evidence, test_run_id, raw_probe, monitor_run_id, group_id = _physical_context(tmp_path)
    _publish_physical_test_run(
        paths,
        evidence,
        test_run_id=test_run_id,
        raw_probe=raw_probe,
        monitor_run_id=monitor_run_id,
    )
    request = _physical_request(
        paths,
        raw_probe,
        monitor_run_id,
        group_id,
        test_run_id,
    )
    history = HistoryStore(paths)
    try:
        result = history.query_history(
            HistoryQuery(
                session_id=paths.session_id,
                start_ns=0,
                end_ns=(1 << 63) - 1,
                limit=10_000,
                run_id=monitor_run_id,
                group_id=group_id,
            )
        )
    finally:
        history.close()
    assert result.ok and result.data is not None
    shifted = tuple(
        replace(item, captured_unix_ns=item.captured_unix_ns + 1)
        for item in result.data.batches
    )
    page = HistoryPage.create(shifted, next_cursor=None)
    calls: list[HistoryQuery] = []

    def shifted_time_page(history: HistoryStore, query: HistoryQuery):
        calls.append(query)
        return ProtocolResult(
            ok=True,
            operation="history.query",
            code="OK",
            message="",
            data=page,
        )

    monkeypatch.setattr(replay_module.HistoryStore, "query_history", shifted_time_page)
    with pytest.raises(MonitorReplayError) as error:
        publish_physical_monitor_run(paths, evidence, **request)

    assert error.value.code == "INCOMPATIBLE_IDENTITY"
    assert calls
    assert _monitor_root_files(evidence, "monitor-run") == ()
    assert _monitor_root_files(evidence, "monitor-run-ref") == ()


def test_physical_history_binding_contradiction_fails_before_monitor_roots(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from stm32_monitor import replay as replay_module

    paths, evidence, test_run_id, raw_probe, monitor_run_id, group_id = _physical_context(tmp_path)
    _publish_physical_test_run(
        paths,
        evidence,
        test_run_id=test_run_id,
        raw_probe=raw_probe,
        monitor_run_id=monitor_run_id,
    )
    request = _physical_request(
        paths,
        raw_probe,
        monitor_run_id,
        group_id,
        test_run_id,
    )
    history = HistoryStore(paths)
    try:
        result = history.query_history(
            HistoryQuery(
                session_id=paths.session_id,
                start_ns=0,
                end_ns=(1 << 63) - 1,
                limit=10_000,
                run_id=monitor_run_id,
                group_id=group_id,
            )
        )
    finally:
        history.close()
    assert result.ok and result.data is not None
    changed_group = UUID("33333333-3333-4333-8333-333333333333")
    changed = tuple(
        replace(item, group_id=changed_group) if index == 1 else item
        for index, item in enumerate(result.data.batches)
    )
    page = HistoryPage.create(changed, next_cursor=None)
    calls: list[HistoryQuery] = []

    def inconsistent_page(history: HistoryStore, query: HistoryQuery):
        calls.append(query)
        return ProtocolResult(
            ok=True,
            operation="history.query",
            code="OK",
            message="",
            data=page,
        )

    monkeypatch.setattr(replay_module.HistoryStore, "query_history", inconsistent_page)
    with pytest.raises(MonitorReplayError) as error:
        publish_physical_monitor_run(paths, evidence, **request)

    assert error.value.code == "INCOMPATIBLE_IDENTITY"
    assert calls
    assert _monitor_root_files(evidence, "monitor-run") == ()
    assert _monitor_root_files(evidence, "monitor-run-ref") == ()


def test_physical_project_manifest_failure_is_environment_error_before_monitor_roots(
    tmp_path: Path,
) -> None:
    paths, evidence, test_run_id, raw_probe, monitor_run_id, group_id = _physical_context(tmp_path)
    _publish_physical_test_run(
        paths,
        evidence,
        test_run_id=test_run_id,
        raw_probe=raw_probe,
        monitor_run_id=monitor_run_id,
    )
    request = _physical_request(
        paths,
        raw_probe,
        monitor_run_id,
        group_id,
        test_run_id,
    )
    (paths.project_root / ".stm32-project.json").write_bytes(b"not-json")

    with pytest.raises(MonitorReplayError) as error:
        publish_physical_monitor_run(paths, evidence, **request)

    assert error.value.code == ENVIRONMENT_FAILURE
    assert _monitor_root_files(evidence, "monitor-run") == ()
    assert _monitor_root_files(evidence, "monitor-run-ref") == ()


def test_physical_test_run_state_contradiction_fails_before_monitor_roots(
    tmp_path: Path,
) -> None:
    paths, evidence, test_run_id, raw_probe, monitor_run_id, group_id = _physical_context(tmp_path)
    _publish_physical_test_run(
        paths,
        evidence,
        test_run_id=test_run_id,
        raw_probe=raw_probe,
        monitor_run_id=monitor_run_id,
        state="passed",
    )
    request = _physical_request(
        paths,
        raw_probe,
        monitor_run_id,
        group_id,
        test_run_id,
    )

    with pytest.raises(MonitorReplayError) as error:
        publish_physical_monitor_run(paths, evidence, **request)

    assert error.value.code == "INCOMPATIBLE_IDENTITY"
    assert _monitor_root_files(evidence, "monitor-run") == ()
    assert _monitor_root_files(evidence, "monitor-run-ref") == ()


def test_physical_loader_rejects_provider_reference_metadata_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from stm32_monitor import replay as replay_module

    paths, evidence, test_run_id, raw_probe, monitor_run_id, group_id = _physical_context(tmp_path)
    _publish_physical_test_run(
        paths,
        evidence,
        test_run_id=test_run_id,
        raw_probe=raw_probe,
        monitor_run_id=monitor_run_id,
    )
    request = _physical_request(
        paths,
        raw_probe,
        monitor_run_id,
        group_id,
        test_run_id,
    )
    publish_physical_monitor_run(paths, evidence, **request)
    reference_root = json.loads(_monitor_root_files(evidence, "monitor-run-ref")[0].read_bytes().decode("utf-8"))
    transcript_root = _monitor_root_files(evidence, "monitor-run")[0].read_bytes()
    before_reference = _monitor_root_files(evidence, "monitor-run-ref")[0].read_bytes()
    original_get_envelope = evidence.get_envelope
    calls: list[str] = []

    def contradictory_envelope(evidence_id: str):
        calls.append(evidence_id)
        envelope = original_get_envelope(evidence_id)
        if evidence_id == reference_root["manifest_id"]:
            metadata = dict(envelope.metadata)
            metadata["run_ref_sha256"] = "0" * 64
            return replace(envelope, metadata=metadata)
        return envelope

    monkeypatch.setattr(evidence, "get_envelope", contradictory_envelope)
    with pytest.raises(MonitorReplayError) as error:
        load_monitor_run_reference(paths, evidence, str(monitor_run_id))

    assert error.value.code == EVIDENCE_INTEGRITY_FAILURE
    assert reference_root["manifest_id"] in calls
    assert _monitor_root_files(evidence, "monitor-run-ref")[0].read_bytes() == before_reference
    assert _monitor_root_files(evidence, "monitor-run")[0].read_bytes() == transcript_root


@pytest.mark.parametrize(
    ("mutation", "cause"),
    (
        ("identity", "physical transcript identity is invalid"),
        ("metadata", "physical transcript metadata is invalid"),
    ),
    ids=("identity", "metadata"),
)
def test_physical_loader_rejects_provider_transcript_identity_or_metadata_drift(
    tmp_path: Path,
    mutation: str,
    cause: str,
) -> None:
    paths, evidence, test_run_id, raw_probe, monitor_run_id, group_id = _physical_context(tmp_path)
    _publish_physical_test_run(
        paths,
        evidence,
        test_run_id=test_run_id,
        raw_probe=raw_probe,
        monitor_run_id=monitor_run_id,
    )
    request = _physical_request(
        paths,
        raw_probe,
        monitor_run_id,
        group_id,
        test_run_id,
    )
    original_reference = publish_physical_monitor_run(paths, evidence, **request)
    reference_root_path = _monitor_root_files(evidence, "monitor-run-ref")[0]
    transcript_root_path = _monitor_root_files(evidence, "monitor-run")[0]
    reference_root = json.loads(reference_root_path.read_bytes().decode("utf-8"))
    transcript_root = json.loads(transcript_root_path.read_bytes().decode("utf-8"))
    original_loaded = load_monitor_run_reference(
        paths,
        EvidenceStore(evidence.root),
        str(monitor_run_id),
    )
    assert original_loaded.to_dict() == original_reference.to_dict()

    stored_transcript = evidence.get_envelope(transcript_root["manifest_id"])
    if mutation == "identity":
        contradictory_transcript = EvidenceEnvelope(
            identity=replace(stored_transcript.identity, workspace_id="f" * 64),
            operation=stored_transcript.operation,
            produced_at_utc=stored_transcript.produced_at_utc,
            parents=stored_transcript.parents,
            artifacts=stored_transcript.artifacts,
            metadata=stored_transcript.metadata,
        )
    else:
        contradictory_metadata = dict(stored_transcript.metadata)
        contradictory_metadata["scenario_role"] = "fixed-after"
        contradictory_transcript = EvidenceEnvelope(
            identity=stored_transcript.identity,
            operation=stored_transcript.operation,
            produced_at_utc=stored_transcript.produced_at_utc,
            parents=stored_transcript.parents,
            artifacts=stored_transcript.artifacts,
            metadata=contradictory_metadata,
        )
    evidence.put_envelope(contradictory_transcript)

    stored_reference = evidence.get_envelope(reference_root["manifest_id"])
    reference_payload = original_reference.to_dict()
    reference_payload["transcript_evidence_id"] = str(contradictory_transcript.evidence_id)
    reference_payload["run_ref_sha256"] = sha256(
        canonical_replay_json_bytes(
            {
                key: value
                for key, value in reference_payload.items()
                if key != "run_ref_sha256"
            }
        )
    ).hexdigest()
    updated_reference = MonitorRunRefV2.from_value(reference_payload)

    reference_source = tmp_path / f"provider-drift-{mutation}.json"
    reference_source.write_bytes(canonical_replay_json_bytes(updated_reference.to_dict()))
    reference_artifact = evidence.ingest_file(
        reference_source,
        kind="monitor-run-ref",
        media_type="application/json",
    )
    reference_metadata = dict(stored_reference.metadata)
    reference_metadata["run_ref_sha256"] = updated_reference.run_ref_sha256
    replacement_reference = EvidenceEnvelope(
        identity=contradictory_transcript.identity,
        operation=stored_reference.operation,
        produced_at_utc=stored_reference.produced_at_utc,
        parents=(str(contradictory_transcript.evidence_id),),
        artifacts=(reference_artifact,),
        metadata=reference_metadata,
    )
    evidence.put_envelope(replacement_reference)

    transcript_root["manifest_id"] = str(contradictory_transcript.evidence_id)
    transcript_root_metadata = dict(transcript_root["metadata"])
    transcript_root_metadata["run_ref_sha256"] = updated_reference.run_ref_sha256
    transcript_root["metadata"] = transcript_root_metadata
    transcript_root_path.write_bytes(canonical_json_bytes(transcript_root))

    reference_root["manifest_id"] = str(replacement_reference.evidence_id)
    reference_root_metadata = dict(reference_root["metadata"])
    reference_root_metadata["run_ref_sha256"] = updated_reference.run_ref_sha256
    reference_root["metadata"] = reference_root_metadata
    reference_root_path.write_bytes(canonical_json_bytes(reference_root))

    before = {
        str(path.relative_to(evidence.root)): path.read_bytes()
        for path in evidence.root.rglob("*")
        if path.is_file()
    }

    with pytest.raises(MonitorReplayError) as error:
        load_monitor_run_reference(
            paths,
            EvidenceStore(evidence.root),
            str(monitor_run_id),
        )

    assert error.value.code == EVIDENCE_INTEGRITY_FAILURE
    assert str(error.value.__cause__) == cause
    assert {
        str(path.relative_to(evidence.root)): path.read_bytes()
        for path in evidence.root.rglob("*")
        if path.is_file()
    } == before


def test_physical_loader_rejects_persisted_reference_root_metadata_drift(tmp_path: Path) -> None:
    paths, evidence, test_run_id, raw_probe, monitor_run_id, group_id = _physical_context(tmp_path)
    _publish_physical_test_run(
        paths,
        evidence,
        test_run_id=test_run_id,
        raw_probe=raw_probe,
        monitor_run_id=monitor_run_id,
    )
    request = _physical_request(
        paths,
        raw_probe,
        monitor_run_id,
        group_id,
        test_run_id,
    )
    reference = publish_physical_monitor_run(paths, evidence, **request)
    reference_root_path = _monitor_root_files(evidence, "monitor-run-ref")[0]
    transcript_root_path = _monitor_root_files(evidence, "monitor-run")[0]
    before_transcript = transcript_root_path.read_bytes()
    root = json.loads(reference_root_path.read_bytes().decode("utf-8"))
    root["metadata"]["run_ref_sha256"] = "0" * 64
    reference_root_path.write_bytes(canonical_json_bytes(root))

    with pytest.raises(MonitorReplayError) as error:
        load_monitor_run_reference(
            paths,
            EvidenceStore(evidence.root),
            str(monitor_run_id),
        )

    assert error.value.code == EVIDENCE_INTEGRITY_FAILURE
    assert reference_root_path.read_bytes() == canonical_json_bytes(root)
    assert transcript_root_path.read_bytes() == before_transcript
    assert reference.schema == "stm32-monitor-run-ref/2"


def test_physical_loader_rejects_persisted_noncanonical_reference_bytes_before_authentication(
    tmp_path: Path,
) -> None:
    paths, evidence, test_run_id, raw_probe, monitor_run_id, group_id = _physical_context(tmp_path)
    _publish_physical_test_run(
        paths,
        evidence,
        test_run_id=test_run_id,
        raw_probe=raw_probe,
        monitor_run_id=monitor_run_id,
    )
    request = _physical_request(
        paths,
        raw_probe,
        monitor_run_id,
        group_id,
        test_run_id,
    )
    publish_physical_monitor_run(paths, evidence, **request)

    reference_root_path = _monitor_root_files(evidence, "monitor-run-ref")[0]
    reference_root = json.loads(reference_root_path.read_bytes().decode("utf-8"))
    stored = evidence.get_envelope(reference_root["manifest_id"])
    source = tmp_path / "reference-with-final-lf.json"
    source.write_bytes(
        evidence.read_artifact(stored.artifacts[0], maximum_bytes=64 * 1024 * 1024) + b"\n"
    )
    replacement_artifact = evidence.ingest_file(
        source,
        kind="monitor-run-ref",
        media_type="application/json",
    )
    replacement = EvidenceEnvelope(
        identity=stored.identity,
        operation=stored.operation,
        produced_at_utc=stored.produced_at_utc,
        parents=stored.parents,
        artifacts=(replacement_artifact,),
        metadata=stored.metadata,
    )
    evidence.put_envelope(replacement)
    reference_root["manifest_id"] = str(replacement.evidence_id)
    reference_root_path.write_bytes(canonical_json_bytes(reference_root))

    def persisted_state() -> dict[str, bytes]:
        return {
            str(path.relative_to(evidence.root)): path.read_bytes()
            for path in evidence.root.rglob("*")
            if path.is_file()
        }

    before = persisted_state()
    with pytest.raises(MonitorReplayError) as error:
        load_monitor_run_reference(
            paths,
            EvidenceStore(evidence.root),
            str(monitor_run_id),
        )

    assert error.value.code == EVIDENCE_INTEGRITY_FAILURE
    assert str(error.value.__cause__) == "replay JSON is not canonical"
    assert persisted_state() == before


@pytest.mark.parametrize(
    ("mutation", "expected_cause"),
    [
        ("bom", "physical transcript must not include a BOM"),
        ("duplicate-key", "physical transcript has duplicate keys"),
        ("noncanonical", "physical transcript JSON is not canonical"),
        ("scalar-root", "physical transcript must be a JSON object"),
    ],
    ids=("bom", "duplicate-key", "noncanonical", "scalar-root"),
)
def test_physical_loader_rejects_persisted_transcript_decoder_variants(
    tmp_path: Path,
    mutation: str,
    expected_cause: str,
) -> None:
    paths, evidence, test_run_id, raw_probe, monitor_run_id, group_id = _physical_context(tmp_path)
    _publish_physical_test_run(
        paths,
        evidence,
        test_run_id=test_run_id,
        raw_probe=raw_probe,
        monitor_run_id=monitor_run_id,
    )
    request = _physical_request(
        paths,
        raw_probe,
        monitor_run_id,
        group_id,
        test_run_id,
    )
    reference = publish_physical_monitor_run(paths, evidence, **request)
    assert load_monitor_run_reference(
        paths,
        EvidenceStore(evidence.root),
        str(monitor_run_id),
    ).to_dict() == reference.to_dict()

    _replace_persisted_physical_transcript(tmp_path, evidence, reference, mutation)
    before = _physical_evidence_state(evidence)

    with pytest.raises(MonitorReplayError) as error:
        load_monitor_run_reference(
            paths,
            EvidenceStore(evidence.root),
            str(monitor_run_id),
        )

    assert error.value.code == EVIDENCE_INTEGRITY_FAILURE
    assert error.value.message == "physical Monitor transcript is corrupt"
    assert str(error.value.__cause__) == expected_cause
    assert _physical_evidence_state(evidence) == before


def test_physical_loader_rejects_provider_transcript_envelope_structure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths, evidence, test_run_id, raw_probe, monitor_run_id, group_id = _physical_context(tmp_path)
    _publish_physical_test_run(
        paths,
        evidence,
        test_run_id=test_run_id,
        raw_probe=raw_probe,
        monitor_run_id=monitor_run_id,
    )
    request = _physical_request(
        paths,
        raw_probe,
        monitor_run_id,
        group_id,
        test_run_id,
    )
    reference = publish_physical_monitor_run(paths, evidence, **request)
    transcript_root = json.loads(_monitor_root_files(evidence, "monitor-run")[0].read_bytes().decode("utf-8"))
    before_transcript = _monitor_root_files(evidence, "monitor-run")[0].read_bytes()
    before_reference = _monitor_root_files(evidence, "monitor-run-ref")[0].read_bytes()
    original_get_envelope = evidence.get_envelope
    stored_transcript_envelope = original_get_envelope(transcript_root["manifest_id"])
    contradictory_transcript_envelope = EvidenceEnvelope(
        identity=stored_transcript_envelope.identity,
        operation=stored_transcript_envelope.operation,
        produced_at_utc=stored_transcript_envelope.produced_at_utc,
        parents=(transcript_root["manifest_id"],),
        artifacts=stored_transcript_envelope.artifacts,
        metadata=stored_transcript_envelope.metadata,
    )
    calls: list[str] = []
    returned: list[EvidenceEnvelope] = []

    def contradictory_envelope(evidence_id: str):
        calls.append(evidence_id)
        if evidence_id == transcript_root["manifest_id"]:
            returned.append(contradictory_transcript_envelope)
            return contradictory_transcript_envelope
        return original_get_envelope(evidence_id)

    monkeypatch.setattr(evidence, "get_envelope", contradictory_envelope)
    with pytest.raises(MonitorReplayError) as error:
        load_monitor_run_reference(paths, evidence, str(monitor_run_id))

    assert error.value.code == EVIDENCE_INTEGRITY_FAILURE
    assert transcript_root["manifest_id"] in calls
    assert returned == [contradictory_transcript_envelope]
    assert contradictory_transcript_envelope.evidence_id != stored_transcript_envelope.evidence_id
    assert str(error.value.__cause__) == "physical transcript envelope is invalid"
    assert _monitor_root_files(evidence, "monitor-run")[0].read_bytes() == before_transcript
    assert _monitor_root_files(evidence, "monitor-run-ref")[0].read_bytes() == before_reference
    assert reference.schema == "stm32-monitor-run-ref/2"


def test_physical_loader_rejects_provider_reference_artifact_operation_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths, evidence, test_run_id, raw_probe, monitor_run_id, group_id = _physical_context(tmp_path)
    _publish_physical_test_run(
        paths,
        evidence,
        test_run_id=test_run_id,
        raw_probe=raw_probe,
        monitor_run_id=monitor_run_id,
    )
    request = _physical_request(
        paths,
        raw_probe,
        monitor_run_id,
        group_id,
        test_run_id,
    )
    reference = publish_physical_monitor_run(paths, evidence, **request)
    reference_root = json.loads(_monitor_root_files(evidence, "monitor-run-ref")[0].read_bytes().decode("utf-8"))
    reference_artifact = evidence.get_envelope(reference_root["manifest_id"]).artifacts[0]
    mutated = reference.to_dict()
    replacement_operation = "99999999-9999-4999-8999-999999999999"
    mutated["operation_id"] = replacement_operation
    mutated["origin_run_id"] = replacement_operation
    mutated["projected_run_id"] = replacement_operation
    unsigned = dict(mutated)
    unsigned.pop("run_ref_sha256")
    mutated["run_ref_sha256"] = sha256(canonical_replay_json_bytes(unsigned)).hexdigest()
    replacement = canonical_replay_json_bytes(mutated)
    original_read_artifact = evidence.read_artifact
    calls: list[object] = []

    def contradictory_artifact(artifact, *, maximum_bytes: int):
        if artifact == reference_artifact:
            calls.append(artifact)
            return replacement
        return original_read_artifact(artifact, maximum_bytes=maximum_bytes)

    before_transcript = _monitor_root_files(evidence, "monitor-run")[0].read_bytes()
    before_reference = _monitor_root_files(evidence, "monitor-run-ref")[0].read_bytes()
    monkeypatch.setattr(evidence, "read_artifact", contradictory_artifact)
    with pytest.raises(MonitorReplayError) as error:
        load_monitor_run_reference(paths, evidence, str(monitor_run_id))

    assert error.value.code == EVIDENCE_INTEGRITY_FAILURE
    assert calls == [reference_artifact]
    assert _monitor_root_files(evidence, "monitor-run")[0].read_bytes() == before_transcript
    assert _monitor_root_files(evidence, "monitor-run-ref")[0].read_bytes() == before_reference


def test_physical_loader_rejects_provider_transcript_digest_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths, evidence, test_run_id, raw_probe, monitor_run_id, group_id = _physical_context(tmp_path)
    _publish_physical_test_run(
        paths,
        evidence,
        test_run_id=test_run_id,
        raw_probe=raw_probe,
        monitor_run_id=monitor_run_id,
    )
    request = _physical_request(
        paths,
        raw_probe,
        monitor_run_id,
        group_id,
        test_run_id,
    )
    publish_physical_monitor_run(paths, evidence, **request)
    transcript_root = json.loads(_monitor_root_files(evidence, "monitor-run")[0].read_bytes().decode("utf-8"))
    transcript_envelope = evidence.get_envelope(transcript_root["manifest_id"])
    transcript_artifact = transcript_envelope.artifacts[0]
    original_read_artifact = evidence.read_artifact
    original_transcript = original_read_artifact(
        transcript_artifact,
        maximum_bytes=64 * 1024 * 1024,
    )
    mutated = json.loads(original_transcript.decode("utf-8"))
    mutated["batches"][0]["values"][0]["typedValue"]["value"] += 1
    replacement = canonical_replay_json_bytes(mutated)
    calls: list[object] = []

    def contradictory_artifact(artifact, *, maximum_bytes: int):
        if artifact == transcript_artifact:
            calls.append(artifact)
            return replacement
        return original_read_artifact(artifact, maximum_bytes=maximum_bytes)

    monkeypatch.setattr(evidence, "read_artifact", contradictory_artifact)
    with pytest.raises(MonitorReplayError) as error:
        load_monitor_run_reference(paths, evidence, str(monitor_run_id))

    assert error.value.code == EVIDENCE_INTEGRITY_FAILURE
    assert calls == [transcript_artifact]


def test_physical_loader_rejects_provider_transcript_root_metadata_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from stm32_monitor import replay as replay_module

    paths, evidence, test_run_id, raw_probe, monitor_run_id, group_id = _physical_context(tmp_path)
    _publish_physical_test_run(
        paths,
        evidence,
        test_run_id=test_run_id,
        raw_probe=raw_probe,
        monitor_run_id=monitor_run_id,
    )
    request = _physical_request(
        paths,
        raw_probe,
        monitor_run_id,
        group_id,
        test_run_id,
    )
    publish_physical_monitor_run(paths, evidence, **request)
    before_transcript = _monitor_root_files(evidence, "monitor-run")[0].read_bytes()
    before_reference = _monitor_root_files(evidence, "monitor-run-ref")[0].read_bytes()
    original_get_root = replay_module.get_root
    calls: list[tuple[str, str]] = []

    def contradictory_root(store, root_type: str, root_id: str):
        calls.append((root_type, root_id))
        root = original_get_root(store, root_type, root_id)
        if root_type == "monitor-run":
            metadata = dict(root.metadata)
            metadata["run_ref_sha256"] = "0" * 64
            return replace(root, metadata=metadata)
        return root

    monkeypatch.setattr(replay_module, "get_root", contradictory_root)
    with pytest.raises(MonitorReplayError) as error:
        load_monitor_run_reference(paths, EvidenceStore(evidence.root), str(monitor_run_id))

    assert error.value.code == EVIDENCE_INTEGRITY_FAILURE
    assert ("monitor-run", str(monitor_run_id)) in calls
    assert _monitor_root_files(evidence, "monitor-run")[0].read_bytes() == before_transcript
    assert _monitor_root_files(evidence, "monitor-run-ref")[0].read_bytes() == before_reference
