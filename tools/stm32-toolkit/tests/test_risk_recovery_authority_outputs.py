from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest
import test_vs08a_scenarios as vs08a
import test_vs08b_scenarios as vs08b
from stm32_toolkit.acceptance import recovery_workflows
from stm32_toolkit.acceptance.recovery_workflows import (
    AcceptanceRecoveryContext,
    authorize_acceptance_source_change,
    begin_acceptance_attempt,
    checkpoint_acceptance_attempt,
    resume_acceptance_attempt,
)
from stm32_toolkit.diagnostic_workflows import (
    DiagnosticWorkflowContext,
    diagnostic_declare_source_change,
)
from stm32_toolkit.evidence import EvidenceIdentity
from stm32_toolkit.evidence.store import EvidenceStore
from stm32_toolkit.paths import WorkspacePaths
from stm32_toolkit.result import OperationResult
from stm32_toolkit.testing.model import calculate_inventory_digest
from stm32_toolkit.testing.publication import TestRunRepository
from stm32_toolkit.testing.replay import (
    calculate_replay_id,
    canonical_replay_json_bytes,
    load_target_replay_fixture,
)
from stm32_toolkit.testing.target import TargetFrameDecoder, encode_frame
from stm32_toolkit.testing_workflows import (
    TestingWorkflowContext,
    target_replay_run,
)
from stm32_toolkit.testing_workflows import (
    test_show as public_test_show,
)

BEFORE_BUILD_ID = "c6b3ea0b953c3d62d50db1bbf4226cd2ff3652ecc271a7a8b5e58913e084f2d0"
BEFORE_ELF_SHA256 = "13dbac824a8ef5ff8034860da48cc55243ab60673a539e73c366e59d40412880"
BEFORE_INPUT_SNAPSHOT_SHA256 = "7104a6333bf42b87ff41445a90f5b547e7256acd84c8e06e4c87eace48c6f139"
AFTER_BUILD_ID = "65e2176034d1f74df3ab4ff1c6099938420ca6cb6367f76458f40ad4dee36ece"
AFTER_ELF_SHA256 = "2b2268ba7c6caa110688f872a4f4264ffdf2c75ceff9bc341d17c2eaedf106c0"
AFTER_INPUT_SNAPSHOT_SHA256 = "70891c0e753d1b65d7fa40f0bbfd78f04b9432e733d89d342081df4b4af813dd"
ALTERNATE_BUILD_ID = "9" * 64
ALTERNATE_ELF_SHA256 = "8" * 64
WRONG_AFTER_BUILD_ID = "7" * 64
WRONG_AFTER_ELF_SHA256 = "6" * 64
ALTERNATE_RUN_ID = "00000000-0000-4000-8000-000000000004"


def _build_identity(build_id: str, elf_sha256: str, input_snapshot_sha256: str) -> dict[str, str]:
    return {
        "buildId": build_id,
        "elfSha256": elf_sha256,
        "inputSnapshotSha256": input_snapshot_sha256,
    }


BEFORE_IDENTITY = _build_identity(
    BEFORE_BUILD_ID, BEFORE_ELF_SHA256, BEFORE_INPUT_SNAPSHOT_SHA256
)
AFTER_IDENTITY = _build_identity(AFTER_BUILD_ID, AFTER_ELF_SHA256, AFTER_INPUT_SNAPSHOT_SHA256)
ALTERNATE_IDENTITY = _build_identity(
    ALTERNATE_BUILD_ID, ALTERNATE_ELF_SHA256, BEFORE_INPUT_SNAPSHOT_SHA256
)
WRONG_AFTER_IDENTITY = _build_identity(
    WRONG_AFTER_BUILD_ID, WRONG_AFTER_ELF_SHA256, AFTER_INPUT_SNAPSHOT_SHA256
)


@dataclass
class _Prefix:
    project_root: Path
    data_root: Path
    runtime_session_id: str
    diagnostic_id: str
    hypothesis_id: str
    fixed_descriptor: Path
    fixed_stream: Path
    context: AcceptanceRecoveryContext
    revision_four_attempt: dict[str, object]
    build_calls: list[dict[str, str]]
    snapshot_calls: list[str]


def _file_snapshot(root: Path) -> dict[str, bytes]:
    if not root.exists():
        return {}
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def _persistence_snapshot(prefix: _Prefix) -> tuple[dict[str, bytes], dict[str, bytes]]:
    workspace = WorkspacePaths.from_roots(
        prefix.data_root,
        prefix.project_root,
        vs08a.PROJECT_ID,
        prefix.runtime_session_id,
    )
    return (
        _file_snapshot(workspace.workspace_root / "evidence"),
        _file_snapshot(workspace.diagnostics_root),
    )


def _install_build_seam(
    monkeypatch: pytest.MonkeyPatch,
    build_values: Sequence[Mapping[str, str]],
    snapshot_values: Sequence[str],
) -> tuple[list[dict[str, str]], list[str]]:
    build_calls: list[dict[str, str]] = []
    snapshot_calls: list[str] = []

    def build_context(*_args: object) -> OperationResult[dict[str, object]]:
        index = len(build_calls)
        if index >= len(build_values):
            raise AssertionError("unexpected build provider call")
        value = dict(build_values[index])
        build_calls.append(value)
        return OperationResult.success(
            "project.context",
            {
                "build": {
                    "elfFresh": True,
                    "preset": "arm-debug",
                    "buildId": value["buildId"],
                    "elfSha256": value["elfSha256"],
                }
            },
        )

    def snapshot_provider(_model: object) -> object:
        index = len(snapshot_calls)
        if index >= len(snapshot_values):
            raise AssertionError("unexpected input snapshot provider call")
        value = snapshot_values[index]
        snapshot_calls.append(value)
        return SimpleNamespace(sha256=value)

    monkeypatch.setattr(recovery_workflows, "_build_project_context", build_context)
    monkeypatch.setattr(recovery_workflows, "snapshot_project_inputs", snapshot_provider)
    return build_calls, snapshot_calls


def _prepare_prefix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    build_values: Sequence[Mapping[str, str]],
    snapshot_values: Sequence[str],
) -> _Prefix:
    runtime_session_id = "w4r-recovery-keil"
    (
        project_root,
        data_root,
        diagnostic_id,
        hypothesis_id,
        _failed_descriptor,
        fixed_descriptor,
        fixed_stream,
    ) = vs08b._prepare_real_diagnostic_before_source(
        tmp_path,
        "keil",
        monkeypatch,
        runtime_session_id,
    )
    build_calls, snapshot_calls = _install_build_seam(
        monkeypatch, build_values, snapshot_values
    )
    context = AcceptanceRecoveryContext(
        project_root,
        data_root,
        runtime_session_id,
        clock=lambda: "2026-08-24T00:00:00.000000Z",
    )
    started = begin_acceptance_attempt(
        context,
        attempt_id=vs08b.ATTEMPT_ID,
        scenario_id="legacy-keil-migration",
        scenario_version="1",
    )
    assert started.ok is True, started.to_dict()
    for expected_revision, stage, kwargs in (
        (0, "project-materialized", {}),
        (1, "firmware-built-before", {}),
        (
            2,
            "target-failure-replayed",
            {"test_run_id": vs08a.FAILED_RUN_ID},
        ),
        (
            3,
            "diagnosis-completed",
            {"diagnostic_session_id": diagnostic_id},
        ),
    ):
        result = checkpoint_acceptance_attempt(
            context,
            attempt_id=vs08b.ATTEMPT_ID,
            expected_revision=expected_revision,
            stage=stage,
            **kwargs,
        )
        assert result.ok is True, result.to_dict()
    resumed = resume_acceptance_attempt(context, attempt_id=vs08b.ATTEMPT_ID)
    assert resumed.ok is True, resumed.to_dict()
    attempt = resumed.to_dict()["data"]["attempt"]
    assert isinstance(attempt, dict)
    assert attempt["revision"] == 4
    assert resumed.to_dict()["data"]["nextStage"] == "firmware-built-after"
    assert len(build_calls) == 1
    assert len(snapshot_calls) == 1
    return _Prefix(
        project_root=project_root,
        data_root=data_root,
        runtime_session_id=runtime_session_id,
        diagnostic_id=diagnostic_id,
        hypothesis_id=hypothesis_id,
        fixed_descriptor=fixed_descriptor,
        fixed_stream=fixed_stream,
        context=context,
        revision_four_attempt=attempt,
        build_calls=build_calls,
        snapshot_calls=snapshot_calls,
    )


def _assert_failure(
    result: object,
    *,
    operation: str,
    code: str,
) -> None:
    messages = {
        "ACCEPTANCE_ATTEMPT_AUTHORIZATION_REQUIRED": (
            "Acceptance attempt requires explicit source-change authorization."
        ),
        "ACCEPTANCE_ATTEMPT_OUTPUT_INVALID": "Acceptance attempt public output is invalid.",
        "ACCEPTANCE_ATTEMPT_IDENTITY_MISMATCH": "Acceptance attempt identity does not match.",
    }
    assert result.to_dict() == {
        "protocol": "stm32-toolkit/1",
        "ok": False,
        "operation": operation,
        "code": code,
        "message": messages[code],
        "data": None,
        "details": {},
    }


def _assert_resume(
    result: object,
    *,
    expected_attempt: dict[str, object],
    next_stage: str,
    authorization_required: bool,
    action_digest: str | None,
) -> dict[str, object]:
    payload = result.to_dict()
    assert payload["protocol"] == "stm32-toolkit/1"
    assert payload["ok"] is True
    assert payload["operation"] == "acceptance.attempt.resume"
    assert payload["code"] == "OK"
    assert payload["message"] == ""
    assert payload["details"] == {}
    data = payload["data"]
    assert isinstance(data, dict)
    assert set(data) == {
        "authoritative",
        "attempt",
        "nextStage",
        "authorizationRequired",
        "actionDigest",
        "timedOut",
        "recoveryPolicy",
    }
    assert data["authoritative"] is True
    assert data["attempt"] == expected_attempt
    assert data["nextStage"] == next_stage
    assert data["authorizationRequired"] is authorization_required
    assert data["actionDigest"] == action_digest
    assert data["timedOut"] is False
    assert isinstance(data["recoveryPolicy"], dict)
    return data


def _assert_target_show(
    result: object,
    *,
    run_id: str,
    build_id: str,
    elf_sha256: str,
) -> dict[str, object]:
    payload = result.to_dict()
    assert payload["protocol"] == "stm32-toolkit/1"
    assert payload["ok"] is True
    assert payload["operation"] == "test.show"
    assert payload["code"] == "OK"
    assert payload["message"] == ""
    assert payload["details"] == {}
    data = payload["data"]
    assert isinstance(data, dict)
    assert set(data) == {
        "run",
        "test_manifest",
        "evidence_id",
        "execution_source",
        "physical_transport_evidence",
        "origin_workspace_id",
        "import_workspace_id",
        "authoritative",
    }
    assert data["authoritative"] is True
    run = data["run"]
    assert isinstance(run, dict)
    assert run["run_id"] == run_id
    identity = run["identity"]
    assert isinstance(identity, dict)
    assert identity["build_id"] == build_id
    assert identity["elf_sha256"] == elf_sha256
    assert data["execution_source"] == "replay"
    assert data["physical_transport_evidence"] is False
    return data


def _alternate_replay_inputs(tmp_path: Path, workspace_id: str) -> tuple[Path, Path]:
    descriptor_path, stream_path = vs08a._canonical_replay_inputs(
        tmp_path, "failed-before", ALTERNATE_RUN_ID
    )
    descriptor = json.loads(descriptor_path.read_text(encoding="utf-8"))
    descriptor["identity"]["workspace_id"] = workspace_id
    descriptor["identity"]["build_id"] = ALTERNATE_BUILD_ID
    descriptor["identity"]["elf_sha256"] = ALTERNATE_ELF_SHA256
    identity = EvidenceIdentity.from_dict(descriptor["identity"])
    case_ids = ("case.replay",)
    inventory_digest = calculate_inventory_digest("target", identity, case_ids)
    descriptor["inventory_digest"] = inventory_digest

    stream = bytes.fromhex(stream_path.read_text(encoding="ascii"))
    decoder = TargetFrameDecoder(max_stream_bytes=len(stream))
    frames = decoder.feed(stream)
    decoder.finish()
    encoded: list[bytes] = []
    for frame in frames[:-1]:
        payload = vs08a._json_thaw(frame.payload)
        assert isinstance(payload, dict)
        if frame.kind == 1:
            payload["identity"] = identity.to_dict()
            payload["inventory_digest"] = inventory_digest
        elif frame.kind == 2:
            payload["inventory_digest"] = inventory_digest
        encoded.append(encode_frame(frame.kind, frame.sequence, payload))
    terminal = vs08a._json_thaw(frames[-1].payload)
    assert isinstance(terminal, dict)
    terminal["build_id"] = ALTERNATE_BUILD_ID
    terminal["elf_sha256"] = ALTERNATE_ELF_SHA256
    terminal["inventory_digest"] = inventory_digest
    terminal["event_stream_digest"] = hashlib.sha256(b"".join(encoded)).hexdigest()
    encoded.append(encode_frame(frames[-1].kind, frames[-1].sequence, terminal))
    rewritten = b"".join(encoded)
    descriptor["stream"]["sha256"] = hashlib.sha256(rewritten).hexdigest()
    descriptor["stream"]["size_bytes"] = len(rewritten)
    descriptor["replay_id"] = calculate_replay_id(descriptor)
    descriptor_path.write_bytes(canonical_replay_json_bytes(descriptor))
    stream_path.write_text(rewritten.hex(), encoding="ascii")
    return descriptor_path, stream_path


def _authorize_revision_four(prefix: _Prefix) -> dict[str, object]:
    resumed = resume_acceptance_attempt(prefix.context, attempt_id=vs08b.ATTEMPT_ID)
    data = _assert_resume(
        resumed,
        expected_attempt=prefix.revision_four_attempt,
        next_stage="firmware-built-after",
        authorization_required=True,
        action_digest=None,
    )
    digest = data["actionDigest"]
    assert isinstance(digest, str) and len(digest) == 64
    authorized = authorize_acceptance_source_change(
        prefix.context,
        attempt_id=vs08b.ATTEMPT_ID,
        expected_revision=4,
        action_digest=digest,
        authorized=True,
    )
    payload = authorized.to_dict()
    assert payload["protocol"] == "stm32-toolkit/1"
    assert payload["ok"] is True
    assert payload["operation"] == "acceptance.attempt.authorize-source-change"
    assert payload["code"] == "OK"
    assert payload["message"] == ""
    assert payload["details"] == {}
    data = payload["data"]
    assert isinstance(data, dict) and set(data) == {"attempt"}
    attempt = data["attempt"]
    assert isinstance(attempt, dict)
    assert attempt["revision"] == 5
    authorization = attempt["sourceChangeAuthorization"]
    assert isinstance(authorization, dict)
    assert authorization["actionDigest"] == digest
    assert authorization["authorized"] is True
    return attempt


def test_recovery_rejects_different_build_replay_without_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prefix = _prepare_prefix(
        tmp_path,
        monkeypatch,
        build_values=(BEFORE_IDENTITY,),
        snapshot_values=(BEFORE_INPUT_SNAPSHOT_SHA256,),
    )
    workspace = WorkspacePaths.from_roots(
        prefix.data_root,
        prefix.project_root,
        vs08a.PROJECT_ID,
        prefix.runtime_session_id,
    )
    alternate_descriptor, alternate_stream = _alternate_replay_inputs(
        tmp_path, workspace.workspace_id
    )
    testing = TestingWorkflowContext(
        prefix.project_root, prefix.data_root, prefix.runtime_session_id
    )
    imported = target_replay_run(
        testing,
        ALTERNATE_RUN_ID,
        alternate_descriptor,
        alternate_stream,
    )
    assert imported.ok is True, imported.to_dict()
    _assert_target_show(
        public_test_show(testing, run_id=ALTERNATE_RUN_ID),
        run_id=ALTERNATE_RUN_ID,
        build_id=ALTERNATE_BUILD_ID,
        elf_sha256=ALTERNATE_ELF_SHA256,
    )
    before_files = _persistence_snapshot(prefix)
    refused = checkpoint_acceptance_attempt(
        prefix.context,
        attempt_id=vs08b.ATTEMPT_ID,
        expected_revision=2,
        stage="target-failure-replayed",
        test_run_id=ALTERNATE_RUN_ID,
    )
    _assert_failure(
        refused,
        operation="acceptance.attempt.checkpoint",
        code="ACCEPTANCE_ATTEMPT_OUTPUT_INVALID",
    )
    _assert_resume(
        resume_acceptance_attempt(prefix.context, attempt_id=vs08b.ATTEMPT_ID),
        expected_attempt=prefix.revision_four_attempt,
        next_stage="firmware-built-after",
        authorization_required=True,
        action_digest=None,
    )
    assert _persistence_snapshot(prefix) == before_files
    _assert_target_show(
        public_test_show(testing, run_id=vs08a.FAILED_RUN_ID),
        run_id=vs08a.FAILED_RUN_ID,
        build_id=BEFORE_BUILD_ID,
        elf_sha256=BEFORE_ELF_SHA256,
    )
    _assert_target_show(
        public_test_show(testing, run_id=ALTERNATE_RUN_ID),
        run_id=ALTERNATE_RUN_ID,
        build_id=ALTERNATE_BUILD_ID,
        elf_sha256=ALTERNATE_ELF_SHA256,
    )


def test_recovery_requires_public_authorization_before_after_build(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prefix = _prepare_prefix(
        tmp_path,
        monkeypatch,
        build_values=(BEFORE_IDENTITY,),
        snapshot_values=(BEFORE_INPUT_SNAPSHOT_SHA256,),
    )
    before_files = _persistence_snapshot(prefix)
    build_call_count = len(prefix.build_calls)
    snapshot_call_count = len(prefix.snapshot_calls)
    refused = checkpoint_acceptance_attempt(
        prefix.context,
        attempt_id=vs08b.ATTEMPT_ID,
        expected_revision=4,
        stage="firmware-built-after",
    )
    _assert_failure(
        refused,
        operation="acceptance.attempt.checkpoint",
        code="ACCEPTANCE_ATTEMPT_AUTHORIZATION_REQUIRED",
    )
    assert len(prefix.build_calls) == build_call_count
    assert len(prefix.snapshot_calls) == snapshot_call_count
    assert _persistence_snapshot(prefix) == before_files
    authorized = _authorize_revision_four(prefix)
    assert authorized["revision"] == 5
    resumed = resume_acceptance_attempt(prefix.context, attempt_id=vs08b.ATTEMPT_ID)
    _assert_resume(
        resumed,
        expected_attempt=authorized,
        next_stage="firmware-built-after",
        authorization_required=False,
        action_digest=None,
    )


def test_recovery_rejects_unchanged_after_build_and_preserves_authorization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prefix = _prepare_prefix(
        tmp_path,
        monkeypatch,
        build_values=(BEFORE_IDENTITY, BEFORE_IDENTITY),
        snapshot_values=(BEFORE_INPUT_SNAPSHOT_SHA256, BEFORE_INPUT_SNAPSHOT_SHA256),
    )
    authorized = _authorize_revision_four(prefix)
    before_files = _persistence_snapshot(prefix)
    refused = checkpoint_acceptance_attempt(
        prefix.context,
        attempt_id=vs08b.ATTEMPT_ID,
        expected_revision=5,
        stage="firmware-built-after",
    )
    _assert_failure(
        refused,
        operation="acceptance.attempt.checkpoint",
        code="ACCEPTANCE_ATTEMPT_OUTPUT_INVALID",
    )
    assert len(prefix.build_calls) == 2
    assert len(prefix.snapshot_calls) == 2
    _assert_resume(
        resume_acceptance_attempt(prefix.context, attempt_id=vs08b.ATTEMPT_ID),
        expected_attempt=authorized,
        next_stage="firmware-built-after",
        authorization_required=False,
        action_digest=None,
    )
    assert _persistence_snapshot(prefix) == before_files


def test_recovery_requires_exact_declared_after_identity_then_publishes_revision_six(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prefix = _prepare_prefix(
        tmp_path,
        monkeypatch,
        build_values=(BEFORE_IDENTITY, WRONG_AFTER_IDENTITY, AFTER_IDENTITY),
        snapshot_values=(
            BEFORE_INPUT_SNAPSHOT_SHA256,
            AFTER_INPUT_SNAPSHOT_SHA256,
            AFTER_INPUT_SNAPSHOT_SHA256,
        ),
    )
    authorized = _authorize_revision_four(prefix)
    fixed_fixture = load_target_replay_fixture(prefix.fixed_descriptor, prefix.fixed_stream)
    testing = TestingWorkflowContext(
        prefix.project_root, prefix.data_root, prefix.runtime_session_id
    )
    fixed = target_replay_run(
        testing,
        vs08a.FIXED_RUN_ID,
        prefix.fixed_descriptor,
        prefix.fixed_stream,
    )
    assert fixed.ok is True, fixed.to_dict()
    workspace = WorkspacePaths.from_roots(
        prefix.data_root,
        prefix.project_root,
        vs08a.PROJECT_ID,
        prefix.runtime_session_id,
    )
    evidence = EvidenceStore(workspace.workspace_root / "evidence")
    before_run = TestRunRepository(evidence).load(vs08a.FAILED_RUN_ID)
    declaration = vs08a._source_change(
        tmp_path,
        evidence,
        before_run,
        fixed_fixture.descriptor.identity,
        prefix.hypothesis_id,
    )
    declared = diagnostic_declare_source_change(
        DiagnosticWorkflowContext(
            prefix.project_root, prefix.data_root, prefix.runtime_session_id
        ),
        operation_id="w4r-source-change-declare",
        diagnostic_session_id=prefix.diagnostic_id.replace("-", ""),
        expected_revision=6,
        source_change_declaration=declaration,
    )
    assert declared.ok is True, declared.to_dict()
    before_files = _persistence_snapshot(prefix)
    refused = checkpoint_acceptance_attempt(
        prefix.context,
        attempt_id=vs08b.ATTEMPT_ID,
        expected_revision=5,
        stage="firmware-built-after",
    )
    _assert_failure(
        refused,
        operation="acceptance.attempt.checkpoint",
        code="ACCEPTANCE_ATTEMPT_IDENTITY_MISMATCH",
    )
    _assert_resume(
        resume_acceptance_attempt(prefix.context, attempt_id=vs08b.ATTEMPT_ID),
        expected_attempt=authorized,
        next_stage="firmware-built-after",
        authorization_required=False,
        action_digest=None,
    )
    assert _persistence_snapshot(prefix) == before_files
    recovered = checkpoint_acceptance_attempt(
        prefix.context,
        attempt_id=vs08b.ATTEMPT_ID,
        expected_revision=5,
        stage="firmware-built-after",
    )
    assert recovered.ok is True, recovered.to_dict()
    recovered_attempt = recovered.to_dict()["data"]["attempt"]
    assert isinstance(recovered_attempt, dict)
    assert recovered_attempt["revision"] == 6
    assert recovered_attempt["stageOutputs"]["afterBuildId"] == AFTER_BUILD_ID
    assert recovered_attempt["stageOutputs"]["afterElfSha256"] == AFTER_ELF_SHA256
    assert recovered_attempt["stageOutputs"]["afterInputSnapshotSha256"] == AFTER_INPUT_SNAPSHOT_SHA256
    assert recovered_attempt["stageOutputs"]["sourceChangeDeclarationId"] == declaration.declaration_id
    _assert_resume(
        resume_acceptance_attempt(prefix.context, attempt_id=vs08b.ATTEMPT_ID),
        expected_attempt=recovered_attempt,
        next_stage="target-fix-verified",
        authorization_required=False,
        action_digest=None,
    )
