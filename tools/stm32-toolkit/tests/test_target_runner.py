from __future__ import annotations

import asyncio
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
import os
import shutil
import subprocess
import sys
import threading
import time
from types import SimpleNamespace

import pytest
from stm32_toolkit.evidence import EvidenceIdentity, canonical_json_bytes
from stm32_toolkit.result import OperationResult

from stm32_toolkit.probe import client as probe_client
from stm32_toolkit.probe.authorization import ControlAuthorizationError, ControlAuthorizationStore
from stm32_toolkit.testing import target as target_module
from stm32_toolkit.testing.model import calculate_inventory_digest
from stm32_toolkit.testing.protocol import calculate_case_inventory_digest

ProbeClientError = probe_client.ProbeClientError

WORKSPACE_ID = "0" * 64
PROJECT_ID = "123e4567-e89b-42d3-a456-426614174000"
SESSION_ID = "session-0601-t09"
REVISION = "c" * 40
PROBE_SELECTOR = "probe-a"
PROBE_HASH = sha256(PROBE_SELECTOR.encode("utf-8")).hexdigest()


IDENTITY = {
    "board_id": "board-a",
    "mcu": "stm32f407vg",
    "target_id": "target-a",
    "probe_serial_hash": PROBE_HASH,
}
STATE = {"state": "halted", "reason": "requested"}
MAILBOX_PROJECT_CONFIG = {
    "kind": "memory-mailbox", "options": {"address": 0x20000000, "size": 4096},
}
TARGET_SUPPORT = {
    "backend": "pyocd", "board_id": "board-a", "mcu": "stm32f407vg",
    "target_id": "target-a", "ram": [{"start": 0x20000000, "size": 0x10000}],
    "mailbox": {"address": 0x20000000, "size": 4096},
    "rtt": {"channel": 0, "control_block_address": 0x20000100},
    "uart": {"port": "COM3", "baud": 115200},
    "semihosting": {"declared": True},
    "semihosting_runtime": {"elf_path": "C:\\fixture\\app.elf", "elf_sha256": "e" * 64},
}


class FakeProbeClient:
    def __init__(self) -> None:
        self.calls: list[tuple[object, ...]] = []
        self.identity = dict(IDENTITY)
        self.state = dict(STATE)
        self.closed = False

    async def target_identity(self):
        self.calls.append(("identity",))
        return dict(self.identity)

    async def target_state(self):
        self.calls.append(("state",))
        return dict(self.state)

    async def target_control(self, operation, arguments, authorization):
        self.calls.append(("control", operation, dict(arguments), authorization))
        return {"state": "running"}

    async def close(self):
        self.calls.append(("close",))
        self.closed = True


def run(coro):
    return asyncio.run(coro)


def release_process_barrier(
    children: list[subprocess.Popen[bytes]], ready: list[Path], start: Path,
) -> None:
    deadline = time.monotonic() + 15
    while not all(path.exists() for path in ready) and time.monotonic() < deadline:
      if any(child.poll() is not None for child in children):
        break
      time.sleep(0.005)
    if not all(path.exists() for path in ready):
      for child in children:
        if child.poll() is None:
          child.terminate()
      for child in children:
        child.wait(timeout=5)
      pytest.fail("authorization consumers did not reach the start barrier")
    start.write_text("go", encoding="utf-8")


def _target_evidence_identity(
    input_snapshot_sha256: str = "9" * 64,
) -> EvidenceIdentity:
    return EvidenceIdentity.from_dict({
        "workspace_id": WORKSPACE_ID, "project_id": PROJECT_ID, "session_id": SESSION_ID,
        "build_id": "b" * 64, "elf_sha256": "e" * 64, "target_device": "target-a",
        "input_snapshot_sha256": input_snapshot_sha256, "git_commit": REVISION, "git_dirty": False,
    })


def _target_inventory_digest(
    case_id: str = "suite.case", *, input_snapshot_sha256: str = "9" * 64,
) -> str:
    return calculate_inventory_digest(
        "target", _target_evidence_identity(input_snapshot_sha256), (case_id,)
    )


def _target_stream(
    case_id: str = "suite.case",
    *,
    input_snapshot_sha256: str = "9" * 64,
    inventory_digest: str | None = None,
) -> bytes:
    identity = _target_evidence_identity(input_snapshot_sha256)
    digest = inventory_digest or calculate_inventory_digest("target", identity, (case_id,))
    bodies = [
        (1, {"mode": "target", "identity": identity.to_dict(), "case_ids": [case_id], "inventory_digest": digest, "discovered_at_utc": "2026-08-16T00:00:00.000000Z"}),
        (2, {"run_id": "run-1", "started_at_utc": "2026-08-16T00:00:00.000000Z", "case_ids": [case_id], "inventory_digest": digest}),
        (3, {"case_id": case_id, "started_at_utc": "2026-08-16T00:00:00.000000Z"}),
        (4, {"case_id": case_id, "state": "passed", "ended_at_utc": "2026-08-16T00:00:01.000000Z", "duration_ms": 1000, "message": None, "stdout": None, "stderr": None}),
    ]
    frames = [target_module.encode_frame(kind, sequence, body) for sequence, (kind, body) in enumerate(bodies)]
    terminal = {
        "state": "passed", "ended_at_utc": "2026-08-16T00:00:01.000000Z", "duration_ms": 1000,
        "inventory_digest": digest, "build_id": "b" * 64, "elf_sha256": "e" * 64,
        "target_device": "target-a", "counts": {"passed": 1, "failed": 0, "skipped": 0, "error": 0, "timeout": 0},
        "event_stream_digest": sha256(b"".join(frames)).hexdigest(),
    }
    frames.append(target_module.encode_frame(5, len(frames), terminal))
    return b"".join(frames)


def valid_target_stream(case_id: str = "suite.case") -> bytes:
    return _target_stream(case_id)


TARGET_RUN_INVENTORY_DIGEST = _target_inventory_digest()


V2_CASE_ID = "suite.case"
V2_CASE_INVENTORY_DIGEST = calculate_case_inventory_digest([V2_CASE_ID])


def _v2_target_stream(case_id: str = V2_CASE_ID) -> tuple[bytes, bytes]:
  case_digest = calculate_case_inventory_digest([case_id])
  nonterminal = [
      (1, {"mode": "target", "case_ids": [case_id], "case_inventory_digest": case_digest, "monotonic_ms": 0}),
      (2, {"case_ids": [case_id], "case_inventory_digest": case_digest, "monotonic_ms": 1}),
      (3, {"case_id": case_id, "monotonic_ms": 2}),
      (4, {"case_id": case_id, "state": "passed", "monotonic_ms": 3, "message": None}),
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
  return b"".join(frames[:1]), b"".join(frames)


def test_control_prepare_binds_snapshot_and_execute_consumes_before_denial(tmp_path: Path):
  async def scenario():
    probe = FakeProbeClient()
    auth = getattr(probe_client, "ControlAuthorizationClient")(
        ControlAuthorizationStore((tmp_path / "control").absolute()), probe
    )
    prepared = await auth.prepare(
        workspace_id="workspace-a", project_id="project-a", session_id="session-a",
        revision="rev-a", target=IDENTITY, firmware={"build_id": "b" * 64, "elf_sha256": "e" * 64},
        operation="target.resume", arguments={}, now=datetime(2026, 8, 16, tzinfo=timezone.utc),
    )
    assert len(prepared.nonce) == 64
    assert prepared.expires_at_utc <= datetime(2026, 8, 16, tzinfo=timezone.utc) + timedelta(minutes=5)
    assert probe.calls == [("identity",), ("state",)]

    result = await auth.execute(
        prepared, prepared.action_digest, now=datetime(2026, 8, 16, tzinfo=timezone.utc)
    )
    assert result == {"state": "running"}
    assert probe.closed
  run(scenario())


class FakeFlashWorkflow(target_module.GuardedTargetFlashAdapter):
    def __init__(self) -> None:
        self.calls = []
        super().__init__(
            project_root=Path.cwd().absolute(), data_root=(Path.cwd() / ".test-data").absolute(),
            session_id="session-a", probe_id="probe-a", workflow=self._run,
        )

    async def _run(self, request):
        self.calls.append(request)
        return OperationResult.success("stm32_flash", {"status": "success"})


class FakeTransport:
    def __init__(self, chunks: list[bytes]) -> None:
        self.chunks = chunks
        self.calls = []
        self.config = None

    def open(self, config, deadline):
        self.config = dict(config)
        self.calls.append(("open", dict(config), deadline))
    def read(self, maximum, deadline):
        self.calls.append(("read", maximum, deadline))
        return self.chunks.pop(0) if self.chunks else b""
    def eof(self): return not self.chunks
    def close(self): self.calls.append(("close",))
    def identity(self):
        config = self.config
        if not isinstance(config, dict) or not {
            "address", "size", "ram", "target_id", "probe_id"
        }.issubset(config):
          config = {
            "address": 0x20000000, "size": 4096,
            "ram": [{"start": 0x20000000, "size": 0x10000}],
            "target_id": "target-a", "probe_id": PROBE_HASH,
          }
        identity = {
            "probe_id": str(config["probe_id"]), "target_id": str(config["target_id"]),
            "transport": "mailbox", "config_digest": "0" * 64,
            "address": f"0x{int(config['address']):08x}", "ring_size": str(config["size"]),
            "ram_bounds": "0x20000000+0x00010000",
        }
        identity["config_digest"] = target_module._task8_identity_digest("mailbox", config, identity)
        return identity


class _ResumeGatedTransport(FakeTransport):
    """A Target transport that may open only after the physical target is running."""

    def __init__(self, probe: FakeProbeClient, chunks: list[bytes]) -> None:
        super().__init__(chunks)
        self._probe = probe

    def open(self, config, deadline):
        if self._probe.state != {"state": "running", "reason": "requested"}:
            raise AssertionError("physical Target transport opened while the core was halted")
        return super().open(config, deadline)


class _StartingPhysicalFlashAdapter(target_module.PhysicalTargetFlashAdapter):
    """Small runner seam that records the required post-flash transition."""

    def __init__(self, probe: FakeProbeClient) -> None:
        # Keep the test seam independent of the implementation constructor so RED
        # proves the runner is missing the transition, rather than its test setup.
        self.probe = probe
        self.events: list[tuple[object, ...]] = []

    async def run(self, binding) -> None:
        self.events.append(("flash",))

    async def start_after_flash(self, binding, deadline) -> None:
        self.events.append(("reset", dict(binding)))
        self.probe.state = {"state": "running", "reason": "requested"}


def test_target_run_preflights_project_v3_config_and_exact_authorized_cases_before_flash(
    tmp_path: Path,
) -> None:
  async def scenario() -> None:
    flash = FakeFlashWorkflow()
    runner = target_module.TargetTestRunner(
        (tmp_path / "invalid-config").absolute(), FakeProbeClient(), flash,
        lambda name: FakeTransport([]),
    )
    common = dict(
        workspace_id="workspace-a", project_id="project-a", session_id="session-a",
        revision="rev-a", target=IDENTITY, probe_serial_hash=PROBE_HASH,
        elf_path="build/app.elf", elf_sha256="e" * 64, build_id="b" * 64,
        inventory_digest="a" * 64, transport="mailbox", support_profile=TARGET_SUPPORT,
        cases=("suite.case",),
        timeout_ms=1000, now=datetime(2026, 8, 16, tzinfo=timezone.utc),
    )
    with pytest.raises(target_module.TargetRunError) as invalid:
      await runner.prepare(transport_config={"address": 0x20000000}, **common)
    assert invalid.value.code == "TEST_PROTOCOL_INVALID"
    assert flash.calls == []

    unsupported_runner = target_module.TargetTestRunner(
        (tmp_path / "unsupported").absolute(), FakeProbeClient(), flash,
        lambda name: object(),
    )
    unsupported = await unsupported_runner.prepare(
        transport_config=MAILBOX_PROJECT_CONFIG, **common,
    )
    with pytest.raises(target_module.TargetRunError) as support_error:
      await unsupported_runner.run(
          unsupported, unsupported.action_digest, current_revision="rev-a",
          current_inventory_digest="a" * 64,
          now=datetime(2026, 8, 16, tzinfo=timezone.utc),
      )
    assert support_error.value.code == "TEST_TRANSPORT_UNAVAILABLE"
    assert flash.calls == []

    transport = FakeTransport([valid_target_stream("other.case"), b""])
    exact_runner = target_module.TargetTestRunner(
        (tmp_path / "wrong-case").absolute(), FakeProbeClient(), flash,
        lambda name: transport,
    )
    wrong_case_inventory_digest = _target_inventory_digest("other.case")
    prepared = await exact_runner.prepare(
        transport_config={"kind": "memory-mailbox", "options": {"address": 0x20000000, "size": 4096}},
        **{**common, "inventory_digest": wrong_case_inventory_digest},
    )
    with pytest.raises(target_module.TargetRunError) as mismatch:
      await exact_runner.run(
          prepared, prepared.action_digest, current_revision="rev-a",
          current_inventory_digest=wrong_case_inventory_digest,
          now=datetime(2026, 8, 16, tzinfo=timezone.utc),
      )
    assert mismatch.value.code == "TEST_IDENTITY_MISMATCH"
    assert len(flash.calls) == 1

  run(scenario())


def test_target_runner_prepare_is_single_use_and_closes_stale_identity(tmp_path: Path):
  async def scenario():
    probe = FakeProbeClient()
    flash = FakeFlashWorkflow()
    transport = FakeTransport([])
    runner = getattr(target_module, "TargetTestRunner")(tmp_path / "runs", probe, flash, lambda name: transport)
    prepared = await runner.prepare(
        workspace_id="workspace-a", project_id="project-a", session_id="session-a",
        revision="rev-a", target=IDENTITY, probe_serial_hash=PROBE_HASH,
        elf_path="build/app.elf", elf_sha256="e" * 64, build_id="b" * 64,
        inventory_digest="a" * 64, transport="mailbox", transport_config=MAILBOX_PROJECT_CONFIG,
        support_profile=TARGET_SUPPORT,
        cases=("suite.case",), timeout_ms=1_000,
        now=datetime(2026, 8, 16, tzinfo=timezone.utc),
    )
    assert len(prepared.nonce) == 64
    probe.identity["target_id"] = "different"
    with pytest.raises(getattr(target_module, "TargetRunError")) as mismatch:
        await runner.run(prepared, prepared.action_digest, current_revision="rev-a", current_inventory_digest="a" * 64, now=datetime(2026, 8, 16, tzinfo=timezone.utc))
    assert mismatch.value.code == "TEST_IDENTITY_MISMATCH"
    assert probe.closed
    assert not flash.calls

    with pytest.raises(getattr(target_module, "TargetRunError")) as reused:
        await runner.run(prepared, prepared.action_digest, current_revision="rev-a", current_inventory_digest="a" * 64, now=datetime(2026, 8, 16, tzinfo=timezone.utc))
    assert reused.value.code == "TEST_AUTHORIZATION_INVALID"
  run(scenario())


def test_discovery_is_read_only_and_never_consumes_modify_authorization(tmp_path: Path):
  async def scenario():
    probe = FakeProbeClient()
    flash = FakeFlashWorkflow()
    transport = FakeTransport([_r5_inventory_frame()])
    root = (tmp_path / "runs").absolute()
    runner = getattr(target_module, "TargetTestRunner")(root, probe, flash, lambda name: transport)
    instant = datetime(2026, 8, 16, tzinfo=timezone.utc)
    prepared = await runner.prepare(
        workspace_id=WORKSPACE_ID, project_id=PROJECT_ID, session_id=SESSION_ID,
        revision=REVISION, target=IDENTITY, probe_serial_hash=PROBE_HASH,
        elf_path="build/app.elf", elf_sha256="e" * 64, build_id="b" * 64,
        inventory_digest="a" * 64, transport="mailbox",
        transport_config=MAILBOX_PROJECT_CONFIG, support_profile=TARGET_SUPPORT,
        cases=("suite.case",), timeout_ms=1000, now=instant,
    )
    deadline = time.monotonic() + 1.0
    discovered = await _r5_discover(runner, deadline=deadline)
    assert discovered["identity"]["target_id"] == "target-a"
    assert discovered["inventory"]["inventory_digest"] == R5_INVENTORY_DIGEST
    assert discovered["inventory"]["identity"]["build_id"] == "b" * 64
    assert discovered["raw"] == _r5_inventory_frame()
    assert transport.calls[0] == ("open", {
        "address": 0x20000000, "size": 4096, "ram": TARGET_SUPPORT["ram"],
        "target_id": "target-a", "probe_id": PROBE_HASH,
    }, deadline)
    assert [call[0] for call in transport.calls] == ["open", "read", "read", "close"]
    assert transport.calls[1] == ("read", 65_536, deadline)
    assert 0 < transport.calls[2][1] < 65_536
    assert transport.calls[2][2] == deadline
    assert not flash.calls
    assert not (root / "records" / f"{prepared.action_digest}.consumed.json").exists()
  run(scenario())


def test_discovery_async_transport_composition_rejects_identity_and_nonbytes(tmp_path: Path):
  class AsyncTransport(FakeTransport):
    def __init__(self, raw=None, identity_mutation=None):
      super().__init__([_r5_inventory_frame() if raw is None else raw])
      self.identity_mutation = identity_mutation
    async def open(self, config, deadline):
      self.config = dict(config)
      self.calls.append(("open", dict(config), deadline))
    async def read_async(self, maximum, deadline): return self.read(maximum, deadline)
    async def close_async(self): self.calls.append(("close",))
    def identity(self):
      value = super().identity()
      if self.identity_mutation is not None:
        value.update(self.identity_mutation)
      return value

  async def scenario():
    active = AsyncTransport()
    runner = target_module.TargetTestRunner(
        (tmp_path / "success").absolute(), FakeProbeClient(), FakeFlashWorkflow(), lambda name: active,
    )
    assert (await _r5_discover(runner))["raw"] == _r5_inventory_frame()
    assert active.calls[0][0] == "open"
    assert active.calls[1][0] == "read"
    assert active.calls[-1] == ("close",)

    for index, probe_identity, raw, identity_mutation in (
        (0, {**IDENTITY, "target_id": "other"}, _r5_inventory_frame(), None),
        (1, IDENTITY, "not-bytes", None),
        (2, IDENTITY, _r5_inventory_frame(), {"target_id": "other"}),
    ):
      probe = FakeProbeClient()
      probe.identity = probe_identity
      invalid = AsyncTransport(raw, identity_mutation)
      candidate = target_module.TargetTestRunner(
          (tmp_path / f"invalid-{index}").absolute(), probe, FakeFlashWorkflow(), lambda name, item=invalid: item,
      )
      with pytest.raises(target_module.TargetRunError) as caught:
        await _r5_discover(candidate)
      assert caught.value.code == "TEST_TRANSPORT_UNAVAILABLE"
      assert invalid.calls[-1] == ("close",)
  run(scenario())


def test_target_runner_success_persists_three_manifests_and_guarded_flash(tmp_path: Path):
  async def scenario():
    from stm32_toolkit.evidence import EvidenceEnvelope
    from stm32_toolkit.evidence.store import EvidenceStore
    from stm32_toolkit.hardware_workflows import FlashWorkflowRequest
    from stm32_toolkit.result import OperationResult
    from stm32_toolkit.testing.artifacts import TestArtifactCollector
    from stm32_toolkit.testing.model import TestRunManifest

    probe = FakeProbeClient()
    workflow_calls = []
    async def workflow(request):
      assert isinstance(request, FlashWorkflowRequest)
      workflow_calls.append(request)
      return OperationResult.success("stm32_flash", {"status": "success"})
    project_root = tmp_path / "project"
    project_root.mkdir()
    evidence_store = EvidenceStore((tmp_path / "evidence").absolute())
    collector = TestArtifactCollector(
        (tmp_path / "results").absolute(), evidence_store, project_root=project_root,
    )
    flash = target_module.GuardedTargetFlashAdapter(
        project_root=project_root, data_root=(tmp_path / "data").absolute(),
        session_id=SESSION_ID, probe_id="probe-a", workflow=workflow,
    )
    class AsyncRunTransport(FakeTransport):
      async def open(self, config, deadline): self.calls.append(("open", config, deadline))
      async def read_async(self, maximum, deadline): return self.read(maximum, deadline)
      async def close_async(self): self.close()

    transport = AsyncRunTransport([valid_target_stream(), b""])
    runner = target_module.TargetTestRunner(
        (tmp_path / "runs").absolute(), probe, flash, lambda name: transport,
        artifact_collector=collector,
    )
    instant = datetime.now(timezone.utc)
    prepared = await runner.prepare(
        workspace_id=WORKSPACE_ID, project_id=PROJECT_ID, session_id=SESSION_ID, revision=REVISION,
        target=IDENTITY, probe_serial_hash=PROBE_HASH, elf_path="build/app.elf", elf_sha256="e" * 64,
        build_id="b" * 64, inventory_digest=TARGET_RUN_INVENTORY_DIGEST, transport="mailbox",
        transport_config=MAILBOX_PROJECT_CONFIG, support_profile=TARGET_SUPPORT,
        cases=("suite.case",), timeout_ms=1000, now=instant,
    )
    before_deadline = time.monotonic()
    result = await runner.run(
        prepared, prepared.action_digest, current_revision=REVISION,
        current_inventory_digest=TARGET_RUN_INVENTORY_DIGEST, now=instant,
    )
    assert isinstance(result["test_manifest"], TestRunManifest)
    assert result["test_manifest"].schema == "stm32-test/1"
    assert result["test_manifest"].state == "passed"
    assert [case.case_id for case in result["test_manifest"].cases] == ["suite.case"]
    assert isinstance(result["evidence"], EvidenceEnvelope)
    assert evidence_store.get_envelope(str(result["evidence"].evidence_id)) == result["evidence"]
    assert {artifact.kind for artifact in result["evidence"].artifacts} == {"test-events", "test-manifest"}
    assert len(workflow_calls) == 1
    assert workflow_calls[0].probe_id == PROBE_SELECTOR
    assert sha256(workflow_calls[0].probe_id.encode("utf-8")).hexdigest() == PROBE_HASH
    metadata = result["evidence"].metadata
    assert metadata["action_digest"] == prepared.action_digest
    assert metadata["probe_serial_hash"] == PROBE_HASH
    assert metadata["transport_config_digest"] == transport.identity()["config_digest"]
    manifest_artifact = next(
        artifact for artifact in result["evidence"].artifacts
        if artifact.kind == "test-manifest"
    )
    assert metadata["test_manifest_sha256"] == manifest_artifact.sha256
    assert transport.calls[0][2] > before_deadline
    assert transport.calls[-1] == ("close",)
    assert probe.closed
  run(scenario())


def test_physical_target_runner_starts_from_reset_after_postflash_identity_before_transport(
    tmp_path: Path,
) -> None:
  async def scenario() -> None:
    from stm32_toolkit.evidence.store import EvidenceStore
    from stm32_toolkit.testing.artifacts import TestArtifactCollector

    probe = FakeProbeClient()
    probe.endpoint = SimpleNamespace(lease_id="lease")
    flash = _StartingPhysicalFlashAdapter(probe)
    transport = _ResumeGatedTransport(probe, [valid_target_stream(), b""])
    evidence_store = EvidenceStore((tmp_path / "evidence").absolute())
    project_root = (tmp_path / "project").absolute()
    project_root.mkdir(parents=True)
    collector = TestArtifactCollector(
        (tmp_path / "results").absolute(), evidence_store,
        project_root=project_root,
    )
    runner = target_module.TargetTestRunner(
        (tmp_path / "runs").absolute(), probe, flash, lambda _name: transport,
        artifact_collector=collector,
    )
    instant = datetime.now(timezone.utc)
    prepared = await runner.prepare(
        workspace_id=WORKSPACE_ID, project_id=PROJECT_ID, session_id=SESSION_ID,
        revision=REVISION, target=IDENTITY, probe_serial_hash=PROBE_HASH,
        elf_path="build/app.elf", elf_sha256="e" * 64, build_id="b" * 64,
        inventory_digest=TARGET_RUN_INVENTORY_DIGEST, transport="mailbox",
        transport_config=MAILBOX_PROJECT_CONFIG, support_profile=TARGET_SUPPORT,
        cases=("suite.case",), timeout_ms=1000, now=instant,
    )
    result = await runner.run(
        None, prepared.action_digest, current_revision=REVISION,
        current_inventory_digest=TARGET_RUN_INVENTORY_DIGEST, now=instant,
        consumed=target_module.ConsumedTargetRun(
            prepared.action_digest,
            prepared.binding,
            target_module.PhysicalRunProvenance(
                WORKSPACE_ID, SESSION_ID, PROBE_HASH, SESSION_ID, "lease"
            ),
        ),
    )

    assert result["test_manifest"].state == "passed"
    assert [event[0] for event in flash.events] == ["flash", "reset"]
    assert transport.calls[0][0] == "open"
    assert probe.state == {"state": "running", "reason": "requested"}

  run(scenario())


@pytest.mark.parametrize("mutation", ["revision", "inventory", "digest", "expired"])
def test_target_runner_consumes_before_stale_or_denied_run(tmp_path: Path, mutation: str):
  async def scenario():
    probe = FakeProbeClient()
    flash = FakeFlashWorkflow()
    transport = FakeTransport([])
    runner = target_module.TargetTestRunner(tmp_path / mutation, probe, flash, lambda name: transport)
    instant = datetime(2026, 8, 16, tzinfo=timezone.utc)
    prepared = await runner.prepare(
        workspace_id="workspace-a", project_id="project-a", session_id="session-a", revision="rev-a",
        target=IDENTITY, probe_serial_hash=PROBE_HASH, elf_path="build/app.elf", elf_sha256="e" * 64,
        build_id="b" * 64, inventory_digest="a" * 64, transport="mailbox",
        transport_config=MAILBOX_PROJECT_CONFIG, support_profile=TARGET_SUPPORT,
        cases=("suite.case",), timeout_ms=1000, now=instant,
    )
    with pytest.raises(target_module.TargetRunError) as caught:
      await runner.run(
          prepared, "0" * 64 if mutation == "digest" else prepared.action_digest,
          current_revision="changed" if mutation == "revision" else "rev-a",
          current_inventory_digest="f" * 64 if mutation == "inventory" else "a" * 64,
          now=instant + timedelta(minutes=6) if mutation == "expired" else instant,
      )
    assert caught.value.code in {"TEST_AUTHORIZATION_INVALID", "TEST_INVENTORY_CHANGED"}
    assert not flash.calls
    assert probe.closed
  run(scenario())


def test_target_runner_prepare_rejects_nonclosed_and_bad_limits(tmp_path: Path):
  async def scenario():
    runner = target_module.TargetTestRunner(tmp_path, FakeProbeClient(), FakeFlashWorkflow(), lambda name: FakeTransport([]))
    with pytest.raises(target_module.TargetRunError):
      await runner.prepare(now=datetime.now(timezone.utc), extra=True)
    common = dict(
        workspace_id="w", project_id="p", session_id="s", revision="r", target=IDENTITY,
        probe_serial_hash=PROBE_HASH, elf_path="a.elf", elf_sha256="e" * 64, build_id="b" * 64,
        inventory_digest="a" * 64, transport="mailbox", transport_config=MAILBOX_PROJECT_CONFIG,
        support_profile=TARGET_SUPPORT, cases=("c",), timeout_ms=True,
    )
    with pytest.raises(target_module.TargetRunError):
      await runner.prepare(now=datetime.now(timezone.utc), **common)
    common["timeout_ms"] = 1
    common["build_id"] = "not-a-digest"
    with pytest.raises(target_module.TargetRunError):
      await runner.prepare(now=datetime.now(timezone.utc), **common)
    common["build_id"] = "b" * 64
    with pytest.raises(target_module.TargetRunError):
      await runner.prepare(now=datetime(2026, 8, 16), **common)
  run(scenario())


def test_target_authorization_record_exact_size_bound_round_trips_without_side_effect_overflow(
    tmp_path: Path,
) -> None:
  async def scenario():
    limit = 64 * 1024
    instant = datetime(2026, 8, 16, tzinfo=timezone.utc)
    common = dict(
        workspace_id="w", project_id="p", session_id="s", revision="r", target=IDENTITY,
        probe_serial_hash=PROBE_HASH, elf_path="", elf_sha256="e" * 64,
        build_id="b" * 64, inventory_digest="a" * 64, transport="mailbox",
        transport_config=MAILBOX_PROJECT_CONFIG, support_profile=TARGET_SUPPORT,
        cases=("suite.case",), timeout_ms=1_000,
    )
    template = {
        **common,
        "cases": ["suite.case"],
        "nonce": "0" * 64,
        "prepared_at_utc": "2026-08-16T00:00:00.000000Z",
        "expires_at_utc": "2026-08-16T00:05:00.000000Z",
    }
    exact_path = "a" * (limit - len(canonical_json_bytes(template)))
    exact_root = (tmp_path / "exact-authorizations").absolute()
    runner = target_module.TargetTestRunner(
        exact_root, FakeProbeClient(), FakeFlashWorkflow(), lambda name: FakeTransport([])
    )
    prepared = await runner.prepare(now=instant, **{**common, "elf_path": exact_path})
    record_path = exact_root / "records" / f"{prepared.action_digest}.prepared.json"
    assert record_path.stat().st_size == limit

    restarted = target_module.TargetTestRunner(
        exact_root, FakeProbeClient(), FakeFlashWorkflow(), lambda name: FakeTransport([])
    )
    assert restarted.load_prepared(prepared.action_digest).binding["elf_path"] == exact_path
    assert restarted.consume_prepared(prepared.action_digest, now=instant).binding["elf_path"] == exact_path

    overflow_root = (tmp_path / "overflow-authorizations").absolute()
    overflow = target_module.TargetTestRunner(
        overflow_root, FakeProbeClient(), FakeFlashWorkflow(), lambda name: FakeTransport([])
    )
    with pytest.raises(target_module.TargetRunError) as error:
      await overflow.prepare(
          now=instant, **{**common, "elf_path": exact_path + "a"}
      )
    assert error.value.code == "TEST_PROTOCOL_INVALID"
    assert not overflow_root.exists()
  run(scenario())


def test_probe_client_target_transport_latches_only_explicit_service_eof() -> None:
  async def scenario():
    class Client:
      def __init__(self):
        self.reads = [(b"", False), (b"terminal", True)]

      async def target_transport_open(self, transport, config, remaining):
        return {"transport_id": "live-1", "identity": {"transport": transport}}

      async def target_transport_read(self, transport_id, maximum, remaining):
        return self.reads.pop(0)

      async def target_transport_close(self, transport_id):
        return None

    transport = target_module.ProbeClientTargetTransport(
        Client(), MAILBOX_PROJECT_CONFIG, "mailbox"
    )
    deadline = time.monotonic() + 1
    await transport.open(MAILBOX_PROJECT_CONFIG, deadline)
    assert await transport.read_async(1024, deadline) == b""
    assert transport.eof() is False
    assert await transport.read_async(1024, deadline) == b"terminal"
    assert transport.eof() is True
  run(scenario())


def test_target_prepared_record_closed_validation_rejects_each_identity_and_limit_boundary():
  valid = {
      "workspace_id": "w", "project_id": "p", "session_id": "s", "revision": "r",
      "target": IDENTITY, "probe_serial_hash": PROBE_HASH, "elf_path": "a.elf",
      "elf_sha256": "e" * 64, "build_id": "b" * 64, "inventory_digest": "a" * 64,
      "transport": "mailbox", "transport_config": MAILBOX_PROJECT_CONFIG,
      "support_profile": TARGET_SUPPORT, "cases": ["suite.case"],
      "timeout_ms": 1, "nonce": "2" * 64,
      "prepared_at_utc": "2026-08-16T00:00:00.000000Z",
      "expires_at_utc": "2026-08-16T00:05:00.000000Z",
  }
  target_module.TargetTestRunner._validate_prepared_record(valid)
  invalid = [
      {key: value for key, value in valid.items() if key != "revision"},
      {**valid, "workspace_id": ""},
      {**valid, "nonce": "bad"},
      {**valid, "target": []},
      {**valid, "target": {**IDENTITY, "probe_serial_hash": "3" * 64}},
      {**valid, "transport": "swo"},
      {**valid, "transport_config": []},
      {**valid, "cases": []},
      {**valid, "cases": ["suite.case", "suite.case"]},
      {**valid, "timeout_ms": True},
      {**valid, "prepared_at_utc": "not-time"},
      {**valid, "expires_at_utc": "2026-08-15T23:59:59.000000Z"},
      {**valid, "expires_at_utc": "2026-08-16T00:05:00.000001Z"},
  ]
  for record in invalid:
    with pytest.raises(ValueError):
      target_module.TargetTestRunner._validate_prepared_record(record)


@pytest.mark.parametrize("recovery_under_reset", [False, True])
def test_target_runner_prepared_binding_accepts_recovery_boolean_and_legacy_shape(
    tmp_path: Path, recovery_under_reset: bool,
) -> None:
  async def scenario() -> None:
    runner = target_module.TargetTestRunner(
        tmp_path / "runs", FakeProbeClient(), FakeFlashWorkflow(),
        lambda _name: FakeTransport([]),
    )
    common = {
        "workspace_id": "workspace-a", "project_id": "project-a", "session_id": "session-a",
        "revision": "rev-a", "target": IDENTITY, "probe_serial_hash": PROBE_HASH,
        "elf_path": "build/app.elf", "elf_sha256": "e" * 64, "build_id": "b" * 64,
        "inventory_digest": "a" * 64, "transport": "mailbox",
        "transport_config": MAILBOX_PROJECT_CONFIG, "support_profile": TARGET_SUPPORT,
        "cases": ("suite.case",), "timeout_ms": 1000,
        "now": datetime(2026, 8, 16, tzinfo=timezone.utc),
    }
    prepared = await runner.prepare(
        **common, recovery_under_reset=recovery_under_reset,
    )
    loaded = runner.load_prepared(prepared.action_digest)
    assert loaded.binding["recovery_under_reset"] is recovery_under_reset

    legacy = await runner.prepare(**common)
    assert "recovery_under_reset" not in runner.load_prepared(legacy.action_digest).binding

  run(scenario())


@pytest.mark.parametrize("recovery_under_reset", [None, 0, 1, "true", []])
def test_target_runner_rejects_non_boolean_recovery_at_prepare_and_load(
    tmp_path: Path, recovery_under_reset: object,
) -> None:
  async def scenario() -> None:
    runner = target_module.TargetTestRunner(
        tmp_path / "runs", FakeProbeClient(), FakeFlashWorkflow(),
        lambda _name: FakeTransport([]),
    )
    common = {
        "workspace_id": "workspace-a", "project_id": "project-a", "session_id": "session-a",
        "revision": "rev-a", "target": IDENTITY, "probe_serial_hash": PROBE_HASH,
        "elf_path": "build/app.elf", "elf_sha256": "e" * 64, "build_id": "b" * 64,
        "inventory_digest": "a" * 64, "transport": "mailbox",
        "transport_config": MAILBOX_PROJECT_CONFIG, "support_profile": TARGET_SUPPORT,
        "cases": ("suite.case",), "timeout_ms": 1000,
        "now": datetime(2026, 8, 16, tzinfo=timezone.utc),
    }
    with pytest.raises(target_module.TargetRunError) as invalid_prepare:
      await runner.prepare(**common, recovery_under_reset=recovery_under_reset)
    assert invalid_prepare.value.code == "TEST_PROTOCOL_INVALID"

    prepared = await runner.prepare(**common)
    invalid_record = dict(prepared.binding, recovery_under_reset=recovery_under_reset)
    payload = canonical_json_bytes(invalid_record)
    digest = sha256(payload).hexdigest()
    runner._authorization_authority._path(digest, "prepared").write_bytes(payload)
    with pytest.raises(target_module.TargetRunError) as invalid_load:
      runner.load_prepared(digest)
    assert invalid_load.value.code == "TEST_AUTHORIZATION_INVALID"

  run(scenario())


@pytest.mark.parametrize("transport,config", [
    ("bad", MAILBOX_PROJECT_CONFIG),
    ("mailbox", []),
    ("mailbox", {"kind": "rtt", "options": {"channel": 0}}),
    ("mailbox", {"kind": "memory-mailbox", "options": []}),
    ("mailbox", {"kind": "memory-mailbox", "options": {"address": True, "size": 1}}),
    ("mailbox", {"kind": "memory-mailbox", "options": {"address": 0, "size": 0}}),
    ("mailbox", {"kind": "memory-mailbox", "options": {"address": 0xFFFF_FFFF, "size": 2}}),
    ("rtt", {"kind": "rtt", "options": {}}),
    ("rtt", {"kind": "rtt", "options": {"channel": True}}),
    ("rtt", {"kind": "rtt", "options": {"channel": 16}}),
    ("rtt", {"kind": "rtt", "options": {"channel": 0, "controlBlockAddress": True}}),
    ("uart", {"kind": "uart", "options": {"port": "COM1"}}),
    ("uart", {"kind": "uart", "options": {"port": 1, "baud": 115200}}),
    ("uart", {"kind": "uart", "options": {"port": "bad\n", "baud": 115200}}),
    ("uart", {"kind": "uart", "options": {"port": "COM1", "baud": True}}),
    ("uart", {"kind": "uart", "options": {"port": "COM1", "baud": 1}}),
    ("semihosting", {"kind": "semihosting", "options": {"host": True}}),
])
def test_project_v3_target_transport_union_rejects_every_closed_boundary(transport, config):
  with pytest.raises(ValueError):
    target_module._closed_project_transport_config(transport, config)


def test_project_v3_target_transport_union_accepts_all_four_exact_variants():
  for transport, config in (
      ("mailbox", MAILBOX_PROJECT_CONFIG),
      ("rtt", {"kind": "rtt", "options": {"channel": 0, "controlBlockAddress": 0x20000000}}),
      ("uart", {"kind": "uart", "options": {"port": "COM1", "baud": 115200}}),
      ("semihosting", {"kind": "semihosting", "options": {}}),
  ):
    assert target_module._closed_project_transport_config(transport, config) == config


def test_control_authorization_rejects_naive_invalid_and_changed_snapshot(tmp_path: Path):
  async def scenario():
    probe = FakeProbeClient()
    auth = probe_client.ControlAuthorizationClient(
        ControlAuthorizationStore((tmp_path / "control").absolute()), probe
    )
    common = dict(
        workspace_id="w", project_id="p", session_id="s", revision="r", target=IDENTITY,
        firmware={"build_id": "b" * 64, "elf_sha256": "e" * 64}, operation="target.resume", arguments={},
    )
    with pytest.raises(ProbeClientError) as naive:
      await auth.prepare(**common, now=datetime(2026, 8, 16))
    assert naive.value.code == "PROBE_PROTOCOL_INVALID"
    with pytest.raises(ProbeClientError) as invalid:
      await auth.prepare(
          **{
              **common,
              "operation": "target.reset",
              "arguments": {"unexpected": True},
          },
          now=datetime(2026, 8, 16, tzinfo=timezone.utc),
      )
    assert invalid.value.code == "PROBE_PROTOCOL_INVALID"
  run(scenario())


def test_persistent_control_store_rejects_unknown_and_consumes_binding_before_denial(
    tmp_path: Path,
) -> None:
  try:
    from stm32_toolkit.probe.authorization import (
        ControlAuthorizationError,
        ControlAuthorizationStore,
    )
  except ModuleNotFoundError:
    pytest.fail("persistent control authorization store is missing")

  instant = datetime(2026, 8, 16, tzinfo=timezone.utc)
  root = (tmp_path / "control-authorizations").absolute()
  store = ControlAuthorizationStore(root)
  binding = {
      "workspace_id": "workspace-a",
      "project_id": "project-a",
      "session_id": "session-a",
      "revision": "rev-a",
      "target": IDENTITY,
      "firmware": {"build_id": "b" * 64, "elf_sha256": "e" * 64},
      "operation": "target.resume",
      "arguments": {},
      "identity_snapshot": IDENTITY,
      "state_snapshot": STATE,
  }
  prepared = store.prepare(binding, now=instant)
  with pytest.raises(ControlAuthorizationError) as mismatch:
    store.consume(
        prepared.action_digest,
        operation="target.halt",
        arguments={},
        workspace_id="workspace-a",
        session_id="session-a",
        identity=IDENTITY,
        state=STATE,
        now=instant,
    )
  assert mismatch.value.code == "PROBE_AUTHORIZATION_INVALID"

  restarted = ControlAuthorizationStore(root)
  with pytest.raises(ControlAuthorizationError) as replay:
    restarted.consume(
        prepared.action_digest,
        operation="target.resume",
        arguments={},
        workspace_id="workspace-a",
        session_id="session-a",
        identity=IDENTITY,
        state=STATE,
        now=instant,
    )
  assert replay.value.code == "PROBE_AUTHORIZATION_INVALID"
  with pytest.raises(ControlAuthorizationError) as unknown:
    restarted.consume(
        "0" * 64,
        operation="target.resume",
        arguments={},
        workspace_id="workspace-a",
        session_id="session-a",
        identity=IDENTITY,
        state=STATE,
        now=instant,
    )
  assert unknown.value.code == "PROBE_AUTHORIZATION_INVALID"


def test_control_authorization_store_rejects_every_closed_binding_and_record_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
  from stm32_toolkit.evidence import canonical_json_bytes
  from stm32_toolkit.probe import authorization as authorization_module
  from stm32_toolkit.probe.authorization import ControlAuthorizationError, ControlAuthorizationStore

  instant = datetime(2026, 8, 16, tzinfo=timezone.utc)
  base = {
      "workspace_id": "workspace-a", "project_id": "project-a",
      "session_id": "session-a", "revision": "rev-a", "target": IDENTITY,
      "firmware": {"build_id": "b" * 64, "elf_sha256": "e" * 64},
      "operation": "target.resume", "arguments": {},
      "identity_snapshot": IDENTITY, "state_snapshot": STATE,
  }
  invalid = [
      {key: value for key, value in base.items() if key != "revision"},
      {**base, "operation": "target.reset", "arguments": {"unexpected": True}},
      {**base, "arguments": []},
      {**base, "workspace_id": ""},
      {**base, "target": []},
      {**base, "target": {**IDENTITY, "extra": "bad"}},
      {**base, "firmware": {"build_id": "bad", "elf_sha256": "e" * 64}},
      {**base, "state_snapshot": {"state": "sleeping", "reason": "requested"}},
      {**base, "operation": "target.halt", "arguments": {"count": 1}},
      {**base, "operation": "target.breakpoint.set", "arguments": {"address": True, "kind": "temporary", "size": 2}},
      {**base, "operation": "target.breakpoint.clear", "arguments": {"breakpoint_id": "bad value"}},
      {**base, "arguments": {"bad": {1, 2}}},
  ]
  store = ControlAuthorizationStore((tmp_path / "closed").absolute())
  for binding in invalid:
    with pytest.raises(ControlAuthorizationError) as caught:
      store.prepare(binding, now=instant)
    assert caught.value.code == "PROBE_PROTOCOL_INVALID"
  with pytest.raises(ControlAuthorizationError):
    store.prepare(base, now=datetime(2026, 8, 16))
  with pytest.raises(TypeError):
    ControlAuthorizationStore(Path("relative"))
  with pytest.raises(TypeError):
    ControlAuthorizationStore((tmp_path / "bad-clock").absolute(), monotonic_clock=object())
  with pytest.raises(ControlAuthorizationError):
    store._path("bad", "prepared")
  with pytest.raises(ControlAuthorizationError):
    authorization_module._parse_utc("not-utc")
  with pytest.raises(ControlAuthorizationError):
    authorization_module._parse_utc("not-timeZ")

  monkeypatch.setattr("secrets.token_hex", lambda size: "a" * 64)
  prepared = store.prepare(base, now=instant)
  with pytest.raises(ControlAuthorizationError) as duplicate:
    store.prepare(base, now=instant)
  assert duplicate.value.code == "PROBE_AUTHORIZATION_INVALID"
  assert prepared.nonce == "a" * 64

  accepted_store = ControlAuthorizationStore((tmp_path / "accepted").absolute())
  accepted = accepted_store.prepare(base, now=instant)
  assert accepted_store.consume(
      accepted.action_digest, operation="target.resume", arguments={},
      workspace_id="workspace-a", session_id="session-a", identity=None, state=None,
      now=instant,
  )["nonce"] == accepted.nonce

  mismatches = [
      {"now": instant - timedelta(microseconds=1)},
      {"now": instant + timedelta(minutes=5, microseconds=1)},
      {"arguments": {"unexpected": True}},
      {"workspace_id": "workspace-b"},
      {"session_id": "session-b"},
      {"identity": {**IDENTITY, "target_id": "target-b"}},
      {"state": {"state": "running", "reason": "requested"}},
  ]
  for index, replacement in enumerate(mismatches):
    mismatch_store = ControlAuthorizationStore((tmp_path / f"mismatch-{index}").absolute())
    mismatch_prepared = mismatch_store.prepare(base, now=instant)
    arguments = {
        "operation": "target.resume", "arguments": {}, "workspace_id": "workspace-a",
        "session_id": "session-a", "identity": IDENTITY, "state": STATE, "now": instant,
        **replacement,
    }
    with pytest.raises(ControlAuthorizationError) as mismatch:
      mismatch_store.consume(mismatch_prepared.action_digest, **arguments)
    assert mismatch.value.code == "PROBE_AUTHORIZATION_INVALID"

  template = dict(prepared.binding)
  corruptions = [
      b"x" * 65_537,
      b"not-json",
      canonical_json_bytes({"unexpected": True}),
      canonical_json_bytes({**template, "nonce": "bad"}),
      canonical_json_bytes({**template, "prepared_at_utc": "not-utc"}),
      b'{"arguments": {}, "arguments": {}}',
  ]
  for index, raw in enumerate(corruptions):
    corrupt_store = ControlAuthorizationStore((tmp_path / f"corrupt-{index}").absolute())
    corrupt_store.prepare(base, now=instant)
    digest = sha256(raw).hexdigest()
    corrupt_store._path(digest, "prepared").write_bytes(raw)
    with pytest.raises(ControlAuthorizationError) as corrupt:
      corrupt_store.consume(
          digest, operation="target.resume", arguments={}, workspace_id="workspace-a",
          session_id="session-a", identity=IDENTITY, state=STATE, now=instant,
      )
    assert corrupt.value.code == "PROBE_AUTHORIZATION_INVALID"

  for index, raw in enumerate((b"x" * 4097, canonical_json_bytes({"unexpected": True}))):
    authority_store = ControlAuthorizationStore((tmp_path / f"authority-corrupt-{index}" / "control").absolute())
    authority_store.prepare(base, now=instant)
    authority_path = authority_store._authority_path()
    authority_path.write_bytes(raw)
    with pytest.raises(ControlAuthorizationError):
      authority_store._read_authority()

  shaped_store = ControlAuthorizationStore((tmp_path / "authority-corrupt-shape" / "control").absolute())
  shaped_store.prepare(base, now=instant)
  shaped_authority = dict(shaped_store._read_authority())
  shaped_authority["records"] = ["device", "inode"]
  shaped_store._authority_path().write_bytes(canonical_json_bytes(shaped_authority))
  with pytest.raises(ControlAuthorizationError):
    shaped_store._read_authority()

  changed_store = ControlAuthorizationStore((tmp_path / "authority-create-race" / "control").absolute())
  parent_store = changed_store._parent_store()
  with parent_store._mutation_lock():
    pass
  monkeypatch.setattr(
      changed_store, "_authorization_create_new", lambda *args, **kwargs: False
  )
  with pytest.raises(ControlAuthorizationError):
    changed_store.prepare(base, now=instant)


def test_control_authorization_store_pins_root_authority_across_copy_and_restart(tmp_path: Path) -> None:
  from stm32_toolkit.probe.authorization import ControlAuthorizationError, ControlAuthorizationStore

  instant = datetime(2026, 8, 16, tzinfo=timezone.utc)
  root = (tmp_path / "authority-parent" / "control").absolute()
  store = ControlAuthorizationStore(root)
  assert not root.exists()
  binding = {
      "workspace_id": "workspace-a", "project_id": "project-a",
      "session_id": "session-a", "revision": "rev-a", "target": IDENTITY,
      "firmware": {"build_id": "b" * 64, "elf_sha256": "e" * 64},
      "operation": "target.resume", "arguments": {},
      "identity_snapshot": IDENTITY, "state_snapshot": STATE,
  }
  prepared = store.prepare(binding, now=instant)
  backup = tmp_path / "original-control"
  shutil.move(root, backup)
  shutil.copytree(backup, root)

  for candidate in (store, ControlAuthorizationStore(root)):
    with pytest.raises(ControlAuthorizationError) as swapped:
      candidate.consume(
          prepared.action_digest, operation="target.resume", arguments={},
          workspace_id="workspace-a", session_id="session-a",
          identity=IDENTITY, state=STATE, now=instant,
      )
    assert swapped.value.code == "PROBE_AUTHORIZATION_INVALID"


def test_live_control_authorization_uses_monotonic_expiry_when_wall_clock_rolls_back(
    tmp_path: Path,
) -> None:
  from stm32_toolkit.probe.authorization import ControlAuthorizationError, ControlAuthorizationStore

  instant = datetime(2026, 8, 16, tzinfo=timezone.utc)
  ticks = [10.0]
  root = (tmp_path / "monotonic-control").absolute()
  store = ControlAuthorizationStore(root, monotonic_clock=lambda: ticks[0])
  binding = {
      "workspace_id": "workspace-a", "project_id": "project-a",
      "session_id": "session-a", "revision": "rev-a", "target": IDENTITY,
      "firmware": {"build_id": "b" * 64, "elf_sha256": "e" * 64},
      "operation": "target.resume", "arguments": {},
      "identity_snapshot": IDENTITY, "state_snapshot": STATE,
  }
  prepared = store.prepare(binding, now=instant)
  ticks[0] += 301.0
  with pytest.raises(ControlAuthorizationError) as expired:
    store.consume(
        prepared.action_digest, operation="target.resume", arguments={},
        workspace_id="workspace-a", session_id="session-a",
        identity=IDENTITY, state=STATE,
        now=instant,
    )
  assert expired.value.code == "PROBE_AUTHORIZATION_INVALID"
  consumed = root / "records" / f"{prepared.action_digest}.consumed.json"
  assert consumed.is_file()

  # A restarted process has no trusted monotonic origin and therefore applies
  # only the persistent UTC contract, while retaining persistent single-use.
  with pytest.raises(ControlAuthorizationError) as replay:
    ControlAuthorizationStore(root).consume(
        prepared.action_digest, operation="target.resume", arguments={},
        workspace_id="workspace-a", session_id="session-a",
        identity=IDENTITY, state=STATE, now=instant,
    )
  assert replay.value.code == "PROBE_AUTHORIZATION_INVALID"


def test_control_authorization_is_invalid_at_exact_utc_and_monotonic_expiry(
    tmp_path: Path,
) -> None:
  instant = datetime(2026, 8, 16, tzinfo=timezone.utc)
  clock = [10.0]
  store = ControlAuthorizationStore(
      (tmp_path / "control").absolute(), monotonic_clock=lambda: clock[0]
  )
  binding = {
      "workspace_id": "workspace-a", "project_id": "project-a",
      "session_id": "session-a", "revision": "rev-a", "target": IDENTITY,
      "firmware": {"build_id": "b" * 64, "elf_sha256": "e" * 64},
      "operation": "target.resume", "arguments": {},
      "identity_snapshot": IDENTITY, "state_snapshot": STATE,
  }
  utc = store.prepare(binding, now=instant)
  with pytest.raises(ControlAuthorizationError):
    store.consume(
        utc.action_digest, operation="target.resume", arguments={},
        workspace_id="workspace-a", session_id="session-a",
        identity=IDENTITY, state=STATE, now=utc.expires_at_utc,
    )

  monotonic = store.prepare(binding, now=instant)
  clock[0] = 310.0
  with pytest.raises(ControlAuthorizationError):
    store.consume(
        monotonic.action_digest, operation="target.resume", arguments={},
        workspace_id="workspace-a", session_id="session-a",
        identity=IDENTITY, state=STATE, now=instant,
    )


def test_target_run_is_consumed_and_denied_at_exact_expiry_before_flash(tmp_path: Path) -> None:
  async def scenario() -> None:
    flash = FakeFlashWorkflow()
    runner = target_module.TargetTestRunner(
        (tmp_path / "runs").absolute(), FakeProbeClient(), flash,
        lambda name: FakeTransport([valid_target_stream(), b""]),
    )
    instant = datetime(2026, 8, 16, tzinfo=timezone.utc)
    prepared = await runner.prepare(
        workspace_id="workspace-a", project_id="project-a", session_id="session-a",
        revision="rev-a", target=IDENTITY, probe_serial_hash=PROBE_HASH,
        elf_path="build/app.elf", elf_sha256="e" * 64, build_id="b" * 64,
        inventory_digest="a" * 64, transport="mailbox",
        transport_config=MAILBOX_PROJECT_CONFIG, support_profile=TARGET_SUPPORT,
        cases=("suite.case",), timeout_ms=1000,
        now=instant,
    )
    with pytest.raises(target_module.TargetRunError) as caught:
      await runner.run(
          prepared, prepared.action_digest, current_revision="rev-a",
          current_inventory_digest="a" * 64, now=prepared.expires_at_utc,
      )
    assert caught.value.code == "TEST_AUTHORIZATION_INVALID"
    assert flash.calls == []

  run(scenario())


def test_control_authority_rejects_hardlinked_ledger_and_copied_parent(tmp_path: Path) -> None:
  from stm32_toolkit.probe.authorization import ControlAuthorizationError, ControlAuthorizationStore

  instant = datetime(2026, 8, 16, tzinfo=timezone.utc)
  binding = {
      "workspace_id": "workspace-a", "project_id": "project-a",
      "session_id": "session-a", "revision": "rev-a", "target": IDENTITY,
      "firmware": {"build_id": "b" * 64, "elf_sha256": "e" * 64},
      "operation": "target.resume", "arguments": {},
      "identity_snapshot": IDENTITY, "state_snapshot": STATE,
  }
  hard_root = (tmp_path / "hard-parent" / "control").absolute()
  hard_store = ControlAuthorizationStore(hard_root)
  hard = hard_store.prepare(binding, now=instant)
  ledger = next(hard_root.parent.glob(".*.control-authority.json"))
  os.link(ledger, hard_root.parent / "authority-hardlink")
  with pytest.raises(ControlAuthorizationError):
    hard_store.consume(
        hard.action_digest, operation="target.resume", arguments={},
        workspace_id="workspace-a", session_id="session-a", identity=IDENTITY,
        state=STATE, now=instant,
    )

  parent = (tmp_path / "copied-parent").absolute()
  copied_root = parent / "control"
  copied_store = ControlAuthorizationStore(copied_root)
  copied = copied_store.prepare(binding, now=instant)
  backup = tmp_path / "copied-parent-original"
  shutil.move(parent, backup)
  shutil.copytree(backup, parent)
  for candidate in (copied_store, ControlAuthorizationStore(copied_root)):
    with pytest.raises(ControlAuthorizationError):
      candidate.consume(
          copied.action_digest, operation="target.resume", arguments={},
          workspace_id="workspace-a", session_id="session-a", identity=IDENTITY,
          state=STATE, now=instant,
      )


def test_control_consume_pins_the_validated_records_directory_through_create_new(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
  instant = datetime(2026, 8, 16, tzinfo=timezone.utc)
  root = (tmp_path / "control").absolute()
  store = ControlAuthorizationStore(root)
  binding = {
      "workspace_id": "workspace-a", "project_id": "project-a",
      "session_id": "session-a", "revision": "rev-a", "target": IDENTITY,
      "firmware": {"build_id": "b" * 64, "elf_sha256": "e" * 64},
      "operation": "target.resume", "arguments": {},
      "identity_snapshot": IDENTITY, "state_snapshot": STATE,
  }
  prepared = store.prepare(binding, now=instant)
  original_read = store._read_prepared
  replacement = root / "records"
  original = root / "records-original"

  def swap_after_authority_validation(
      digest: str, *, directory_descriptor: int | None = None,
  ):
    try:
      replacement.rename(original)
      shutil.copytree(original, replacement)
    except OSError as error:
      raise ControlAuthorizationError(
          "PROBE_AUTHORIZATION_INVALID", "Authorization directory changed"
      ) from error
    return original_read(digest, directory_descriptor=directory_descriptor)

  monkeypatch.setattr(store, "_read_prepared", swap_after_authority_validation)
  with pytest.raises(ControlAuthorizationError) as caught:
    store.consume(
        prepared.action_digest, operation="target.resume", arguments={},
        workspace_id="workspace-a", session_id="session-a",
        identity=IDENTITY, state=STATE, now=instant,
    )
  assert caught.value.code == "PROBE_AUTHORIZATION_INVALID"
  assert not (replacement / f"{prepared.action_digest}.consumed.json").exists()


def test_control_authority_holds_the_original_root_before_entering_its_mutation_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
  """A copied replacement cannot become authoritative between the two locks."""
  instant = datetime(2026, 8, 16, tzinfo=timezone.utc)
  root = (tmp_path / "authority-root-race" / "control").absolute()
  store = ControlAuthorizationStore(root)
  binding = {
      "workspace_id": "workspace-a", "project_id": "project-a",
      "session_id": "session-a", "revision": "rev-a", "target": IDENTITY,
      "firmware": {"build_id": "b" * 64, "elf_sha256": "e" * 64},
      "operation": "target.resume", "arguments": {},
      "identity_snapshot": IDENTITY, "state_snapshot": STATE,
  }
  prepared = store.prepare(binding, now=instant)
  storage = store._evidence_store()
  original_mutation_lock = storage._mutation_lock
  original_root = root.with_name("control-original")
  attempted: list[str] = []

  @contextmanager
  def swap_before_root_lock(*, create: bool = True):
    attempted.append("swapped")
    root.rename(original_root)
    shutil.copytree(original_root, root)
    with original_mutation_lock(create=create):
      yield

  monkeypatch.setattr(storage, "_mutation_lock", swap_before_root_lock)
  with pytest.raises(ControlAuthorizationError) as caught:
    store.consume(
        prepared.action_digest, operation="target.resume", arguments={},
        workspace_id="workspace-a", session_id="session-a",
        identity=IDENTITY, state=STATE, now=instant,
    )
  assert attempted == ["swapped"]
  assert caught.value.code == "PROBE_AUTHORIZATION_INVALID"
  assert not (root / "records" / f"{prepared.action_digest}.consumed.json").exists()
  assert not (original_root / "records" / f"{prepared.action_digest}.consumed.json").exists()


def test_control_authority_blocks_a_real_cross_process_root_copy_race(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
  instant = datetime(2026, 8, 16, tzinfo=timezone.utc)
  root = (tmp_path / "authority-process-race" / "control").absolute()
  store = ControlAuthorizationStore(root)
  binding = {
      "workspace_id": "workspace-a", "project_id": "project-a",
      "session_id": "session-a", "revision": "rev-a", "target": IDENTITY,
      "firmware": {"build_id": "b" * 64, "elf_sha256": "e" * 64},
      "operation": "target.resume", "arguments": {},
      "identity_snapshot": IDENTITY, "state_snapshot": STATE,
  }
  prepared = store.prepare(binding, now=instant)
  original_root = root.with_name("control-original")
  signal = tmp_path / "race.go"
  outcome = tmp_path / "race.outcome"
  script = (
      "import pathlib,shutil,sys,time\n"
      "root,original,signal,outcome=map(pathlib.Path,sys.argv[1:])\n"
      "deadline=time.monotonic()+10\n"
      "while not signal.exists() and time.monotonic()<deadline: time.sleep(0.005)\n"
      "try:\n"
      " root.rename(original); shutil.copytree(original,root); result='swapped'\n"
      "except OSError:\n"
      " result='blocked'\n"
      "outcome.write_text(result,encoding='utf-8')\n"
  )
  child = subprocess.Popen([
      sys.executable, "-c", script, str(root), str(original_root),
      str(signal), str(outcome),
  ])
  original_read_authority = store._read_authority
  signalled = False

  def read_while_attacker_runs():
    nonlocal signalled
    value = original_read_authority()
    if not signalled:
      signalled = True
      signal.write_text("go", encoding="utf-8")
      deadline = time.monotonic() + 10
      while not outcome.exists() and time.monotonic() < deadline:
        time.sleep(0.005)
      assert outcome.exists()
    return value

  monkeypatch.setattr(store, "_read_authority", read_while_attacker_runs)
  consumed = store.consume(
      prepared.action_digest, operation="target.resume", arguments={},
      workspace_id="workspace-a", session_id="session-a",
      identity=IDENTITY, state=STATE, now=instant,
  )
  assert consumed["nonce"] == prepared.nonce
  assert child.wait(timeout=10) == 0
  assert outcome.read_text(encoding="utf-8") == "blocked"
  assert not original_root.exists()
  assert (root / "records" / f"{prepared.action_digest}.consumed.json").is_file()


def test_control_authority_blocks_a_real_thread_root_copy_race(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
  instant = datetime(2026, 8, 16, tzinfo=timezone.utc)
  root = (tmp_path / "authority-thread-race" / "control").absolute()
  store = ControlAuthorizationStore(root)
  binding = {
      "workspace_id": "workspace-a", "project_id": "project-a",
      "session_id": "session-a", "revision": "rev-a", "target": IDENTITY,
      "firmware": {"build_id": "b" * 64, "elf_sha256": "e" * 64},
      "operation": "target.resume", "arguments": {},
      "identity_snapshot": IDENTITY, "state_snapshot": STATE,
  }
  prepared = store.prepare(binding, now=instant)
  storage = store._evidence_store()
  original_mutation_lock = storage._mutation_lock
  original_root = root.with_name("control-original")
  attack = threading.Event()
  attempted = threading.Event()
  outcome: list[str] = []

  def attacker() -> None:
    assert attack.wait(10)
    try:
      root.rename(original_root)
      shutil.copytree(original_root, root)
      outcome.append("swapped")
    except OSError:
      outcome.append("blocked")
    finally:
      attempted.set()

  thread = threading.Thread(target=attacker, name="authorization-root-attacker")
  thread.start()

  @contextmanager
  def race_before_root_lock(*, create: bool = True):
    attack.set()
    assert attempted.wait(10)
    with original_mutation_lock(create=create):
      yield

  monkeypatch.setattr(storage, "_mutation_lock", race_before_root_lock)
  consumed = store.consume(
      prepared.action_digest, operation="target.resume", arguments={},
      workspace_id="workspace-a", session_id="session-a",
      identity=IDENTITY, state=STATE, now=instant,
  )
  thread.join(10)
  assert not thread.is_alive()
  assert outcome == ["blocked"]
  assert consumed["nonce"] == prepared.nonce
  assert not original_root.exists()
  assert (root / "records" / f"{prepared.action_digest}.consumed.json").is_file()


@pytest.mark.skipif(os.name != "nt", reason="Windows junction contract")
def test_control_authority_rejects_a_root_replaced_by_a_real_junction(tmp_path: Path) -> None:
  instant = datetime(2026, 8, 16, tzinfo=timezone.utc)
  root = (tmp_path / "authority-junction" / "control").absolute()
  store = ControlAuthorizationStore(root)
  binding = {
      "workspace_id": "workspace-a", "project_id": "project-a",
      "session_id": "session-a", "revision": "rev-a", "target": IDENTITY,
      "firmware": {"build_id": "b" * 64, "elf_sha256": "e" * 64},
      "operation": "target.resume", "arguments": {},
      "identity_snapshot": IDENTITY, "state_snapshot": STATE,
  }
  prepared = store.prepare(binding, now=instant)
  original = root.with_name("control-original")
  root.rename(original)
  created = subprocess.run(
      ["cmd", "/d", "/c", "mklink", "/J", str(root), str(original)],
      capture_output=True, text=True, timeout=10, check=False,
  )
  if created.returncode != 0:
    original.rename(root)
    pytest.skip("junction creation is unavailable")
  try:
    with pytest.raises(ControlAuthorizationError):
      store.consume(
          prepared.action_digest, operation="target.resume", arguments={},
          workspace_id="workspace-a", session_id="session-a",
          identity=IDENTITY, state=STATE, now=instant,
      )
    assert not (original / "records" / f"{prepared.action_digest}.consumed.json").exists()
  finally:
    os.rmdir(root)
    original.rename(root)


def test_control_directory_pin_rejects_posix_handle_and_named_identity_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
  from stm32_toolkit.probe import authorization as module

  root = (tmp_path / "control-pin").absolute()
  store = ControlAuthorizationStore(root)
  instant = datetime(2026, 8, 16, tzinfo=timezone.utc)
  store.prepare({
      "workspace_id": "workspace-a", "project_id": "project-a",
      "session_id": "session-a", "revision": "rev-a", "target": IDENTITY,
      "firmware": {"build_id": "b" * 64, "elf_sha256": "e" * 64},
      "operation": "target.resume", "arguments": {},
      "identity_snapshot": IDENTITY, "state_snapshot": STATE,
  }, now=instant)
  directory = root / "records"
  real = os.lstat(directory)
  storage = store._evidence_store()
  closed: list[int] = []
  monkeypatch.setattr(store, "_directory", lambda: directory)
  monkeypatch.setattr(store, "_evidence_store", lambda: storage)
  monkeypatch.setattr(storage, "_validate_existing_path", lambda *args, **kwargs: real)
  monkeypatch.setattr(module.os, "name", "posix")
  monkeypatch.setattr(module.os, "open", lambda *args, **kwargs: 73)
  monkeypatch.setattr(module.os, "close", closed.append)
  monkeypatch.setattr(module.os, "fstat", lambda descriptor: real)
  with store._pinned_records_directory() as pinned:
    assert pinned == 73
  assert closed == [73]

  with pytest.raises(ControlAuthorizationError) as caught:
    with store._pinned_records_directory(
        expected_identity={"device": "0", "inode": "0"}
    ):
      pass
  assert caught.value.code == "PROBE_AUTHORIZATION_INVALID"
  assert str(caught.value) == "Authorization directory is invalid"

  different = type("Metadata", (), {
      "st_mode": real.st_mode, "st_dev": real.st_dev, "st_ino": real.st_ino + 1,
  })()
  monkeypatch.setattr(module.os, "fstat", lambda descriptor: different)
  with pytest.raises(ControlAuthorizationError) as caught:
    with store._pinned_records_directory():
      pass
  assert caught.value.code == "PROBE_AUTHORIZATION_INVALID"
  assert str(caught.value) == "Authorization directory is invalid"

  for sequence in ((real, different), (real, real, different)):
    values = iter(sequence)
    monkeypatch.setattr(storage, "_validate_existing_path", lambda *args, **kwargs: next(values))
    monkeypatch.setattr(module.os, "fstat", lambda descriptor: real)
    with pytest.raises(ControlAuthorizationError) as caught:
      with store._pinned_records_directory():
        pass
    assert caught.value.code == "PROBE_AUTHORIZATION_INVALID"
    assert str(caught.value) == "Authorization directory is invalid"


def test_control_root_pin_rejects_non_directory_and_posix_identity_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
  from stm32_toolkit.probe import authorization as module

  root = (tmp_path / "control-root-pin").absolute()
  store = ControlAuthorizationStore(root)
  instant = datetime(2026, 8, 16, tzinfo=timezone.utc)
  store.prepare({
      "workspace_id": "workspace-a", "project_id": "project-a",
      "session_id": "session-a", "revision": "rev-a", "target": IDENTITY,
      "firmware": {"build_id": "b" * 64, "elf_sha256": "e" * 64},
      "operation": "target.resume", "arguments": {},
      "identity_snapshot": IDENTITY, "state_snapshot": STATE,
  }, now=instant)
  real = os.lstat(root)
  storage = store._evidence_store()
  closed: list[int] = []
  monkeypatch.setattr(store, "_evidence_store", lambda: storage)
  monkeypatch.setattr(storage, "_validate_existing_path", lambda *args, **kwargs: real)
  monkeypatch.setattr(module.os, "name", "posix")
  monkeypatch.setattr(module.os, "open", lambda *args, **kwargs: 79)
  monkeypatch.setattr(module.os, "close", closed.append)
  monkeypatch.setattr(module.os, "fstat", lambda descriptor: real)
  with store._pinned_root_directory() as pinned:
    assert pinned == store._identity(real)
  assert closed == [79]

  different = type("Metadata", (), {
      "st_mode": real.st_mode, "st_dev": real.st_dev, "st_ino": real.st_ino + 1,
  })()
  monkeypatch.setattr(module.os, "fstat", lambda descriptor: different)
  with pytest.raises(module._ControlAuthorizationStorageError):
    with store._pinned_root_directory():
      pass

  monkeypatch.setattr(module.os, "fstat", lambda descriptor: real)
  for sequence in ((real, different), (real, real, different)):
    values = iter(sequence)
    monkeypatch.setattr(storage, "_validate_existing_path", lambda *args, **kwargs: next(values))
    with pytest.raises(module._ControlAuthorizationStorageError):
      with store._pinned_root_directory():
        pass

  not_directory = type("Metadata", (), {
      "st_mode": 0, "st_dev": real.st_dev, "st_ino": real.st_ino,
  })()
  monkeypatch.setattr(storage, "_validate_existing_path", lambda *args, **kwargs: not_directory)
  with pytest.raises(module._ControlAuthorizationStorageError):
    with store._pinned_root_directory():
      pass


def test_control_authority_rejects_root_drift_before_and_after_locked_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
  instant = datetime(2026, 8, 16, tzinfo=timezone.utc)
  binding = {
      "workspace_id": "workspace-a", "project_id": "project-a",
      "session_id": "session-a", "revision": "rev-a", "target": IDENTITY,
      "firmware": {"build_id": "b" * 64, "elf_sha256": "e" * 64},
      "operation": "target.resume", "arguments": {},
      "identity_snapshot": IDENTITY, "state_snapshot": STATE,
  }

  before_store = ControlAuthorizationStore((tmp_path / "before" / "control").absolute())
  before = before_store.prepare(binding, now=instant)

  @contextmanager
  def wrong_root_pin():
    yield {"device": "0", "inode": "0"}

  monkeypatch.setattr(before_store, "_pinned_root_directory", wrong_root_pin)
  with pytest.raises(ControlAuthorizationError):
    before_store.consume(
        before.action_digest, operation="target.resume", arguments={},
        workspace_id="workspace-a", session_id="session-a",
        identity=IDENTITY, state=STATE, now=instant,
    )
  assert not (
      before_store.root / "records" / f"{before.action_digest}.consumed.json"
  ).exists()

  after_store = ControlAuthorizationStore((tmp_path / "after" / "control").absolute())
  after = after_store.prepare(binding, now=instant)
  original_read = after_store._read_authority
  reads = 0

  def read_then_drift():
    nonlocal reads
    reads += 1
    authority = original_read()
    if reads == 2:
      return {**authority, "root": {"device": "0", "inode": "0"}}
    return authority

  monkeypatch.setattr(after_store, "_read_authority", read_then_drift)
  with pytest.raises(ControlAuthorizationError):
    after_store.consume(
        after.action_digest, operation="target.resume", arguments={},
        workspace_id="workspace-a", session_id="session-a",
        identity=IDENTITY, state=STATE, now=instant,
    )
  assert reads == 2
  assert (
      after_store.root / "records" / f"{after.action_digest}.consumed.json"
  ).is_file()


def test_control_authorization_cross_process_consume_has_one_winner(tmp_path: Path) -> None:
  from stm32_toolkit.probe.authorization import ControlAuthorizationStore

  instant = datetime(2026, 8, 16, tzinfo=timezone.utc)
  root = (tmp_path / "cross-process" / "control").absolute()
  store = ControlAuthorizationStore(root)
  prepared = store.prepare({
      "workspace_id": "workspace-a", "project_id": "project-a",
      "session_id": "session-a", "revision": "rev-a", "target": IDENTITY,
      "firmware": {"build_id": "b" * 64, "elf_sha256": "e" * 64},
      "operation": "target.resume", "arguments": {},
      "identity_snapshot": IDENTITY, "state_snapshot": STATE,
  }, now=instant)
  script = """
import json, pathlib, sys, time
from datetime import datetime, timezone
from stm32_toolkit.probe.authorization import ControlAuthorizationError, ControlAuthorizationStore
root=pathlib.Path(sys.argv[1]); digest=sys.argv[2]
identity=json.loads(sys.argv[3]); state=json.loads(sys.argv[4])
ready=pathlib.Path(sys.argv[5]); start=pathlib.Path(sys.argv[6])
ready.write_text('ready', encoding='utf-8')
deadline=time.monotonic()+15
while not start.exists() and time.monotonic()<deadline: time.sleep(0.001)
if not start.exists(): raise SystemExit(4)
try:
    ControlAuthorizationStore(root).consume(digest, operation='target.resume', arguments={}, workspace_id='workspace-a', session_id='session-a', identity=identity, state=state, now=datetime(2026,8,16,tzinfo=timezone.utc))
except ControlAuthorizationError:
    raise SystemExit(3)
"""
  start = tmp_path / "control-consume.start"
  ready = [tmp_path / f"control-consume-{index}.ready" for index in range(2)]
  base = [
      str(root), prepared.action_digest, __import__("json").dumps(IDENTITY),
      __import__("json").dumps(STATE),
  ]
  children = [
      subprocess.Popen([sys.executable, "-c", script, *base, str(path), str(start)])
      for path in ready
  ]
  release_process_barrier(children, ready, start)
  codes = sorted(child.wait(timeout=15) for child in children)
  assert codes == [0, 3]


def test_target_runner_rejects_forged_prepared_value_without_persistent_record(
    tmp_path: Path,
) -> None:
  async def scenario() -> None:
    probe = FakeProbeClient()
    flash = FakeFlashWorkflow()
    (tmp_path / "runs").mkdir()
    runner = target_module.TargetTestRunner(
        tmp_path / "runs", probe, flash, lambda name: FakeTransport([b""])
    )
    instant = datetime(2026, 8, 16, tzinfo=timezone.utc)
    binding = {
        "workspace_id": "workspace-a", "project_id": "project-a",
        "session_id": "session-a", "revision": "rev-a", "target": IDENTITY,
        "probe_serial_hash": PROBE_HASH, "elf_path": "build/app.elf",
        "elf_sha256": "e" * 64, "build_id": "b" * 64,
        "inventory_digest": "a" * 64, "transport": "mailbox",
        "transport_config": MAILBOX_PROJECT_CONFIG, "support_profile": TARGET_SUPPORT,
        "cases": ["suite.case"], "timeout_ms": 1000,
        "nonce": "2" * 64, "expires_at_utc": "2026-08-16T00:05:00.000000Z",
    }
    digest = __import__("hashlib").sha256(
        target_module.canonical_json_bytes(binding)
    ).hexdigest()
    forged = target_module.PreparedTargetRun(digest, "2" * 64, instant + timedelta(minutes=5), binding)
    with pytest.raises(target_module.TargetRunError) as caught:
      await runner.run(
          forged, digest, current_revision="rev-a",
          current_inventory_digest="a" * 64, now=instant,
      )
    assert caught.value.code == "TEST_AUTHORIZATION_INVALID"
    assert flash.calls == []

  run(scenario())


@pytest.mark.parametrize("raw", [b"", b"raw"])
def test_target_runner_rejects_empty_or_unframed_stream_before_publication(
    tmp_path: Path, raw: bytes,
) -> None:
  async def scenario() -> None:
    probe = FakeProbeClient()
    flash = FakeFlashWorkflow()
    runner = target_module.TargetTestRunner(
        tmp_path / "runs", probe, flash, lambda name: FakeTransport([raw, b""])
    )
    instant = datetime(2026, 8, 16, tzinfo=timezone.utc)
    prepared = await runner.prepare(
        workspace_id="workspace-a", project_id="project-a", session_id="session-a",
        revision="rev-a", target=IDENTITY, probe_serial_hash=PROBE_HASH,
        elf_path="build/app.elf", elf_sha256="e" * 64, build_id="b" * 64,
        inventory_digest="a" * 64, transport="mailbox", transport_config=MAILBOX_PROJECT_CONFIG,
        support_profile=TARGET_SUPPORT,
        cases=("suite.case",), timeout_ms=1000, now=instant,
    )
    with pytest.raises(Exception):
      await runner.run(
          prepared, prepared.action_digest, current_revision="rev-a",
          current_inventory_digest="a" * 64, now=instant,
      )
    assert not (tmp_path / "runs" / prepared.action_digest / "test-manifest.json").exists()

  run(scenario())


@pytest.mark.parametrize(
    "value,binding",
    [
        ([], {"target": {"target_id": "target-a"}, "transport": "mailbox"}),
        ({"target_id": "", "transport": "mailbox"}, {"target": {"target_id": "target-a"}, "transport": "mailbox"}),
        ({"target_id": "target-b", "transport": "mailbox"}, {"target": {"target_id": "target-a"}, "transport": "mailbox"}),
    ],
)
def test_closed_transport_identity_rejects_shape_empty_and_changed_values(value, binding):
  with pytest.raises(target_module.TargetRunError) as caught:
    target_module._closed_transport_identity(value, binding)
  assert caught.value.code == "TEST_IDENTITY_MISMATCH"


@pytest.mark.parametrize(
    "transport,identity",
    [
        ("mailbox", {"probe_id": PROBE_HASH, "target_id": "target-a", "transport": "mailbox", "config_digest": "0" * 64, "address": "0x20000000", "ring_size": "4096", "ram_bounds": "0x20000000+0x00010000"}),
        ("rtt", {"probe_id": PROBE_HASH, "target_id": "target-a", "transport": "rtt", "config_digest": "0" * 64, "channel": "0", "control_block_address": "0x20000100", "ram_bounds": "0x20000000+0x00010000"}),
        ("uart", {"probe_id": PROBE_HASH, "target_id": "target-a", "transport": "uart", "config_digest": "0" * 64, "port": "COM3", "baud": "115200", "data_bits": "8", "parity": "N", "stop_bits": "1", "flow_control": "xonxoff=0,rtscts=0,dsrdtr=0"}),
        ("semihosting", {"probe_id": PROBE_HASH, "target_id": "target-a", "transport": "semihosting", "config_digest": "0" * 64, "elf_path": "C:\\fixture\\app.elf", "elf_sha256": "e" * 64, "host_file_policy": "deny"}),
    ],
)
def test_closed_transport_identity_accepts_each_task8_production_shape(transport, identity):
  configs = {
      "mailbox": MAILBOX_PROJECT_CONFIG,
      "rtt": {"kind": "rtt", "options": {"channel": 0, "controlBlockAddress": 0x20000100}},
      "uart": {"kind": "uart", "options": {"port": "COM3", "baud": 115200}},
      "semihosting": {"kind": "semihosting", "options": {}},
  }
  binding = {
      "target": IDENTITY, "probe_serial_hash": PROBE_HASH,
      "elf_path": "build/app.elf", "elf_sha256": "e" * 64,
      "transport": transport, "transport_config": configs[transport],
      "support_profile": TARGET_SUPPORT,
  }
  effective = target_module._effective_target_transport_config(binding)
  identity["config_digest"] = target_module._task8_identity_digest(
      transport, effective, identity
  )
  assert target_module._closed_transport_identity(identity, binding) == identity


@pytest.mark.parametrize(
    "transport,project_config,expected",
    [
        ("mailbox", MAILBOX_PROJECT_CONFIG, {"address": 0x20000000, "size": 4096, "ram": TARGET_SUPPORT["ram"], "target_id": "target-a", "probe_id": PROBE_HASH}),
        ("rtt", {"kind": "rtt", "options": {"channel": 0, "controlBlockAddress": 0x20000100}}, {"channel": 0, "control_block_address": 0x20000100, "ram": TARGET_SUPPORT["ram"], "target_id": "target-a", "probe_id": PROBE_HASH}),
        ("uart", {"kind": "uart", "options": {"port": "COM3", "baud": 115200}}, {"port": "COM3", "baud": 115200, "data_bits": 8, "parity": "N", "stop_bits": 1, "target_id": "target-a", "probe_id": PROBE_HASH}),
        ("semihosting", {"kind": "semihosting", "options": {}}, {"elf_path": "C:\\fixture\\app.elf", "elf_sha256": "e" * 64, "host_files": False, "target_id": "target-a", "probe_id": PROBE_HASH}),
    ],
)
def test_target_builds_each_real_task8_effective_config_from_frozen_inputs(
    transport, project_config, expected,
):
  binding = {
      "target": IDENTITY, "probe_serial_hash": PROBE_HASH,
      "elf_path": "build/app.elf", "elf_sha256": "e" * 64,
      "transport": transport, "transport_config": project_config,
      "support_profile": TARGET_SUPPORT,
  }
  assert target_module._effective_target_transport_config(binding) == expected


def test_target_transport_identity_rejects_a_stable_but_unrecomputed_digest():
  binding = {
      "target": IDENTITY, "probe_serial_hash": PROBE_HASH,
      "elf_path": "build/app.elf", "elf_sha256": "e" * 64,
      "transport": "mailbox", "transport_config": MAILBOX_PROJECT_CONFIG,
      "support_profile": TARGET_SUPPORT,
  }
  identity = {
      "probe_id": PROBE_HASH, "target_id": "target-a", "transport": "mailbox",
      "config_digest": "d" * 64, "address": "0x20000000", "ring_size": "4096",
      "ram_bounds": "0x20000000+0x00010000",
  }
  with pytest.raises(target_module.TargetRunError) as caught:
    target_module._closed_transport_identity(identity, binding)
  assert caught.value.code == "TEST_IDENTITY_MISMATCH"


def test_target_runner_dependency_and_authorization_boundaries_are_closed(tmp_path: Path):
  with pytest.raises(TypeError):
    target_module.GuardedTargetFlashAdapter(
        project_root=Path("relative"), data_root=tmp_path.absolute(),
        session_id="session-a", probe_id="probe-a", workflow=lambda request: None,
    )
  with pytest.raises(TypeError):
    target_module.TargetTestRunner(
        Path("relative"), FakeProbeClient(), FakeFlashWorkflow(), lambda name: FakeTransport([]),
    )

  runner = target_module.TargetTestRunner(
      (tmp_path / "runs").absolute(), FakeProbeClient(), FakeFlashWorkflow(),
      lambda name: FakeTransport([]),
  )
  with pytest.raises(target_module.TargetRunError) as caught:
    runner._consume_prepared("not-a-digest", now=datetime(2026, 8, 16, tzinfo=timezone.utc))
  assert caught.value.code == "TEST_AUTHORIZATION_INVALID"
  with pytest.raises(target_module.TargetRunError) as forged:
    run(runner.run(
        object(), "0" * 64, current_revision="rev-a",
        current_inventory_digest="a" * 64,
        now=datetime(2026, 8, 16, tzinfo=timezone.utc),
    ))
  assert forged.value.code == "TEST_AUTHORIZATION_INVALID"


R5_EVIDENCE_IDENTITY = EvidenceIdentity.from_dict({
    "workspace_id": WORKSPACE_ID,
    "project_id": PROJECT_ID,
    "session_id": SESSION_ID,
    "build_id": "b" * 64,
    "elf_sha256": "e" * 64,
    "target_device": "target-a",
    "input_snapshot_sha256": "9" * 64,
    "git_commit": REVISION,
    "git_dirty": False,
})
R5_INVENTORY_DIGEST = calculate_inventory_digest(
    "target", R5_EVIDENCE_IDENTITY, ("suite.case",)
)


def _r5_inventory_frame(
    *,
    build_id: str = "b" * 64,
    elf_sha256: str = "e" * 64,
    revision: str = REVISION,
    inventory_digest: str | None = None,
    input_snapshot_sha256: str = "9" * 64,
    case_ids: tuple[str, ...] = ("suite.case",),
    target_device: str = "target-a",
) -> bytes:
  identity = EvidenceIdentity.from_dict({
      "workspace_id": WORKSPACE_ID,
      "project_id": PROJECT_ID,
      "session_id": SESSION_ID,
      "build_id": build_id,
      "elf_sha256": elf_sha256,
      "target_device": target_device,
      "input_snapshot_sha256": input_snapshot_sha256,
      "git_commit": revision,
      "git_dirty": False,
  })
  digest = (
      calculate_inventory_digest("target", identity, case_ids)
      if inventory_digest is None
      else inventory_digest
  )
  return target_module.encode_frame(1, 0, {
      "mode": "target",
      "identity": identity.to_dict(),
      "case_ids": list(case_ids),
      "inventory_digest": digest,
      "discovered_at_utc": "2026-08-16T00:00:00.000000Z",
  })


async def _r5_authorized_ledger(root: Path):
  runner = target_module.TargetTestRunner(
      root, FakeProbeClient(), FakeFlashWorkflow(), lambda name: FakeTransport([]),
  )
  instant = datetime(2026, 8, 16, tzinfo=timezone.utc)
  prepared = await runner.prepare(
      workspace_id="workspace-a", project_id="project-a", session_id="session-a",
      revision="rev-a", target=IDENTITY, probe_serial_hash=PROBE_HASH,
      elf_path="build/app.elf", elf_sha256="e" * 64, build_id="b" * 64,
      inventory_digest="a" * 64, transport="mailbox",
      transport_config=MAILBOX_PROJECT_CONFIG, support_profile=TARGET_SUPPORT,
      cases=("suite.case",), timeout_ms=1000, now=instant,
  )
  return runner, prepared, instant


async def _r5_discover(runner, **overrides):
  arguments = {
      "transport": "mailbox",
      "transport_config": MAILBOX_PROJECT_CONFIG,
      "support_profile": TARGET_SUPPORT,
      "deadline": time.monotonic() + 1.0,
      "expected_identity": IDENTITY,
      "expected_firmware": {
          "build_id": "b" * 64,
          "elf_sha256": "e" * 64,
          "revision": REVISION,
          "inventory_digest": R5_INVENTORY_DIGEST,
      },
  }
  arguments.update(overrides)
  return await runner.discover(**arguments)


@pytest.mark.parametrize("stream_kind", ["empty", "truncated", "extra"])
def test_target_discovery_rejects_non_inventory_streams_and_closes(
    tmp_path: Path, stream_kind: str,
) -> None:
  """Discovery accepts exactly one complete canonical inventory frame."""
  async def scenario() -> None:
    frame = _r5_inventory_frame()
    streams = {
        "empty": b"",
        "truncated": frame[:-1],
        "extra": frame + frame,
    }
    active = FakeTransport([streams[stream_kind]])
    probe = FakeProbeClient()
    flash = FakeFlashWorkflow()
    runner = target_module.TargetTestRunner(
        (tmp_path / stream_kind / "runs").absolute(),
        probe,
        flash,
        lambda _name: active,
    )

    with pytest.raises(target_module.TargetRunError) as caught:
      await _r5_discover(runner)

    assert caught.value.code == "TEST_TRANSPORT_UNAVAILABLE"
    assert active.calls[-1] == ("close",)
    assert probe.closed
    assert flash.calls == []

  run(scenario())


def test_target_discovery_rejects_invalid_binding_before_factory_and_closes_probe(
    tmp_path: Path,
) -> None:
  async def scenario() -> None:
    probe = FakeProbeClient()
    factory_calls = []
    runner = target_module.TargetTestRunner(
        (tmp_path / "runs").absolute(),
        probe,
        FakeFlashWorkflow(),
        lambda name: factory_calls.append(name),
    )

    with pytest.raises(target_module.TargetRunError) as caught:
      await _r5_discover(runner, deadline=time.monotonic() - 1.0)

    assert caught.value.code == "TEST_TRANSPORT_UNAVAILABLE"
    assert factory_calls == []
    assert probe.closed

  run(scenario())


def test_target_discovery_attempts_both_cleanups_when_both_fail(tmp_path: Path) -> None:
  class FailingTransport(FakeTransport):
    def close(self):
      self.calls.append(("close",))
      raise OSError("simulated-transport-close-failure")

  class FailingProbe(FakeProbeClient):
    def close(self):
      self.calls.append(("close",))
      raise OSError("simulated-probe-close-failure")

  async def scenario() -> None:
    active = FailingTransport([_r5_inventory_frame()])
    probe = FailingProbe()
    runner = target_module.TargetTestRunner(
        (tmp_path / "runs").absolute(),
        probe,
        FakeFlashWorkflow(),
        lambda _name: active,
    )

    with pytest.raises(target_module.TargetRunError) as caught:
      await _r5_discover(runner)

    assert caught.value.code == "TEST_TRANSPORT_UNAVAILABLE"
    assert active.calls[-1] == ("close",)
    assert probe.calls[-1] == ("close",)

  run(scenario())


async def _r5_prepared_runner(
    tmp_path: Path,
    transport: FakeTransport,
    *,
    timeout_ms: int = 250,
    probe: FakeProbeClient | None = None,
    inventory_digest: str = TARGET_RUN_INVENTORY_DIGEST,
    flash_workflow: object | None = None,
    transport_factory: object | None = None,
):
  from stm32_toolkit.evidence.store import EvidenceStore
  from stm32_toolkit.testing.artifacts import TestArtifactCollector

  project = tmp_path / "project"
  project.mkdir(parents=True)
  evidence_store = EvidenceStore((tmp_path / "evidence").absolute())
  collector = TestArtifactCollector(
      (tmp_path / "results").absolute(), evidence_store, project_root=project,
  )
  workflow_calls = []

  async def workflow(request):
    workflow_calls.append(request)
    return OperationResult.success("stm32_flash", {"status": "success"})

  probe = probe or FakeProbeClient()
  probe.identity = dict(IDENTITY)
  flash = target_module.GuardedTargetFlashAdapter(
      project_root=project,
      data_root=(tmp_path / "data").absolute(),
      session_id=SESSION_ID,
      probe_id=PROBE_SELECTOR,
      workflow=flash_workflow or workflow,
  )
  runner = target_module.TargetTestRunner(
      (tmp_path / "runs").absolute(),
      probe,
      flash,
      transport_factory or (lambda name: transport),
      artifact_collector=collector,
  )
  instant = datetime.now(timezone.utc)
  prepared = await runner.prepare(
      workspace_id=WORKSPACE_ID,
      project_id=PROJECT_ID,
      session_id=SESSION_ID,
      revision=REVISION,
      target=IDENTITY,
      probe_serial_hash=PROBE_HASH,
      elf_path="build/app.elf",
      elf_sha256="e" * 64,
      build_id="b" * 64,
      inventory_digest=inventory_digest,
      transport="mailbox",
      transport_config=MAILBOX_PROJECT_CONFIG,
      support_profile=TARGET_SUPPORT,
      cases=("suite.case",),
      timeout_ms=timeout_ms,
      now=instant,
  )
  return runner, prepared, instant, probe, evidence_store, workflow_calls


async def _v2_prepared_runner(
    tmp_path: Path,
    transport: FakeTransport,
    *,
    timeout_ms: int = 1_000,
    probe: FakeProbeClient | None = None,
    flash_workflow: object | None = None,
    transport_factory: object | None = None,
):
  from stm32_toolkit.evidence.store import EvidenceStore
  from stm32_toolkit.testing.artifacts import TestArtifactCollector

  project = tmp_path / "v2-project"
  project.mkdir(parents=True)
  evidence_store = EvidenceStore((tmp_path / "v2-evidence").absolute())
  collector = TestArtifactCollector(
      (tmp_path / "v2-results").absolute(), evidence_store, project_root=project,
  )
  workflow_calls = []

  async def workflow(request):
    workflow_calls.append(request)
    return OperationResult.success("stm32_flash", {"status": "success"})

  probe = probe or FakeProbeClient()
  probe.identity = dict(IDENTITY)
  flash = target_module.GuardedTargetFlashAdapter(
      project_root=project,
      data_root=(tmp_path / "v2-data").absolute(),
      session_id=SESSION_ID,
      probe_id=PROBE_SELECTOR,
      workflow=flash_workflow or workflow,
  )
  runner = target_module.TargetTestRunner(
      (tmp_path / "v2-runs").absolute(),
      probe,
      flash,
      transport_factory or (lambda _name: transport),
      artifact_collector=collector,
  )
  instant = datetime(2026, 8, 25, tzinfo=timezone.utc)
  host_identity = _target_evidence_identity()
  prepared = await runner.prepare(
      workspace_id=WORKSPACE_ID,
      project_id=PROJECT_ID,
      session_id=SESSION_ID,
      revision=REVISION,
      input_snapshot_sha256="9" * 64,
      target=IDENTITY,
      probe_serial_hash=PROBE_HASH,
      elf_path="build/app.elf",
      elf_sha256="e" * 64,
      build_id="b" * 64,
      inventory_digest=calculate_inventory_digest(
          "target", host_identity, (V2_CASE_ID,)
      ),
      protocol="stm32-target-frame/2",
      case_inventory_digest=V2_CASE_INVENTORY_DIGEST,
      git_dirty=False,
      transport="mailbox",
      transport_config=MAILBOX_PROJECT_CONFIG,
      support_profile=TARGET_SUPPORT,
      cases=(V2_CASE_ID,),
      timeout_ms=timeout_ms,
      now=instant,
  )
  return runner, prepared, instant, probe, evidence_store, workflow_calls


def test_v2_execute_assembles_manifest_after_guarded_flash_and_transport(
    tmp_path: Path,
) -> None:
  async def scenario() -> None:
    _inventory, stream = _v2_target_stream()
    transport = FakeTransport([stream])
    runner, prepared, instant, probe, _store, workflow_calls = (
        await _v2_prepared_runner(tmp_path, transport)
    )

    result = await runner.run(
        prepared,
        prepared.action_digest,
        current_revision=REVISION,
        current_inventory_digest=prepared.binding["inventory_digest"],
        current_input_snapshot_sha256="9" * 64,
        now=instant,
    )

    assert result["test_manifest"].state == "passed"
    assert result["test_manifest"].raw_events.size_bytes == len(stream)
    assert len(workflow_calls) == 1
    assert [call[0] for call in transport.calls] == ["open", "read", "close"]
    assert probe.closed

  run(scenario())


def test_v2_execute_stops_on_run_end_without_transport_eof(tmp_path: Path) -> None:
  class NoEofTransport(FakeTransport):
    def __init__(self, chunk: bytes) -> None:
      super().__init__([chunk])

    def eof(self):
      return False

  async def scenario() -> None:
    _inventory, stream = _v2_target_stream()
    transport = NoEofTransport(stream)
    runner, prepared, instant, _probe, _store, workflow_calls = (
        await _v2_prepared_runner(tmp_path, transport)
    )

    result = await runner.run(
        prepared,
        prepared.action_digest,
        current_revision=REVISION,
        current_inventory_digest=prepared.binding["inventory_digest"],
        current_input_snapshot_sha256="9" * 64,
        now=instant,
    )

    assert result["test_manifest"].state == "passed"
    assert result["test_manifest"].raw_events.size_bytes == len(stream)
    assert len(workflow_calls) == 1
    assert [call[0] for call in transport.calls] == ["open", "read", "close"]

  run(scenario())


def test_v2_execute_times_out_without_run_end_even_without_transport_eof(
    tmp_path: Path,
) -> None:
  class NoEofTransport(FakeTransport):
    def __init__(self, chunk: bytes) -> None:
      super().__init__([chunk])

    def eof(self):
      return False

  async def scenario() -> None:
    _inventory, stream = _v2_target_stream()
    decoded = target_module.TargetFrameDecoder(expected_version=2).feed(stream)
    incomplete = b"".join(frame.raw_bytes for frame in decoded[:-1])
    transport = NoEofTransport(incomplete)
    runner, prepared, instant, probe, _store, workflow_calls = (
        await _v2_prepared_runner(tmp_path, transport, timeout_ms=250)
    )

    with pytest.raises(target_module.TargetRunError) as caught:
      await runner.run(
          prepared,
          prepared.action_digest,
          current_revision=REVISION,
          current_inventory_digest=prepared.binding["inventory_digest"],
          current_input_snapshot_sha256="9" * 64,
          now=instant,
      )

    assert caught.value.code == "TEST_TIMEOUT"
    assert len(workflow_calls) == 1
    assert transport.calls[0][0] == "open"
    assert sum(call[0] == "read" for call in transport.calls) >= 2
    assert transport.calls[-1][0] == "close"
    assert probe.closed

  run(scenario())


def test_v2_execute_rejects_frames_after_run_end_from_the_same_chunk(
    tmp_path: Path,
) -> None:
  async def scenario() -> None:
    _inventory, stream = _v2_target_stream()
    decoded = target_module.TargetFrameDecoder(expected_version=2).feed(stream)
    extra = target_module.encode_frame(
        6,
        len(decoded),
        {"stream": "stdout", "message": "late", "monotonic_ms": 5},
        version=2,
    )
    transport = FakeTransport([stream + extra])
    runner, prepared, instant, probe, _store, workflow_calls = (
        await _v2_prepared_runner(tmp_path, transport)
    )

    with pytest.raises(target_module.TargetRunError) as caught:
      await runner.run(
          prepared,
          prepared.action_digest,
          current_revision=REVISION,
          current_inventory_digest=prepared.binding["inventory_digest"],
          current_input_snapshot_sha256="9" * 64,
          now=instant,
      )

    assert caught.value.code == "TEST_EVENT_SEQUENCE_INVALID"
    assert len(workflow_calls) == 1
    assert [call[0] for call in transport.calls] == ["open", "read", "close"]
    assert probe.closed

  run(scenario())


@pytest.mark.parametrize("mutation", ["digest", "count", "premature"])
def test_v2_execute_rejects_invalid_terminal_contract(
    tmp_path: Path, mutation: str,
) -> None:
  async def scenario() -> None:
    _inventory, stream = _v2_target_stream()
    decoded = target_module.TargetFrameDecoder(expected_version=2).feed(stream)
    prefix = decoded[:-1]
    terminal = dict(decoded[-1].payload)
    terminal["counts"] = dict(terminal["counts"])
    if mutation == "digest":
      terminal["event_stream_digest"] = "f" * 64
      terminal_sequence = len(prefix)
      frames = prefix
    elif mutation == "count":
      counts = dict(terminal["counts"])
      counts["passed"] = 0
      terminal["counts"] = counts
      terminal_sequence = len(prefix)
      frames = prefix
    else:
      prefix = prefix[:-1]
      terminal["state"] = "error"
      terminal["counts"] = {
          "passed": 0, "failed": 0, "skipped": 0, "error": 1, "timeout": 0
      }
      prefix_raw = b"".join(frame.raw_bytes for frame in prefix)
      terminal["event_stream_digest"] = sha256(prefix_raw).hexdigest()
      terminal_sequence = len(prefix)
      frames = prefix
    invalid_terminal = target_module.encode_frame(
        5, terminal_sequence, terminal, version=2
    )
    invalid_stream = b"".join(frame.raw_bytes for frame in frames) + invalid_terminal
    transport = FakeTransport([invalid_stream])
    runner, prepared, instant, probe, _store, workflow_calls = (
        await _v2_prepared_runner(tmp_path, transport)
    )

    with pytest.raises(target_module.TargetRunError) as caught:
      await runner.run(
          prepared,
          prepared.action_digest,
          current_revision=REVISION,
          current_inventory_digest=prepared.binding["inventory_digest"],
          current_input_snapshot_sha256="9" * 64,
          now=instant,
      )

    assert caught.value.code == "TEST_EVENT_SEQUENCE_INVALID"
    assert len(workflow_calls) == 1
    assert [call[0] for call in transport.calls] == ["open", "read", "close"]
    assert probe.closed

  run(scenario())


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        ("revision", "TEST_INVENTORY_CHANGED"),
        ("inventory", "TEST_INVENTORY_CHANGED"),
        ("input_snapshot", "TEST_INVENTORY_CHANGED"),
        ("target", "TEST_IDENTITY_MISMATCH"),
        ("probe", "TEST_IDENTITY_MISMATCH"),
    ],
)
def test_v2_execute_rejects_live_identity_and_inventory_drift(
    tmp_path: Path, mutation: str, expected_code: str,
) -> None:
  async def scenario() -> None:
    _inventory, stream = _v2_target_stream()
    transport = FakeTransport([stream])
    runner, prepared, instant, probe, _store, workflow_calls = (
        await _v2_prepared_runner(tmp_path, transport)
    )
    current_revision = "d" * 40 if mutation == "revision" else REVISION
    current_inventory = "f" * 64 if mutation == "inventory" else prepared.binding["inventory_digest"]
    current_snapshot = "8" * 64 if mutation == "input_snapshot" else "9" * 64
    if mutation == "target":
      probe.identity["target_id"] = "target-drift"
    if mutation == "probe":
      probe.identity["probe_serial_hash"] = "a" * 64

    with pytest.raises(target_module.TargetRunError) as caught:
      await runner.run(
          prepared,
          prepared.action_digest,
          current_revision=current_revision,
          current_inventory_digest=current_inventory,
          current_input_snapshot_sha256=current_snapshot,
          now=instant,
      )

    assert caught.value.code == expected_code
    assert workflow_calls == []
    assert transport.calls == []
    assert probe.closed

  run(scenario())


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("project_id", "223e4567-e89b-42d3-a456-426614174000"),
        ("elf_sha256", "f" * 64),
        ("build_id", "d" * 64),
    ],
)
def test_v2_execute_rejects_host_identity_binding_drift(
    tmp_path: Path, field: str, value: str,
) -> None:
  async def scenario() -> None:
    _inventory, stream = _v2_target_stream()
    transport = FakeTransport([stream])
    runner, prepared, instant, probe, _store, workflow_calls = (
        await _v2_prepared_runner(tmp_path, transport)
    )
    binding = dict(prepared.binding)
    binding[field] = value
    consumed = target_module.ConsumedTargetRun(prepared.action_digest, binding)

    with pytest.raises(target_module.TargetRunError) as caught:
      await runner.run(
          None,
          prepared.action_digest,
          current_revision=REVISION,
          current_inventory_digest=prepared.binding["inventory_digest"],
          current_input_snapshot_sha256="9" * 64,
          consumed=consumed,
          now=instant,
      )

    assert caught.value.code == "TEST_INVENTORY_CHANGED"
    assert len(workflow_calls) == 1
    assert [call[0] for call in transport.calls] == ["open", "read", "close"]
    assert probe.closed

  run(scenario())


def test_v2_execute_rejects_protocol_and_case_inventory_drift(
    tmp_path: Path,
) -> None:
  async def scenario() -> None:
    for field, value, expected in (
        ("protocol", "stm32-target-frame/1", "TEST_FRAME_VERSION_INVALID"),
        ("case_inventory_digest", "f" * 64, "TEST_INVENTORY_CHANGED"),
    ):
      _inventory, stream = _v2_target_stream()
      transport = FakeTransport([stream])
      runner, prepared, instant, probe, _store, workflow_calls = (
          await _v2_prepared_runner(tmp_path / field, transport)
      )
      binding = dict(prepared.binding)
      binding[field] = value
      consumed = target_module.ConsumedTargetRun(prepared.action_digest, binding)

      with pytest.raises(target_module.TargetRunError) as caught:
        await runner.run(
            None,
            prepared.action_digest,
            current_revision=REVISION,
            current_inventory_digest=prepared.binding["inventory_digest"],
            current_input_snapshot_sha256="9" * 64,
            consumed=consumed,
            now=instant,
        )

      assert caught.value.code == expected
      assert len(workflow_calls) == 1
      assert probe.closed

  run(scenario())


def test_v2_execute_rejects_transport_identity_drift(
    tmp_path: Path,
) -> None:
  class DriftTransport(FakeTransport):
    identity_calls = 0

    def identity(self):
      self.identity_calls += 1
      value = super().identity()
      if self.identity_calls > 1:
        value["config_digest"] = "f" * 64
      return value

  async def scenario() -> None:
    _inventory, stream = _v2_target_stream()
    transport = DriftTransport([stream])
    runner, prepared, instant, probe, _store, workflow_calls = (
        await _v2_prepared_runner(tmp_path, transport)
    )

    with pytest.raises(target_module.TargetRunError) as caught:
      await runner.run(
          prepared,
          prepared.action_digest,
          current_revision=REVISION,
          current_inventory_digest=prepared.binding["inventory_digest"],
          current_input_snapshot_sha256="9" * 64,
          now=instant,
      )

    assert caught.value.code == "TEST_IDENTITY_MISMATCH"
    assert len(workflow_calls) == 1
    assert probe.closed

  run(scenario())


def test_v2_execute_rejects_lease_provenance_drift(
    tmp_path: Path,
) -> None:
  async def scenario() -> None:
    _inventory, stream = _v2_target_stream()
    transport = FakeTransport([stream])
    probe = FakeProbeClient()
    probe.endpoint = SimpleNamespace(lease_id="lease-current")
    runner, prepared, instant, probe, _store, workflow_calls = (
        await _v2_prepared_runner(tmp_path, transport, probe=probe)
    )
    provenance = target_module.PhysicalRunProvenance(
        WORKSPACE_ID, SESSION_ID, PROBE_HASH, "flash-session", "lease-stale"
    )
    consumed = target_module.ConsumedTargetRun(
        prepared.action_digest, prepared.binding, provenance
    )

    with pytest.raises(target_module.TargetRunError) as caught:
      await runner.run(
          None,
          prepared.action_digest,
          current_revision=REVISION,
          current_inventory_digest=prepared.binding["inventory_digest"],
          current_input_snapshot_sha256="9" * 64,
          consumed=consumed,
          now=instant,
      )

    assert caught.value.code == "TEST_IDENTITY_MISMATCH"
    assert workflow_calls == []
    assert transport.calls == []
    assert probe.closed

  run(scenario())


def test_v2_authorization_is_single_use(tmp_path: Path) -> None:
  async def scenario() -> None:
    _inventory, stream = _v2_target_stream()
    transport = FakeTransport([stream, b""])
    runner, prepared, instant, probe, _store, workflow_calls = (
        await _v2_prepared_runner(tmp_path, transport)
    )
    kwargs = {
        "current_revision": REVISION,
        "current_inventory_digest": prepared.binding["inventory_digest"],
        "current_input_snapshot_sha256": "9" * 64,
        "now": instant,
    }

    first = await runner.run(prepared, prepared.action_digest, **kwargs)
    with pytest.raises(target_module.TargetRunError) as caught:
      await runner.run(prepared, prepared.action_digest, **kwargs)

    assert first["test_manifest"].state == "passed"
    assert caught.value.code == "TEST_AUTHORIZATION_INVALID"
    assert len(workflow_calls) == 1
    assert probe.closed

  run(scenario())


def test_v2_retry_uses_fresh_capture_after_stale_bytes_fail(
    tmp_path: Path,
) -> None:
  async def scenario() -> None:
    _inventory, valid_stream = _v2_target_stream()
    stale_stream = b"\x00" + valid_stream
    transports = [FakeTransport([stale_stream]), FakeTransport([valid_stream])]
    runner, first, instant, probe, _store, workflow_calls = (
        await _v2_prepared_runner(
            tmp_path,
            transports[0],
            transport_factory=lambda _name: transports.pop(0),
        )
    )
    second_binding = {
        key: value
        for key, value in first.binding.items()
        if key not in {"nonce", "prepared_at_utc", "expires_at_utc"}
    }
    second = await runner.prepare(**second_binding, now=instant)

    with pytest.raises(target_module.TargetRunError) as caught:
      await runner.run(
          first,
          first.action_digest,
          current_revision=REVISION,
          current_inventory_digest=first.binding["inventory_digest"],
          current_input_snapshot_sha256="9" * 64,
          now=instant,
      )
    result = await runner.run(
        second,
        second.action_digest,
        current_revision=REVISION,
        current_inventory_digest=second.binding["inventory_digest"],
        current_input_snapshot_sha256="9" * 64,
        now=instant,
    )

    assert caught.value.code == "TEST_PROTOCOL_INVALID"
    assert result["test_manifest"].raw_events.size_bytes == len(valid_stream)
    assert result["test_manifest"].raw_events.sha256 == sha256(valid_stream).hexdigest()
    assert len(workflow_calls) == 2
    assert probe.closed

  run(scenario())


def test_guarded_flash_rejects_raw_probe_selector_not_bound_to_authorized_hash(tmp_path: Path):
  workflow_calls = []

  async def workflow(request):
    workflow_calls.append(request)
    return OperationResult.success("stm32_flash", {"status": "success"})

  flash = target_module.GuardedTargetFlashAdapter(
      project_root=tmp_path.absolute(),
      data_root=(tmp_path / "data").absolute(),
      session_id=SESSION_ID,
      probe_id=PROBE_SELECTOR,
      workflow=workflow,
  )
  binding = {
      "session_id": SESSION_ID,
      "probe_serial_hash": "1" * 64,
      "build_id": "b" * 64,
      "elf_sha256": "e" * 64,
  }
  with pytest.raises(target_module.TargetRunError) as caught:
    run(flash.run(binding))
  assert caught.value.code == "TEST_IDENTITY_MISMATCH"
  assert workflow_calls == []


def test_target_modify_authority_rejects_a_copied_root_before_replay(tmp_path: Path):
  async def scenario() -> None:
    root = (tmp_path / "authority-parent" / "runs").absolute()
    _runner, prepared, instant = await _r5_authorized_ledger(root)
    original = root.with_name("runs-original")
    root.rename(original)
    shutil.copytree(original, root)
    copied = target_module.TargetTestRunner(
        root, FakeProbeClient(), FakeFlashWorkflow(), lambda name: FakeTransport([]),
    )
    with pytest.raises(target_module.TargetRunError) as caught:
      copied._consume_prepared(prepared.action_digest, now=instant)
    assert caught.value.code == "TEST_AUTHORIZATION_INVALID"
    assert not (root / "records" / f"{prepared.action_digest}.consumed.json").exists()

  run(scenario())


def test_target_modify_authority_rejects_records_snapshot_replay(tmp_path: Path):
  async def scenario() -> None:
    root = (tmp_path / "authority-parent" / "runs").absolute()
    runner, prepared, instant = await _r5_authorized_ledger(root)
    snapshot = root.with_name("prepared-records-snapshot")
    shutil.copytree(root / "records", snapshot)
    assert runner._consume_prepared(prepared.action_digest, now=instant)["nonce"] == prepared.nonce

    consumed_records = root.with_name("consumed-records")
    (root / "records").rename(consumed_records)
    shutil.copytree(snapshot, root / "records")
    replay = target_module.TargetTestRunner(
        root, FakeProbeClient(), FakeFlashWorkflow(), lambda name: FakeTransport([]),
    )
    with pytest.raises(target_module.TargetRunError) as caught:
      replay._consume_prepared(prepared.action_digest, now=instant)
    assert caught.value.code == "TEST_AUTHORIZATION_INVALID"
    assert not (root / "records" / f"{prepared.action_digest}.consumed.json").exists()

  run(scenario())


def test_authorization_publication_is_true_create_new_without_rename_overwrite(
    tmp_path: Path,
) -> None:
  store = ControlAuthorizationStore((tmp_path / "control").absolute())
  storage = store._evidence_store()
  target = storage._managed_directory("records") / f"{'d' * 64}.consumed.json"
  target.write_bytes(b"original")
  assert not store._authorization_create_new(
      target, b"replacement", phase="authorization-create-new-contract"
  )
  assert target.read_bytes() == b"original"


def test_control_stable_record_read_rejects_named_open_identity_swap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
  from stm32_toolkit.probe import authorization as authorization_module

  instant = datetime(2026, 8, 16, tzinfo=timezone.utc)
  store = ControlAuthorizationStore((tmp_path / "control").absolute())
  prepared = store.prepare({
      "workspace_id": "workspace-a", "project_id": "project-a",
      "session_id": "session-a", "revision": "rev-a", "target": IDENTITY,
      "firmware": {"build_id": "b" * 64, "elf_sha256": "e" * 64},
      "operation": "target.resume", "arguments": {},
      "identity_snapshot": IDENTITY, "state_snapshot": STATE,
  }, now=instant)
  path = store._path(prepared.action_digest, "prepared")
  replacement = path.with_name("replacement.prepared.json")
  replacement.write_bytes(path.read_bytes())
  original = path.with_name("original.prepared.json")
  real_open = authorization_module.os.open
  swapped = False

  def swap_before_named_open(candidate, flags, *args):
    nonlocal swapped
    if Path(candidate) == path and not swapped:
      swapped = True
      path.rename(original)
      replacement.rename(path)
    return real_open(candidate, flags, *args)

  monkeypatch.setattr(authorization_module.os, "open", swap_before_named_open)
  with pytest.raises(ControlAuthorizationError) as caught:
    store._read_prepared(prepared.action_digest)
  assert swapped
  assert caught.value.code == "PROBE_AUTHORIZATION_INVALID"


def test_control_stable_record_read_rejects_short_read_with_trailing_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
  from stm32_toolkit.probe import authorization as authorization_module

  instant = datetime(2026, 8, 16, tzinfo=timezone.utc)
  store = ControlAuthorizationStore((tmp_path / "control").absolute())
  prepared = store.prepare({
      "workspace_id": "workspace-a", "project_id": "project-a",
      "session_id": "session-a", "revision": "rev-a", "target": IDENTITY,
      "firmware": {"build_id": "b" * 64, "elf_sha256": "e" * 64},
      "operation": "target.resume", "arguments": {},
      "identity_snapshot": IDENTITY, "state_snapshot": STATE,
  }, now=instant)
  path = store._path(prepared.action_digest, "prepared")
  canonical = path.read_bytes()
  path.write_bytes(canonical + b"trailing")
  target_identity = (path.stat().st_dev, path.stat().st_ino)
  real_read = authorization_module.os.read
  shortened = False

  def short_read(descriptor: int, maximum: int) -> bytes:
    nonlocal shortened
    opened = authorization_module.os.fstat(descriptor)
    if not shortened and (opened.st_dev, opened.st_ino) == target_identity:
      shortened = True
      return real_read(descriptor, len(canonical))
    return real_read(descriptor, maximum)

  monkeypatch.setattr(authorization_module.os, "read", short_read)
  with pytest.raises(ControlAuthorizationError) as caught:
    store._read_prepared(prepared.action_digest)
  assert shortened
  assert caught.value.code == "PROBE_AUTHORIZATION_INVALID"


def test_posix_authorization_record_io_is_anchored_to_the_pinned_directory_fd() -> None:
  from inspect import getsource

  create_source = getsource(ControlAuthorizationStore._authorization_create_new)
  read_source = getsource(ControlAuthorizationStore._read_stable_record_bytes)
  pin_source = getsource(ControlAuthorizationStore._pinned_records_directory)
  assert "src_dir_fd=directory_descriptor" in create_source
  assert "dst_dir_fd=directory_descriptor" in create_source
  assert "dir_fd=directory_descriptor" in create_source
  assert "dir_fd=directory_descriptor" in read_source
  assert "yield descriptor" in pin_source


def test_posix_authorization_record_io_executes_relative_to_pinned_descriptor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
  from stm32_toolkit.probe import authorization as module

  root = (tmp_path / "posix-record-io").absolute()
  records = root / "records"
  records.mkdir(parents=True)
  store = ControlAuthorizationStore(root)
  pinned_descriptor = 987_654
  real_open, real_stat = module.os.open, module.os.stat
  real_link, real_unlink = module.os.link, module.os.unlink
  real_fsync, real_read = module.os.fsync, module.os.read
  relative_calls: list[tuple[str, str]] = []

  def anchored(path, descriptor):
    if descriptor == pinned_descriptor:
      relative_calls.append(("path", os.fspath(path)))
      return records / os.fspath(path)
    return path

  def open_anchored(path, flags, mode=0o777, *, dir_fd=None):
    return real_open(anchored(path, dir_fd), flags, mode)

  def stat_anchored(path, *, dir_fd=None, follow_symlinks=True):
    return real_stat(
        anchored(path, dir_fd), follow_symlinks=follow_symlinks
    )

  def link_anchored(
      source, target, *, src_dir_fd=None, dst_dir_fd=None, follow_symlinks=True,
  ):
    relative_calls.append(("link", f"{src_dir_fd}:{dst_dir_fd}"))
    return real_link(
        anchored(source, src_dir_fd), anchored(target, dst_dir_fd),
        follow_symlinks=follow_symlinks,
    )

  def unlink_anchored(path, *, dir_fd=None):
    return real_unlink(anchored(path, dir_fd))

  def fsync_anchored(descriptor):
    if descriptor != pinned_descriptor:
      return real_fsync(descriptor)
    relative_calls.append(("fsync", str(descriptor)))
    return None

  monkeypatch.setattr(module.os, "open", open_anchored)
  monkeypatch.setattr(module.os, "stat", stat_anchored)
  monkeypatch.setattr(module.os, "link", link_anchored)
  monkeypatch.setattr(module.os, "unlink", unlink_anchored)
  monkeypatch.setattr(module.os, "fsync", fsync_anchored)

  target = records / f"{'e' * 64}.prepared.json"
  payload = b"descriptor-relative-payload"
  assert store._authorization_create_new(
      target, payload, phase="posix-create-new",
      directory_descriptor=pinned_descriptor,
  )
  assert store._read_stable_record_bytes(
      target, 1024, directory_descriptor=pinned_descriptor,
  ) == payload
  assert ("link", f"{pinned_descriptor}:{pinned_descriptor}") in relative_calls
  assert ("fsync", str(pinned_descriptor)) in relative_calls

  assert not store._authorization_create_new(
      target, b"replacement", phase="posix-create-existing",
      directory_descriptor=pinned_descriptor,
  )
  assert target.read_bytes() == payload

  with pytest.raises(module._ControlAuthorizationStorageError):
    store._read_stable_record_bytes(
        target, len(payload) - 1, directory_descriptor=pinned_descriptor,
    )
  with pytest.raises(module._ControlAuthorizationStorageError):
    store._authorization_create_new(
        root / "wrong" / "record.json", b"invalid", phase="posix-wrong-parent",
        directory_descriptor=pinned_descriptor,
    )

  invalid_record = records / "directory-record"
  invalid_record.mkdir()
  with pytest.raises(module._ControlAuthorizationStorageError):
    store._record_info(invalid_record, directory_descriptor=pinned_descriptor)

  first_read = True

  def premature_eof(descriptor: int, maximum: int) -> bytes:
    nonlocal first_read
    if first_read:
      first_read = False
      return b""
    return real_read(descriptor, maximum)

  monkeypatch.setattr(module.os, "read", premature_eof)
  with pytest.raises(module._ControlAuthorizationStorageError):
    store._read_stable_record_bytes(
        target, 1024, directory_descriptor=pinned_descriptor,
    )

  monkeypatch.setattr(module.os, "read", real_read)
  collision = records / f".tmp-authorization-{'00' * 16}"
  collision.write_bytes(b"occupied")
  monkeypatch.setattr(module.os, "urandom", lambda size: b"\x00" * size)
  with pytest.raises(module._ControlAuthorizationStorageError):
    store._authorization_create_new(
        records / "new-record.json", b"payload", phase="posix-temp-exhaustion",
        directory_descriptor=pinned_descriptor,
    )


def test_target_modify_cross_process_consume_has_exactly_one_winner(
    tmp_path: Path,
) -> None:
  root = (tmp_path / "cross-process" / "runs").absolute()
  _runner, prepared, _instant = run(_r5_authorized_ledger(root))
  script = """
import pathlib, sys, time
from datetime import datetime, timezone
from stm32_toolkit.testing.target import TargetRunError, TargetTestRunner
runner=TargetTestRunner(pathlib.Path(sys.argv[1]), object(), object(), lambda name: object())
ready=pathlib.Path(sys.argv[3]); start=pathlib.Path(sys.argv[4])
ready.write_text('ready', encoding='utf-8')
deadline=time.monotonic()+15
while not start.exists() and time.monotonic()<deadline: time.sleep(0.001)
if not start.exists(): raise SystemExit(4)
try:
    runner._consume_prepared(sys.argv[2], now=datetime(2026,8,16,tzinfo=timezone.utc))
except TargetRunError:
    raise SystemExit(3)
"""
  start = tmp_path / "target-consume.start"
  ready = [tmp_path / f"target-consume-{index}.ready" for index in range(2)]
  children = [
      subprocess.Popen([
          sys.executable, "-c", script, str(root), prepared.action_digest,
          str(path), str(start),
      ])
      for path in ready
  ]
  release_process_barrier(children, ready, start)
  codes = sorted(child.wait(timeout=15) for child in children)
  assert codes == [0, 3]
  assert (root / "records" / f"{prepared.action_digest}.consumed.json").is_file()


def test_target_modify_same_process_threads_have_exactly_one_winner(
    tmp_path: Path,
) -> None:
  root = (tmp_path / "same-process" / "runs").absolute()
  _runner, prepared, instant = run(_r5_authorized_ledger(root))
  barrier = threading.Barrier(2)
  outcome: list[str] = []
  outcome_lock = threading.Lock()

  def consume() -> None:
    runner = target_module.TargetTestRunner(
        root, object(), object(), lambda name: object()
    )
    barrier.wait(timeout=10)
    try:
      runner._consume_prepared(prepared.action_digest, now=instant)
      result = "success"
    except target_module.TargetRunError as error:
      result = error.code
    with outcome_lock:
      outcome.append(result)

  threads = [threading.Thread(target=consume) for _ in range(2)]
  for thread in threads:
    thread.start()
  for thread in threads:
    thread.join(timeout=15)
  assert all(not thread.is_alive() for thread in threads)
  assert sorted(outcome) == ["TEST_AUTHORIZATION_INVALID", "success"]


@pytest.mark.skipif(os.name != "nt", reason="Windows root pin contract")
def test_target_modify_blocks_real_cross_process_root_copy_swap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
  root = (tmp_path / "process-copy-race" / "runs").absolute()
  runner, prepared, instant = run(_r5_authorized_ledger(root))
  original_root = root.with_name("runs-original")
  signal = tmp_path / "copy-race.go"
  outcome = tmp_path / "copy-race.outcome"
  script = (
      "import pathlib,shutil,sys,time\n"
      "root,original,signal,outcome=map(pathlib.Path,sys.argv[1:])\n"
      "deadline=time.monotonic()+10\n"
      "while not signal.exists() and time.monotonic()<deadline: time.sleep(0.005)\n"
      "try:\n"
      " root.rename(original); shutil.copytree(original,root); result='swapped'\n"
      "except OSError:\n"
      " result='blocked'\n"
      "outcome.write_text(result,encoding='utf-8')\n"
  )
  child = subprocess.Popen([
      sys.executable, "-c", script, str(root), str(original_root),
      str(signal), str(outcome),
  ])
  authority = runner._authorization_authority
  real_read_authority = authority._read_authority
  signalled = False

  def read_while_attacker_runs():
    nonlocal signalled
    value = real_read_authority()
    if not signalled:
      signalled = True
      signal.write_text("go", encoding="utf-8")
      wait_deadline = time.monotonic() + 10
      while not outcome.exists() and time.monotonic() < wait_deadline:
        time.sleep(0.005)
      assert outcome.exists()
    return value

  monkeypatch.setattr(authority, "_read_authority", read_while_attacker_runs)
  try:
    consumed = runner._consume_prepared(prepared.action_digest, now=instant)
    assert consumed["nonce"] == prepared.nonce
    assert child.wait(timeout=10) == 0
  finally:
    if child.poll() is None:
      child.terminate()
      child.wait(timeout=10)
  assert outcome.read_text(encoding="utf-8") == "blocked"
  assert not original_root.exists()


@pytest.mark.skipif(os.name != "nt", reason="Windows junction contract")
@pytest.mark.parametrize("replacement", ["root", "records"])
def test_target_modify_rejects_real_junction_replacement(
    tmp_path: Path, replacement: str,
) -> None:
  async def scenario() -> None:
    root = (tmp_path / replacement / "runs").absolute()
    runner, prepared, instant = await _r5_authorized_ledger(root)
    target = root if replacement == "root" else root / "records"
    original = target.with_name(f"{target.name}-original")
    target.rename(original)
    created = subprocess.run(
        ["cmd", "/d", "/c", "mklink", "/J", str(target), str(original)],
        capture_output=True, text=True, timeout=10, check=False,
    )
    if created.returncode != 0:
      original.rename(target)
      pytest.skip("junction creation is unavailable")
    try:
      with pytest.raises(target_module.TargetRunError) as caught:
        runner._consume_prepared(prepared.action_digest, now=instant)
      assert caught.value.code == "TEST_AUTHORIZATION_INVALID"
      records = original / "records" if replacement == "root" else original
      assert not (records / f"{prepared.action_digest}.consumed.json").exists()
    finally:
      os.rmdir(target)
      original.rename(target)

  run(scenario())


def test_target_runner_polls_transient_empty_reads_until_validated_terminal(tmp_path: Path):
  async def scenario() -> None:
    stream = valid_target_stream()
    transport = FakeTransport([b"", stream[:7], b"", stream[7:], b"unread"])
    runner, prepared, instant, _probe, _store, _workflow = await _r5_prepared_runner(
        tmp_path, transport
    )
    result = await runner.run(
        prepared,
        prepared.action_digest,
        current_revision=REVISION,
        current_inventory_digest=TARGET_RUN_INVENTORY_DIGEST,
        now=instant,
    )
    assert result["test_manifest"].state == "passed"
    reads = [call for call in transport.calls if call[0] == "read"]
    assert len(reads) == 4
    assert len({call[2] for call in reads}) == 1
    assert transport.chunks == [b"unread"]

  run(scenario())


def test_target_runner_empty_polling_uses_bounded_backoff_until_absolute_deadline(
    tmp_path: Path,
) -> None:
  class LiveEmptyTransport(FakeTransport):
    def __init__(self):
      super().__init__([])
    def eof(self): return False

  async def scenario() -> None:
    transport = LiveEmptyTransport()
    runner, prepared, instant, probe, evidence_store, _workflow = (
        await _r5_prepared_runner(tmp_path, transport, timeout_ms=30)
    )
    started = time.monotonic()
    with pytest.raises(target_module.TargetRunError) as caught:
      await runner.run(
          prepared,
          prepared.action_digest,
          current_revision=REVISION,
          current_inventory_digest=TARGET_RUN_INVENTORY_DIGEST,
          now=instant,
      )
    elapsed = time.monotonic() - started
    assert caught.value.code == "TEST_TIMEOUT"
    reads = [call for call in transport.calls if call[0] == "read"]
    assert 2 <= len(reads) < 20
    assert len({call[2] for call in reads}) == 1
    assert elapsed < 1.0
    assert transport.calls[-1] == ("close",)
    assert probe.closed
    manifests = evidence_store.root / "manifests"
    assert not manifests.exists() or list(manifests.iterdir()) == []

  run(scenario())


def test_target_runner_cancels_a_never_resolving_async_read_at_deadline(
    tmp_path: Path,
) -> None:
  class HungReadTransport(FakeTransport):
    async def read_async(self, maximum, deadline):
      self.calls.append(("read", maximum, deadline))
      await asyncio.Event().wait()

  async def scenario() -> None:
    transport = HungReadTransport([])
    runner, prepared, instant, probe, _store, _workflow = await _r5_prepared_runner(
        tmp_path, transport, timeout_ms=30
    )
    started = time.monotonic()
    with pytest.raises(target_module.TargetRunError) as caught:
      await runner.run(
          prepared,
          prepared.action_digest,
          current_revision=REVISION,
          current_inventory_digest=TARGET_RUN_INVENTORY_DIGEST,
          now=instant,
      )
    assert caught.value.code == "TEST_TIMEOUT"
    assert time.monotonic() - started < 1.0
    assert transport.calls[-1] == ("close",)
    assert probe.closed

  run(scenario())


@pytest.mark.parametrize(
    "mutation",
    [
        "build", "elf", "revision", "target", "input_snapshot", "case_ids",
        "inventory_claim", "config_digest", "final_config_digest", "support_config",
    ],
)
def test_target_discovery_maps_every_firmware_config_mismatch_to_unavailable(
    tmp_path: Path, mutation: str,
) -> None:
  class DiscoveryTransport(FakeTransport):
    def __init__(self, frame: bytes, *, identity_mutation=None, final_mutation=None):
      super().__init__([frame])
      self.identity_mutation = identity_mutation
      self.final_mutation = final_mutation
      self.identity_calls = 0

    def identity(self):
      self.identity_calls += 1
      value = super().identity()
      mutation_value = (
          self.final_mutation
          if self.final_mutation is not None and self.identity_calls > 1
          else self.identity_mutation
      )
      if mutation_value is not None:
        value.update(mutation_value)
      return value

  async def scenario() -> None:
    frame_arguments = {}
    if mutation == "build": frame_arguments["build_id"] = "f" * 64
    if mutation == "elf": frame_arguments["elf_sha256"] = "d" * 64
    if mutation == "revision": frame_arguments["revision"] = "d" * 40
    if mutation == "target": frame_arguments["target_device"] = "target-b"
    if mutation == "input_snapshot": frame_arguments["input_snapshot_sha256"] = "8" * 64
    if mutation == "case_ids": frame_arguments["case_ids"] = ("different.case",)
    if mutation == "inventory_claim": frame_arguments["inventory_digest"] = "a" * 64
    frame = _r5_inventory_frame(**frame_arguments)
    decoded = target_module.TargetFrameDecoder().feed(frame)
    frame_digest = str(decoded[0].payload["inventory_digest"])
    expected_firmware = {
        "build_id": "b" * 64,
        "elf_sha256": "e" * 64,
        "revision": REVISION,
        "inventory_digest": R5_INVENTORY_DIGEST,
    }
    if mutation in {"build", "elf", "revision", "target"}:
      expected_firmware["inventory_digest"] = frame_digest
    identity_mutation = (
        {"config_digest": "f" * 64} if mutation == "config_digest" else None
    )
    final_mutation = (
        {"config_digest": "f" * 64}
        if mutation == "final_config_digest"
        else None
    )
    active = DiscoveryTransport(
        frame,
        identity_mutation=identity_mutation,
        final_mutation=final_mutation,
    )
    probe = FakeProbeClient()
    flash = FakeFlashWorkflow()
    runner = target_module.TargetTestRunner(
        (tmp_path / mutation / "runs").absolute(),
        probe,
        flash,
        lambda name: active,
    )
    support = TARGET_SUPPORT
    if mutation == "support_config":
      support = {
          **TARGET_SUPPORT,
          "mailbox": {"address": 0x20000000, "size": 2048},
      }
    with pytest.raises(target_module.TargetRunError) as caught:
      await _r5_discover(
          runner,
          support_profile=support,
          expected_firmware=expected_firmware,
      )
    assert caught.value.code == "TEST_TRANSPORT_UNAVAILABLE"
    assert flash.calls == []
    assert probe.closed
    assert {call[0] for call in active.calls} <= {"open", "read", "close"}
    if mutation != "support_config":
      assert active.calls[-1] == ("close",)

  run(scenario())


@pytest.mark.parametrize(
    "failure_stage",
    ["factory", "interface", "probe", "open", "identity", "read", "eof", "final_identity"],
)
def test_target_discovery_closes_and_maps_runtime_failures_to_unavailable(
    tmp_path: Path, failure_stage: str,
) -> None:
  class FailingProbe(FakeProbeClient):
    async def target_identity(self):
      if failure_stage == "probe":
        raise OSError("simulated-probe-failure")
      return await super().target_identity()

  class FailingTransport(FakeTransport):
    def __init__(self):
      super().__init__([b"" if failure_stage == "eof" else _r5_inventory_frame()])
      self.identity_calls = 0

    def open(self, config, deadline):
      super().open(config, deadline)
      if failure_stage == "open":
        raise OSError("simulated-open-failure")

    def identity(self):
      self.identity_calls += 1
      if failure_stage == "identity" or (
          failure_stage == "final_identity" and self.identity_calls > 1
      ):
        raise OSError("simulated-identity-failure")
      return super().identity()

    def read(self, maximum, deadline):
      if failure_stage == "read":
        raise OSError("simulated-read-failure")
      return super().read(maximum, deadline)

    def eof(self):
      if failure_stage == "eof":
        raise OSError("simulated-eof-failure")
      return super().eof()

  class InvalidInterface:
    def __init__(self): self.calls = []
    def close(self): self.calls.append(("close",))

  async def scenario() -> None:
    probe = FailingProbe()
    active = InvalidInterface() if failure_stage == "interface" else FailingTransport()

    def factory(name):
      if failure_stage == "factory":
        raise OSError("simulated-factory-failure")
      return active

    runner = target_module.TargetTestRunner(
        (tmp_path / failure_stage / "runs").absolute(),
        probe,
        FakeFlashWorkflow(),
        factory,
    )
    with pytest.raises(target_module.TargetRunError) as caught:
      await _r5_discover(runner, deadline=time.monotonic() + 0.2)
    assert caught.value.code == "TEST_TRANSPORT_UNAVAILABLE"
    assert probe.closed
    if failure_stage != "factory":
      assert active.calls[-1] == ("close",)

  run(scenario())


@pytest.mark.parametrize("owner,async_close", [("transport", False), ("transport", True), ("probe", False), ("probe", True)])
def test_target_discovery_maps_required_sync_async_cleanup_failure(
    tmp_path: Path, owner: str, async_close: bool,
) -> None:
  class SyncTransportFailure(FakeTransport):
    def close(self):
      self.calls.append(("close",))
      raise OSError("simulated-transport-close-failure")

  class AsyncTransportFailure(FakeTransport):
    async def close_async(self):
      self.calls.append(("close",))
      raise OSError("simulated-transport-close-failure")

  class SyncProbeFailure(FakeProbeClient):
    def close(self):
      self.calls.append(("close",))
      raise OSError("simulated-probe-close-failure")

  class AsyncProbeFailure(FakeProbeClient):
    async def close(self):
      self.calls.append(("close",))
      raise OSError("simulated-probe-close-failure")

  async def scenario() -> None:
    transport_type = (
        AsyncTransportFailure if async_close else SyncTransportFailure
    ) if owner == "transport" else FakeTransport
    probe_type = (
        AsyncProbeFailure if async_close else SyncProbeFailure
    ) if owner == "probe" else FakeProbeClient
    active = transport_type([_r5_inventory_frame()])
    probe = probe_type()
    runner = target_module.TargetTestRunner(
        (tmp_path / f"{owner}-{async_close}" / "runs").absolute(),
        probe,
        FakeFlashWorkflow(),
        lambda name: active,
    )
    with pytest.raises(target_module.TargetRunError) as caught:
      await _r5_discover(runner)
    assert caught.value.code == "TEST_TRANSPORT_UNAVAILABLE"
    assert active.calls[-1] == ("close",)
    assert probe.calls[-1] == ("close",)

  run(scenario())


def test_target_discovery_bounds_a_hung_transport_close_and_attempts_probe(
    tmp_path: Path,
) -> None:
  """Discovery must close both dependencies without an external timeout."""
  class HungTransport(FakeTransport):
    async def close_async(self):
      self.calls.append(("close",))
      await asyncio.Event().wait()

  async def scenario() -> None:
    active = HungTransport([_r5_inventory_frame()])
    probe = FakeProbeClient()
    root = (tmp_path / "hung-transport" / "runs").absolute()
    runner = target_module.TargetTestRunner(
        root, probe, FakeFlashWorkflow(), lambda _name: active,
    )
    started = time.monotonic()

    with pytest.raises(target_module.TargetRunError) as caught:
      await asyncio.wait_for(
          _r5_discover(runner, deadline=time.monotonic() + 0.1), timeout=0.3,
      )

    assert caught.value.code == "TEST_TRANSPORT_UNAVAILABLE"
    assert time.monotonic() - started < 0.3
    assert active.calls[-1] == ("close",)
    assert probe.closed
    assert not root.exists()

  run(scenario())


def test_target_discovery_bounds_a_hung_probe_close(
    tmp_path: Path,
) -> None:
  """A cooperative probe close is bounded by the discovery deadline."""
  class HungProbe(FakeProbeClient):
    async def close(self):
      self.calls.append(("close",))
      await asyncio.Event().wait()

  async def scenario() -> None:
    active = FakeTransport([_r5_inventory_frame()])
    probe = HungProbe()
    root = (tmp_path / "hung-probe" / "runs").absolute()
    runner = target_module.TargetTestRunner(
        root, probe, FakeFlashWorkflow(), lambda _name: active,
    )
    started = time.monotonic()

    with pytest.raises(target_module.TargetRunError) as caught:
      await asyncio.wait_for(
          _r5_discover(runner, deadline=time.monotonic() + 0.1), timeout=0.3,
      )

    assert caught.value.code == "TEST_TRANSPORT_UNAVAILABLE"
    assert time.monotonic() - started < 0.3
    assert active.calls[-1] == ("close",)
    assert probe.calls[-1] == ("close",)
    assert not root.exists()

  run(scenario())


def test_target_discovery_bounds_the_total_cleanup_window_when_both_closes_hang(
    tmp_path: Path,
) -> None:
  """Both discovery dependencies receive one finite post-deadline attempt."""
  class HungTransport(FakeTransport):
    async def close_async(self):
      self.calls.append(("close",))
      await asyncio.Event().wait()

  class HungProbe(FakeProbeClient):
    async def close(self):
      self.calls.append(("close",))
      await asyncio.Event().wait()

  async def scenario() -> None:
    active = HungTransport([_r5_inventory_frame()])
    probe = HungProbe()
    root = (tmp_path / "both-hung" / "runs").absolute()
    runner = target_module.TargetTestRunner(
        root, probe, FakeFlashWorkflow(), lambda _name: active,
    )
    started = time.monotonic()

    with pytest.raises(target_module.TargetRunError) as caught:
      await asyncio.wait_for(
          _r5_discover(runner, deadline=time.monotonic() + 0.1), timeout=0.3,
      )

    assert caught.value.code == "TEST_TRANSPORT_UNAVAILABLE"
    assert time.monotonic() - started < 0.3
    assert active.calls[-1] == ("close",)
    assert probe.calls[-1] == ("close",)
    assert not root.exists()

  run(scenario())


def test_target_discovery_retains_its_primary_error_when_cleanup_hangs(
    tmp_path: Path,
) -> None:
  """A required cleanup timeout supplements, never replaces, discovery failure."""
  class HungTransport(FakeTransport):
    async def close_async(self):
      self.calls.append(("close",))
      await asyncio.Event().wait()

  async def scenario() -> None:
    active = HungTransport([b""])
    probe = FakeProbeClient()
    root = (tmp_path / "primary-error" / "runs").absolute()
    runner = target_module.TargetTestRunner(
        root, probe, FakeFlashWorkflow(), lambda _name: active,
    )
    started = time.monotonic()

    with pytest.raises(target_module.TargetRunError) as caught:
      await asyncio.wait_for(
          _r5_discover(runner, deadline=time.monotonic() + 0.1), timeout=0.3,
      )

    assert caught.value.code == "TEST_TRANSPORT_UNAVAILABLE"
    assert any(
        "Target cleanup also failed: TEST_TRANSPORT_UNAVAILABLE" in note
        for note in caught.value.cleanup_notes
    )
    assert time.monotonic() - started < 0.3
    assert active.calls[-1] == ("close",)
    assert probe.closed
    assert not root.exists()

  run(scenario())


@pytest.mark.parametrize("async_close", [False, True])
def test_target_runner_never_publishes_pass_when_required_close_fails(
    tmp_path: Path, async_close: bool,
) -> None:
  class SyncCloseFailure(FakeTransport):
    def close(self):
      self.calls.append(("close",))
      raise OSError("simulated-close-failure")

  class AsyncCloseFailure(FakeTransport):
    async def close_async(self):
      self.calls.append(("close",))
      raise OSError("simulated-close-failure")

  async def scenario() -> None:
    transport_type = AsyncCloseFailure if async_close else SyncCloseFailure
    transport = transport_type([valid_target_stream(), b""])
    runner, prepared, instant, _probe, evidence_store, _workflow = await _r5_prepared_runner(
        tmp_path, transport
    )
    with pytest.raises(target_module.TargetRunError) as caught:
      await runner.run(
          prepared,
          prepared.action_digest,
          current_revision=REVISION,
          current_inventory_digest=TARGET_RUN_INVENTORY_DIGEST,
          now=instant,
      )
    assert caught.value.code == "TEST_TRANSPORT_UNAVAILABLE"
    manifests = evidence_store.root / "manifests"
    assert not manifests.exists() or list(manifests.iterdir()) == []

  run(scenario())


@pytest.mark.parametrize("async_close", [False, True])
def test_target_runner_never_publishes_pass_when_required_probe_close_fails(
    tmp_path: Path, async_close: bool,
) -> None:
  class SyncProbeCloseFailure(FakeProbeClient):
    def close(self):
      self.calls.append(("close",))
      raise OSError("simulated-probe-close-failure")

  class AsyncProbeCloseFailure(FakeProbeClient):
    async def close(self):
      self.calls.append(("close",))
      raise OSError("simulated-probe-close-failure")

  async def scenario() -> None:
    probe_type = AsyncProbeCloseFailure if async_close else SyncProbeCloseFailure
    probe = probe_type()
    transport = FakeTransport([valid_target_stream(), b""])
    runner, prepared, instant, _probe, evidence_store, _workflow = await _r5_prepared_runner(
        tmp_path, transport, probe=probe
    )
    with pytest.raises(target_module.TargetRunError) as caught:
      await runner.run(
          prepared,
          prepared.action_digest,
          current_revision=REVISION,
          current_inventory_digest=TARGET_RUN_INVENTORY_DIGEST,
          now=instant,
      )
    assert caught.value.code == "TEST_TRANSPORT_UNAVAILABLE"
    assert transport.calls[-1] == ("close",)
    assert probe.calls[-1] == ("close",)
    manifests = evidence_store.root / "manifests"
    assert not manifests.exists() or list(manifests.iterdir()) == []

  run(scenario())


def test_target_run_accepts_a_canonical_inventory_with_an_independent_input_snapshot(
    tmp_path: Path,
) -> None:
  """The inventory digest covers identity fields; it is not the input snapshot digest."""
  async def scenario() -> None:
    transport = FakeTransport([valid_target_stream(), b""])
    runner, prepared, instant, _probe, evidence_store, _workflow = (
        await _r5_prepared_runner(tmp_path, transport)
    )

    result = await runner.run(
        prepared,
        prepared.action_digest,
        current_revision=REVISION,
        current_inventory_digest=TARGET_RUN_INVENTORY_DIGEST,
        now=instant,
    )

    assert result["test_manifest"].identity.input_snapshot_sha256 == "9" * 64
    assert result["evidence"].identity == result["test_manifest"].identity
    assert evidence_store.get_envelope(result["evidence"].evidence_id) == result["evidence"]

  run(scenario())


def test_target_run_rejects_a_digest_that_contradicts_visible_inventory_before_evidence(
    tmp_path: Path,
) -> None:
  async def scenario() -> None:
    contradictory_digest = "a" * 64
    transport = FakeTransport([
        _target_stream(
            input_snapshot_sha256=contradictory_digest,
            inventory_digest=contradictory_digest,
        ),
        b"",
    ])
    runner, prepared, instant, _probe, evidence_store, _workflow = (
        await _r5_prepared_runner(
            tmp_path,
            transport,
            inventory_digest=contradictory_digest,
        )
    )

    with pytest.raises(target_module.TargetRunError) as caught:
      await runner.run(
          prepared,
          prepared.action_digest,
          current_revision=REVISION,
          current_inventory_digest=contradictory_digest,
          now=instant,
      )

    assert caught.value.code == "TEST_INVENTORY_CHANGED"
    manifests = evidence_store.root / "manifests"
    assert not manifests.exists() or list(manifests.iterdir()) == []

  run(scenario())


@pytest.mark.parametrize("placement", ["same-chunk", "split-chunk"])
@pytest.mark.parametrize("suffix_kind", ["complete-frame", "trailing-byte"])
def test_target_discovery_rejects_extra_complete_or_trailing_bytes_in_any_chunking(
    tmp_path: Path, placement: str, suffix_kind: str,
) -> None:
  async def scenario() -> None:
    frame = _r5_inventory_frame()
    suffix = frame if suffix_kind == "complete-frame" else b"x"
    chunks = [frame + suffix] if placement == "same-chunk" else [frame, suffix]
    active = FakeTransport(chunks)
    probe = FakeProbeClient()
    runner = target_module.TargetTestRunner(
        (tmp_path / placement / suffix_kind / "runs").absolute(),
        probe,
        FakeFlashWorkflow(),
        lambda _name: active,
    )

    with pytest.raises(target_module.TargetRunError) as caught:
      await _r5_discover(runner)

    assert caught.value.code == "TEST_TRANSPORT_UNAVAILABLE"
    assert active.calls[-1] == ("close",)
    assert probe.closed

  run(scenario())


def test_target_discovery_accepts_one_canonical_inventory_without_eof_at_deadline(
    tmp_path: Path,
) -> None:
  """The four live transports are polling ports, not EOF-delimited streams."""
  class ProductionShapeTransport(FakeTransport):
    eof = None

  async def scenario() -> None:
    frame = _r5_inventory_frame()
    active = ProductionShapeTransport([frame])
    probe = FakeProbeClient()
    runner = target_module.TargetTestRunner(
        (tmp_path / "no-eof" / "runs").absolute(),
        probe,
        FakeFlashWorkflow(),
        lambda _name: active,
    )

    discovered = await _r5_discover(
        runner, deadline=time.monotonic() + 0.03,
    )

    assert discovered["raw"] == frame
    assert discovered["inventory"]["inventory_digest"] == R5_INVENTORY_DIGEST
    reads = [call for call in active.calls if call[0] == "read"]
    assert 2 <= len(reads) < 20
    assert active.calls[-1] == ("close",)
    assert probe.closed

  run(scenario())


def test_target_discovery_does_not_complete_at_deadline_with_a_pending_read(
    tmp_path: Path,
) -> None:
  """Deadline collection completion is valid only after every read returned."""
  class PendingReadTransport(FakeTransport):
    eof = None

    async def read_async(self, maximum, deadline):
      self.calls.append(("read", maximum, deadline))
      if self.chunks:
        return self.chunks.pop(0)
      await asyncio.Event().wait()

  async def scenario() -> None:
    active = PendingReadTransport([_r5_inventory_frame()])
    probe = FakeProbeClient()
    runner = target_module.TargetTestRunner(
        (tmp_path / "pending-read" / "runs").absolute(),
        probe,
        FakeFlashWorkflow(),
        lambda _name: active,
    )

    with pytest.raises(target_module.TargetRunError) as caught:
      await _r5_discover(runner, deadline=time.monotonic() + 0.03)

    assert caught.value.code == "TEST_TRANSPORT_UNAVAILABLE"
    assert len([call for call in active.calls if call[0] == "read"]) == 2
    assert active.calls[-1] == ("close",)
    assert probe.closed

  run(scenario())


def test_target_transport_poller_rejects_a_port_without_any_read_operation() -> None:
  """A malformed live port is not silently treated as an empty collection."""
  async def scenario() -> None:
    with pytest.raises(target_module.TargetRunError) as caught:
      async for _chunk in target_module._poll_transport_chunks(
          object(),
          deadline=time.monotonic() + 1.0,
          maximum_bytes=1,
          timeout_code="TEST_TIMEOUT",
          timeout_message="deadline elapsed",
          invalid_code="TEST_TRANSPORT_UNAVAILABLE",
          invalid_message="port is invalid",
          too_large_code="TEST_STREAM_TOO_LARGE",
          too_large_message="stream is too large",
      ):
        pytest.fail("invalid port yielded data")
    assert caught.value.code == "TEST_TRANSPORT_UNAVAILABLE"

  run(scenario())


def test_target_discovery_rejects_a_synchronous_read_that_crosses_its_deadline(
    tmp_path: Path,
) -> None:
  """Discovery completion never accepts an inventory from a pending timed-out read."""
  class DelayedSyncTransport(FakeTransport):
    eof = None

    def read(self, maximum, deadline):
      self.calls.append(("read", maximum, deadline))
      time.sleep(0.03)
      return self.chunks.pop(0) if self.chunks else b""

  async def scenario() -> None:
    active = DelayedSyncTransport([_r5_inventory_frame()])
    probe = FakeProbeClient()
    runner = target_module.TargetTestRunner(
        (tmp_path / "delayed-discovery" / "runs").absolute(),
        probe,
        FakeFlashWorkflow(),
        lambda _name: active,
    )

    with pytest.raises(target_module.TargetRunError) as caught:
      await _r5_discover(runner, deadline=time.monotonic() + 0.005)

    assert caught.value.code == "TEST_TRANSPORT_UNAVAILABLE"
    assert active.calls[-1] == ("close",)
    assert probe.closed

  run(scenario())


def test_v2_discovery_returns_host_inventory_and_only_first_frame_bytes_with_trailing_run(
    tmp_path: Path,
) -> None:
  """The v2 handshake stops at the first complete inventory frame, not EOF."""
  async def scenario() -> None:
    inventory_frame, stream = _v2_target_stream()
    active = FakeTransport([stream])
    probe = FakeProbeClient()
    runner = target_module.TargetTestRunner(
        (tmp_path / "v2-discovery" / "runs").absolute(),
        probe,
        FakeFlashWorkflow(),
        lambda _name: active,
    )
    host_identity = _target_evidence_identity()

    discovered = await runner.discover(
        transport="mailbox",
        transport_config=MAILBOX_PROJECT_CONFIG,
        support_profile=TARGET_SUPPORT,
        deadline=time.monotonic() + 1.0,
        protocol="stm32-target-frame/2",
        host_identity=host_identity,
        expected_identity=IDENTITY,
        expected_firmware={
            "build_id": host_identity.build_id,
            "elf_sha256": host_identity.elf_sha256,
            "revision": host_identity.git_commit,
            "inventory_digest": calculate_inventory_digest(
                "target", host_identity, (V2_CASE_ID,)
            ),
            "case_inventory_digest": V2_CASE_INVENTORY_DIGEST,
            "case_ids": (V2_CASE_ID,),
        },
    )

    assert discovered["protocol"] == "stm32-target-frame/2"
    assert discovered["raw"] == inventory_frame
    assert discovered["raw"] != stream
    assert discovered["case_inventory_digest"] == V2_CASE_INVENTORY_DIGEST
    assert discovered["inventory"]["identity"] == host_identity.to_dict()
    assert active.calls[-1] == ("close",)
    assert probe.closed

  run(scenario())


def test_v2_prepare_persists_closed_protocol_and_case_inventory_bindings(
    tmp_path: Path,
) -> None:
  async def scenario() -> None:
    runner = target_module.TargetTestRunner(
        (tmp_path / "v2-prepare" / "runs").absolute(),
        FakeProbeClient(),
        FakeFlashWorkflow(),
        lambda _name: FakeTransport([]),
    )
    prepared = await runner.prepare(
        workspace_id=WORKSPACE_ID,
        project_id=PROJECT_ID,
        session_id=SESSION_ID,
        revision=REVISION,
        input_snapshot_sha256="9" * 64,
        target=IDENTITY,
        probe_serial_hash=PROBE_HASH,
        elf_path="build/app.elf",
        elf_sha256="e" * 64,
        build_id="b" * 64,
        inventory_digest=_target_inventory_digest(),
        case_inventory_digest=V2_CASE_INVENTORY_DIGEST,
        protocol="stm32-target-frame/2",
        transport="mailbox",
        transport_config=MAILBOX_PROJECT_CONFIG,
        support_profile=TARGET_SUPPORT,
        cases=(V2_CASE_ID,),
        timeout_ms=1000,
        now=datetime(2026, 8, 25, tzinfo=timezone.utc),
    )

    record = runner.load_prepared(prepared.action_digest).binding
    assert record["protocol"] == "stm32-target-frame/2"
    assert record["case_inventory_digest"] == V2_CASE_INVENTORY_DIGEST
    assert record["inventory_digest"] == _target_inventory_digest()

  run(scenario())


def test_target_runner_rejects_a_synchronous_read_that_crosses_its_deadline(
    tmp_path: Path,
) -> None:
  """A timed-out synchronous target read cannot publish a terminal PASS."""
  class DelayedSyncTransport(FakeTransport):
    def read(self, maximum, deadline):
      self.calls.append(("read", maximum, deadline))
      time.sleep(0.15)
      return self.chunks.pop(0) if self.chunks else b""

  async def scenario() -> None:
    transport = DelayedSyncTransport([valid_target_stream()])
    runner, prepared, instant, probe, evidence_store, _workflow = (
        await _r5_prepared_runner(tmp_path, transport, timeout_ms=100)
    )

    with pytest.raises(target_module.TargetRunError) as caught:
      await runner.run(
          prepared,
          prepared.action_digest,
          current_revision=REVISION,
          current_inventory_digest=TARGET_RUN_INVENTORY_DIGEST,
          now=instant,
      )

    assert caught.value.code == "TEST_TIMEOUT"
    assert transport.calls[-1] == ("close",)
    assert probe.closed
    manifests = evidence_store.root / "manifests"
    assert not manifests.exists() or list(manifests.iterdir()) == []

  run(scenario())


def test_target_discovery_rejects_an_async_read_that_blocks_past_its_deadline(
    tmp_path: Path,
) -> None:
  """An event-loop-blocking async read cannot complete discovery after deadline."""
  class DelayedAsyncTransport(FakeTransport):
    eof = None

    async def read_async(self, maximum, deadline):
      self.calls.append(("read_async", maximum, deadline))
      time.sleep(0.03)
      return self.chunks.pop(0) if self.chunks else b""

  async def scenario() -> None:
    active = DelayedAsyncTransport([_r5_inventory_frame()])
    probe = FakeProbeClient()
    runner = target_module.TargetTestRunner(
        (tmp_path / "blocked-async-discovery" / "runs").absolute(),
        probe,
        FakeFlashWorkflow(),
        lambda _name: active,
    )

    with pytest.raises(target_module.TargetRunError) as caught:
      await _r5_discover(runner, deadline=time.monotonic() + 0.005)

    assert caught.value.code == "TEST_TRANSPORT_UNAVAILABLE"
    assert active.calls[-1] == ("close",)
    assert probe.closed

  run(scenario())


def test_target_runner_rejects_an_async_read_that_blocks_past_its_deadline(
    tmp_path: Path,
) -> None:
  """A blocking async target read cannot publish a terminal PASS after deadline."""
  class DelayedAsyncTransport(FakeTransport):
    async def read_async(self, maximum, deadline):
      self.calls.append(("read_async", maximum, deadline))
      time.sleep(0.15)
      return self.chunks.pop(0) if self.chunks else b""

  async def scenario() -> None:
    transport = DelayedAsyncTransport([valid_target_stream()])
    runner, prepared, instant, probe, evidence_store, _workflow = (
        await _r5_prepared_runner(tmp_path, transport, timeout_ms=100)
    )

    with pytest.raises(target_module.TargetRunError) as caught:
      await runner.run(
          prepared,
          prepared.action_digest,
          current_revision=REVISION,
          current_inventory_digest=TARGET_RUN_INVENTORY_DIGEST,
          now=instant,
      )

    assert caught.value.code == "TEST_TIMEOUT"
    assert transport.calls[-1] == ("close",)
    assert probe.closed
    manifests = evidence_store.root / "manifests"
    assert not manifests.exists() or list(manifests.iterdir()) == []

  run(scenario())


def test_target_runner_rejects_a_post_terminal_identity_that_crosses_deadline(
    tmp_path: Path,
) -> None:
  """RUN cannot publish PASS when final transport binding returns after deadline."""
  class DelayedFinalIdentityTransport(FakeTransport):
    def __init__(self, chunks: list[bytes]) -> None:
      super().__init__(chunks)
      self.identity_calls = 0

    def identity(self):
      self.identity_calls += 1
      if self.identity_calls == 2:
        time.sleep(0.15)
      return super().identity()

  async def scenario() -> None:
    transport = DelayedFinalIdentityTransport([valid_target_stream()])
    runner, prepared, instant, probe, evidence_store, _workflow = (
        await _r5_prepared_runner(tmp_path, transport, timeout_ms=100)
    )

    with pytest.raises(target_module.TargetRunError) as caught:
      await runner.run(
          prepared,
          prepared.action_digest,
          current_revision=REVISION,
          current_inventory_digest=TARGET_RUN_INVENTORY_DIGEST,
          now=instant,
      )

    assert caught.value.code == "TEST_TIMEOUT"
    assert transport.calls[-1] == ("close",)
    assert probe.closed
    manifests = evidence_store.root / "manifests"
    assert not manifests.exists() or list(manifests.iterdir()) == []

  run(scenario())


def test_target_discovery_uses_only_pre_deadline_identity_snapshots_for_no_eof(
    tmp_path: Path,
) -> None:
  """No-EOF collection may validate bytes late but may not start late identity I/O."""
  class NoEofIdentitySnapshotTransport(FakeTransport):
    eof = None

    def __init__(self, chunks: list[bytes]) -> None:
      super().__init__(chunks)
      self.collection_deadline: float | None = None

    def identity(self):
      if (
          self.collection_deadline is not None
          and time.monotonic() >= self.collection_deadline
      ):
        raise AssertionError("identity started after discovery collection deadline")
      return super().identity()

  async def scenario() -> None:
    active = NoEofIdentitySnapshotTransport([_r5_inventory_frame()])
    probe = FakeProbeClient()
    runner = target_module.TargetTestRunner(
        (tmp_path / "snapshot-discovery" / "runs").absolute(),
        probe,
        FakeFlashWorkflow(),
        lambda _name: active,
    )
    deadline = time.monotonic() + 0.03
    active.collection_deadline = deadline

    discovered = await _r5_discover(runner, deadline=deadline)

    assert discovered["inventory"]["case_ids"] == ["suite.case"]
    assert active.calls[-1] == ("close",)
    assert probe.closed

  run(scenario())


def test_target_runner_rejects_a_validator_that_crosses_its_deadline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
  """A late pure validator boundary cannot reach Evidence publication."""
  original_finish = target_module.TargetRunValidator.finish

  def delayed_finish(self):
    time.sleep(0.15)
    return original_finish(self)

  monkeypatch.setattr(target_module.TargetRunValidator, "finish", delayed_finish)

  async def scenario() -> None:
    transport = FakeTransport([valid_target_stream()])
    runner, prepared, instant, probe, evidence_store, _workflow = (
        await _r5_prepared_runner(tmp_path, transport, timeout_ms=100)
    )

    with pytest.raises(target_module.TargetRunError) as caught:
      await runner.run(
          prepared,
          prepared.action_digest,
          current_revision=REVISION,
          current_inventory_digest=TARGET_RUN_INVENTORY_DIGEST,
          now=instant,
      )

    assert caught.value.code == "TEST_TIMEOUT"
    assert transport.calls[-1] == ("close",)
    assert probe.closed
    assert not (evidence_store.root / "manifests").exists()

  run(scenario())


def test_target_runner_rejects_an_evidence_build_that_crosses_its_deadline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
  """A late artifact write may not advance to manifest publication."""
  async def scenario() -> None:
    transport = FakeTransport([valid_target_stream()])
    runner, prepared, instant, probe, evidence_store, _workflow = (
        await _r5_prepared_runner(tmp_path, transport, timeout_ms=100)
    )
    collector = runner._collector
    assert isinstance(collector, target_module.TestArtifactCollector)
    original_write_and_ingest = collector.write_and_ingest

    def delayed_write_and_ingest(*args, **kwargs):
      artifact = original_write_and_ingest(*args, **kwargs)
      time.sleep(0.15)
      return artifact

    monkeypatch.setattr(collector, "write_and_ingest", delayed_write_and_ingest)

    with pytest.raises(target_module.TargetRunError) as caught:
      await runner.run(
          prepared,
          prepared.action_digest,
          current_revision=REVISION,
          current_inventory_digest=TARGET_RUN_INVENTORY_DIGEST,
          now=instant,
      )

    assert caught.value.code == "TEST_TIMEOUT"
    assert transport.calls[-1] == ("close",)
    assert probe.closed
    assert not (evidence_store.root / "manifests").exists()

  run(scenario())


def test_target_runner_rejects_a_cleanup_that_crosses_its_deadline(
    tmp_path: Path,
) -> None:
  """A late successful close does not permit a late PASS envelope."""
  class DelayedCloseTransport(FakeTransport):
    def close(self):
      super().close()
      time.sleep(0.15)

  async def scenario() -> None:
    transport = DelayedCloseTransport([valid_target_stream()])
    runner, prepared, instant, probe, evidence_store, _workflow = (
        await _r5_prepared_runner(tmp_path, transport, timeout_ms=100)
    )

    with pytest.raises(target_module.TargetRunError) as caught:
      await runner.run(
          prepared,
          prepared.action_digest,
          current_revision=REVISION,
          current_inventory_digest=TARGET_RUN_INVENTORY_DIGEST,
          now=instant,
      )

    assert caught.value.code == "TEST_TIMEOUT"
    assert transport.calls[-1] == ("close",)
    assert probe.closed
    assert not (evidence_store.root / "manifests").exists()

  run(scenario())


def test_target_runner_preserves_timeout_when_cleanup_also_fails(
    tmp_path: Path,
) -> None:
  """Cleanup failure is recorded by cleanup, but cannot replace the primary timeout."""
  class DelayedReadTransport(FakeTransport):
    def read(self, maximum, deadline):
      self.calls.append(("read", maximum, deadline))
      time.sleep(0.15)
      return self.chunks.pop(0) if self.chunks else b""

  class FailingProbe(FakeProbeClient):
    def close(self):
      self.calls.append(("close",))
      self.closed = True
      raise OSError("simulated-probe-close-failure")

  async def scenario() -> None:
    transport = DelayedReadTransport([valid_target_stream()])
    probe = FailingProbe()
    runner, prepared, instant, prepared_probe, evidence_store, _workflow = (
        await _r5_prepared_runner(tmp_path, transport, timeout_ms=100, probe=probe)
    )
    assert prepared_probe is probe

    with pytest.raises(target_module.TargetRunError) as caught:
      await runner.run(
          prepared,
          prepared.action_digest,
          current_revision=REVISION,
          current_inventory_digest=TARGET_RUN_INVENTORY_DIGEST,
          now=instant,
      )

    assert caught.value.code == "TEST_TIMEOUT"
    assert any(
        "Target cleanup also failed: TEST_TRANSPORT_UNAVAILABLE" in note
        for note in caught.value.cleanup_notes
    )
    assert transport.calls[-1] == ("close",)
    assert probe.closed
    assert not (evidence_store.root / "manifests").exists()

  run(scenario())


def test_target_runner_bounds_a_hung_async_transport_close_and_attempts_probe_cleanup(
    tmp_path: Path,
) -> None:
  """A cooperative hung transport closer must not require an external timeout."""
  class HungCloseTransport(FakeTransport):
    async def close_async(self):
      self.calls.append(("close",))
      await asyncio.Event().wait()

  async def scenario() -> None:
    transport = HungCloseTransport([valid_target_stream()])
    runner, prepared, instant, probe, evidence_store, _workflow = (
        await _r5_prepared_runner(tmp_path, transport, timeout_ms=30)
    )
    started = time.monotonic()

    with pytest.raises(target_module.TargetRunError) as caught:
      await asyncio.wait_for(
          runner.run(
              prepared,
              prepared.action_digest,
              current_revision=REVISION,
              current_inventory_digest=TARGET_RUN_INVENTORY_DIGEST,
              now=instant,
          ),
          timeout=0.35,
      )

    assert caught.value.code == "TEST_TIMEOUT"
    assert time.monotonic() - started < 0.35
    assert transport.calls[-1] == ("close",)
    assert probe.closed
    assert not (evidence_store.root / "manifests").exists()

  run(scenario())


def test_target_runner_bounds_a_hung_async_probe_close(
    tmp_path: Path,
) -> None:
  """A cooperative hung probe closer must not require an external timeout."""
  class HungProbe(FakeProbeClient):
    async def close(self):
      self.calls.append(("close",))
      await asyncio.Event().wait()

  async def scenario() -> None:
    transport = FakeTransport([valid_target_stream()])
    probe = HungProbe()
    runner, prepared, instant, prepared_probe, evidence_store, _workflow = (
        await _r5_prepared_runner(tmp_path, transport, timeout_ms=30, probe=probe)
    )
    assert prepared_probe is probe
    started = time.monotonic()

    with pytest.raises(target_module.TargetRunError) as caught:
      await asyncio.wait_for(
          runner.run(
              prepared,
              prepared.action_digest,
              current_revision=REVISION,
              current_inventory_digest=TARGET_RUN_INVENTORY_DIGEST,
              now=instant,
          ),
          timeout=0.2,
      )

    assert caught.value.code == "TEST_TIMEOUT"
    assert time.monotonic() - started < 0.2
    assert transport.calls[-1] == ("close",)
    assert probe.calls[-1] == ("close",)
    assert not (evidence_store.root / "manifests").exists()

  run(scenario())


def test_target_runner_bounds_the_total_cleanup_envelope_when_both_closes_hang(
    tmp_path: Path,
) -> None:
  """Both cooperative closers share a finite two-attempt cleanup upper bound."""
  class HungCloseTransport(FakeTransport):
    async def close_async(self):
      self.calls.append(("close",))
      await asyncio.Event().wait()

  class HungProbe(FakeProbeClient):
    async def close(self):
      self.calls.append(("close",))
      await asyncio.Event().wait()

  async def scenario() -> None:
    transport = HungCloseTransport([valid_target_stream()])
    probe = HungProbe()
    runner, prepared, instant, prepared_probe, evidence_store, _workflow = (
        await _r5_prepared_runner(tmp_path, transport, timeout_ms=100, probe=probe)
    )
    assert prepared_probe is probe
    started = time.monotonic()

    with pytest.raises(target_module.TargetRunError) as caught:
      await asyncio.wait_for(
          runner.run(
              prepared,
              prepared.action_digest,
              current_revision=REVISION,
              current_inventory_digest=TARGET_RUN_INVENTORY_DIGEST,
              now=instant,
          ),
          timeout=0.35,
      )

    assert caught.value.code == "TEST_TIMEOUT"
    assert time.monotonic() - started < 0.35
    assert transport.calls[-1] == ("close",)
    assert probe.calls[-1] == ("close",)
    assert not (evidence_store.root / "manifests").exists()

  run(scenario())


def test_target_runner_rejects_an_envelope_commit_that_crosses_its_deadline(
    tmp_path: Path,
) -> None:
  """The store commit guard prevents a late Target Evidence manifest."""
  async def scenario() -> None:
    transport = FakeTransport([valid_target_stream()])
    runner, prepared, instant, probe, evidence_store, _workflow = (
        await _r5_prepared_runner(tmp_path, transport, timeout_ms=100)
    )

    def inject(point: str) -> None:
      if point == "manifest.before_publish":
        time.sleep(0.15)

    evidence_store._fault_injector = inject
    with pytest.raises(target_module.TargetRunError) as caught:
      await runner.run(
          prepared,
          prepared.action_digest,
          current_revision=REVISION,
          current_inventory_digest=TARGET_RUN_INVENTORY_DIGEST,
          now=instant,
      )

    assert caught.value.code == "TEST_TIMEOUT"
    assert transport.calls[-1] == ("close",)
    assert probe.closed
    manifests = evidence_store.root / "manifests"
    assert not manifests.exists() or list(manifests.glob("*.json")) == []

  run(scenario())


def test_target_runner_times_out_a_hung_initial_probe_identity_without_external_cancel(
    tmp_path: Path,
) -> None:
  """RUN consumes its authorization but closes a probe whose first identity never resolves."""
  class HungInitialIdentityProbe(FakeProbeClient):
    async def target_identity(self):
      self.calls.append(("identity",))
      await asyncio.Event().wait()

  async def scenario() -> None:
    transport = FakeTransport([valid_target_stream()])
    probe = HungInitialIdentityProbe()
    runner, prepared, instant, prepared_probe, evidence_store, workflow_calls = (
        await _r5_prepared_runner(
            tmp_path, transport, timeout_ms=5, probe=probe,
        )
    )
    assert prepared_probe is probe

    with pytest.raises(target_module.TargetRunError) as caught:
      await asyncio.wait_for(
          runner.run(
              prepared,
              prepared.action_digest,
              current_revision=REVISION,
              current_inventory_digest=TARGET_RUN_INVENTORY_DIGEST,
              now=instant,
          ),
          timeout=0.35,
      )

    assert caught.value.code == "TEST_TIMEOUT"
    assert workflow_calls == []
    assert transport.calls == []
    assert probe.closed
    assert not (evidence_store.root / "manifests").exists()
    with pytest.raises(target_module.TargetRunError) as reused:
      await runner.run(
          prepared,
          prepared.action_digest,
          current_revision=REVISION,
          current_inventory_digest=TARGET_RUN_INVENTORY_DIGEST,
          now=instant,
      )
    assert reused.value.code == "TEST_AUTHORIZATION_INVALID"

  run(scenario())


def test_target_runner_times_out_a_hung_guarded_flash_without_external_cancel(
    tmp_path: Path,
) -> None:
  """RUN bounds a cooperative flash hang and still attempts both created dependencies."""
  flash_calls = []

  async def never_returning_flash(request):
    flash_calls.append(request)
    await asyncio.Event().wait()

  async def scenario() -> None:
    transport = FakeTransport([valid_target_stream()])
    runner, prepared, instant, probe, evidence_store, _workflow = (
        await _r5_prepared_runner(
            tmp_path,
            transport,
            timeout_ms=100,
            flash_workflow=never_returning_flash,
        )
    )
    started = time.monotonic()

    with pytest.raises(target_module.TargetRunError) as caught:
      await asyncio.wait_for(
          runner.run(
              prepared,
              prepared.action_digest,
              current_revision=REVISION,
              current_inventory_digest=TARGET_RUN_INVENTORY_DIGEST,
              now=instant,
          ),
          timeout=0.35,
      )

    assert caught.value.code == "TEST_TIMEOUT"
    assert time.monotonic() - started < 0.35
    assert len(flash_calls) == 1
    assert transport.calls[-1] == ("close",)
    assert probe.closed
    assert not (evidence_store.root / "manifests").exists()
    with pytest.raises(target_module.TargetRunError) as reused:
      await runner.run(
          prepared,
          prepared.action_digest,
          current_revision=REVISION,
          current_inventory_digest=TARGET_RUN_INVENTORY_DIGEST,
          now=instant,
      )
    assert reused.value.code == "TEST_AUTHORIZATION_INVALID"

  run(scenario())


def test_target_runner_rejects_a_guarded_flash_that_blocks_before_its_first_await(
    tmp_path: Path,
) -> None:
  """A late async flash return cannot start another live identity call or publish PASS."""
  flash_calls = []

  async def blocked_before_first_await_flash(request):
    flash_calls.append(request)
    time.sleep(0.15)
    await asyncio.sleep(0)
    return OperationResult.success("stm32_flash", {"status": "success"})

  async def scenario() -> None:
    transport = FakeTransport([valid_target_stream()])
    runner, prepared, instant, probe, evidence_store, _workflow = (
        await _r5_prepared_runner(
            tmp_path,
            transport,
            timeout_ms=100,
            flash_workflow=blocked_before_first_await_flash,
        )
    )

    with pytest.raises(target_module.TargetRunError) as caught:
      await runner.run(
          prepared,
          prepared.action_digest,
          current_revision=REVISION,
          current_inventory_digest=TARGET_RUN_INVENTORY_DIGEST,
          now=instant,
      )

    assert caught.value.code == "TEST_TIMEOUT"
    assert len(flash_calls) == 1
    assert probe.calls == [("identity",), ("close",)]
    assert transport.calls[-1] == ("close",)
    assert not (evidence_store.root / "manifests").exists()

  run(scenario())


def test_target_runner_keeps_an_authorized_guarded_flash_success_before_deadline(
    tmp_path: Path,
) -> None:
  """The run deadline guard preserves normal one-shot guarded-flash success."""
  async def scenario() -> None:
    transport = FakeTransport([valid_target_stream()])
    runner, prepared, instant, probe, evidence_store, workflow_calls = (
        await _r5_prepared_runner(tmp_path, transport)
    )

    result = await runner.run(
        prepared,
        prepared.action_digest,
        current_revision=REVISION,
        current_inventory_digest=TARGET_RUN_INVENTORY_DIGEST,
        now=instant,
    )

    assert result["test_manifest"].state == "passed"
    assert len(workflow_calls) == 1
    assert transport.calls[-1] == ("close",)
    assert probe.closed
    assert evidence_store.get_envelope(result["evidence"].evidence_id) == result["evidence"]

  run(scenario())


def test_target_runner_prefers_timeout_when_initial_identity_raises_after_deadline(
    tmp_path: Path,
) -> None:
  """An initial probe exception after the RUN deadline is a closed timeout, not raw I/O."""
  class LateInitialIdentityProbe(FakeProbeClient):
    async def target_identity(self):
      self.calls.append(("identity",))
      time.sleep(0.15)
      raise OSError("late initial identity")

  async def scenario() -> None:
    transport = FakeTransport([valid_target_stream()])
    probe = LateInitialIdentityProbe()
    runner, prepared, instant, prepared_probe, evidence_store, workflow_calls = (
        await _r5_prepared_runner(
            tmp_path, transport, timeout_ms=100, probe=probe,
        )
    )
    assert prepared_probe is probe

    with pytest.raises(target_module.TargetRunError) as caught:
      await runner.run(
          prepared,
          prepared.action_digest,
          current_revision=REVISION,
          current_inventory_digest=TARGET_RUN_INVENTORY_DIGEST,
          now=instant,
      )

    assert caught.value.code == "TEST_TIMEOUT"
    assert workflow_calls == []
    assert transport.calls == []
    assert probe.closed
    assert not (evidence_store.root / "manifests").exists()
    with pytest.raises(target_module.TargetRunError) as reused:
      await runner.run(
          prepared,
          prepared.action_digest,
          current_revision=REVISION,
          current_inventory_digest=TARGET_RUN_INVENTORY_DIGEST,
          now=instant,
      )
    assert reused.value.code == "TEST_AUTHORIZATION_INVALID"

  run(scenario())


def test_target_runner_prefers_timeout_when_guarded_flash_raises_after_deadline(
    tmp_path: Path,
) -> None:
  """A late guarded-flash I/O error cannot replace the authorized RUN timeout."""
  flash_calls = []

  async def late_flash_failure(request):
    flash_calls.append(request)
    time.sleep(0.15)
    raise OSError("late flash")

  async def scenario() -> None:
    transport = FakeTransport([valid_target_stream()])
    runner, prepared, instant, probe, evidence_store, _workflow = (
        await _r5_prepared_runner(
            tmp_path,
            transport,
            timeout_ms=100,
            flash_workflow=late_flash_failure,
        )
    )

    with pytest.raises(target_module.TargetRunError) as caught:
      await runner.run(
          prepared,
          prepared.action_digest,
          current_revision=REVISION,
          current_inventory_digest=TARGET_RUN_INVENTORY_DIGEST,
          now=instant,
      )

    assert caught.value.code == "TEST_TIMEOUT"
    assert len(flash_calls) == 1
    assert transport.calls[-1] == ("close",)
    assert probe.closed
    assert not (evidence_store.root / "manifests").exists()

  run(scenario())


def test_target_runner_prefers_timeout_when_post_flash_identity_raises_after_deadline(
    tmp_path: Path,
) -> None:
  """A post-flash identity I/O error after expiry cannot escape the closed protocol."""
  class LatePostFlashIdentityProbe(FakeProbeClient):
    async def target_identity(self):
      self.calls.append(("identity",))
      if len([call for call in self.calls if call == ("identity",)]) == 2:
        time.sleep(0.15)
        raise OSError("late post-flash identity")
      return dict(self.identity)

  async def scenario() -> None:
    transport = FakeTransport([valid_target_stream()])
    probe = LatePostFlashIdentityProbe()
    runner, prepared, instant, prepared_probe, evidence_store, workflow_calls = (
        await _r5_prepared_runner(
            tmp_path, transport, timeout_ms=100, probe=probe,
        )
    )
    assert prepared_probe is probe

    with pytest.raises(target_module.TargetRunError) as caught:
      await runner.run(
          prepared,
          prepared.action_digest,
          current_revision=REVISION,
          current_inventory_digest=TARGET_RUN_INVENTORY_DIGEST,
          now=instant,
      )

    assert caught.value.code == "TEST_TIMEOUT"
    assert len(workflow_calls) == 1
    assert transport.calls[-1] == ("close",)
    assert probe.closed
    assert not (evidence_store.root / "manifests").exists()

  run(scenario())


def test_target_runner_prefers_timeout_when_factory_raises_after_deadline(
    tmp_path: Path,
) -> None:
  """A synchronous factory failure after expiry maps to the authoritative RUN timeout."""
  def late_factory(_name):
    time.sleep(0.15)
    raise OSError("late factory")

  async def scenario() -> None:
    transport = FakeTransport([valid_target_stream()])
    runner, prepared, instant, probe, evidence_store, workflow_calls = (
        await _r5_prepared_runner(
            tmp_path,
            transport,
            timeout_ms=100,
            transport_factory=late_factory,
        )
    )

    with pytest.raises(target_module.TargetRunError) as caught:
      await runner.run(
          prepared,
          prepared.action_digest,
          current_revision=REVISION,
          current_inventory_digest=TARGET_RUN_INVENTORY_DIGEST,
          now=instant,
      )

    assert caught.value.code == "TEST_TIMEOUT"
    assert workflow_calls == []
    assert transport.calls == []
    assert probe.closed
    assert not (evidence_store.root / "manifests").exists()

  run(scenario())


@pytest.mark.parametrize("outcome", ["return", "raise"])
def test_target_runner_prefers_timeout_for_a_late_synchronous_transport_open(
    tmp_path: Path, outcome: str,
) -> None:
  """A synchronous transport open cannot return or raise past the RUN deadline."""
  class LateOpenTransport(FakeTransport):
    def open(self, config, deadline):
      super().open(config, deadline)
      time.sleep(0.15)
      if outcome == "raise":
        raise OSError("late transport open")

  async def scenario() -> None:
    transport = LateOpenTransport([valid_target_stream()])
    runner, prepared, instant, probe, evidence_store, workflow_calls = (
        await _r5_prepared_runner(tmp_path, transport, timeout_ms=100)
    )

    with pytest.raises(target_module.TargetRunError) as caught:
      await runner.run(
          prepared,
          prepared.action_digest,
          current_revision=REVISION,
          current_inventory_digest=TARGET_RUN_INVENTORY_DIGEST,
          now=instant,
      )

    assert caught.value.code == "TEST_TIMEOUT"
    assert len(workflow_calls) == 1
    assert transport.calls[-1] == ("close",)
    assert probe.closed
    assert not (evidence_store.root / "manifests").exists()

  run(scenario())


@pytest.mark.parametrize("outcome", ["return", "raise"])
def test_target_runner_prefers_timeout_for_a_late_synchronous_initial_identity(
    tmp_path: Path, outcome: str,
) -> None:
  """A synchronous initial identity call cannot return or raise after expiry."""
  class LateInitialIdentityProbe(FakeProbeClient):
    def target_identity(self):
      self.calls.append(("identity",))
      time.sleep(0.15)
      if outcome == "raise":
        raise OSError("late initial identity")
      return dict(self.identity)

  async def scenario() -> None:
    transport = FakeTransport([valid_target_stream()])
    probe = LateInitialIdentityProbe()
    runner, prepared, instant, prepared_probe, evidence_store, workflow_calls = (
        await _r5_prepared_runner(
            tmp_path, transport, timeout_ms=100, probe=probe,
        )
    )
    assert prepared_probe is probe

    with pytest.raises(target_module.TargetRunError) as caught:
      await runner.run(
          prepared,
          prepared.action_digest,
          current_revision=REVISION,
          current_inventory_digest=TARGET_RUN_INVENTORY_DIGEST,
          now=instant,
      )

    assert caught.value.code == "TEST_TIMEOUT"
    assert workflow_calls == []
    assert transport.calls == []
    assert probe.closed
    assert not (evidence_store.root / "manifests").exists()

  run(scenario())


@pytest.mark.parametrize("outcome", ["return", "raise"])
def test_target_runner_prefers_timeout_for_a_late_synchronous_post_flash_identity(
    tmp_path: Path, outcome: str,
) -> None:
  """A synchronous post-flash identity cannot return or raise after expiry."""
  class LatePostFlashIdentityProbe(FakeProbeClient):
    def target_identity(self):
      self.calls.append(("identity",))
      if len([call for call in self.calls if call == ("identity",)]) == 2:
        time.sleep(0.15)
        if outcome == "raise":
          raise OSError("late post-flash identity")
      return dict(self.identity)

  async def scenario() -> None:
    transport = FakeTransport([valid_target_stream()])
    probe = LatePostFlashIdentityProbe()
    runner, prepared, instant, prepared_probe, evidence_store, workflow_calls = (
        await _r5_prepared_runner(
            tmp_path, transport, timeout_ms=100, probe=probe,
        )
    )
    assert prepared_probe is probe

    with pytest.raises(target_module.TargetRunError) as caught:
      await runner.run(
          prepared,
          prepared.action_digest,
          current_revision=REVISION,
          current_inventory_digest=TARGET_RUN_INVENTORY_DIGEST,
          now=instant,
      )

    assert caught.value.code == "TEST_TIMEOUT"
    assert len(workflow_calls) == 1
    assert transport.calls[-1] == ("close",)
    assert probe.closed
    assert not (evidence_store.root / "manifests").exists()

  run(scenario())


@pytest.mark.parametrize("outcome", ["return", "raise"])
def test_target_runner_prefers_timeout_for_a_late_synchronous_transport_identity(
    tmp_path: Path, outcome: str,
) -> None:
  """A synchronous transport identity cannot return or raise after expiry."""
  class LateTransportIdentity(FakeTransport):
    def identity(self):
      time.sleep(0.15)
      if outcome == "raise":
        raise OSError("late transport identity")
      return super().identity()

  async def scenario() -> None:
    transport = LateTransportIdentity([valid_target_stream()])
    runner, prepared, instant, probe, evidence_store, workflow_calls = (
        await _r5_prepared_runner(tmp_path, transport, timeout_ms=100)
    )

    with pytest.raises(target_module.TargetRunError) as caught:
      await runner.run(
          prepared,
          prepared.action_digest,
          current_revision=REVISION,
          current_inventory_digest=TARGET_RUN_INVENTORY_DIGEST,
          now=instant,
      )

    assert caught.value.code == "TEST_TIMEOUT"
    assert len(workflow_calls) == 1
    assert transport.calls[-1] == ("close",)
    assert probe.closed
    assert not (evidence_store.root / "manifests").exists()

  run(scenario())
