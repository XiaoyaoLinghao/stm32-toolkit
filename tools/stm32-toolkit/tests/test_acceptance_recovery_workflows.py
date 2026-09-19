from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
from pathlib import Path
import shutil
from types import SimpleNamespace
from uuid import UUID

import pytest

import stm32_toolkit.acceptance.recovery_workflows as recovery_workflows
from stm32_toolkit.acceptance.recovery_workflows import (
    AcceptanceRecoveryContext,
    _base_snapshot,
    _validate_diagnostic_session,
    begin_acceptance_attempt,
    checkpoint_acceptance_attempt,
    authorize_acceptance_source_change,
    resume_acceptance_attempt,
)
from stm32_toolkit.evidence import ArtifactRef, EvidenceEnvelope, EvidenceIdentity
from stm32_toolkit.evidence.gc import RootRecord, get_root
from stm32_toolkit.diagnostics import (
    DiagnosticSession,
    DiagnosticStoreBusyError,
    Hypothesis,
    SourceChangeDeclaration,
)


ATTEMPT_ID = "00000000-0000-4000-8000-000000000001"


def test_diagnostic_store_busy_maps_to_acceptance_availability_result() -> None:
    def busy() -> object:
        raise DiagnosticStoreBusyError()

    result = recovery_workflows._result("acceptance.attempt.show", busy)

    assert result.ok is False
    assert result.code == "ACCEPTANCE_ATTEMPT_BUSY"
    assert result.message == "Acceptance attempt storage is busy."
    assert result.details == {}


def test_begin_publishes_revision_zero_and_retry_returns_the_same_snapshot(tmp_path: Path, monkeypatch):
    project = tmp_path / "project"
    data = tmp_path / "data"
    project.mkdir(parents=True)
    monkeypatch.setattr(
        "stm32_toolkit.acceptance.recovery_workflows._load_project_model",
        lambda _root: SimpleNamespace(
            schema_version=3,
            logical_project_id=UUID("00000000-0000-4000-8000-000000000002"),
            memory=SimpleNamespace(source="keil"),
            target_device="STM32F429ZITx",
        ),
    )
    context = AcceptanceRecoveryContext(project, data, "session-a")
    first = begin_acceptance_attempt(
        context,
        attempt_id=ATTEMPT_ID,
        scenario_id="legacy-keil-migration",
        scenario_version="1",
    )
    assert first.ok is True
    assert first.data["attempt"]["revision"] == 0
    second = begin_acceptance_attempt(
        context,
        attempt_id=ATTEMPT_ID,
        scenario_id="legacy-keil-migration",
        scenario_version="1",
    )
    assert second.ok is True
    assert second.data["attempt"] == first.data["attempt"]
    resumed = resume_acceptance_attempt(context, attempt_id=ATTEMPT_ID)
    assert resumed.ok is True
    assert resumed.data["attempt"] == first.data["attempt"]
    assert resumed.data["nextStage"] == "project-materialized"
    assert resumed.data["authorizationRequired"] is False


def test_identical_checkpoint_retry_returns_the_published_snapshot(
    tmp_path: Path, monkeypatch
):
    project = tmp_path / "project"
    project.mkdir(parents=True)
    monkeypatch.setattr(
        "stm32_toolkit.acceptance.recovery_workflows._load_project_model",
        lambda _root: SimpleNamespace(
            schema_version=3,
            logical_project_id=UUID("00000000-0000-4000-8000-000000000002"),
            memory=SimpleNamespace(source="keil"),
            target_device="STM32F429ZITx",
        ),
    )
    context = AcceptanceRecoveryContext(project, tmp_path / "data", "session-a")
    assert begin_acceptance_attempt(
        context,
        attempt_id=ATTEMPT_ID,
        scenario_id="legacy-keil-migration",
        scenario_version="1",
    ).ok
    first = checkpoint_acceptance_attempt(
        context,
        attempt_id=ATTEMPT_ID,
        expected_revision=0,
        stage="project-materialized",
    )
    retry = checkpoint_acceptance_attempt(
        context,
        attempt_id=ATTEMPT_ID,
        expected_revision=0,
        stage="project-materialized",
    )
    assert first.ok is True
    assert retry.ok is True
    assert retry.data == first.data


def test_distinct_stale_checkpoint_request_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    project, data, context = _project_transition_context(
        tmp_path, monkeypatch, lambda: "2026-08-24T00:00:00.000000Z"
    )
    assert begin_acceptance_attempt(
        context, attempt_id=ATTEMPT_ID, scenario_id="legacy-keil-migration", scenario_version="1"
    ).ok
    assert checkpoint_acceptance_attempt(
        context, attempt_id=ATTEMPT_ID, expected_revision=0, stage="project-materialized"
    ).ok
    stale = checkpoint_acceptance_attempt(
        context, attempt_id=ATTEMPT_ID, expected_revision=0, stage="firmware-built-before"
    )
    assert stale.code == "ACCEPTANCE_ATTEMPT_REVISION_CONFLICT"


def _project_transition_context(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, clock):
    project = tmp_path / "project"
    data = tmp_path / "data"
    project.mkdir(parents=True)
    monkeypatch.setattr(
        recovery_workflows,
        "_load_project_model",
        lambda _root: SimpleNamespace(
            schema_version=3,
            logical_project_id=UUID("00000000-0000-4000-8000-000000000002"),
            memory=SimpleNamespace(source="keil"),
            target_device="STM32F429ZITx",
        ),
    )
    monkeypatch.setattr(
        recovery_workflows,
        "_build_project_context",
        lambda *_args: recovery_workflows.OperationResult.success(
            "project.context",
            {"build": {"elfFresh": True, "preset": "arm-debug", "buildId": "b" * 64, "elfSha256": "e" * 64}},
        ),
    )
    monkeypatch.setattr(
        recovery_workflows,
        "snapshot_project_inputs",
        lambda _model: SimpleNamespace(sha256="d" * 64),
    )
    return project, data, AcceptanceRecoveryContext(project, data, "session-a", clock=clock)


@pytest.mark.parametrize(
    ("begin_args", "expected_code"),
    [
        pytest.param(
            {
                "attempt_id": "not-a-uuid",
                "scenario_id": "legacy-keil-migration",
                "scenario_version": "1",
            },
            "ACCEPTANCE_ATTEMPT_INPUT_INVALID",
            id="attempt-id",
        ),
        pytest.param(
            {
                "attempt_id": ATTEMPT_ID,
                "scenario_id": "unsupported-scenario",
                "scenario_version": "1",
            },
            "ACCEPTANCE_ATTEMPT_INPUT_INVALID",
            id="scenario-id",
        ),
        pytest.param(
            {
                "attempt_id": ATTEMPT_ID,
                "scenario_id": "legacy-keil-migration",
                "scenario_version": "2",
            },
            "ACCEPTANCE_ATTEMPT_INPUT_INVALID",
            id="scenario-version",
        ),
        pytest.param(
            {
                "attempt_id": ATTEMPT_ID,
                "scenario_id": 1,
                "scenario_version": "1",
            },
            "ACCEPTANCE_ATTEMPT_INPUT_INVALID",
            id="scenario-type",
        ),
    ],
)
def test_begin_public_input_rejection_publishes_no_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    begin_args: dict[str, object],
    expected_code: str,
) -> None:
    project, data, context = _project_transition_context(
        tmp_path, monkeypatch, lambda: "2026-08-24T00:00:00.000000Z"
    )

    result = begin_acceptance_attempt(context, **begin_args)

    assert result.ok is False
    assert result.code == expected_code
    assert not data.exists()
    assert list(project.iterdir()) == []


def test_checkpoint_public_input_rejection_preserves_revision_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project, data, context = _project_transition_context(
        tmp_path, monkeypatch, lambda: "2026-08-24T00:00:00.000000Z"
    )
    first = begin_acceptance_attempt(
        context,
        attempt_id=ATTEMPT_ID,
        scenario_id="legacy-keil-migration",
        scenario_version="1",
    )
    assert first.ok is True
    original_attempt = first.data["attempt"]
    original_files = {
        str(path.relative_to(data)): path.read_bytes()
        for path in data.rglob("*")
        if path.is_file()
    }

    for expected_revision, stage, expected_code in (
        (True, "project-materialized", "ACCEPTANCE_ATTEMPT_INPUT_INVALID"),
        (8, "project-materialized", "ACCEPTANCE_ATTEMPT_INPUT_INVALID"),
        (0, "unknown-stage", "ACCEPTANCE_ATTEMPT_STAGE_INVALID"),
    ):
        result = checkpoint_acceptance_attempt(
            context,
            attempt_id=ATTEMPT_ID,
            expected_revision=expected_revision,
            stage=stage,
        )
        assert result.ok is False
        assert result.code == expected_code
        resumed = resume_acceptance_attempt(context, attempt_id=ATTEMPT_ID)
        assert resumed.ok is True
        assert resumed.data["attempt"] == original_attempt
        assert resumed.data["attempt"]["revision"] == 0
        assert {
            str(path.relative_to(data)): path.read_bytes()
            for path in data.rglob("*")
            if path.is_file()
        } == original_files


def test_public_checkpoint_build_provider_failure_preserves_revision_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project, data, context = _project_transition_context(
        tmp_path, monkeypatch, lambda: "2026-08-24T00:00:00.000000Z"
    )
    assert begin_acceptance_attempt(
        context,
        attempt_id=ATTEMPT_ID,
        scenario_id="legacy-keil-migration",
        scenario_version="1",
    ).ok
    first = checkpoint_acceptance_attempt(
        context,
        attempt_id=ATTEMPT_ID,
        expected_revision=0,
        stage="project-materialized",
    )
    assert first.ok is True
    original_files = {
        str(path.relative_to(data)): path.read_bytes()
        for path in data.rglob("*")
        if path.is_file()
    }

    monkeypatch.setattr(
        recovery_workflows,
        "_build_project_context",
        lambda *_args: recovery_workflows.OperationResult.failure(
            "project.context", "BUILD_FAILED", "provider rejected the build", {}
        ),
    )
    result = checkpoint_acceptance_attempt(
        context,
        attempt_id=ATTEMPT_ID,
        expected_revision=1,
        stage="firmware-built-before",
    )

    assert result.ok is False
    assert result.code == "ACCEPTANCE_ATTEMPT_OUTPUT_INVALID"
    resumed = resume_acceptance_attempt(context, attempt_id=ATTEMPT_ID)
    assert resumed.ok is True
    assert resumed.data["attempt"] == first.data["attempt"]
    assert resumed.data["nextStage"] == "firmware-built-before"
    assert {
        str(path.relative_to(data)): path.read_bytes()
        for path in data.rglob("*")
        if path.is_file()
    } == original_files


def test_resume_public_attempt_id_rejection_creates_no_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project, data, context = _project_transition_context(
        tmp_path, monkeypatch, lambda: "2026-08-24T00:00:00.000000Z"
    )

    result = resume_acceptance_attempt(context, attempt_id="not-a-uuid")

    assert result.ok is False
    assert result.code == "ACCEPTANCE_ATTEMPT_INPUT_INVALID"
    assert not data.exists()
    assert list(project.iterdir()) == []


def test_checkpoint_at_exact_deadline_is_not_expired(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    now = ["2026-08-24T00:00:00.000000Z"]
    project, data, context = _project_transition_context(tmp_path, monkeypatch, lambda: now[0])
    assert begin_acceptance_attempt(context, attempt_id=ATTEMPT_ID, scenario_id="legacy-keil-migration", scenario_version="1").ok
    now[0] = "2026-08-24T00:01:00.000000Z"
    result = checkpoint_acceptance_attempt(context, attempt_id=ATTEMPT_ID, expected_revision=0, stage="project-materialized")
    assert result.ok is True, result.to_dict()


def test_chain_gap_and_corrupt_root_fail_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    project, data, context = _project_transition_context(tmp_path, monkeypatch, lambda: "2026-08-24T00:00:00.000000Z")
    assert begin_acceptance_attempt(context, attempt_id=ATTEMPT_ID, scenario_id="legacy-keil-migration", scenario_version="1").ok
    assert checkpoint_acceptance_attempt(context, attempt_id=ATTEMPT_ID, expected_revision=0, stage="project-materialized").ok
    workspace = recovery_workflows._workspace_paths_factory(data, project, "00000000-0000-4000-8000-000000000002", "session-a")
    evidence = recovery_workflows._evidence_store_factory(workspace.workspace_root / "evidence")
    recovery_workflows._typed_root_path(evidence, recovery_workflows._root_id(ATTEMPT_ID, 0)).write_bytes(b"{}")
    assert resume_acceptance_attempt(context, attempt_id=ATTEMPT_ID).code == "ACCEPTANCE_ATTEMPT_EVIDENCE_INTEGRITY_FAILED"


def test_orphan_envelope_can_be_retried_to_publish_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    project, data, context = _project_transition_context(tmp_path, monkeypatch, lambda: "2026-08-24T00:00:00.000000Z")
    assert begin_acceptance_attempt(context, attempt_id=ATTEMPT_ID, scenario_id="legacy-keil-migration", scenario_version="1").ok
    original = recovery_workflows._publish_root_locked
    calls = [0]
    def fail_once(evidence, root):
        if calls[0] == 0:
            calls[0] += 1
            raise OSError("simulated orphan root")
        return original(evidence, root)
    monkeypatch.setattr(recovery_workflows, "_publish_root_locked", fail_once)
    first = checkpoint_acceptance_attempt(context, attempt_id=ATTEMPT_ID, expected_revision=0, stage="project-materialized")
    assert first.ok is False
    monkeypatch.setattr(recovery_workflows, "_publish_root_locked", original)
    retry = checkpoint_acceptance_attempt(context, attempt_id=ATTEMPT_ID, expected_revision=0, stage="project-materialized")
    assert retry.ok is True, retry.to_dict()


def test_copied_workspace_root_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    project_a, data_a, context_a = _project_transition_context(tmp_path / "a", monkeypatch, lambda: "2026-08-24T00:00:00.000000Z")
    assert begin_acceptance_attempt(context_a, attempt_id=ATTEMPT_ID, scenario_id="legacy-keil-migration", scenario_version="1").ok
    workspace_a = recovery_workflows._workspace_paths_factory(data_a, project_a, "00000000-0000-4000-8000-000000000002", "session-a")
    project_b = tmp_path / "b" / "project"
    data_b = tmp_path / "b" / "data"
    project_b.mkdir(parents=True)
    data_b.mkdir(parents=True)
    project_b_context = AcceptanceRecoveryContext(project_b, data_b, "session-b", clock=lambda: "2026-08-24T00:00:00.000000Z")
    monkeypatch.setattr(recovery_workflows, "_load_project_model", lambda _root: SimpleNamespace(schema_version=3, logical_project_id=UUID("00000000-0000-4000-8000-000000000002"), memory=SimpleNamespace(source="keil"), target_device="STM32F429ZITx"))
    workspace_b = recovery_workflows._workspace_paths_factory(data_b, project_b, "00000000-0000-4000-8000-000000000002", "session-b")
    shutil.copytree(workspace_a.workspace_root / "evidence", workspace_b.workspace_root / "evidence")
    result = resume_acceptance_attempt(project_b_context, attempt_id=ATTEMPT_ID)
    assert result.code == "ACCEPTANCE_ATTEMPT_EVIDENCE_INTEGRITY_FAILED"


def test_one_workspace_has_one_published_checkpoint_winner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    project, data, context = _project_transition_context(tmp_path, monkeypatch, lambda: "2026-08-24T00:00:00.000000Z")
    assert begin_acceptance_attempt(context, attempt_id=ATTEMPT_ID, scenario_id="legacy-keil-migration", scenario_version="1").ok
    contexts = [AcceptanceRecoveryContext(project, data, "session-a", clock=lambda: "2026-08-24T00:00:00.000000Z") for _ in range(2)]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda item: checkpoint_acceptance_attempt(item, attempt_id=ATTEMPT_ID, expected_revision=0, stage="project-materialized"), contexts))
    assert all(result.ok for result in results), [result.to_dict() for result in results]
    assert results[0].data == results[1].data


def _replace_revision_one(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    mutate_attempt=None,
    mutate_envelope=None,
    target_revision: int = 1,
):
    project, data, context = _project_transition_context(
        tmp_path, monkeypatch, lambda: "2026-08-24T00:00:00.000000Z"
    )
    assert begin_acceptance_attempt(
        context, attempt_id=ATTEMPT_ID, scenario_id="legacy-keil-migration", scenario_version="1"
    ).ok
    assert checkpoint_acceptance_attempt(
        context, attempt_id=ATTEMPT_ID, expected_revision=0, stage="project-materialized"
    ).ok
    if target_revision == 2:
        assert checkpoint_acceptance_attempt(
            context, attempt_id=ATTEMPT_ID, expected_revision=1, stage="firmware-built-before"
        ).ok
    workspace = recovery_workflows._workspace_paths_factory(
        data, project, "00000000-0000-4000-8000-000000000002", "session-a"
    )
    evidence = recovery_workflows._evidence_store_factory(workspace.workspace_root / "evidence")
    root_id = recovery_workflows._root_id(ATTEMPT_ID, target_revision)
    root = get_root(evidence, "acceptance-attempt", root_id)
    old_envelope = evidence.get_envelope(root.manifest_id)
    attempt = recovery_workflows.AcceptanceAttempt.from_value(
        json.loads(recovery_workflows.canonical_json_bytes(old_envelope.metadata["attempt"]).decode("utf-8"))
    )
    payload = attempt.to_dict()
    if mutate_attempt is not None:
        mutate_attempt(payload)
    payload["checkpointId"] = "0" * 64
    payload["checkpointId"] = recovery_workflows.hashlib.sha256(
        recovery_workflows.canonical_json_bytes(
            {key: value for key, value in payload.items() if key != "checkpointId"}
        )
    ).hexdigest()
    replacement = recovery_workflows.AcceptanceAttempt.from_value(payload)
    envelope_values = {
        "identity": old_envelope.identity,
        "operation": old_envelope.operation,
        "produced_at_utc": replacement.updated_at_utc,
        "parents": old_envelope.parents,
        "artifacts": old_envelope.artifacts,
        "metadata": recovery_workflows._envelope_metadata(replacement),
    }
    artifact_bytes = b"tampered-artifact"
    artifact_hash = recovery_workflows.hashlib.sha256(artifact_bytes).hexdigest()
    artifact_path = evidence.root / "objects" / "sha256" / artifact_hash[:2] / artifact_hash
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_bytes(artifact_bytes)
    if mutate_envelope is not None:
        mutate_envelope(envelope_values)
    replacement_envelope = EvidenceEnvelope(**envelope_values)
    with evidence._mutation_lock():
        evidence._put_envelope_locked(replacement_envelope)
        root_path = recovery_workflows._typed_root_path(evidence, root_id)
        root_path.unlink()
        recovery_workflows._publish_root_locked(
            evidence,
            RootRecord("acceptance-attempt", root_id, str(replacement_envelope.evidence_id), recovery_workflows._root_metadata(replacement)),
        )
    return context


def test_canonical_revision_scenario_switch_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    def mutate(payload):
        payload["scenarioId"] = "new-cubemx-project"
        payload["scenarioDigest"] = recovery_workflows.describe_scenario(
            "new-cubemx-project", "1"
        ).scenario_digest
        payload["projectOrigin"] = "cubemx"
    context = _replace_revision_one(tmp_path, monkeypatch, mutate_attempt=mutate)
    result = resume_acceptance_attempt(context, attempt_id=ATTEMPT_ID)
    assert result.code == "ACCEPTANCE_ATTEMPT_EVIDENCE_INTEGRITY_FAILED"


@pytest.mark.parametrize(
    "mutation",
    [
        pytest.param(("attempt2", lambda payload: payload["stageOutputs"].__setitem__("projectModelDigest", "f" * 64)), id="prior-output"),
        pytest.param(
            ("attempt", lambda payload: payload.update(
                {
                    "openedAtUtc": "2026-08-24T00:00:01.000000Z",
                    "updatedAtUtc": "2026-08-24T00:00:01.000000Z",
                    "deadlineAtUtc": "2026-08-24T00:15:01.000000Z",
                }
            )),
            id="opened-time",
        ),
        pytest.param(("attempt", lambda payload: payload.__setitem__("deadlineAtUtc", "2026-08-24T00:16:00.000000Z")), id="deadline-policy"),
        pytest.param(("envelope", lambda envelope: envelope.update({"parents": ("a" * 64,)})), id="wrong-parent"),
        pytest.param(("envelope", lambda envelope: envelope.update({"parents": ()})), id="missing-parent"),
        pytest.param(
            ("envelope", lambda envelope: envelope.update(
                {
                    "artifacts": (
                        ArtifactRef(
                            recovery_workflows.hashlib.sha256(b"tampered-artifact").hexdigest(),
                            len(b"tampered-artifact"),
                            "objects/sha256/" + recovery_workflows.hashlib.sha256(b"tampered-artifact").hexdigest()[:2] + "/" + recovery_workflows.hashlib.sha256(b"tampered-artifact").hexdigest(),
                            "log",
                            "text/plain",
                        ),
                    )
                }
            )),
            id="artifact",
        ),
        pytest.param(
            ("envelope", lambda envelope: envelope.update({"produced_at_utc": "2026-08-24T00:00:01.000000Z"})),
            id="produced-time",
        ),
    ],
)
def test_canonical_chain_mutations_fail_closed_without_new_roots(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutation
):
    target, mutate = mutation
    context = _replace_revision_one(
        tmp_path,
        monkeypatch,
        mutate_attempt=(mutate if target in {"attempt", "attempt2"} else None),
        mutate_envelope=(mutate if target == "envelope" else None),
        target_revision=(2 if target == "attempt2" else 1),
    )
    result = resume_acceptance_attempt(context, attempt_id=ATTEMPT_ID)
    assert result.code == "ACCEPTANCE_ATTEMPT_EVIDENCE_INTEGRITY_FAILED"


def test_current_project_origin_drift_fails_closed_on_public_resume_and_show(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    project, data, context = _project_transition_context(
        tmp_path, monkeypatch, lambda: "2026-08-24T00:00:00.000000Z"
    )
    assert begin_acceptance_attempt(
        context, attempt_id=ATTEMPT_ID, scenario_id="legacy-keil-migration", scenario_version="1"
    ).ok
    monkeypatch.setattr(
        recovery_workflows,
        "_load_project_model",
        lambda _root: SimpleNamespace(
            schema_version=3,
            logical_project_id=UUID("00000000-0000-4000-8000-000000000002"),
            memory=SimpleNamespace(source="cubemx"),
            target_device="STM32F429ZITx",
        ),
    )
    assert resume_acceptance_attempt(context, attempt_id=ATTEMPT_ID).code == "ACCEPTANCE_ATTEMPT_IDENTITY_MISMATCH"
    assert recovery_workflows.show_acceptance_attempt(context, attempt_id=ATTEMPT_ID).code == "ACCEPTANCE_ATTEMPT_IDENTITY_MISMATCH"


@pytest.mark.parametrize(
    ("provider_data", "case_id"),
    [
        pytest.param({}, "missing-build", id="missing-build"),
        pytest.param({"build": []}, "non-mapping-build", id="non-mapping-build"),
        pytest.param(
            {
                "build": {
                    "elfFresh": False,
                    "preset": "arm-debug",
                    "buildId": "b" * 64,
                    "elfSha256": "e" * 64,
                }
            },
            "stale-elf",
            id="stale-elf",
        ),
        pytest.param(
            {
                "build": {
                    "elfFresh": True,
                    "preset": "arm-release",
                    "buildId": "b" * 64,
                    "elfSha256": "e" * 64,
                }
            },
            "wrong-preset",
            id="wrong-preset",
        ),
        pytest.param(
            {
                "build": {
                    "elfFresh": True,
                    "preset": "arm-debug",
                    "buildId": "bad",
                    "elfSha256": "e" * 64,
                }
            },
            "invalid-build-id",
            id="invalid-build-id",
        ),
        pytest.param(
            {
                "build": {
                    "elfFresh": True,
                    "preset": "arm-debug",
                    "buildId": "b" * 64,
                    "elfSha256": "bad",
                }
            },
            "invalid-elf-sha",
            id="invalid-elf-sha",
        ),
    ],
)
def test_public_build_output_refusals_preserve_revision_one(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    provider_data: dict[str, object],
    case_id: str,
) -> None:
    _project, data, context = _project_transition_context(
        tmp_path, monkeypatch, lambda: "2026-08-24T00:00:00.000000Z"
    )
    assert begin_acceptance_attempt(
        context,
        attempt_id=ATTEMPT_ID,
        scenario_id="legacy-keil-migration",
        scenario_version="1",
    ).ok
    materialized = checkpoint_acceptance_attempt(
        context,
        attempt_id=ATTEMPT_ID,
        expected_revision=0,
        stage="project-materialized",
    )
    assert materialized.ok is True, case_id
    before_files = {
        str(path.relative_to(data)): path.read_bytes()
        for path in data.rglob("*")
        if path.is_file()
    }

    def malformed_build(*_args: object) -> recovery_workflows.OperationResult[object]:
        return recovery_workflows.OperationResult.success("project.context", provider_data)

    monkeypatch.setattr(recovery_workflows, "_build_project_context", malformed_build)
    result = checkpoint_acceptance_attempt(
        context,
        attempt_id=ATTEMPT_ID,
        expected_revision=1,
        stage="firmware-built-before",
    )

    assert result.ok is False
    assert result.code == "ACCEPTANCE_ATTEMPT_OUTPUT_INVALID"
    resumed = resume_acceptance_attempt(context, attempt_id=ATTEMPT_ID)
    assert resumed.ok is True
    assert resumed.data["attempt"] == materialized.data["attempt"]
    assert resumed.data["nextStage"] == "firmware-built-before"
    assert {
        str(path.relative_to(data)): path.read_bytes()
        for path in data.rglob("*")
        if path.is_file()
    } == before_files


TARGET_REPLAY_RUN_ID = "00000000-0000-4000-8000-000000000003"


@pytest.mark.parametrize(
    ("case_id", "expected_code"),
    [
        pytest.param("reader-failure", "ACCEPTANCE_ATTEMPT_OUTPUT_INVALID"),
        pytest.param("reader-shape", "ACCEPTANCE_ATTEMPT_OUTPUT_INVALID"),
        pytest.param("run-state", "ACCEPTANCE_ATTEMPT_OUTPUT_INVALID"),
        pytest.param("execution-policy", "ACCEPTANCE_ATTEMPT_OUTPUT_INVALID"),
        pytest.param("workspace-identity", "ACCEPTANCE_ATTEMPT_IDENTITY_MISMATCH"),
        pytest.param(
            "repository-load",
            "ACCEPTANCE_ATTEMPT_EVIDENCE_INTEGRITY_FAILED",
        ),
    ],
)
def test_public_target_replay_refusals_preserve_revision_two(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    case_id: str,
    expected_code: str,
) -> None:
    project, data, context = _project_transition_context(
        tmp_path, monkeypatch, lambda: "2026-08-24T00:00:00.000000Z"
    )
    assert begin_acceptance_attempt(
        context,
        attempt_id=ATTEMPT_ID,
        scenario_id="legacy-keil-migration",
        scenario_version="1",
    ).ok
    assert checkpoint_acceptance_attempt(
        context,
        attempt_id=ATTEMPT_ID,
        expected_revision=0,
        stage="project-materialized",
    ).ok
    built = checkpoint_acceptance_attempt(
        context,
        attempt_id=ATTEMPT_ID,
        expected_revision=1,
        stage="firmware-built-before",
    )
    assert built.ok is True, case_id
    workspace = recovery_workflows._workspace_paths_factory(
        data,
        project,
        "00000000-0000-4000-8000-000000000002",
        "session-a",
    )
    valid_public_data = {
        "run": {
            "run_id": TARGET_REPLAY_RUN_ID,
            "mode": "target",
            "state": "failed",
        },
        "execution_source": "replay",
        "physical_transport_evidence": False,
        "import_workspace_id": workspace.workspace_id,
        "evidence_id": "f" * 64,
    }

    if case_id == "reader-failure":
        def show_failure(*_args: object, **_kwargs: object) -> object:
            return recovery_workflows.OperationResult.failure(
                "test.show", "TEST_RUN_UNAVAILABLE", "provider rejected the run", {}
            )

        monkeypatch.setattr(recovery_workflows, "_test_show", show_failure)
    elif case_id == "reader-shape":
        monkeypatch.setattr(
            recovery_workflows,
            "_test_show",
            lambda *_args, **_kwargs: recovery_workflows.OperationResult.success(
                "test.show", []
            ),
        )
    else:
        public_data = dict(valid_public_data)
        public_data["run"] = dict(valid_public_data["run"])
        if case_id == "run-state":
            public_data["run"]["state"] = "passed"
        elif case_id == "execution-policy":
            public_data["execution_source"] = "physical"
            public_data["physical_transport_evidence"] = True
        elif case_id == "workspace-identity":
            public_data["import_workspace_id"] = "c" * 64
        monkeypatch.setattr(
            recovery_workflows,
            "_test_show",
            lambda *_args, _public_data=public_data, **_kwargs: recovery_workflows.OperationResult.success(
                "test.show", _public_data
            ),
        )

    if case_id == "repository-load":
        evidence = recovery_workflows._evidence_store_factory(
            workspace.workspace_root / "evidence"
        )
        root_path = recovery_workflows._typed_root_path(
            evidence, TARGET_REPLAY_RUN_ID, "test-run"
        )
        root_path.parent.mkdir(parents=True, exist_ok=True)
        root_path.write_bytes(b"{}")

        class Repository:
            def __init__(self, _store: object) -> None:
                pass

            def load(self, _run_id: str) -> object:
                raise OSError("test-run evidence provider unavailable")

        monkeypatch.setattr(recovery_workflows, "TestRunRepository", Repository)

    before_files = {
        str(path.relative_to(data)): path.read_bytes()
        for path in data.rglob("*")
        if path.is_file()
    }
    result = checkpoint_acceptance_attempt(
        context,
        attempt_id=ATTEMPT_ID,
        expected_revision=2,
        stage="target-failure-replayed",
        test_run_id=TARGET_REPLAY_RUN_ID,
    )

    assert result.ok is False
    assert result.code == expected_code
    resumed = resume_acceptance_attempt(context, attempt_id=ATTEMPT_ID)
    assert resumed.ok is True
    assert resumed.data["attempt"] == built.data["attempt"]
    assert resumed.data["nextStage"] == "target-failure-replayed"
    assert {
        str(path.relative_to(data)): path.read_bytes()
        for path in data.rglob("*")
        if path.is_file()
    } == before_files


def test_failed_replay_target_only_mismatch_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    model = SimpleNamespace(logical_project_id=UUID("00000000-0000-4000-8000-000000000002"), target_device="STM32F429ZITx")
    workspace = SimpleNamespace(workspace_id="a" * 64, workspace_root=tmp_path)
    attempt = _base_snapshot(
        attempt_id=ATTEMPT_ID,
        scenario_id="legacy-keil-migration",
        scenario_version="1",
        scenario_digest="e6fc21a053645f6ae3af8be59ed95941f1dddb57921baeff4263b4276e1cd6cb",
        workspace_id=workspace.workspace_id,
        logical_project_id=str(model.logical_project_id),
        project_origin="keil",
        opened_at="2026-08-24T00:00:00.000000Z",
        updated_at="2026-08-24T00:00:00.000000Z",
        revision=2,
        previous_checkpoint_id="a" * 64,
        outputs={
            "projectModelDigest": "c" * 64,
            "beforeBuildId": "b" * 64,
            "beforeElfSha256": "e" * 64,
            "beforeInputSnapshotSha256": "d" * 64,
            "failedBeforeTestRunId": None,
            "failedBeforeEvidenceId": None,
            "diagnosticSessionId": None,
            "diagnosticRevision": None,
            "diagnosticEventHead": None,
            "afterBuildId": None,
            "afterElfSha256": None,
            "afterInputSnapshotSha256": None,
            "sourceChangeDeclarationId": None,
            "acceptanceRecordId": None,
        },
        deadline_at="2026-08-24T00:15:00.000000Z",
    )
    monkeypatch.setattr(
        recovery_workflows,
        "_test_show",
        lambda *_args, **_kwargs: recovery_workflows.OperationResult.success(
            "test.show",
            {
                "run": {"run_id": "00000000-0000-4000-8000-000000000003", "mode": "target", "state": "failed"},
                "execution_source": "replay",
                "physical_transport_evidence": False,
                "import_workspace_id": workspace.workspace_id,
                "evidence_id": "f" * 64,
            },
        ),
    )
    published = SimpleNamespace(
        manifest=SimpleNamespace(
            mode="target", state="failed", transport="replay",
            identity=SimpleNamespace(
                project_id=str(model.logical_project_id), build_id="b" * 64,
                elf_sha256="e" * 64, target_device="OTHER-MCU",
            ),
        ),
        root=SimpleNamespace(metadata={"physical_transport_evidence": False, "import_workspace_id": workspace.workspace_id}),
        envelope=SimpleNamespace(evidence_id="f" * 64),
    )
    monkeypatch.setattr(recovery_workflows, "TestRunRepository", lambda *_args: SimpleNamespace(load=lambda _run_id: published))
    with pytest.raises(recovery_workflows._RecoveryFailure) as error:
        recovery_workflows._build_transition(
            AcceptanceRecoveryContext(tmp_path, tmp_path / "data", "session-a"),
            model,
            workspace,
            attempt,
            "target-failure-replayed",
            test_run_id="00000000-0000-4000-8000-000000000003",
            diagnostic_session_id=None,
            acceptance_record_id=None,
        )
    assert error.value.code == "ACCEPTANCE_ATTEMPT_IDENTITY_MISMATCH"


def test_concurrent_identical_begin_returns_one_exact_revision_zero(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    project, data, context = _project_transition_context(tmp_path, monkeypatch, lambda: "2026-08-24T00:00:00.000000Z")
    contexts = [AcceptanceRecoveryContext(project, data, "session-a", clock=lambda: "2026-08-24T00:00:00.000000Z") for _ in range(2)]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda item: begin_acceptance_attempt(item, attempt_id=ATTEMPT_ID, scenario_id="legacy-keil-migration", scenario_version="1"), contexts))
    assert all(result.ok for result in results), [result.to_dict() for result in results]
    assert results[0].data == results[1].data


def _authorize_revision_four_with_diagnostic_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    source_declaration: bool = False,
    stale: bool = False,
    diagnostic_busy: bool = False,
):
    model = SimpleNamespace(
        logical_project_id=UUID("00000000-0000-4000-8000-000000000002"),
        memory=SimpleNamespace(source="keil"),
        target_device="STM32F429ZITx",
    )
    workspace = SimpleNamespace(workspace_id="a" * 64)
    outputs = {
        "projectModelDigest": "c" * 64,
        "beforeBuildId": "b" * 64,
        "beforeElfSha256": "e" * 64,
        "beforeInputSnapshotSha256": "d" * 64,
        "failedBeforeTestRunId": "00000000-0000-4000-8000-000000000003",
        "failedBeforeEvidenceId": "f" * 64,
        "diagnosticSessionId": "00000000-0000-4000-8000-000000000004",
        "diagnosticRevision": 6,
        "diagnosticEventHead": "1" * 64,
        "afterBuildId": None,
        "afterElfSha256": None,
        "afterInputSnapshotSha256": None,
        "sourceChangeDeclarationId": None,
        "acceptanceRecordId": None,
    }
    current = _base_snapshot(
        attempt_id=ATTEMPT_ID,
        scenario_id="legacy-keil-migration",
        scenario_version="1",
        scenario_digest="e6fc21a053645f6ae3af8be59ed95941f1dddb57921baeff4263b4276e1cd6cb",
        workspace_id=workspace.workspace_id,
        logical_project_id=str(model.logical_project_id),
        project_origin="keil",
        opened_at="2026-08-24T00:00:00.000000Z",
        updated_at="2026-08-24T00:00:00.000000Z",
        revision=4,
        previous_checkpoint_id="a" * 64,
        outputs=outputs,
        deadline_at="2026-08-24T00:15:00.000000Z",
    )
    monkeypatch.setattr(recovery_workflows, "_load_project_and_workspace", lambda _context: (model, workspace, SimpleNamespace()))
    monkeypatch.setattr(recovery_workflows, "_load_chain", lambda *_args, **_kwargs: [(current, SimpleNamespace(evidence_id="2" * 64))])
    monkeypatch.setattr(recovery_workflows, "_validate_chain_semantics", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(recovery_workflows, "_publish_snapshot", lambda *args, **_kwargs: args[4])
    hypothesis = Hypothesis(
        hypothesis_id="9" * 32,
        statement="the captured failure is reproducible",
        status="open",
        confidence_basis="unrated",
        supporting=(),
        refuting=(),
    )
    declaration = SourceChangeDeclaration.new(
        before_source_sha256="1" * 64,
        after_source_sha256="2" * 64,
        before_build_id=outputs["beforeBuildId"],
        before_elf_sha256=outputs["beforeElfSha256"],
        after_build_id="3" * 64,
        after_elf_sha256="4" * 64,
        changed_paths=("src/main.c",),
        diff_evidence_id="5" * 64,
        diff_artifact=ArtifactRef("6" * 64, 4, "objects/sha256/66/" + "6" * 64, "diff", "text/plain"),
        claimed_hypothesis_ids=(hypothesis.hypothesis_id,),
        validation_plan_id="7" * 64,
    )
    diagnostic_session = DiagnosticSession(
        diagnostic_session_id=outputs["diagnosticSessionId"].replace("-", ""),
        revision=outputs["diagnosticRevision"] + (1 if stale else 0),
        state="INVESTIGATING",
        identity=EvidenceIdentity(
            workspace_id=workspace.workspace_id,
            project_id=str(model.logical_project_id),
            session_id="session-a",
            build_id=outputs["beforeBuildId"],
            elf_sha256=outputs["beforeElfSha256"],
            target_device=model.target_device,
            input_snapshot_sha256=outputs["beforeInputSnapshotSha256"],
            git_commit="8" * 40,
            git_dirty=False,
        ),
        failed_test_run_id=outputs["failedBeforeTestRunId"],
        failed_evidence_id=outputs["failedBeforeEvidenceId"],
        event_head="2" * 64 if stale else outputs["diagnosticEventHead"],
        hypotheses=(hypothesis,),
        observation_plans=(),
        observation_results=(),
        source_change_declarations=(declaration,) if source_declaration else (),
    )
    def diagnostic_show(*_args, **_kwargs):
        if diagnostic_busy:
            return recovery_workflows.OperationResult.failure(
                "diagnostic.show",
                "DIAGNOSTIC_STORE_BUSY",
                "Diagnostic store is busy.",
                {},
            )
        return recovery_workflows.OperationResult.success(
            "diagnostic.show", {"session": diagnostic_session.to_dict()}
        )

    monkeypatch.setattr(recovery_workflows, "_diagnostic_show", diagnostic_show)
    context = AcceptanceRecoveryContext(tmp_path, tmp_path / "data", "session-a", clock=lambda: "2026-08-24T00:00:00.000000Z")
    digest = recovery_workflows._action_digest(current)
    return authorize_acceptance_source_change(context, attempt_id=ATTEMPT_ID, expected_revision=4, action_digest=digest, authorized=True)


def test_source_declaration_before_authorization_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    result = _authorize_revision_four_with_diagnostic_failure(tmp_path, monkeypatch, source_declaration=True)
    assert result.code == "ACCEPTANCE_ATTEMPT_OUTPUT_INVALID"


def test_stale_diagnostic_revision_or_head_fails_closed_before_authorization(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    result = _authorize_revision_four_with_diagnostic_failure(tmp_path, monkeypatch, stale=True)
    assert result.code == "ACCEPTANCE_ATTEMPT_IDENTITY_MISMATCH"


def test_nested_diagnostic_store_busy_maps_to_acceptance_availability_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    result = _authorize_revision_four_with_diagnostic_failure(
        tmp_path, monkeypatch, diagnostic_busy=True
    )

    assert result.ok is False
    assert result.code == "ACCEPTANCE_ATTEMPT_BUSY"
    assert result.message == "Acceptance attempt storage is busy."
    assert result.details == {}


@pytest.mark.parametrize(
    "field",
    ["diagnostic_session_id", "workspace_id", "project_id", "target_device", "build_id", "elf_sha256", "input_snapshot_sha256"],
)
def test_diagnostic_lineage_mismatch_fails_closed(field: str, tmp_path: Path):
    model = SimpleNamespace(
        logical_project_id=UUID("00000000-0000-4000-8000-000000000002"),
        target_device="STM32F429ZITx",
    )
    workspace = SimpleNamespace(workspace_id="a" * 64)
    attempt = _base_snapshot(
        attempt_id=ATTEMPT_ID,
        scenario_id="legacy-keil-migration",
        scenario_version="1",
        scenario_digest="e6fc21a053645f6ae3af8be59ed95941f1dddb57921baeff4263b4276e1cd6cb",
        workspace_id=workspace.workspace_id,
        logical_project_id=str(model.logical_project_id),
        project_origin="keil",
        opened_at="2026-08-24T00:00:00.000000Z",
        updated_at="2026-08-24T00:00:00.000000Z",
        revision=4,
        previous_checkpoint_id="a" * 64,
        outputs={
            "projectModelDigest": "c" * 64,
            "beforeBuildId": "b" * 64,
            "beforeElfSha256": "e" * 64,
            "beforeInputSnapshotSha256": "d" * 64,
            "failedBeforeTestRunId": "00000000-0000-4000-8000-000000000003",
            "failedBeforeEvidenceId": "f" * 64,
            "diagnosticSessionId": "00000000-0000-4000-8000-000000000004",
            "diagnosticRevision": 6,
            "diagnosticEventHead": "1" * 64,
            "afterBuildId": None,
            "afterElfSha256": None,
            "afterInputSnapshotSha256": None,
            "sourceChangeDeclarationId": None,
            "acceptanceRecordId": None,
        },
        deadline_at="2026-08-24T00:15:00.000000Z",
    )
    identity = EvidenceIdentity(
        workspace_id=workspace.workspace_id,
        project_id=str(model.logical_project_id),
        session_id="session-a",
        build_id="b" * 64,
        elf_sha256="e" * 64,
        target_device=model.target_device,
        input_snapshot_sha256="d" * 64,
        git_commit="0" * 40,
        git_dirty=False,
    )
    session = SimpleNamespace(
        diagnostic_session_id="00000000000040008000000000000004",
        failed_test_run_id="00000000-0000-4000-8000-000000000003",
        failed_evidence_id="f" * 64,
        event_head="1" * 64,
        identity=identity,
        state="INVESTIGATING",
        source_change_declarations=(),
    )
    if field == "diagnostic_session_id":
        session.diagnostic_session_id = "00000000000040008000000000000005"
    elif field == "workspace_id":
        session.identity = replace(identity, workspace_id="2" * 64)
    elif field == "project_id":
        session.identity = replace(identity, project_id="00000000-0000-4000-8000-000000000005")
    else:
        session.identity = replace(identity, **{field: "2" * 64 if field != "target_device" else "other-target"})
    with pytest.raises(recovery_workflows._RecoveryFailure) as error:
        _validate_diagnostic_session(
            session,
            attempt,
            model,
            workspace,
            expected_session_id="00000000000040008000000000000004",
            allow_source_change=False,
        )
    assert error.value.code == "ACCEPTANCE_ATTEMPT_IDENTITY_MISMATCH"
