from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from uuid import UUID

import pytest

from stm32_monitor.history import HistoryStore
from stm32_monitor.models import ObservationBinding, SampleBatch, SampleValue, WatchItem
from stm32_monitor.replay import (
    EVIDENCE_INTEGRITY_FAILURE,
    ENVIRONMENT_FAILURE,
    OPERATION_CONFLICT,
    MonitorReplayError,
    MonitorRunRef,
    MonitorRunRefV2,
    publish_physical_monitor_run,
    load_monitor_run_reference,
)
from stm32_toolkit.evidence import EvidenceEnvelope, EvidenceIdentity
from stm32_toolkit.evidence.model import canonical_json_bytes
from stm32_toolkit.evidence.store import EvidenceStore
from stm32_toolkit.paths import WorkspacePaths
from stm32_toolkit.testing.model import TestCaseResult as _TestCaseResult
from stm32_toolkit.testing.model import TestRunManifest as _TestRunManifest
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


def test_physical_v2_reference_rejects_replay_probe_labels() -> None:
    payload = _physical_v2_candidate()
    payload["probe_id"] = "replay:probe-v2"
    payload["run_ref_sha256"] = sha256(
        canonical_json_bytes(
            {key: value for key, value in payload.items() if key != "run_ref_sha256"}
        )
    ).hexdigest()

    with pytest.raises(MonitorReplayError):
        MonitorRunRef.from_value(payload)


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
) -> None:
    identity = EvidenceIdentity(
        workspace_id=paths.workspace_id,
        project_id="123e4567-e89b-42d3-a456-426614174000",
        session_id=paths.session_id,
        build_id="b" * 64,
        elf_sha256="c" * 64,
        target_device="stm32:stm32f429zi",
        input_snapshot_sha256="d" * 64,
        git_commit="e" * 40,
        git_dirty=False,
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
        "failed",
        identity,
        "semihosting",
        (
            _TestCaseResult(
                "case.counter",
                "failed",
                "2026-08-22T00:00:00.000000Z",
                "2026-08-22T00:00:00.001000Z",
                1,
                "expected failure",
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
            "import_session_id": paths.session_id,
            "import_workspace_id": paths.workspace_id,
            "intent_digest": digest,
            "inventory_digest": "1" * 64,
            "lease_id": "lease-01",
            "origin_session_id": paths.session_id,
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
    return batches


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


def _monitor_root_files(evidence: EvidenceStore, root_type: str) -> tuple[Path, ...]:
    directory = evidence.root / "roots" / root_type
    return tuple(directory.glob("*.json")) if directory.exists() else ()


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
) -> dict[str, object]:
    batches = _append_physical_history(paths, raw_probe, monitor_run_id, group_id)
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
    assert conflict.value.code == "INCOMPATIBLE_IDENTITY"
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
