"""Optional-Git provenance across Host, Target, replay and controlled debug.

These tests exercise the explicit snapshot form end to end: Host discovery and
run without Git, Target prepare/consume/fake execution/evidence for both wire
protocols, replay consumption, and controlled-debug source revision
projection.  Legacy Git records keep their historical bytes and decoding.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import subprocess
from types import SimpleNamespace
from uuid import UUID

import pytest

import stm32_toolkit.testing_workflows as workflows
from stm32_toolkit.debug.model import DebugFirmwareBinding, MemoryRegionBinding
from stm32_toolkit.evidence import EvidenceIdentity, canonical_json_bytes
from stm32_toolkit.evidence.store import EvidenceStore
from stm32_toolkit.hardware_workflows import _control_authorization_binding
from stm32_toolkit.testing import target as target_module
from stm32_toolkit.testing.artifacts import TestArtifactCollector
from stm32_toolkit.testing.model import calculate_inventory_digest
from stm32_toolkit.testing.protocol import calculate_case_inventory_digest

from test_target_runner import (
    FakeProbeClient,
    FakeTransport,
    IDENTITY,
    MAILBOX_PROJECT_CONFIG,
    PROBE_HASH,
    PROJECT_ID,
    SESSION_ID,
    TARGET_SUPPORT,
    WORKSPACE_ID,
)


SNAPSHOT = "9" * 64
GIT_HEAD = "c" * 40
BUILD_ID = "b" * 64
ELF_SHA256 = "e" * 64
SNAPSHOT_BASELINE = "input-snapshot-v1"
SNAPSHOT_EVIDENCE = {"status": "unavailable", "code": "BUILD_GIT_INVALID", "rule": "head"}
SNAPSHOT_REVISION = f"{SNAPSHOT_BASELINE}:{SNAPSHOT}"
CASE_ID = "suite.case"
V2_CASE_DIGEST = calculate_case_inventory_digest([CASE_ID])


def _run(coro):
    return asyncio.run(coro)


def _snapshot_identity() -> EvidenceIdentity:
    return EvidenceIdentity.from_dict(
        {
            "workspace_id": WORKSPACE_ID,
            "project_id": PROJECT_ID,
            "session_id": SESSION_ID,
            "build_id": BUILD_ID,
            "elf_sha256": ELF_SHA256,
            "target_device": "target-a",
            "input_snapshot_sha256": SNAPSHOT,
            "git_commit": None,
            "git_dirty": None,
            "source_baseline": SNAPSHOT_BASELINE,
            "git_evidence": dict(SNAPSHOT_EVIDENCE),
        }
    )


def _legacy_identity() -> EvidenceIdentity:
    """The accepted Git form, which still records the input snapshot digest."""
    return EvidenceIdentity.from_dict(
        {
            "workspace_id": WORKSPACE_ID,
            "project_id": PROJECT_ID,
            "session_id": SESSION_ID,
            "build_id": BUILD_ID,
            "elf_sha256": ELF_SHA256,
            "target_device": "target-a",
            "input_snapshot_sha256": SNAPSHOT,
            "git_commit": GIT_HEAD,
            "git_dirty": False,
        }
    )


def _v1_stream(identity: EvidenceIdentity) -> bytes:
    digest = calculate_inventory_digest("target", identity, (CASE_ID,))
    bodies = [
        (
            1,
            {
                "mode": "target",
                "identity": identity.to_dict(),
                "case_ids": [CASE_ID],
                "inventory_digest": digest,
                "discovered_at_utc": "2026-08-16T00:00:00.000000Z",
            },
        ),
        (
            2,
            {
                "run_id": "run-1",
                "started_at_utc": "2026-08-16T00:00:00.000000Z",
                "case_ids": [CASE_ID],
                "inventory_digest": digest,
            },
        ),
        (3, {"case_id": CASE_ID, "started_at_utc": "2026-08-16T00:00:00.000000Z"}),
        (
            4,
            {
                "case_id": CASE_ID,
                "state": "passed",
                "ended_at_utc": "2026-08-16T00:00:01.000000Z",
                "duration_ms": 1000,
                "message": None,
                "stdout": None,
                "stderr": None,
            },
        ),
    ]
    frames = [
        target_module.encode_frame(kind, sequence, body)
        for sequence, (kind, body) in enumerate(bodies)
    ]
    terminal = {
        "state": "passed",
        "ended_at_utc": "2026-08-16T00:00:01.000000Z",
        "duration_ms": 1000,
        "inventory_digest": digest,
        "build_id": BUILD_ID,
        "elf_sha256": ELF_SHA256,
        "target_device": "target-a",
        "counts": {"passed": 1, "failed": 0, "skipped": 0, "error": 0, "timeout": 0},
        "event_stream_digest": sha256(b"".join(frames)).hexdigest(),
    }
    frames.append(target_module.encode_frame(5, len(frames), terminal))
    return b"".join(frames)


def _v2_stream() -> bytes:
    case_digest = V2_CASE_DIGEST
    nonterminal = [
        (1, {"mode": "target", "case_ids": [CASE_ID], "case_inventory_digest": case_digest, "monotonic_ms": 0}),
        (2, {"case_ids": [CASE_ID], "case_inventory_digest": case_digest, "monotonic_ms": 1}),
        (3, {"case_id": CASE_ID, "monotonic_ms": 2}),
        (4, {"case_id": CASE_ID, "state": "passed", "monotonic_ms": 3, "message": None}),
    ]
    frames = [
        target_module.encode_frame(kind, sequence, payload, version=2)
        for sequence, (kind, payload) in enumerate(nonterminal)
    ]
    terminal = {
        "state": "passed",
        "case_inventory_digest": case_digest,
        "counts": {"passed": 1, "failed": 0, "skipped": 0, "error": 0, "timeout": 0},
        "event_stream_digest": sha256(b"".join(frames)).hexdigest(),
        "monotonic_ms": 4,
    }
    frames.append(target_module.encode_frame(5, len(frames), terminal, version=2))
    return b"".join(frames)


def _snapshot_binding_fields() -> dict[str, object]:
    return {
        "revision": SNAPSHOT_REVISION,
        "input_snapshot_sha256": SNAPSHOT,
        "source_baseline": SNAPSHOT_BASELINE,
        "git_evidence": dict(SNAPSHOT_EVIDENCE),
    }


def _target_runner(tmp_path: Path, transport: object):
    project = (tmp_path / "project").absolute()
    project.mkdir(parents=True, exist_ok=True)
    evidence_store = EvidenceStore((tmp_path / "evidence").absolute())
    collector = TestArtifactCollector(
        (tmp_path / "results").absolute(), evidence_store, project_root=project
    )
    workflow_calls: list[object] = []

    async def flash_workflow(request: object):
        workflow_calls.append(request)
        from stm32_toolkit.result import OperationResult

        return OperationResult.success("stm32_flash", {"status": "success"})

    flash = target_module.GuardedTargetFlashAdapter(
        project_root=project,
        data_root=(tmp_path / "data").absolute(),
        session_id=SESSION_ID,
        probe_id="probe-a",
        workflow=flash_workflow,
    )
    runner = target_module.TargetTestRunner(
        (tmp_path / "runs").absolute(),
        FakeProbeClient(),
        flash,
        lambda _name: transport,
        artifact_collector=collector,
    )
    return runner, evidence_store, workflow_calls


async def _prepare_snapshot(runner, identity: EvidenceIdentity, *, protocol: str):
    instant = datetime(2026, 8, 25, tzinfo=timezone.utc)
    fields: dict[str, object] = dict(
        workspace_id=WORKSPACE_ID,
        project_id=PROJECT_ID,
        session_id=SESSION_ID,
        target=IDENTITY,
        probe_serial_hash=PROBE_HASH,
        elf_path="build/app.elf",
        elf_sha256=ELF_SHA256,
        build_id=BUILD_ID,
        transport="mailbox",
        transport_config=MAILBOX_PROJECT_CONFIG,
        support_profile=TARGET_SUPPORT,
        cases=(CASE_ID,),
        timeout_ms=1_000,
        now=instant,
        **_snapshot_binding_fields(),
    )
    inventory_digest = calculate_inventory_digest("target", identity, (CASE_ID,))
    fields["inventory_digest"] = inventory_digest
    if protocol == "stm32-target-frame/2":
        fields.update(
            protocol=protocol,
            case_inventory_digest=V2_CASE_DIGEST,
            git_dirty=None,
        )
    prepared = await runner.prepare(**fields)
    return prepared, instant, inventory_digest


async def _prepare_legacy(runner, identity: EvidenceIdentity, *, protocol: str):
    """Prepare the accepted Git form, which carries the input snapshot digest."""
    instant = datetime(2026, 8, 25, tzinfo=timezone.utc)
    fields: dict[str, object] = dict(
        workspace_id=WORKSPACE_ID,
        project_id=PROJECT_ID,
        session_id=SESSION_ID,
        revision=GIT_HEAD,
        input_snapshot_sha256=SNAPSHOT,
        target=IDENTITY,
        probe_serial_hash=PROBE_HASH,
        elf_path="build/app.elf",
        elf_sha256=ELF_SHA256,
        build_id=BUILD_ID,
        inventory_digest=calculate_inventory_digest("target", identity, (CASE_ID,)),
        transport="mailbox",
        transport_config=MAILBOX_PROJECT_CONFIG,
        support_profile=TARGET_SUPPORT,
        cases=(CASE_ID,),
        timeout_ms=1_000,
        now=instant,
    )
    if protocol == "stm32-target-frame/2":
        fields.update(
            protocol=protocol,
            case_inventory_digest=V2_CASE_DIGEST,
            git_dirty=False,
        )
    prepared = await runner.prepare(**fields)
    return prepared, instant, fields["inventory_digest"]


_LEGACY_BINDING_FIELDS = frozenset(
    {
        "workspace_id",
        "project_id",
        "session_id",
        "revision",
        "target",
        "probe_serial_hash",
        "elf_path",
        "elf_sha256",
        "build_id",
        "inventory_digest",
        "transport",
        "transport_config",
        "support_profile",
        "cases",
        "timeout_ms",
        "input_snapshot_sha256",
        "nonce",
        "prepared_at_utc",
        "expires_at_utc",
    }
)
_V2_LEGACY_BINDING_FIELDS = _LEGACY_BINDING_FIELDS | {
    "protocol",
    "case_inventory_digest",
    "git_dirty",
}


@pytest.mark.parametrize("protocol", ["stm32-target-frame/1", "stm32-target-frame/2"])
def test_snapshot_target_prepare_consume_execute_and_evidence(
    tmp_path: Path, protocol: str
) -> None:
    identity = _snapshot_identity()
    stream = _v1_stream(identity) if protocol == "stm32-target-frame/1" else _v2_stream()
    transport = FakeTransport([stream])
    runner, evidence_store, workflow_calls = _target_runner(tmp_path, transport)

    async def scenario() -> None:
        prepared, instant, inventory_digest = await _prepare_snapshot(
            runner, identity, protocol=protocol
        )
        binding = prepared.binding
        assert binding["revision"] == SNAPSHOT_REVISION
        assert binding["input_snapshot_sha256"] == SNAPSHOT
        assert binding["source_baseline"] == SNAPSHOT_BASELINE
        assert binding["git_evidence"] == SNAPSHOT_EVIDENCE
        assert "git_commit" not in binding and "git_head" not in binding
        if protocol == "stm32-target-frame/1":
            assert "git_dirty" not in binding
        else:
            assert binding["git_dirty"] is None
            assert binding["protocol"] == protocol

        loaded = runner.load_prepared(prepared.action_digest)
        assert loaded.binding == binding
        consumed = runner.consume_prepared(prepared.action_digest, now=instant)
        assert consumed.binding["source_baseline"] == SNAPSHOT_BASELINE

        result = await runner.run(
            None,
            prepared.action_digest,
            current_revision=SNAPSHOT_REVISION,
            current_inventory_digest=inventory_digest,
            current_input_snapshot_sha256=SNAPSHOT,
            now=instant,
            consumed=consumed,
        )

        assert len(workflow_calls) == 1
        assert [call[0] for call in transport.calls] == ["open", "read", "close"]
        manifest = result["test_manifest"]
        envelope = result["evidence"]
        for candidate in (manifest.identity, envelope.identity):
            assert candidate.source_baseline == SNAPSHOT_BASELINE
            assert candidate.git_commit is None
            assert candidate.git_dirty is None
            assert dict(candidate.git_evidence or {}) == SNAPSHOT_EVIDENCE
            assert candidate.input_snapshot_sha256 == SNAPSHOT
            assert candidate.content_revision == SNAPSHOT_REVISION

        stored = evidence_store.get_envelope(str(envelope.evidence_id))
        assert stored.identity.source_baseline == SNAPSHOT_BASELINE
        assert stored.identity.git_commit is None
        assert stored.identity.git_dirty is None

    _run(scenario())


@pytest.mark.parametrize("protocol", ["stm32-target-frame/1", "stm32-target-frame/2"])
def test_legacy_target_record_with_input_snapshot_prepare_consume_run(
    tmp_path: Path, protocol: str
) -> None:
    """A legacy Git record legitimately records only the input snapshot digest."""
    identity = _legacy_identity()
    stream = _v1_stream(identity) if protocol == "stm32-target-frame/1" else _v2_stream()
    transport = FakeTransport([stream])
    runner, evidence_store, workflow_calls = _target_runner(tmp_path, transport)

    async def scenario() -> None:
        prepared, instant, inventory_digest = await _prepare_legacy(
            runner, identity, protocol=protocol
        )
        binding = prepared.binding
        assert binding["revision"] == GIT_HEAD
        assert binding["input_snapshot_sha256"] == SNAPSHOT
        assert "source_baseline" not in binding and "git_evidence" not in binding
        if protocol == "stm32-target-frame/1":
            assert set(binding) == _LEGACY_BINDING_FIELDS
        else:
            assert set(binding) == _V2_LEGACY_BINDING_FIELDS
            assert binding["git_dirty"] is False

        # The accepted legacy record keeps its exact closed fields and bytes:
        # it gains none of the snapshot keys.
        record_path = (
            tmp_path / "runs" / "records" / f"{prepared.action_digest}.prepared.json"
        )
        record_bytes = record_path.read_bytes()
        assert record_bytes == canonical_json_bytes(dict(binding))
        assert b"source_baseline" not in record_bytes
        assert b"git_evidence" not in record_bytes

        loaded = runner.load_prepared(prepared.action_digest)
        assert loaded.binding == binding
        consumed = runner.consume_prepared(prepared.action_digest, now=instant)
        assert consumed.binding["revision"] == GIT_HEAD

        result = await runner.run(
            None,
            prepared.action_digest,
            current_revision=GIT_HEAD,
            current_inventory_digest=inventory_digest,
            current_input_snapshot_sha256=SNAPSHOT,
            now=instant,
            consumed=consumed,
        )

        assert len(workflow_calls) == 1
        manifest = result["test_manifest"]
        envelope = result["evidence"]
        for candidate in (manifest.identity, envelope.identity):
            assert candidate.git_commit == GIT_HEAD
            assert candidate.git_dirty is False
            assert candidate.source_baseline is None
            assert candidate.git_evidence is None
            assert candidate.input_snapshot_sha256 == SNAPSHOT
            assert candidate.content_revision == GIT_HEAD
            assert "source_baseline" not in candidate.to_dict()
        stored = evidence_store.get_envelope(str(envelope.evidence_id))
        assert stored.identity.git_commit == GIT_HEAD
        assert stored.identity.source_baseline is None

    _run(scenario())


def test_legacy_target_run_rejects_a_stale_or_omitted_input_snapshot(
    tmp_path: Path,
) -> None:
    identity = _legacy_identity()
    runner, _store, workflow_calls = _target_runner(tmp_path, FakeTransport([]))

    async def scenario() -> None:
        for current in ("8" * 64, None):
            prepared, instant, inventory_digest = await _prepare_legacy(
                runner, identity, protocol="stm32-target-frame/1"
            )
            with pytest.raises(target_module.TargetRunError) as caught:
                await runner.run(
                    prepared,
                    prepared.action_digest,
                    current_revision=GIT_HEAD,
                    current_inventory_digest=inventory_digest,
                    current_input_snapshot_sha256=current,
                    now=instant,
                )
            assert caught.value.code == "TEST_INVENTORY_CHANGED"
        assert workflow_calls == []

    _run(scenario())


def test_snapshot_target_run_rejects_reused_authorization_and_changed_snapshot(
    tmp_path: Path,
) -> None:
    identity = _snapshot_identity()
    transport = FakeTransport([_v1_stream(identity)])
    runner, _store, workflow_calls = _target_runner(tmp_path, transport)

    async def scenario() -> None:
        prepared, instant, inventory_digest = await _prepare_snapshot(
            runner, identity, protocol="stm32-target-frame/1"
        )
        first = await runner.run(
            prepared,
            prepared.action_digest,
            current_revision=SNAPSHOT_REVISION,
            current_inventory_digest=inventory_digest,
            current_input_snapshot_sha256=SNAPSHOT,
            now=instant,
        )
        assert first["evidence"].identity.source_baseline == SNAPSHOT_BASELINE

        with pytest.raises(target_module.TargetRunError) as reused:
            await runner.run(
                prepared,
                prepared.action_digest,
                current_revision=SNAPSHOT_REVISION,
                current_inventory_digest=inventory_digest,
                current_input_snapshot_sha256=SNAPSHOT,
                now=instant,
            )
        assert reused.value.code == "TEST_AUTHORIZATION_INVALID"

        second, second_instant, second_digest = await _prepare_snapshot(
            runner, identity, protocol="stm32-target-frame/1"
        )
        before_flash = len(workflow_calls)
        with pytest.raises(target_module.TargetRunError) as changed:
            await runner.run(
                second,
                second.action_digest,
                current_revision=SNAPSHOT_REVISION,
                current_inventory_digest=second_digest,
                current_input_snapshot_sha256="8" * 64,
                now=second_instant,
            )
        assert changed.value.code == "TEST_INVENTORY_CHANGED"
        assert len(workflow_calls) == before_flash

    _run(scenario())


def test_snapshot_target_rejects_mixed_partial_and_downgraded_provenance(
    tmp_path: Path,
) -> None:
    identity = _snapshot_identity()
    runner, _store, workflow_calls = _target_runner(tmp_path, FakeTransport([]))
    instant = datetime(2026, 8, 25, tzinfo=timezone.utc)
    base = {
        "workspace_id": WORKSPACE_ID,
        "project_id": PROJECT_ID,
        "session_id": SESSION_ID,
        "target": IDENTITY,
        "probe_serial_hash": PROBE_HASH,
        "elf_path": "build/app.elf",
        "elf_sha256": ELF_SHA256,
        "build_id": BUILD_ID,
        "inventory_digest": calculate_inventory_digest("target", identity, (CASE_ID,)),
        "transport": "mailbox",
        "transport_config": MAILBOX_PROJECT_CONFIG,
        "support_profile": TARGET_SUPPORT,
        "cases": (CASE_ID,),
        "timeout_ms": 1_000,
        "now": instant,
    }

    async def scenario() -> None:
        mixed = dict(base, **_snapshot_binding_fields(), git_dirty=True)
        with pytest.raises(target_module.TargetRunError) as mixed_error:
            await runner.prepare(**mixed)
        assert mixed_error.value.code == "TEST_PROTOCOL_INVALID"

        partial = {**base, "revision": SNAPSHOT_REVISION, "input_snapshot_sha256": SNAPSHOT}
        with pytest.raises(target_module.TargetRunError) as partial_error:
            await runner.prepare(**partial)
        assert partial_error.value.code == "TEST_PROTOCOL_INVALID"

        wrong_revision = dict(
            base, **{**_snapshot_binding_fields(), "revision": "c" * 40}
        )
        with pytest.raises(target_module.TargetRunError) as wrong_error:
            await runner.prepare(**wrong_revision)
        assert wrong_error.value.code == "TEST_PROTOCOL_INVALID"

    _run(scenario())
    assert workflow_calls == []


def _prepared_record(
    identity: EvidenceIdentity, *, protocol: str | None = None, **extra: object
) -> dict[str, object]:
    record: dict[str, object] = {
        "workspace_id": WORKSPACE_ID,
        "project_id": PROJECT_ID,
        "session_id": SESSION_ID,
        "revision": GIT_HEAD,
        "target": dict(IDENTITY),
        "probe_serial_hash": PROBE_HASH,
        "elf_path": "build/app.elf",
        "elf_sha256": ELF_SHA256,
        "build_id": BUILD_ID,
        "input_snapshot_sha256": SNAPSHOT,
        "inventory_digest": calculate_inventory_digest("target", identity, (CASE_ID,)),
        "transport": "mailbox",
        "transport_config": MAILBOX_PROJECT_CONFIG,
        "support_profile": TARGET_SUPPORT,
        "cases": [CASE_ID],
        "timeout_ms": 1_000,
        "nonce": "0" * 64,
        "prepared_at_utc": "2026-08-25T00:00:00.000000Z",
        "expires_at_utc": "2026-08-25T00:05:00.000000Z",
    }
    if protocol is not None:
        record.update(protocol=protocol, case_inventory_digest=V2_CASE_DIGEST)
    record.update(extra)
    return record


def test_legacy_prepared_record_with_input_snapshot_remains_valid() -> None:
    """The accepted Git forms keep their exact closed fields and bytes."""
    identity = _legacy_identity()
    record = _prepared_record(identity)
    target_module.TargetTestRunner._validate_prepared_record(record)
    assert record["revision"] == GIT_HEAD
    assert set(record) == _LEGACY_BINDING_FIELDS
    payload = canonical_json_bytes(record)
    assert b"source_baseline" not in payload
    assert b"git_evidence" not in payload

    v2_record = _prepared_record(
        identity, protocol="stm32-target-frame/2", git_dirty=False
    )
    target_module.TargetTestRunner._validate_prepared_record(v2_record)
    assert set(v2_record) == _V2_LEGACY_BINDING_FIELDS


def test_prepared_record_rejects_partial_null_and_downgraded_snapshot_values() -> None:
    identity = _legacy_identity()
    complete: dict[str, object] = {
        "revision": SNAPSHOT_REVISION,
        "source_baseline": SNAPSHOT_BASELINE,
        "git_evidence": dict(SNAPSHOT_EVIDENCE),
    }
    for mutation in (
        {**complete, "source_baseline": None},
        {**complete, "git_evidence": None},
        {**complete, "revision": GIT_HEAD},
        {"revision": SNAPSHOT_REVISION},
    ):
        with pytest.raises(ValueError):
            target_module.TargetTestRunner._validate_prepared_record(
                _prepared_record(identity, **mutation)
            )

    # Null-only legacy Git state is never coerced into a clean flag.
    with pytest.raises(ValueError):
        target_module.TargetTestRunner._validate_prepared_record(
            _prepared_record(identity, protocol="stm32-target-frame/2", git_dirty=None)
        )

    # A complete snapshot pair may not carry a boolean Git dirty flag.
    with pytest.raises(ValueError):
        target_module.TargetTestRunner._validate_prepared_record(
            _prepared_record(
                identity,
                protocol="stm32-target-frame/2",
                git_dirty=True,
                **complete,
            )
        )


def test_prepared_record_rejects_a_namespaced_revision_without_its_snapshot_pair(
    tmp_path: Path,
) -> None:
    """A downgraded record may not borrow a snapshot revision as a Git commit."""
    identity = _snapshot_identity()
    record = _prepared_record(identity, revision=SNAPSHOT_REVISION)
    with pytest.raises(ValueError):
        target_module.TargetTestRunner._validate_prepared_record(record)


def test_snapshot_target_rejects_tampered_stream_identity_before_evidence(
    tmp_path: Path,
) -> None:
    identity = _snapshot_identity()
    legacy_stream_identity = {
        "workspace_id": WORKSPACE_ID,
        "project_id": PROJECT_ID,
        "session_id": SESSION_ID,
        "build_id": BUILD_ID,
        "elf_sha256": ELF_SHA256,
        "target_device": "target-a",
        "input_snapshot_sha256": SNAPSHOT,
        "git_commit": "1" * 40,
        "git_dirty": False,
    }

    def forged_stream() -> bytes:
        # The stream is internally consistent with its own legacy identity, so
        # only its bound provenance can contradict the snapshot authorization.
        body_identity = EvidenceIdentity.from_dict(legacy_stream_identity)
        digest = calculate_inventory_digest("target", body_identity, (CASE_ID,))
        bodies = [
            (
                1,
                {
                    "mode": "target",
                    "identity": body_identity,
                    "case_ids": [CASE_ID],
                    "inventory_digest": digest,
                    "discovered_at_utc": "2026-08-16T00:00:00.000000Z",
                },
            ),
            (
                2,
                {
                    "run_id": "run-1",
                    "started_at_utc": "2026-08-16T00:00:00.000000Z",
                    "case_ids": [CASE_ID],
                    "inventory_digest": digest,
                },
            ),
            (3, {"case_id": CASE_ID, "started_at_utc": "2026-08-16T00:00:00.000000Z"}),
            (
                4,
                {
                    "case_id": CASE_ID,
                    "state": "passed",
                    "ended_at_utc": "2026-08-16T00:00:01.000000Z",
                    "duration_ms": 1000,
                    "message": None,
                    "stdout": None,
                    "stderr": None,
                },
            ),
        ]
        frames = [
            target_module.encode_frame(kind, sequence, body)
            for sequence, (kind, body) in enumerate(bodies)
        ]
        terminal = {
            "state": "passed",
            "ended_at_utc": "2026-08-16T00:00:01.000000Z",
            "duration_ms": 1000,
            "inventory_digest": digest,
            "build_id": BUILD_ID,
            "elf_sha256": ELF_SHA256,
            "target_device": "target-a",
            "counts": {"passed": 1, "failed": 0, "skipped": 0, "error": 0, "timeout": 0},
            "event_stream_digest": sha256(b"".join(frames)).hexdigest(),
        }
        frames.append(target_module.encode_frame(5, len(frames), terminal))
        return b"".join(frames)

    transport = FakeTransport([forged_stream()])
    runner, evidence_store, _workflow_calls = _target_runner(tmp_path, transport)

    async def scenario() -> None:
        prepared, instant, inventory_digest = await _prepare_snapshot(
            runner, identity, protocol="stm32-target-frame/1"
        )
        with pytest.raises(target_module.TargetRunError) as caught:
            await runner.run(
                prepared,
                prepared.action_digest,
                current_revision=SNAPSHOT_REVISION,
                current_inventory_digest=inventory_digest,
                current_input_snapshot_sha256=SNAPSHOT,
                now=instant,
            )
        assert caught.value.code == "TEST_IDENTITY_MISMATCH"
        assert not any((evidence_store.root).rglob("manifests/*.json"))

    _run(scenario())


@dataclass(frozen=True)
class _HostInventory:
    inventory_digest: str = "c" * 64
    case_ids: tuple[str, ...] = ("passes",)

    def to_dict(self) -> dict[str, object]:
        return {
            "mode": "host",
            "identity": {},
            "case_ids": list(self.case_ids),
            "inventory_digest": self.inventory_digest,
            "discovered_at_utc": "2026-08-20T00:00:00.000000Z",
        }


@dataclass(frozen=True)
class _HostManifest:
    run_id: str = "run-1"
    state: str = "passed"


class _DiscoveryArtifact:
    def to_dict(self) -> dict[str, object]:
        return {
            "sha256": "d" * 64,
            "size_bytes": 4,
            "relative_path": "objects/sha256/dd/" + "d" * 64,
            "kind": "test-discovery",
            "media_type": "application/json",
        }


class _HostPublished:
    def public_data(self, *, authoritative: bool = False) -> dict[str, object]:
        value: dict[str, object] = {
            "run": {"run_id": "run-1", "state": "passed"},
            "test_manifest": {"sha256": "e" * 64},
            "evidence_id": "f" * 64,
        }
        if authoritative:
            value["authoritative"] = True
        return value


def _host_model(project_root: Path):
    return SimpleNamespace(
        project_root=project_root,
        schema_version=3,
        logical_project_id=UUID("12345678-1234-5678-1234-567812345678"),
        testing=SimpleNamespace(host=object()),
    )


def _install_host_seams(
    monkeypatch: pytest.MonkeyPatch,
    project_root: Path,
    identities: list[object],
) -> None:
    class Runner:
        def __init__(self, **_kwargs: object) -> None:
            self.discovery_artifact = _DiscoveryArtifact()

        def discover(self, _host_config: object, identity: object) -> _HostInventory:
            identities.append(identity)
            return _HostInventory()

        def run(self, _inventory: object, _case_ids: object) -> _HostManifest:
            return _HostManifest()

    class Publisher:
        def __init__(self, *_args: object) -> None:
            pass

        def publish_host(self, _manifest: object, *, inventory_digest: str) -> _HostPublished:
            assert inventory_digest == "c" * 64
            return _HostPublished()

    monkeypatch.setattr(
        workflows, "_load_project_model", lambda _root: _host_model(project_root)
    )
    monkeypatch.setattr(
        workflows,
        "_snapshot_project_inputs",
        lambda _model: SimpleNamespace(sha256=SNAPSHOT),
    )
    monkeypatch.setattr(workflows, "_host_runner_factory", Runner)
    monkeypatch.setattr(workflows, "_publisher_factory", Publisher)
    monkeypatch.setattr(workflows, "_evidence_store_factory", lambda _root: object())


def _assert_host_snapshot_identity(identity: object) -> None:
    assert identity.git_commit is None
    assert identity.git_dirty is None
    assert identity.source_baseline == SNAPSHOT_BASELINE
    evidence = identity.git_evidence
    assert evidence is not None
    assert dict(evidence) == SNAPSHOT_EVIDENCE
    assert identity.input_snapshot_sha256 == SNAPSHOT
    bound = identity.bind(build_id=BUILD_ID, elf_sha256=ELF_SHA256)
    document = bound.to_dict()
    assert document["source_baseline"] == SNAPSHOT_BASELINE
    assert document["git_evidence"] == SNAPSHOT_EVIDENCE
    assert document["git_commit"] is None
    assert document["git_dirty"] is None
    assert set(document) == {
        "workspace_id",
        "project_id",
        "session_id",
        "build_id",
        "elf_sha256",
        "target_device",
        "input_snapshot_sha256",
        "git_commit",
        "git_dirty",
        "source_baseline",
        "git_evidence",
    }


def test_host_discover_and_run_without_git_bind_the_snapshot_form(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    project_root = (tmp_path / "project").absolute()
    project_root.mkdir()
    context = workflows.TestingWorkflowContext(
        project_root=project_root,
        data_root=tmp_path / "data",
        session_id="session-1",
    )
    identities: list[object] = []
    _install_host_seams(monkeypatch, project_root, identities)

    discovered = workflows.host_test_discover(context)
    assert discovered.ok is True
    run = workflows.host_test_run(
        context, inventory_digest="c" * 64, case_ids=("passes",)
    )
    assert run.ok is True
    assert len(identities) == 2
    for identity in identities:
        _assert_host_snapshot_identity(identity)


def test_host_discover_and_run_in_an_unborn_repository(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    project_root = (tmp_path / "project").absolute()
    project_root.mkdir()
    try:
        subprocess.run(
            ["git", "init", "--quiet", str(project_root)],
            check=True,
            capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("git is unavailable for the unborn-repository case")

    context = workflows.TestingWorkflowContext(
        project_root=project_root,
        data_root=tmp_path / "data",
        session_id="session-1",
    )
    identities: list[object] = []
    _install_host_seams(monkeypatch, project_root, identities)

    discovered = workflows.host_test_discover(context)
    assert discovered.ok is True
    run = workflows.host_test_run(
        context, inventory_digest="c" * 64, case_ids=("passes",)
    )
    assert run.ok is True
    assert len(identities) == 2
    for identity in identities:
        _assert_host_snapshot_identity(identity)


def _debug_binding(*, snapshot: bool) -> DebugFirmwareBinding:
    evidence = dict(SNAPSHOT_EVIDENCE)
    return DebugFirmwareBinding(
        logical_project_id=PROJECT_ID,
        workspace_id=WORKSPACE_ID,
        observation_session_id=SESSION_ID,
        flash_session_id=SESSION_ID,
        lease_id="lease-a",
        probe_id="probe-a",
        target_device="target-a",
        debug_target="stm32f407vg",
        build_id=BUILD_ID,
        elf_sha256=ELF_SHA256,
        elf_size=4,
        elf_path="build/app.elf",
        input_snapshot_sha256=SNAPSHOT,
        git_head=None if snapshot else "c" * 40,
        git_dirty=None if snapshot else False,
        confirmed_at_utc="2026-08-25T00:00:00.000000Z",
        memory_regions=(MemoryRegionBinding("RAM", 0x20000000, 0x10000, "rw-"),),
        project_root=Path("C:/fixture/project"),
        source_baseline=SNAPSHOT_BASELINE if snapshot else None,
        git_evidence=evidence if snapshot else None,
    )


def test_controlled_debug_authorization_uses_the_snapshot_content_revision() -> None:
    snapshot = _debug_binding(snapshot=True)
    binding = _control_authorization_binding(snapshot, dict(IDENTITY), "target.halt")
    assert binding["revision"] == SNAPSHOT_REVISION
    assert binding["revision"].startswith("input-snapshot-v1:")
    assert binding["firmware"] == {"build_id": BUILD_ID, "elf_sha256": ELF_SHA256}

    legacy = _debug_binding(snapshot=False)
    legacy_binding = _control_authorization_binding(legacy, dict(IDENTITY), "target.halt")
    assert legacy_binding["revision"] == "c" * 40


def test_acceptance_recovery_identity_emits_the_snapshot_form_without_git(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A recovery producer never fabricates a clean or zero Git commit."""
    import stm32_toolkit.acceptance.recovery_workflows as recovery_workflows
    from stm32_toolkit.build.identity import GitEvidence, GitUnavailableEvidence

    project_root = (tmp_path / "project").absolute()
    project_root.mkdir()
    context = recovery_workflows.AcceptanceRecoveryContext(
        project_root=project_root,
        data_root=(tmp_path / "data").absolute(),
        session_id=SESSION_ID,
    )
    workspace = SimpleNamespace(workspace_id=WORKSPACE_ID)
    model = SimpleNamespace(logical_project_id=PROJECT_ID, target_device="target-a")
    monkeypatch.setattr(
        recovery_workflows,
        "snapshot_project_inputs",
        lambda _model: SimpleNamespace(sha256=SNAPSHOT),
    )

    monkeypatch.setattr(
        recovery_workflows,
        "collect_build_git_evidence",
        lambda _root: GitUnavailableEvidence(rule="head"),
    )
    identity = recovery_workflows._current_identity(context, model, workspace)
    assert identity.git_commit is None
    assert identity.git_dirty is None
    assert identity.source_baseline == SNAPSHOT_BASELINE
    assert dict(identity.git_evidence or {}) == SNAPSHOT_EVIDENCE
    assert identity.input_snapshot_sha256 == SNAPSHOT
    assert identity.content_revision == SNAPSHOT_REVISION
    # Pre-build placeholders stay placeholders; they never claim a real input.
    assert identity.build_id == "0" * 64

    monkeypatch.setattr(
        recovery_workflows,
        "collect_build_git_evidence",
        lambda _root: GitEvidence(head=GIT_HEAD, dirty=False),
    )
    legacy = recovery_workflows._current_identity(context, model, workspace)
    assert legacy.git_commit == GIT_HEAD
    assert legacy.git_dirty is False
    assert legacy.source_baseline is None
    assert legacy.git_evidence is None
    assert legacy.content_revision == GIT_HEAD

    def unavailable(_model: object) -> object:
        raise RuntimeError("input enumeration failed")

    monkeypatch.setattr(recovery_workflows, "snapshot_project_inputs", unavailable)
    with pytest.raises(recovery_workflows._RecoveryFailure) as failed:
        recovery_workflows._current_identity(context, model, workspace)
    assert failed.value.code == "ACCEPTANCE_ATTEMPT_OUTPUT_INVALID"


@dataclass(frozen=True)
class _ReplayFixture:
    descriptor: object
    stream_bytes: bytes


def _snapshot_replay_descriptor(identity: EvidenceIdentity, stream: bytes):
    from stm32_toolkit.evidence import ArtifactRef
    from stm32_toolkit.testing.replay import (
        TARGET_REPLAY_SCHEMA,
        TARGET_REPLAY_SOURCE,
        TARGET_REPLAY_STREAM_FORMAT,
        TARGET_REPLAY_STREAM_KIND,
        TargetReplayDescriptor,
        calculate_replay_id,
    )

    artifact = ArtifactRef(
        sha256(stream).hexdigest(),
        len(stream),
        "fixed-after.bin",
        TARGET_REPLAY_STREAM_KIND,
        "application/octet-stream",
    )
    intent = {
        "schema": TARGET_REPLAY_SCHEMA,
        "replay_id": "0" * 64,
        "scenario_role": "fixed-after",
        "source": TARGET_REPLAY_SOURCE,
        "physical_transport_evidence": False,
        "identity": identity.to_dict(),
        "inventory_digest": calculate_inventory_digest("target", identity, (CASE_ID,)),
        "stream": artifact.to_dict(),
        "stream_format": TARGET_REPLAY_STREAM_FORMAT,
        "expected_terminal_state": "passed",
    }
    intent["replay_id"] = calculate_replay_id(intent)
    return TargetReplayDescriptor.from_value(intent)


def _write_replay_fixture(tmp_path: Path, identity: EvidenceIdentity, stream: bytes):
    from stm32_toolkit.testing.replay import canonical_replay_json_bytes

    descriptor = _snapshot_replay_descriptor(identity, stream)
    fixture_dir = tmp_path / "fixture"
    fixture_dir.mkdir()
    descriptor_file = fixture_dir / "fixed-after.json"
    stream_file = fixture_dir / "fixed-after.hex"
    descriptor_file.write_bytes(canonical_replay_json_bytes(descriptor) + b"\n")
    stream_file.write_text(stream.hex() + "\n", encoding="ascii")
    return descriptor_file, stream_file, descriptor


def _install_replay_seams(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    captured: list[tuple[object, object, object]],
) -> Path:
    project_root = (tmp_path / "project").absolute()
    project_root.mkdir(exist_ok=True)
    evidence_store = EvidenceStore((tmp_path / "evidence").absolute())
    state = SimpleNamespace(
        workspace=SimpleNamespace(
            workspace_id=WORKSPACE_ID, project_root=project_root
        ),
        results_root=(tmp_path / "results").absolute(),
        evidence_store=evidence_store,
    )

    class Publisher:
        def __init__(self, *_args: object) -> None:
            pass

        def publish_target_replay(self, manifest, parent, workspace_id):
            captured.append((manifest, parent, workspace_id))
            return _HostPublished()

    monkeypatch.setattr(
        workflows, "_make_state", lambda *_args, **_kwargs: state
    )
    monkeypatch.setattr(workflows, "_publisher_factory", Publisher)
    return project_root


def test_snapshot_replay_accepts_the_snapshot_descriptor_and_publishes_identity(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    identity = _snapshot_identity()
    descriptor_file, stream_file, descriptor = _write_replay_fixture(
        tmp_path, identity, _v1_stream(identity)
    )
    captured: list[tuple[object, object, object]] = []
    project_root = _install_replay_seams(monkeypatch, tmp_path, captured)

    result = workflows.target_replay_run(
        workflows.TestingWorkflowContext(
            project_root=project_root,
            data_root=tmp_path / "data",
            session_id=SESSION_ID,
        ),
        "run-1",
        descriptor_file,
        stream_file,
    )

    assert result.ok is True
    assert len(captured) == 1
    manifest, parent, workspace_id = captured[0]
    assert workspace_id == WORKSPACE_ID
    for envelope in (manifest.identity, parent.identity):
        assert envelope.source_baseline == SNAPSHOT_BASELINE
        assert envelope.git_commit is None
        assert envelope.git_dirty is None
        assert dict(envelope.git_evidence or {}) == SNAPSHOT_EVIDENCE
    assert parent.identity.content_revision == descriptor.identity.content_revision


def test_legacy_replay_accepts_the_git_form_with_input_snapshot(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    identity = _legacy_identity()
    descriptor_file, stream_file, descriptor = _write_replay_fixture(
        tmp_path, identity, _v1_stream(identity)
    )
    captured: list[tuple[object, object, object]] = []
    project_root = _install_replay_seams(monkeypatch, tmp_path, captured)

    result = workflows.target_replay_run(
        workflows.TestingWorkflowContext(
            project_root=project_root,
            data_root=tmp_path / "data",
            session_id=SESSION_ID,
        ),
        "run-1",
        descriptor_file,
        stream_file,
    )

    assert result.ok is True
    assert len(captured) == 1
    manifest, parent, workspace_id = captured[0]
    assert workspace_id == WORKSPACE_ID
    for envelope in (manifest.identity, parent.identity):
        assert envelope.git_commit == GIT_HEAD
        assert envelope.git_dirty is False
        assert envelope.source_baseline is None
        assert envelope.git_evidence is None
        assert envelope.input_snapshot_sha256 == SNAPSHOT
        assert envelope.content_revision == GIT_HEAD
        assert "source_baseline" not in envelope.to_dict()
    assert parent.identity.content_revision == descriptor.identity.content_revision


def test_snapshot_replay_rejects_a_downgraded_descriptor_identity(
    tmp_path: Path,
) -> None:
    from stm32_toolkit.testing.replay import TargetReplayDescriptor

    identity = _snapshot_identity()
    stream = _v1_stream(identity)
    intent = _snapshot_replay_descriptor(identity, stream).to_dict()
    legacy_identity = dict(intent["identity"])
    legacy_identity.pop("source_baseline")
    legacy_identity.pop("git_evidence")
    legacy_identity["git_commit"] = "c" * 40
    legacy_identity["git_dirty"] = False
    intent["identity"] = legacy_identity
    from stm32_toolkit.testing.replay import calculate_replay_id

    intent["replay_id"] = calculate_replay_id(intent)
    descriptor = TargetReplayDescriptor.from_value(intent)

    with pytest.raises(Exception) as caught:
        workflows._target_replay_frames(
            _ReplayFixture(descriptor, stream), "run-1"
        )
    assert getattr(caught.value, "code", None) == "TEST_REPLAY_INTEGRITY"
