from __future__ import annotations

import hashlib
import json
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from stm32_monitor.analysis import AnalysisRequest
from stm32_monitor.analysis_workflows import (
    compare_monitor_runs,
    export_analysis_bundle,
)
from stm32_monitor.replay import ingest_monitor_replay
from stm32_toolkit import __version__
from stm32_toolkit.acceptance.model import AcceptanceRecord
from stm32_toolkit.acceptance.recovery import AcceptanceAttempt
from stm32_toolkit.acceptance.recovery_workflows import (
    AcceptanceRecoveryContext,
    authorize_acceptance_source_change,
    begin_acceptance_attempt,
    checkpoint_acceptance_attempt,
    resume_acceptance_attempt,
    show_acceptance_attempt,
)
from stm32_toolkit.acceptance.workflows import (
    AcceptanceWorkflowContext,
    record_acceptance_scenario,
    show_acceptance_scenario,
)
from stm32_toolkit.build.identity import snapshot_project_inputs
from stm32_toolkit.context import build_project_context
from stm32_toolkit.diagnostic_workflows import (
    DiagnosticWorkflowContext,
    diagnostic_add_hypothesis,
    diagnostic_add_plan,
    diagnostic_add_verification_plan,
    diagnostic_assess_hypothesis,
    diagnostic_attach_marker,
    diagnostic_begin,
    diagnostic_complete_verification,
    diagnostic_declare_source_change,
    diagnostic_run_plan,
    diagnostic_start,
    diagnostic_start_verification,
)
from stm32_toolkit.diagnostics import SourceChangeDeclaration, VerificationPlan
from stm32_toolkit.evidence import (
    EvidenceEnvelope,
    EvidenceIdentity,
    canonical_json_bytes,
)
from stm32_toolkit.evidence.gc import RootRecord, get_root, put_root
from stm32_toolkit.evidence.store import EvidenceStore
from stm32_toolkit.paths import WorkspacePaths
from stm32_toolkit.project_model import load_project_model
from stm32_toolkit.testing.model import calculate_inventory_digest
from stm32_toolkit.testing.publication import TestRunRepository
from stm32_toolkit.testing.replay import (
    calculate_replay_id,
    canonical_replay_json_bytes,
    load_target_replay_fixture,
)
from stm32_toolkit.testing.target import TargetFrameDecoder, encode_frame
from stm32_toolkit.testing_workflows import TestingWorkflowContext, target_replay_run
from test_flash import _publish_current_debug_build
from test_vs08a_scenarios import MONITOR_FIXTURES, MONITOR_OPERATION_IDS

PROJECT_ID = UUID("123e4567-e89b-42d3-a456-426614174000")
ATTEMPT_ID = "00000000-0000-4000-8000-000000000001"
FAILED_RUN_ID = "00000000-0000-4000-8000-000000000002"
SESSION_ID = "wave11-recovery-session"
TARGET_FIXTURES = Path(__file__).parent / "fixtures" / "vs03" / "target"

_MESSAGES = {
    "ACCEPTANCE_ATTEMPT_REVISION_CONFLICT": "Acceptance attempt revision conflicts with the current chain.",
    "ACCEPTANCE_ATTEMPT_STAGE_INVALID": "Acceptance attempt stage is invalid.",
    "ACCEPTANCE_ATTEMPT_AUTHORIZATION_REQUIRED": "Acceptance attempt requires explicit source-change authorization.",
    "ACCEPTANCE_ATTEMPT_INPUT_INVALID": "Acceptance attempt input is invalid.",
    "ACCEPTANCE_ATTEMPT_OUTPUT_INVALID": "Acceptance attempt public output is invalid.",
    "ACCEPTANCE_ATTEMPT_ACTION_DIGEST_MISMATCH": "Acceptance attempt action digest does not match.",
    "ACCEPTANCE_ATTEMPT_EVIDENCE_INTEGRITY_FAILED": "Acceptance attempt evidence failed integrity validation.",
}

_ACCEPTANCE_MESSAGES = {
    "ACCEPTANCE_REFERENCE_INVALID": "Acceptance scenario reference is invalid.",
    "ACCEPTANCE_EVIDENCE_INTEGRITY_FAILED": "Acceptance evidence failed integrity validation.",
    "ACCEPTANCE_IDENTITY_MISMATCH": "Acceptance scenario identity does not match.",
    "ACCEPTANCE_RECORD_CONFLICT": "Acceptance record ID is already bound to different content.",
}


@dataclass(frozen=True)
class _Prefix:
    project_root: Path
    data_root: Path
    context: AcceptanceRecoveryContext
    diagnostic_session_id: str
    diagnostic_compact_id: str
    hypothesis_id: str


def _json_thaw(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _json_thaw(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_thaw(item) for item in value]
    return value


def _data(result: object) -> Mapping[str, object]:
    assert getattr(result, "ok", False), getattr(result, "to_dict", lambda: result)()
    value = getattr(result, "data", None)
    assert isinstance(value, Mapping)
    return value


def _wire(result: object) -> dict[str, object]:
    value = getattr(result, "to_dict", None)
    assert callable(value)
    wire = value()
    assert isinstance(wire, dict)
    return wire


def _assert_failure(result: object, code: str, *, operation: str) -> None:
    wire = _wire(result)
    assert wire == {
        "protocol": "stm32-toolkit/1",
        "ok": False,
        "operation": operation,
        "code": code,
        "message": _MESSAGES[code],
        "data": None,
        "details": {},
    }


def _assert_acceptance_failure(result: object, code: str, *, operation: str) -> None:
    assert _wire(result) == {
        "protocol": "stm32-toolkit/1",
        "ok": False,
        "operation": operation,
        "code": code,
        "message": _ACCEPTANCE_MESSAGES[code],
        "data": None,
        "details": {},
    }


def _file_snapshot(root: Path) -> dict[str, bytes]:
    if not root.exists():
        return {}
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def _restore_file_snapshot(root: Path, snapshot: Mapping[str, bytes]) -> None:
    current = _file_snapshot(root)
    for relative in sorted(set(current) - set(snapshot), reverse=True):
        (root / relative).unlink()
    for relative, payload in snapshot.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)


def _persistence_snapshot(
    project_root: Path, data_root: Path
) -> tuple[dict[str, bytes], dict[str, bytes]]:
    return _file_snapshot(project_root), _file_snapshot(data_root)


def _write_project(project_root: Path) -> None:
    project_root.mkdir(parents=True, exist_ok=True)
    (project_root / "App").mkdir()
    (project_root / "App" / "main.c").write_text(
        "int main(void) { return 0; }\r\n", encoding="utf-8"
    )
    manifest = {
        "schemaVersion": 3,
        "logicalProjectId": str(PROJECT_ID),
        "generatedBy": {"tool": "stm32-toolkit", "version": __version__},
        "project": {"name": "wave11-keil-public", "origin": "keil-migration"},
        "target": {"device": "STM32F429ZGTx", "core": "cortex-m4"},
        "framework": {"type": "spl", "version": None},
        "build": {
            "sources": ["App/main.c"],
            "includePaths": [],
            "defines": [],
            "compileOptions": [],
            "assemblySources": [],
            "presets": [],
            "elf": "build/arm-debug/firmware.elf",
        },
        "memory": {
            "source": "keil",
            "regions": [
                {
                    "name": "FLASH",
                    "origin": 0x08000000,
                    "length": 0x00100000,
                    "attributes": "r-x",
                },
                {
                    "name": "RAM",
                    "origin": 0x20000000,
                    "length": 0x00020000,
                    "attributes": "rwx",
                },
            ],
        },
        "debug": {"backend": "pyocd", "target": "stm32f429zg", "svd": None},
        "generation": {
            "cubeMxIoc": None,
            "managedManifest": ".stm32-toolkit/generated-files.json",
            "generatedDirectories": [],
            "userDirectories": [],
        },
        "testing": {
            "target": {
                "executable": "build/test/firmware-tests.elf",
                "timeout_seconds": 120,
                "transport": {
                    "kind": "memory-mailbox",
                    "options": {"address": 0x20010000, "size": 4096},
                },
            }
        },
    }
    manifest_bytes = canonical_json_bytes(manifest)
    (project_root / ".stm32-project.json").write_bytes(manifest_bytes)
    managed_root = project_root / ".stm32-toolkit"
    managed_root.mkdir()
    (managed_root / "generated-files.json").write_bytes(
        canonical_json_bytes(
            {
                "schemaVersion": 1,
                "tool": "stm32-toolkit",
                "toolVersion": __version__,
                "templateVersion": 1,
                "projectManifestSha256": hashlib.sha256(manifest_bytes).hexdigest(),
                "files": [],
            }
        )
    )


def _initialize_git(project_root: Path) -> None:
    (project_root / ".gitignore").write_text(
        "build/\r\nartifacts/migration/\r\n.stm32-toolkit/build.lock\r\n",
        encoding="utf-8",
    )
    commands = (
        ("git", "init", "-q"),
        ("git", "config", "user.name", "stm32tk-wave11"),
        ("git", "config", "user.email", "stm32tk-wave11@example.invalid"),
        ("git", "add", "-A"),
        ("git", "commit", "-q", "-m", "wave11 fixture"),
    )
    for command in commands:
        subprocess.run(
            command,
            cwd=project_root,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def _wire_diagnostic_id(compact: str) -> str:
    return f"{compact[:8]}-{compact[8:12]}-{compact[12:16]}-{compact[16:20]}-{compact[20:]}"


def _replay_inputs(
    tmp_path: Path,
    role: str,
    run_id: str,
    identity: EvidenceIdentity,
) -> tuple[Path, Path]:
    descriptor = json.loads(
        (TARGET_FIXTURES / f"{role}.json").read_text(encoding="utf-8")
    )
    source_stream = bytes.fromhex(
        "".join((TARGET_FIXTURES / f"{role}.hex").read_text(encoding="ascii").split())
    )
    decoder = TargetFrameDecoder(max_stream_bytes=len(source_stream))
    frames = decoder.feed(source_stream)
    decoder.finish()
    assert frames and frames[0].kind == 1 and frames[-1].kind == 5
    first_payload = _json_thaw(frames[0].payload)
    assert isinstance(first_payload, dict)
    case_ids = tuple(str(case_id) for case_id in first_payload["case_ids"])
    inventory_digest = calculate_inventory_digest("target", identity, case_ids)
    descriptor["identity"] = identity.to_dict()
    descriptor["inventory_digest"] = inventory_digest
    encoded: list[bytes] = []
    for frame in frames[:-1]:
        payload = _json_thaw(frame.payload)
        assert isinstance(payload, dict)
        if frame.kind == 1:
            payload["identity"] = identity.to_dict()
            payload["inventory_digest"] = inventory_digest
        elif frame.kind == 2:
            payload["run_id"] = run_id
            payload["inventory_digest"] = inventory_digest
        encoded.append(encode_frame(frame.kind, frame.sequence, payload))
    terminal = _json_thaw(frames[-1].payload)
    assert isinstance(terminal, dict)
    terminal.update(
        {
            "build_id": identity.build_id,
            "elf_sha256": identity.elf_sha256,
            "inventory_digest": inventory_digest,
            "target_device": identity.target_device,
            "event_stream_digest": hashlib.sha256(b"".join(encoded)).hexdigest(),
        }
    )
    encoded.append(encode_frame(frames[-1].kind, frames[-1].sequence, terminal))
    stream = b"".join(encoded)
    descriptor["stream"]["sha256"] = hashlib.sha256(stream).hexdigest()
    descriptor["stream"]["size_bytes"] = len(stream)
    descriptor["replay_id"] = calculate_replay_id(descriptor)
    root = tmp_path / "replay-inputs" / f"{role}-{run_id}"
    root.mkdir(parents=True)
    descriptor_path = root / "descriptor.json"
    stream_path = root / "stream.hex"
    descriptor_path.write_bytes(canonical_replay_json_bytes(descriptor))
    stream_path.write_text(stream.hex(), encoding="ascii")
    return descriptor_path, stream_path


def _prepare_prefix(tmp_path: Path, *, with_build: bool) -> _Prefix:
    project_root = tmp_path / "project"
    data_root = tmp_path / "data"
    _write_project(project_root)
    _initialize_git(project_root)
    if with_build:
        identity_document = _publish_current_debug_build(project_root)
    model = load_project_model(project_root)
    if with_build:
        context_result = build_project_context(project_root, data_root, SESSION_ID)
        context_data = _data(context_result)
        build = context_data["build"]
        assert isinstance(build, Mapping)
        assert build["elfFresh"] is True
        assert build["buildId"] == identity_document["buildId"]
        assert build["elfSha256"] == identity_document["elfSha256"]
        build_id = str(build["buildId"])
        elf_sha256 = str(build["elfSha256"])
        git_commit = str(build["gitHead"])
        input_snapshot_sha256 = snapshot_project_inputs(model).sha256
        target_device = str(context_data["project"]["target"])
        workspace = WorkspacePaths.from_roots(
            data_root, project_root, PROJECT_ID, SESSION_ID
        )
        replay_identity = EvidenceIdentity(
            workspace_id=workspace.workspace_id,
            project_id=str(PROJECT_ID),
            session_id=workspace.session_id,
            build_id=build_id,
            elf_sha256=elf_sha256,
            target_device=target_device,
            input_snapshot_sha256=input_snapshot_sha256,
            git_commit=git_commit,
            git_dirty=False,
        )
        descriptor, stream = _replay_inputs(
            tmp_path, "failed-before", FAILED_RUN_ID, replay_identity
        )
        testing = TestingWorkflowContext(project_root, data_root, SESSION_ID)
        replayed = target_replay_run(testing, FAILED_RUN_ID, descriptor, stream)
        assert replayed.ok is True, replayed.to_dict()
        diagnostic = DiagnosticWorkflowContext(project_root, data_root, SESSION_ID)
        started = _data(
            diagnostic_start(
                diagnostic,
                operation_id="wave11-diagnostic-start",
                failed_test_run_id=FAILED_RUN_ID,
                failed_run_mode="target",
            )
        )
        session = started["session"]
        assert isinstance(session, Mapping)
        compact_id = str(session["diagnostic_session_id"])
        diagnostic_begin(
            diagnostic,
            operation_id="wave11-diagnostic-begin",
            diagnostic_session_id=compact_id,
            expected_revision=1,
        )
        hypothesis_result = diagnostic_add_hypothesis(
            diagnostic,
            operation_id="wave11-hypothesis-add",
            diagnostic_session_id=compact_id,
            expected_revision=2,
            statement="the failed replay identifies the faulty behavior",
        )
        hypothesis_data = _data(hypothesis_result)["hypothesis"]
        assert isinstance(hypothesis_data, Mapping)
        hypothesis_id = str(hypothesis_data["hypothesis_id"])
        plan_result = diagnostic_add_plan(
            diagnostic,
            operation_id="wave11-observation-plan-add",
            diagnostic_session_id=compact_id,
            expected_revision=3,
            steps=[
                {
                    "step_id": "failed-run",
                    "selector": {"kind": "run-state"},
                    "expected_value": "failed",
                    "purpose": "confirm the failed replay",
                }
            ],
        )
        plan_data = _data(plan_result)["observation_plan"]
        assert isinstance(plan_data, Mapping)
        plan_id = str(plan_data["plan_id"])
        diagnostic_run_plan(
            diagnostic,
            operation_id="wave11-observation-plan-run",
            diagnostic_session_id=compact_id,
            expected_revision=4,
            plan_id=plan_id,
        )
        diagnostic_assess_hypothesis(
            diagnostic,
            operation_id="wave11-hypothesis-assess",
            diagnostic_session_id=compact_id,
            expected_revision=5,
            hypothesis_id=hypothesis_id,
            plan_id=plan_id,
            step_id="failed-run",
            polarity="supports",
            rationale="the failed replay supports the hypothesis",
        )
        diagnostic_id = _wire_diagnostic_id(compact_id)
        diagnostic_hypothesis_id = hypothesis_id
    else:
        diagnostic_id = ""
        compact_id = ""
        diagnostic_hypothesis_id = ""
    return _Prefix(
        project_root=project_root,
        data_root=data_root,
        context=AcceptanceRecoveryContext(project_root, data_root, SESSION_ID),
        diagnostic_session_id=diagnostic_id,
        diagnostic_compact_id=compact_id,
        hypothesis_id=diagnostic_hypothesis_id,
    )


def _revision_root(evidence: EvidenceStore, revision: int) -> tuple[Path, RootRecord]:
    root_directory = evidence.root / "roots" / "acceptance-attempt"
    suffix = f".{revision:08d}"
    for path in root_directory.glob("*.json"):
        document = json.loads(path.read_bytes().decode("utf-8"))
        root_id = document.get("root_id")
        if (
            document.get("root_type") == "acceptance-attempt"
            and isinstance(root_id, str)
            and root_id.startswith(f"{ATTEMPT_ID}.")
            and root_id.endswith(suffix)
        ):
            return path, get_root(evidence, "acceptance-attempt", root_id)
    raise AssertionError(f"missing acceptance root revision {revision}")


def _public_source_change(
    tmp_path: Path,
    evidence: EvidenceStore,
    before: object,
    after_identity: EvidenceIdentity,
    hypothesis_id: str,
) -> SourceChangeDeclaration:
    diff_path = tmp_path / "source-change.diff"
    diff_path.write_bytes(
        b"--- a/App/main.c\n+++ b/App/main.c\n@@ -1 +1 @@\n-old\n+new\n"
    )
    diff_artifact = evidence.ingest_file(
        diff_path, kind="source-diff", media_type="text/x-diff"
    )
    before_identity = before.manifest.identity
    diff_envelope = EvidenceEnvelope(
        identity=before_identity,
        operation="diagnostic-source-change",
        produced_at_utc="2026-08-24T00:00:00.000000Z",
        parents=(),
        artifacts=(diff_artifact,),
        metadata={"kind": "source-change-diff"},
    )
    evidence.put_envelope(diff_envelope)
    return SourceChangeDeclaration.new(
        before_source_sha256=before_identity.input_snapshot_sha256,
        after_source_sha256=after_identity.input_snapshot_sha256,
        before_build_id=before_identity.build_id,
        before_elf_sha256=before_identity.elf_sha256,
        after_build_id=after_identity.build_id,
        after_elf_sha256=after_identity.elf_sha256,
        changed_paths=("App/main.c",),
        diff_evidence_id=str(diff_envelope.evidence_id),
        diff_artifact=diff_artifact,
        claimed_hypothesis_ids=(hypothesis_id,),
        validation_plan_id="b" * 64,
    )


def _complete_public_tail(
    tmp_path: Path,
    prefix: _Prefix,
    attempt_id: str,
    *,
    finalize: bool = True,
) -> tuple[Mapping[str, object], Mapping[str, object]]:
    project_root = prefix.project_root
    data_root = prefix.data_root
    context = prefix.context
    workspace = WorkspacePaths.from_roots(
        data_root, project_root, PROJECT_ID, SESSION_ID
    )
    evidence = EvidenceStore(workspace.workspace_root / "evidence")
    before = TestRunRepository(evidence).load(FAILED_RUN_ID)

    source_path = project_root / "App" / "main.c"
    source_path.write_text("int main(void) { return 1; }\r\n", encoding="utf-8")
    subprocess.run(
        ("git", "add", "App/main.c"),
        cwd=project_root,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    subprocess.run(
        ("git", "commit", "-q", "-m", "wave11 source change"),
        cwd=project_root,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    after_identity_document = _publish_current_debug_build(project_root, text_size=320)
    build_context = _data(build_project_context(project_root, data_root, SESSION_ID))
    build = build_context["build"]
    assert isinstance(build, Mapping)
    after_identity = EvidenceIdentity(
        workspace_id=workspace.workspace_id,
        project_id=str(PROJECT_ID),
        session_id=SESSION_ID,
        build_id=str(after_identity_document["buildId"]),
        elf_sha256=str(after_identity_document["elfSha256"]),
        target_device=str(build_context["project"]["target"]),
        input_snapshot_sha256=snapshot_project_inputs(load_project_model(project_root)).sha256,
        git_commit=str(after_identity_document["gitHead"]),
        git_dirty=False,
    )
    assert build["buildId"] == after_identity.build_id
    assert build["elfSha256"] == after_identity.elf_sha256
    assert build["elfFresh"] is True

    fixed_run_id = "00000000-0000-4000-8000-000000000003"
    fixed_descriptor, fixed_stream = _replay_inputs(
        tmp_path, "fixed-after", fixed_run_id, after_identity
    )
    fixed_fixture = load_target_replay_fixture(fixed_descriptor, fixed_stream)
    declaration = _public_source_change(
        tmp_path, evidence, before, fixed_fixture.descriptor.identity, prefix.hypothesis_id
    )
    diagnostic = DiagnosticWorkflowContext(project_root, data_root, SESSION_ID)
    compact_id = prefix.diagnostic_compact_id
    declared = diagnostic_declare_source_change(
        diagnostic,
        operation_id="wave11-source-change-declare",
        diagnostic_session_id=compact_id,
        expected_revision=6,
        source_change_declaration=declaration,
    )
    assert declared.ok is True, declared.to_dict()
    fixed = target_replay_run(
        TestingWorkflowContext(project_root, data_root, SESSION_ID),
        fixed_run_id,
        fixed_descriptor,
        fixed_stream,
    )
    assert fixed.ok is True, fixed.to_dict()
    after = TestRunRepository(evidence).load(fixed_run_id)

    monitor_paths: dict[str, Path] = {}
    for role in ("failed-before", "fixed-after"):
        descriptor = json.loads(
            (MONITOR_FIXTURES / f"{role}.json").read_text(encoding="utf-8")
        )
        monitor_identity = (
            before.manifest.identity
            if role == "failed-before"
            else after.manifest.identity
        )
        assert monitor_identity.workspace_id == workspace.workspace_id
        assert str(monitor_identity.project_id) == str(PROJECT_ID)
        assert monitor_identity.session_id == SESSION_ID
        monitor_fields = {
            "workspaceId": monitor_identity.workspace_id,
            "logicalProjectId": str(monitor_identity.project_id),
            "sessionId": monitor_identity.session_id,
            "targetDevice": monitor_identity.target_device,
            "buildId": monitor_identity.build_id,
            "elfSha256": monitor_identity.elf_sha256,
            "inputSnapshotSha256": monitor_identity.input_snapshot_sha256,
            "gitHead": monitor_identity.git_commit,
            "gitDirty": monitor_identity.git_dirty,
        }
        descriptor["binding"].update(monitor_fields)
        for batch in descriptor["batches"]:
            batch["binding"].update(monitor_fields)
        unsigned = {key: value for key, value in descriptor.items() if key != "fixture_sha256"}
        descriptor["fixture_sha256"] = hashlib.sha256(
            json.dumps(
                unsigned,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        ).hexdigest()
        monitor_path = tmp_path / f"monitor-{role}.json"
        monitor_path.write_text(
            json.dumps(descriptor, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        monitor_paths[role] = monitor_path
    monitor_before = ingest_monitor_replay(
        workspace, evidence, MONITOR_OPERATION_IDS["failed-before"], monitor_paths["failed-before"]
    )
    monitor_after = ingest_monitor_replay(
        workspace, evidence, MONITOR_OPERATION_IDS["fixed-after"], monitor_paths["fixed-after"]
    )
    analysis_request = AnalysisRequest(
        schema="stm32-monitor-analysis-request/1",
        before_run=monitor_before,
        after_run=monitor_after,
        selector_kind="variable",
        selector="counter",
        alignment="run-relative",
        minimum_valid_pairs=2,
    )
    publication = compare_monitor_runs(
        workspace,
        evidence,
        analysis_request,
        compact_id,
        prefix.hypothesis_id,
        "supports",
        "the fixed replay changed the observed counter",
        declaration,
    )
    export_analysis_bundle(
        workspace,
        evidence,
        analysis_request,
        publication,
        FAILED_RUN_ID,
        fixed_run_id,
        declaration,
    )
    verification_plan = VerificationPlan.new(
        verification_plan_id="b" * 64,
        diagnostic_session_id=compact_id,
        failed_before_run_id=FAILED_RUN_ID,
        failed_before_evidence_id=str(before.envelope.evidence_id),
        source_change_declaration_id=declaration.declaration_id,
        fixed_after_run_id=fixed_run_id,
        fixed_after_evidence_id=str(after.envelope.evidence_id),
        required_analysis_ids=(publication.analysis_result.analysis_id,),
        required_analysis_evidence_ids=(publication.analysis_evidence_ref.evidence_id,),
        required_monitor_quality="VALID",
        expected_changed=True,
    )
    assert diagnostic_add_verification_plan(
        diagnostic,
        operation_id="wave11-verification-plan-add",
        diagnostic_session_id=compact_id,
        expected_revision=7,
        verification_plan=verification_plan,
    ).ok
    assert diagnostic_start_verification(
        diagnostic,
        operation_id="wave11-verification-start",
        diagnostic_session_id=compact_id,
        expected_revision=8,
        verification_plan_id=verification_plan.verification_plan_id,
    ).ok
    marker = diagnostic_attach_marker(
        diagnostic,
        operation_id="wave11-marker-attach",
        diagnostic_session_id=compact_id,
        expected_revision=9,
        diagnostic_marker_ref=publication.diagnostic_marker_ref,
    )
    assert marker.ok is True, marker.to_dict()
    completed = diagnostic_complete_verification(
        diagnostic,
        operation_id="wave11-verification-complete",
        diagnostic_session_id=compact_id,
        expected_revision=10,
        executed_operation_ids=[
            FAILED_RUN_ID,
            fixed_run_id,
            "monitor.analysis.compare",
            "monitor.analysis.bundle",
        ],
        cancelled=False,
    )
    assert completed.ok is True, completed.to_dict()

    after_build = checkpoint_acceptance_attempt(
        context, attempt_id=attempt_id, expected_revision=5, stage="firmware-built-after"
    )
    assert after_build.ok is True, after_build.to_dict()
    after_build_retry = checkpoint_acceptance_attempt(
        context, attempt_id=attempt_id, expected_revision=5, stage="firmware-built-after"
    )
    assert _wire(after_build_retry) == _wire(after_build)
    record = record_acceptance_scenario(
        AcceptanceWorkflowContext(project_root, data_root, SESSION_ID),
        record_id=attempt_id,
        scenario_id="legacy-keil-migration",
        scenario_version="1",
        failed_before_test_run_id=FAILED_RUN_ID,
        fixed_after_test_run_id=fixed_run_id,
        diagnostic_session_id=prefix.diagnostic_compact_id,
    )
    assert record.ok is True, record.to_dict()
    record_data = _data(record)["record"]
    assert isinstance(record_data, Mapping)
    assert record_data["diagnosticSessionId"] == prefix.diagnostic_session_id
    record_retry = record_acceptance_scenario(
        AcceptanceWorkflowContext(project_root, data_root, SESSION_ID),
        record_id=attempt_id,
        scenario_id="legacy-keil-migration",
        scenario_version="1",
        failed_before_test_run_id=FAILED_RUN_ID,
        fixed_after_test_run_id=fixed_run_id,
        diagnostic_session_id=prefix.diagnostic_session_id,
    )
    assert _wire(record_retry) == _wire(record)
    if not finalize:
        current = _data(show_acceptance_attempt(context, attempt_id=attempt_id))["attempt"]
        assert isinstance(current, Mapping)
        assert current["revision"] == 6
        return record_data, current
    final = checkpoint_acceptance_attempt(
        context,
        attempt_id=attempt_id,
        expected_revision=6,
        stage="target-fix-verified",
        acceptance_record_id=attempt_id,
    )
    assert final.ok is True, final.to_dict()
    assert _data(final)["attempt"]["revision"] == 7
    return record_data, _data(final)["attempt"]


def _prepare_acceptance_reader_prefix(
    tmp_path: Path,
) -> tuple[_Prefix, Mapping[str, object]]:
    prefix = _prepare_prefix(tmp_path, with_build=True)
    context = prefix.context
    started = begin_acceptance_attempt(
        context,
        attempt_id=ATTEMPT_ID,
        scenario_id="legacy-keil-migration",
        scenario_version="1",
    )
    assert _data(started)["attempt"]["revision"] == 0
    for revision, stage, kwargs in (
        (0, "project-materialized", {}),
        (1, "firmware-built-before", {}),
        (2, "target-failure-replayed", {"test_run_id": FAILED_RUN_ID}),
    ):
        result = checkpoint_acceptance_attempt(
            context,
            attempt_id=ATTEMPT_ID,
            expected_revision=revision,
            stage=stage,
            **kwargs,
        )
        assert result.ok is True, result.to_dict()
    diagnosed = checkpoint_acceptance_attempt(
        context,
        attempt_id=ATTEMPT_ID,
        expected_revision=3,
        stage="diagnosis-completed",
        diagnostic_session_id=prefix.diagnostic_compact_id,
    )
    assert diagnosed.ok is True, diagnosed.to_dict()
    action_digest = _data(resume_acceptance_attempt(context, attempt_id=ATTEMPT_ID))[
        "actionDigest"
    ]
    authorized = authorize_acceptance_source_change(
        context,
        attempt_id=ATTEMPT_ID,
        expected_revision=4,
        action_digest=action_digest,
        authorized=True,
    )
    assert authorized.ok is True, authorized.to_dict()
    record, current_attempt = _complete_public_tail(
        tmp_path, prefix, ATTEMPT_ID, finalize=False
    )
    assert current_attempt["revision"] == 6
    return prefix, record


def _acceptance_root_path(evidence: EvidenceStore, record_id: str) -> Path:
    name = hashlib.sha256(
        canonical_json_bytes({"root_type": "acceptance-scenario", "root_id": record_id})
    ).hexdigest()
    path = evidence.root / "roots" / "acceptance-scenario" / f"{name}.json"
    assert path.is_file()
    return path


def _acceptance_storage(
    evidence: EvidenceStore, record_id: str
) -> tuple[Path, RootRecord, EvidenceEnvelope]:
    root_path = _acceptance_root_path(evidence, record_id)
    root = get_root(evidence, "acceptance-scenario", record_id)
    envelope = evidence.get_envelope(root.manifest_id)
    return root_path, root, envelope


def _acceptance_root_metadata(record: AcceptanceRecord) -> dict[str, object]:
    return {
        "record_sha256": hashlib.sha256(
            canonical_json_bytes(record.to_dict())
        ).hexdigest(),
        "scenario_digest": record.scenario_digest,
        "workspace_id": record.workspace_id,
        "logical_project_id": record.logical_project_id,
    }


def _install_acceptance_envelope(
    evidence: EvidenceStore,
    root_path: Path,
    root: RootRecord,
    envelope: EvidenceEnvelope,
    *,
    metadata: Mapping[str, object],
) -> None:
    evidence.put_envelope(envelope)
    root_path.unlink()
    put_root(
        evidence,
        RootRecord(
            root_type=root.root_type,
            root_id=root.root_id,
            manifest_id=str(envelope.evidence_id),
            metadata=metadata,
        ),
    )


def _record_acceptance_again(prefix: _Prefix, record: Mapping[str, object]) -> object:
    return record_acceptance_scenario(
        AcceptanceWorkflowContext(prefix.project_root, prefix.data_root, SESSION_ID),
        record_id=ATTEMPT_ID,
        scenario_id="legacy-keil-migration",
        scenario_version="1",
        failed_before_test_run_id=str(record["failedBeforeTestRunId"]),
        fixed_after_test_run_id=str(record["fixedAfterTestRunId"]),
        diagnostic_session_id=str(record["diagnosticSessionId"]),
    )


def _run_acceptance_reader_variant(
    prefix: _Prefix,
    record: Mapping[str, object],
    evidence: EvidenceStore,
    install,
    *,
    show_code: str,
    record_code: str,
    baseline_show_wire: dict[str, object],
    baseline_record_wire: dict[str, object],
    expected_checkpoint_wire: dict[str, object] | None,
) -> dict[str, object]:
    baseline_evidence = _file_snapshot(evidence.root)
    baseline_persistence = _persistence_snapshot(prefix.project_root, prefix.data_root)
    try:
        install()
        corrupted_persistence = _persistence_snapshot(
            prefix.project_root, prefix.data_root
        )
        shown = show_acceptance_scenario(
            AcceptanceWorkflowContext(
                prefix.project_root, prefix.data_root, SESSION_ID
            ),
            record_id=ATTEMPT_ID,
        )
        _assert_acceptance_failure(
            shown, show_code, operation="acceptance.scenario.show"
        )
        rerecorded = _record_acceptance_again(prefix, record)
        _assert_acceptance_failure(
            rerecorded, record_code, operation="acceptance.scenario.record"
        )
        refused_checkpoint = checkpoint_acceptance_attempt(
            prefix.context,
            attempt_id=ATTEMPT_ID,
            expected_revision=6,
            stage="target-fix-verified",
            acceptance_record_id=ATTEMPT_ID,
        )
        _assert_failure(
            refused_checkpoint,
            "ACCEPTANCE_ATTEMPT_OUTPUT_INVALID",
            operation="acceptance.attempt.checkpoint",
        )
        assert (
            _persistence_snapshot(prefix.project_root, prefix.data_root)
            == corrupted_persistence
        )
    finally:
        _restore_file_snapshot(evidence.root, baseline_evidence)
    assert (
        _persistence_snapshot(prefix.project_root, prefix.data_root)
        == baseline_persistence
    )

    restored_show = show_acceptance_scenario(
        AcceptanceWorkflowContext(prefix.project_root, prefix.data_root, SESSION_ID),
        record_id=ATTEMPT_ID,
    )
    assert _wire(restored_show) == baseline_show_wire
    restored_record = _record_acceptance_again(prefix, record)
    assert _wire(restored_record) == baseline_record_wire
    restored_checkpoint = checkpoint_acceptance_attempt(
        prefix.context,
        attempt_id=ATTEMPT_ID,
        expected_revision=6,
        stage="target-fix-verified",
        acceptance_record_id=ATTEMPT_ID,
    )
    assert restored_checkpoint.ok is True, restored_checkpoint.to_dict()
    checkpoint_wire = _wire(restored_checkpoint)
    if expected_checkpoint_wire is not None:
        assert checkpoint_wire == expected_checkpoint_wire
    _restore_file_snapshot(evidence.root, baseline_evidence)
    assert (
        _persistence_snapshot(prefix.project_root, prefix.data_root)
        == baseline_persistence
    )
    return checkpoint_wire


def test_wave11_public_acceptance_reader_corruption_restores_and_reuses(
    tmp_path: Path,
) -> None:
    prefix, record = _prepare_acceptance_reader_prefix(tmp_path)
    context = AcceptanceWorkflowContext(
        prefix.project_root, prefix.data_root, SESSION_ID
    )
    evidence = EvidenceStore(
        WorkspacePaths.from_roots(
            prefix.data_root, prefix.project_root, PROJECT_ID, SESSION_ID
        ).workspace_root
        / "evidence"
    )
    baseline_show = show_acceptance_scenario(context, record_id=ATTEMPT_ID)
    assert baseline_show.ok is True, baseline_show.to_dict()
    baseline_record = _record_acceptance_again(prefix, record)
    assert baseline_record.ok is True, baseline_record.to_dict()
    baseline_show_wire = _wire(baseline_show)
    baseline_record_wire = _wire(baseline_record)
    expected_checkpoint_wire: dict[str, object] | None = None

    def install_root_shape() -> None:
        root_path, root, _ = _acceptance_storage(evidence, ATTEMPT_ID)
        metadata = dict(root.metadata)
        del metadata["scenario_digest"]
        replacement = RootRecord(
            root_type=root.root_type,
            root_id=root.root_id,
            manifest_id=root.manifest_id,
            metadata=metadata,
        )
        root_path.unlink()
        put_root(evidence, replacement)

    expected_checkpoint_wire = _run_acceptance_reader_variant(
        prefix,
        record,
        evidence,
        install_root_shape,
        show_code="ACCEPTANCE_EVIDENCE_INTEGRITY_FAILED",
        record_code="ACCEPTANCE_EVIDENCE_INTEGRITY_FAILED",
        baseline_show_wire=baseline_show_wire,
        baseline_record_wire=baseline_record_wire,
        expected_checkpoint_wire=expected_checkpoint_wire,
    )

    def install_root_manifest_missing() -> None:
        _, root, _ = _acceptance_storage(evidence, ATTEMPT_ID)
        manifest = evidence.root / "manifests" / f"{root.manifest_id}.json"
        assert manifest.is_file()
        manifest.unlink()

    _run_acceptance_reader_variant(
        prefix,
        record,
        evidence,
        install_root_manifest_missing,
        show_code="ACCEPTANCE_EVIDENCE_INTEGRITY_FAILED",
        record_code="ACCEPTANCE_EVIDENCE_INTEGRITY_FAILED",
        baseline_show_wire=baseline_show_wire,
        baseline_record_wire=baseline_record_wire,
        expected_checkpoint_wire=expected_checkpoint_wire,
    )

    def install_root_key_mismatch() -> None:
        root_path, root, _ = _acceptance_storage(evidence, ATTEMPT_ID)
        replacement = RootRecord(
            root_type=root.root_type,
            root_id="00000000-0000-4000-8000-000000000099",
            manifest_id=root.manifest_id,
            metadata=dict(root.metadata),
        )
        root_path.write_bytes(canonical_json_bytes(replacement.to_dict()))

    _run_acceptance_reader_variant(
        prefix,
        record,
        evidence,
        install_root_key_mismatch,
        show_code="ACCEPTANCE_REFERENCE_INVALID",
        record_code="ACCEPTANCE_REFERENCE_INVALID",
        baseline_show_wire=baseline_show_wire,
        baseline_record_wire=baseline_record_wire,
        expected_checkpoint_wire=expected_checkpoint_wire,
    )

    def install_envelope_digest() -> None:
        root_path, root, old = _acceptance_storage(evidence, ATTEMPT_ID)
        metadata = dict(_json_thaw(old.metadata))
        old_digest = str(metadata["record_sha256"])
        metadata["record_sha256"] = "0" * 64 if old_digest != "0" * 64 else "1" * 64
        mutated = EvidenceEnvelope(
            identity=old.identity,
            operation=old.operation,
            produced_at_utc=old.produced_at_utc,
            parents=old.parents,
            artifacts=old.artifacts,
            metadata=metadata,
        )
        _install_acceptance_envelope(
            evidence,
            root_path,
            root,
            mutated,
            metadata=dict(root.metadata),
        )

    _run_acceptance_reader_variant(
        prefix,
        record,
        evidence,
        install_envelope_digest,
        show_code="ACCEPTANCE_EVIDENCE_INTEGRITY_FAILED",
        record_code="ACCEPTANCE_EVIDENCE_INTEGRITY_FAILED",
        baseline_show_wire=baseline_show_wire,
        baseline_record_wire=baseline_record_wire,
        expected_checkpoint_wire=expected_checkpoint_wire,
    )

    def install_workspace_binding() -> None:
        root_path, root, old = _acceptance_storage(evidence, ATTEMPT_ID)
        raw_record = _json_thaw(old.metadata["record"])
        assert isinstance(raw_record, Mapping)
        mutated_payload = dict(raw_record)
        mutated_payload["workspaceId"] = "e" * 64
        mutated_record = AcceptanceRecord.from_value(mutated_payload)
        old_identity = old.identity
        mutated_identity = EvidenceIdentity(
            workspace_id=mutated_record.workspace_id,
            project_id=old_identity.project_id,
            session_id=old_identity.session_id,
            build_id=old_identity.build_id,
            elf_sha256=old_identity.elf_sha256,
            target_device=old_identity.target_device,
            input_snapshot_sha256=old_identity.input_snapshot_sha256,
            git_commit=old_identity.git_commit,
            git_dirty=old_identity.git_dirty,
        )
        mutated = EvidenceEnvelope(
            identity=mutated_identity,
            operation=old.operation,
            produced_at_utc=old.produced_at_utc,
            parents=old.parents,
            artifacts=old.artifacts,
            metadata={
                "record": mutated_record.to_dict(),
                **_acceptance_root_metadata(mutated_record),
            },
        )
        _install_acceptance_envelope(
            evidence,
            root_path,
            root,
            mutated,
            metadata=_acceptance_root_metadata(mutated_record),
        )

    _run_acceptance_reader_variant(
        prefix,
        record,
        evidence,
        install_workspace_binding,
        show_code="ACCEPTANCE_IDENTITY_MISMATCH",
        record_code="ACCEPTANCE_RECORD_CONFLICT",
        baseline_show_wire=baseline_show_wire,
        baseline_record_wire=baseline_record_wire,
        expected_checkpoint_wire=expected_checkpoint_wire,
    )


def test_wave11_public_alias_reaches_record_and_final_checkpoint(tmp_path: Path) -> None:
    prefix = _prepare_prefix(tmp_path, with_build=True)
    context = prefix.context
    started = begin_acceptance_attempt(
        context,
        attempt_id=ATTEMPT_ID,
        scenario_id="legacy-keil-migration",
        scenario_version="1",
    )
    assert _data(started)["attempt"]["revision"] == 0
    for revision, stage, kwargs in (
        (0, "project-materialized", {}),
        (1, "firmware-built-before", {}),
        (2, "target-failure-replayed", {"test_run_id": FAILED_RUN_ID}),
    ):
        result = checkpoint_acceptance_attempt(
            context,
            attempt_id=ATTEMPT_ID,
            expected_revision=revision,
            stage=stage,
            **kwargs,
        )
        assert result.ok is True, result.to_dict()
    compact_id = prefix.diagnostic_compact_id
    diagnosed = checkpoint_acceptance_attempt(
        context,
        attempt_id=ATTEMPT_ID,
        expected_revision=3,
        stage="diagnosis-completed",
        diagnostic_session_id=compact_id,
    )
    assert diagnosed.ok is True, diagnosed.to_dict()
    diagnosed_retry = checkpoint_acceptance_attempt(
        context,
        attempt_id=ATTEMPT_ID,
        expected_revision=3,
        stage="diagnosis-completed",
        diagnostic_session_id=prefix.diagnostic_session_id,
    )
    assert _wire(diagnosed_retry) == _wire(diagnosed)
    action_digest = _data(resume_acceptance_attempt(context, attempt_id=ATTEMPT_ID))["actionDigest"]
    assert isinstance(action_digest, str)
    authorized = authorize_acceptance_source_change(
        context,
        attempt_id=ATTEMPT_ID,
        expected_revision=4,
        action_digest=action_digest,
        authorized=True,
    )
    assert authorized.ok is True, authorized.to_dict()
    authorized_retry = authorize_acceptance_source_change(
        context,
        attempt_id=ATTEMPT_ID,
        expected_revision=4,
        action_digest=action_digest,
        authorized=True,
    )
    assert _wire(authorized_retry) == _wire(authorized)
    record, final = _complete_public_tail(tmp_path, prefix, ATTEMPT_ID)
    assert final["status"] == "COMPLETED"
    shown_record = show_acceptance_scenario(
        AcceptanceWorkflowContext(prefix.project_root, prefix.data_root, SESSION_ID),
        record_id=ATTEMPT_ID,
    )
    assert shown_record.ok is True, shown_record.to_dict()
    assert _data(shown_record)["record"] == record
    shown_attempt = show_acceptance_attempt(context, attempt_id=ATTEMPT_ID)
    resumed_attempt = resume_acceptance_attempt(context, attempt_id=ATTEMPT_ID)
    assert shown_attempt.ok is True and resumed_attempt.ok is True
    assert _data(shown_attempt)["attempt"] == final
    assert _data(resumed_attempt)["attempt"] == final


def test_wave11_public_v1_recovery_retries_and_refusals(tmp_path: Path) -> None:
    prefix = _prepare_prefix(tmp_path, with_build=True)
    context = prefix.context
    started = begin_acceptance_attempt(
        context,
        attempt_id=ATTEMPT_ID,
        scenario_id="legacy-keil-migration",
        scenario_version="1",
    )
    assert _data(started)["attempt"]["revision"] == 0

    materialized = checkpoint_acceptance_attempt(
        context,
        attempt_id=ATTEMPT_ID,
        expected_revision=0,
        stage="project-materialized",
    )
    assert _data(materialized)["attempt"]["revision"] == 1
    materialized_retry = checkpoint_acceptance_attempt(
        context,
        attempt_id=ATTEMPT_ID,
        expected_revision=0,
        stage="project-materialized",
    )
    assert _wire(materialized_retry) == _wire(materialized)

    built = checkpoint_acceptance_attempt(
        context,
        attempt_id=ATTEMPT_ID,
        expected_revision=1,
        stage="firmware-built-before",
    )
    assert _data(built)["attempt"]["revision"] == 2
    built_retry = checkpoint_acceptance_attempt(
        context,
        attempt_id=ATTEMPT_ID,
        expected_revision=1,
        stage="firmware-built-before",
    )
    assert _wire(built_retry) == _wire(built)

    before = _persistence_snapshot(prefix.project_root, prefix.data_root)
    stale = checkpoint_acceptance_attempt(
        context,
        attempt_id=ATTEMPT_ID,
        expected_revision=0,
        stage="project-materialized",
    )
    _assert_failure(
        stale,
        "ACCEPTANCE_ATTEMPT_REVISION_CONFLICT",
        operation="acceptance.attempt.checkpoint",
    )
    assert _persistence_snapshot(prefix.project_root, prefix.data_root) == before

    before = _persistence_snapshot(prefix.project_root, prefix.data_root)
    future = checkpoint_acceptance_attempt(
        context,
        attempt_id=ATTEMPT_ID,
        expected_revision=3,
        stage="target-failure-replayed",
        test_run_id=FAILED_RUN_ID,
    )
    _assert_failure(
        future,
        "ACCEPTANCE_ATTEMPT_EVIDENCE_INTEGRITY_FAILED",
        operation="acceptance.attempt.checkpoint",
    )
    assert _persistence_snapshot(prefix.project_root, prefix.data_root) == before

    before = _persistence_snapshot(prefix.project_root, prefix.data_root)
    wrong_stage = checkpoint_acceptance_attempt(
        context,
        attempt_id=ATTEMPT_ID,
        expected_revision=2,
        stage="project-materialized",
    )
    _assert_failure(
        wrong_stage,
        "ACCEPTANCE_ATTEMPT_STAGE_INVALID",
        operation="acceptance.attempt.checkpoint",
    )
    assert _persistence_snapshot(prefix.project_root, prefix.data_root) == before

    replayed = checkpoint_acceptance_attempt(
        context,
        attempt_id=ATTEMPT_ID,
        expected_revision=2,
        stage="target-failure-replayed",
        test_run_id=FAILED_RUN_ID,
    )
    assert _data(replayed)["attempt"]["revision"] == 3
    replayed_retry = checkpoint_acceptance_attempt(
        context,
        attempt_id=ATTEMPT_ID,
        expected_revision=2,
        stage="target-failure-replayed",
        test_run_id=FAILED_RUN_ID,
    )
    assert _wire(replayed_retry) == _wire(replayed)

    before = _persistence_snapshot(prefix.project_root, prefix.data_root)
    malformed_diagnostic = checkpoint_acceptance_attempt(
        context,
        attempt_id=ATTEMPT_ID,
        expected_revision=3,
        stage="diagnosis-completed",
        diagnostic_session_id="G" * 32,
    )
    _assert_failure(
        malformed_diagnostic,
        "ACCEPTANCE_ATTEMPT_INPUT_INVALID",
        operation="acceptance.attempt.checkpoint",
    )
    assert _persistence_snapshot(prefix.project_root, prefix.data_root) == before

    before = _persistence_snapshot(prefix.project_root, prefix.data_root)
    wrong_diagnostic = checkpoint_acceptance_attempt(
        context,
        attempt_id=ATTEMPT_ID,
        expected_revision=3,
        stage="diagnosis-completed",
        diagnostic_session_id="0" * 32,
    )
    _assert_failure(
        wrong_diagnostic,
        "ACCEPTANCE_ATTEMPT_OUTPUT_INVALID",
        operation="acceptance.attempt.checkpoint",
    )
    assert _persistence_snapshot(prefix.project_root, prefix.data_root) == before

    compact_diagnostic_id = prefix.diagnostic_compact_id
    diagnosed = checkpoint_acceptance_attempt(
        context,
        attempt_id=ATTEMPT_ID,
        expected_revision=3,
        stage="diagnosis-completed",
        diagnostic_session_id=compact_diagnostic_id,
    )
    assert _data(diagnosed)["attempt"]["revision"] == 4
    diagnosed_attempt = _data(diagnosed)["attempt"]
    assert isinstance(diagnosed_attempt, Mapping)
    assert diagnosed_attempt["stageOutputs"]["diagnosticSessionId"] == prefix.diagnostic_session_id
    diagnosed_retry = checkpoint_acceptance_attempt(
        context,
        attempt_id=ATTEMPT_ID,
        expected_revision=3,
        stage="diagnosis-completed",
        diagnostic_session_id=prefix.diagnostic_session_id,
    )
    assert _wire(diagnosed_retry) == _wire(diagnosed)

    before = _persistence_snapshot(prefix.project_root, prefix.data_root)
    wrong_stage_at_revision_four = checkpoint_acceptance_attempt(
        context,
        attempt_id=ATTEMPT_ID,
        expected_revision=4,
        stage="project-materialized",
    )
    _assert_failure(
        wrong_stage_at_revision_four,
        "ACCEPTANCE_ATTEMPT_STAGE_INVALID",
        operation="acceptance.attempt.checkpoint",
    )
    assert _persistence_snapshot(prefix.project_root, prefix.data_root) == before

    before = _persistence_snapshot(prefix.project_root, prefix.data_root)
    requires_authorization = checkpoint_acceptance_attempt(
        context,
        attempt_id=ATTEMPT_ID,
        expected_revision=4,
        stage="firmware-built-after",
    )
    _assert_failure(
        requires_authorization,
        "ACCEPTANCE_ATTEMPT_AUTHORIZATION_REQUIRED",
        operation="acceptance.attempt.checkpoint",
    )
    assert _persistence_snapshot(prefix.project_root, prefix.data_root) == before

    resumed = resume_acceptance_attempt(context, attempt_id=ATTEMPT_ID)
    resumed_data = _data(resumed)
    action_digest = resumed_data["actionDigest"]
    assert isinstance(action_digest, str) and len(action_digest) == 64

    before = _persistence_snapshot(prefix.project_root, prefix.data_root)
    wrong_revision = authorize_acceptance_source_change(
        context,
        attempt_id=ATTEMPT_ID,
        expected_revision=3,
        action_digest=action_digest,
        authorized=True,
    )
    _assert_failure(
        wrong_revision,
        "ACCEPTANCE_ATTEMPT_STAGE_INVALID",
        operation="acceptance.attempt.authorize-source-change",
    )
    assert _persistence_snapshot(prefix.project_root, prefix.data_root) == before

    before = _persistence_snapshot(prefix.project_root, prefix.data_root)
    refused_authorization = authorize_acceptance_source_change(
        context,
        attempt_id=ATTEMPT_ID,
        expected_revision=4,
        action_digest=action_digest,
        authorized=False,
    )
    _assert_failure(
        refused_authorization,
        "ACCEPTANCE_ATTEMPT_INPUT_INVALID",
        operation="acceptance.attempt.authorize-source-change",
    )
    assert _persistence_snapshot(prefix.project_root, prefix.data_root) == before

    wrong_action = "f" * 64 if action_digest != "f" * 64 else "e" * 64
    before = _persistence_snapshot(prefix.project_root, prefix.data_root)
    mismatched_action = authorize_acceptance_source_change(
        context,
        attempt_id=ATTEMPT_ID,
        expected_revision=4,
        action_digest=wrong_action,
        authorized=True,
    )
    _assert_failure(
        mismatched_action,
        "ACCEPTANCE_ATTEMPT_ACTION_DIGEST_MISMATCH",
        operation="acceptance.attempt.authorize-source-change",
    )
    assert _persistence_snapshot(prefix.project_root, prefix.data_root) == before

    authorized = authorize_acceptance_source_change(
        context,
        attempt_id=ATTEMPT_ID,
        expected_revision=4,
        action_digest=action_digest,
        authorized=True,
    )
    assert _data(authorized)["attempt"]["revision"] == 5
    authorized_retry = authorize_acceptance_source_change(
        context,
        attempt_id=ATTEMPT_ID,
        expected_revision=4,
        action_digest=action_digest,
        authorized=True,
    )
    assert _wire(authorized_retry) == _wire(authorized)

    before = _persistence_snapshot(prefix.project_root, prefix.data_root)
    altered_after_authorization = authorize_acceptance_source_change(
        context,
        attempt_id=ATTEMPT_ID,
        expected_revision=4,
        action_digest=wrong_action,
        authorized=True,
    )
    _assert_failure(
        altered_after_authorization,
        "ACCEPTANCE_ATTEMPT_REVISION_CONFLICT",
        operation="acceptance.attempt.authorize-source-change",
    )
    assert _persistence_snapshot(prefix.project_root, prefix.data_root) == before


def test_wave11_public_persisted_evidence_refusal_restores_wire(tmp_path: Path) -> None:
    prefix = _prepare_prefix(tmp_path, with_build=True)
    context = prefix.context
    started = begin_acceptance_attempt(
        context,
        attempt_id=ATTEMPT_ID,
        scenario_id="legacy-keil-migration",
        scenario_version="1",
    )
    assert getattr(started, "ok", False), _wire(started)
    materialized = checkpoint_acceptance_attempt(
        context,
        attempt_id=ATTEMPT_ID,
        expected_revision=0,
        stage="project-materialized",
    )
    assert getattr(materialized, "ok", False), _wire(materialized)
    original_show = show_acceptance_attempt(context, attempt_id=ATTEMPT_ID)
    original_resume = resume_acceptance_attempt(context, attempt_id=ATTEMPT_ID)
    assert getattr(original_show, "ok", False), _wire(original_show)
    assert getattr(original_resume, "ok", False), _wire(original_resume)

    workspace = WorkspacePaths.from_roots(
        prefix.data_root, prefix.project_root, PROJECT_ID, SESSION_ID
    )
    evidence = EvidenceStore(workspace.workspace_root / "evidence")
    before_corruption = _file_snapshot(evidence.root)
    root_path, root = _revision_root(evidence, 1)
    old_root_bytes = root_path.read_bytes()
    old_envelope = evidence.get_envelope(root.manifest_id)
    raw_attempt = _json_thaw(old_envelope.metadata["attempt"])
    assert isinstance(raw_attempt, dict)
    original_attempt = AcceptanceAttempt.from_value(raw_attempt)
    mutated_payload = original_attempt.to_dict()
    mutated_payload["previousCheckpointId"] = "f" * 64
    without_checkpoint = {
        key: value for key, value in mutated_payload.items() if key != "checkpointId"
    }
    mutated_payload["checkpointId"] = hashlib.sha256(
        canonical_json_bytes(without_checkpoint)
    ).hexdigest()
    mutated_attempt = AcceptanceAttempt.from_value(mutated_payload)
    mutated_envelope = EvidenceEnvelope(
        identity=old_envelope.identity,
        operation=old_envelope.operation,
        produced_at_utc=old_envelope.produced_at_utc,
        parents=old_envelope.parents,
        artifacts=old_envelope.artifacts,
        metadata={
            "attempt": mutated_attempt.to_dict(),
            "attempt_sha256": mutated_attempt.checkpoint_id,
        },
    )
    evidence.put_envelope(mutated_envelope)
    mutated_root = RootRecord(
        root_type=root.root_type,
        root_id=root.root_id,
        manifest_id=str(mutated_envelope.evidence_id),
        metadata={
            **dict(root.metadata),
            "attempt_sha256": mutated_attempt.checkpoint_id,
        },
    )
    root_path.unlink()
    put_root(evidence, mutated_root)
    corrupted_snapshot = _file_snapshot(evidence.root)

    refused_show = show_acceptance_attempt(context, attempt_id=ATTEMPT_ID)
    _assert_failure(
        refused_show,
        "ACCEPTANCE_ATTEMPT_EVIDENCE_INTEGRITY_FAILED",
        operation="acceptance.attempt.show",
    )
    assert _file_snapshot(evidence.root) == corrupted_snapshot

    refused_resume = resume_acceptance_attempt(context, attempt_id=ATTEMPT_ID)
    _assert_failure(
        refused_resume,
        "ACCEPTANCE_ATTEMPT_EVIDENCE_INTEGRITY_FAILED",
        operation="acceptance.attempt.resume",
    )
    assert _file_snapshot(evidence.root) == corrupted_snapshot

    refused_checkpoint = checkpoint_acceptance_attempt(
        context,
        attempt_id=ATTEMPT_ID,
        expected_revision=1,
        stage="firmware-built-before",
    )
    _assert_failure(
        refused_checkpoint,
        "ACCEPTANCE_ATTEMPT_EVIDENCE_INTEGRITY_FAILED",
        operation="acceptance.attempt.checkpoint",
    )
    assert _file_snapshot(evidence.root) == corrupted_snapshot

    root_path.unlink()
    root_path.write_bytes(old_root_bytes)
    mutated_manifest = (
        evidence.root / "manifests" / f"{mutated_envelope.evidence_id}.json"
    )
    assert mutated_manifest.is_file()
    mutated_manifest.unlink()
    assert _file_snapshot(evidence.root) == before_corruption
    restored_show = show_acceptance_attempt(context, attempt_id=ATTEMPT_ID)
    restored_resume = resume_acceptance_attempt(context, attempt_id=ATTEMPT_ID)
    assert _wire(restored_show) == _wire(original_show)
    assert _wire(restored_resume) == _wire(original_resume)
