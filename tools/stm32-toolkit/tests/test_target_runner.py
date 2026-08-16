from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
import os
import shutil
import subprocess
import sys
import time

import pytest
from stm32_toolkit.result import OperationResult

from stm32_toolkit.probe import client as probe_client
from stm32_toolkit.probe.authorization import ControlAuthorizationStore
from stm32_toolkit.testing import target as target_module

ProbeClientError = probe_client.ProbeClientError

WORKSPACE_ID = "0" * 64
PROJECT_ID = "123e4567-e89b-42d3-a456-426614174000"
SESSION_ID = "session-0601-t09"
REVISION = "c" * 40


IDENTITY = {
    "board_id": "board-a",
    "mcu": "stm32f407vg",
    "target_id": "target-a",
    "probe_serial_hash": "1" * 64,
}
STATE = {"state": "halted", "reason": "requested"}
MAILBOX_PROJECT_CONFIG = {
    "kind": "memory-mailbox", "options": {"address": 0x20000000, "size": 4096},
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


def valid_target_stream(case_id: str = "suite.case") -> bytes:
    identity = {
        "workspace_id": WORKSPACE_ID, "project_id": PROJECT_ID, "session_id": SESSION_ID,
        "build_id": "b" * 64, "elf_sha256": "e" * 64, "target_device": "target-a",
        "input_snapshot_sha256": "a" * 64, "git_commit": REVISION, "git_dirty": False,
    }
    bodies = [
        (1, {"mode": "target", "identity": identity, "case_ids": [case_id], "inventory_digest": "a" * 64, "discovered_at_utc": "2026-08-16T00:00:00.000000Z"}),
        (2, {"run_id": "run-1", "started_at_utc": "2026-08-16T00:00:00.000000Z", "case_ids": [case_id], "inventory_digest": "a" * 64}),
        (3, {"case_id": case_id, "started_at_utc": "2026-08-16T00:00:00.000000Z"}),
        (4, {"case_id": case_id, "state": "passed", "ended_at_utc": "2026-08-16T00:00:01.000000Z", "duration_ms": 1000, "message": None, "stdout": None, "stderr": None}),
    ]
    frames = [target_module.encode_frame(kind, sequence, body) for sequence, (kind, body) in enumerate(bodies)]
    terminal = {
        "state": "passed", "ended_at_utc": "2026-08-16T00:00:01.000000Z", "duration_ms": 1000,
        "inventory_digest": "a" * 64, "build_id": "b" * 64, "elf_sha256": "e" * 64,
        "target_device": "target-a", "counts": {"passed": 1, "failed": 0, "skipped": 0, "error": 0, "timeout": 0},
        "event_stream_digest": sha256(b"".join(frames)).hexdigest(),
    }
    frames.append(target_module.encode_frame(5, len(frames), terminal))
    return b"".join(frames)


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

    def open(self, config, deadline): self.calls.append(("open", dict(config), deadline))
    def read(self, maximum, deadline):
        self.calls.append(("read", maximum, deadline))
        return self.chunks.pop(0) if self.chunks else b""
    def close(self): self.calls.append(("close",))
    def identity(self):
        return {
            "probe_id": "probe-a", "target_id": "target-a", "transport": "mailbox",
            "config_digest": "d" * 64, "address": "0x20000000", "ring_size": "4096",
            "ram_bounds": "0x20000000+0x00010000",
        }


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
        revision="rev-a", target=IDENTITY, probe_serial_hash="1" * 64,
        elf_path="build/app.elf", elf_sha256="e" * 64, build_id="b" * 64,
        inventory_digest="a" * 64, transport="mailbox", cases=("suite.case",),
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
    prepared = await exact_runner.prepare(
        transport_config={"kind": "memory-mailbox", "options": {"address": 0x20000000, "size": 4096}},
        **common,
    )
    with pytest.raises(target_module.TargetRunError) as mismatch:
      await exact_runner.run(
          prepared, prepared.action_digest, current_revision="rev-a",
          current_inventory_digest="a" * 64,
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
        revision="rev-a", target=IDENTITY, probe_serial_hash="1" * 64,
        elf_path="build/app.elf", elf_sha256="e" * 64, build_id="b" * 64,
        inventory_digest="a" * 64, transport="mailbox", transport_config=MAILBOX_PROJECT_CONFIG,
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
    transport = FakeTransport([b""])
    runner = getattr(target_module, "TargetTestRunner")(tmp_path / "runs", probe, flash, lambda name: transport)
    discovered = await runner.discover(
        transport="mailbox", config={"target_id": "target-a"}, deadline=1.0,
        expected_identity=IDENTITY,
    )
    assert discovered["identity"]["target_id"] == "target-a"
    assert transport.calls == [("open", {"target_id": "target-a"}, 1.0), ("read", 65536, 1.0), ("close",)]
    assert not flash.calls
  run(scenario())


def test_discovery_async_transport_composition_rejects_identity_and_nonbytes(tmp_path: Path):
  class AsyncTransport(FakeTransport):
    def __init__(self, raw=b"inventory", identity=None):
      super().__init__([])
      self.raw = raw
      self.transport_identity = identity or {"target_id": "target-a"}
    async def open(self, config, deadline): self.calls.append(("open", config, deadline))
    async def read_async(self, maximum, deadline): self.calls.append(("read", maximum, deadline)); return self.raw
    async def close_async(self): self.calls.append(("close",))
    def identity(self): return self.transport_identity

  async def scenario():
    active = AsyncTransport()
    runner = target_module.TargetTestRunner(
        (tmp_path / "success").absolute(), FakeProbeClient(), FakeFlashWorkflow(), lambda name: active,
    )
    assert (await runner.discover(
        transport="mailbox", config={}, deadline=1.0, expected_identity=IDENTITY,
    ))["raw"] == b"inventory"
    assert active.calls == [("open", {}, 1.0), ("read", 65536, 1.0), ("close",)]

    for index, probe_identity, raw, transport_identity in (
        (0, {**IDENTITY, "target_id": "other"}, b"x", {"target_id": "target-a"}),
        (1, IDENTITY, "not-bytes", {"target_id": "target-a"}),
        (2, IDENTITY, b"x", {"target_id": "other"}),
    ):
      probe = FakeProbeClient()
      probe.identity = probe_identity
      invalid = AsyncTransport(raw, transport_identity)
      candidate = target_module.TargetTestRunner(
          (tmp_path / f"invalid-{index}").absolute(), probe, FakeFlashWorkflow(), lambda name, item=invalid: item,
      )
      with pytest.raises(target_module.TargetRunError) as caught:
        await candidate.discover(
            transport="mailbox", config={}, deadline=1.0, expected_identity=IDENTITY,
        )
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
        target=IDENTITY, probe_serial_hash="1" * 64, elf_path="build/app.elf", elf_sha256="e" * 64,
        build_id="b" * 64, inventory_digest="a" * 64, transport="mailbox",
        transport_config=MAILBOX_PROJECT_CONFIG, cases=("suite.case",), timeout_ms=1000, now=instant,
    )
    before_deadline = time.monotonic()
    result = await runner.run(
        prepared, prepared.action_digest, current_revision=REVISION, current_inventory_digest="a" * 64, now=instant,
    )
    assert isinstance(result["test_manifest"], TestRunManifest)
    assert result["test_manifest"].schema == "stm32-test/1"
    assert result["test_manifest"].state == "passed"
    assert [case.case_id for case in result["test_manifest"].cases] == ["suite.case"]
    assert isinstance(result["evidence"], EvidenceEnvelope)
    assert evidence_store.get_envelope(str(result["evidence"].evidence_id)) == result["evidence"]
    assert {artifact.kind for artifact in result["evidence"].artifacts} == {"test-events", "test-manifest"}
    assert len(workflow_calls) == 1
    assert transport.calls[0][2] > before_deadline
    assert transport.calls[-1] == ("close",)
    assert probe.closed
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
        target=IDENTITY, probe_serial_hash="1" * 64, elf_path="build/app.elf", elf_sha256="e" * 64,
        build_id="b" * 64, inventory_digest="a" * 64, transport="mailbox", transport_config=MAILBOX_PROJECT_CONFIG,
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
        probe_serial_hash="1" * 64, elf_path="a.elf", elf_sha256="e" * 64, build_id="b" * 64,
        inventory_digest="a" * 64, transport="mailbox", transport_config=MAILBOX_PROJECT_CONFIG, cases=("c",), timeout_ms=True,
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


def test_target_prepared_record_closed_validation_rejects_each_identity_and_limit_boundary():
  valid = {
      "workspace_id": "w", "project_id": "p", "session_id": "s", "revision": "r",
      "target": IDENTITY, "probe_serial_hash": "1" * 64, "elf_path": "a.elf",
      "elf_sha256": "e" * 64, "build_id": "b" * 64, "inventory_digest": "a" * 64,
      "transport": "mailbox", "transport_config": MAILBOX_PROJECT_CONFIG, "cases": ["suite.case"],
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
      await auth.prepare(**{**common, "operation": "target.reset"}, now=datetime(2026, 8, 16, tzinfo=timezone.utc))
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
      {**base, "operation": "target.reset"},
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

  changed_store = ControlAuthorizationStore((tmp_path / "authority-create-race" / "control").absolute())
  parent_store = changed_store._parent_store()
  with parent_store._mutation_lock():
    pass
  monkeypatch.setattr(parent_store, "_atomic_create_new", lambda *args, **kwargs: False)
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
import json, pathlib, sys
from datetime import datetime, timezone
from stm32_toolkit.probe.authorization import ControlAuthorizationError, ControlAuthorizationStore
root=pathlib.Path(sys.argv[1]); digest=sys.argv[2]
identity=json.loads(sys.argv[3]); state=json.loads(sys.argv[4])
try:
    ControlAuthorizationStore(root).consume(digest, operation='target.resume', arguments={}, workspace_id='workspace-a', session_id='session-a', identity=identity, state=state, now=datetime(2026,8,16,tzinfo=timezone.utc))
except ControlAuthorizationError:
    raise SystemExit(3)
"""
  arguments = [str(root), prepared.action_digest, __import__("json").dumps(IDENTITY), __import__("json").dumps(STATE)]
  children = [subprocess.Popen([sys.executable, "-c", script, *arguments]) for _ in range(2)]
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
        "probe_serial_hash": "1" * 64, "elf_path": "build/app.elf",
        "elf_sha256": "e" * 64, "build_id": "b" * 64,
        "inventory_digest": "a" * 64, "transport": "mailbox",
        "transport_config": MAILBOX_PROJECT_CONFIG, "cases": ["suite.case"], "timeout_ms": 1000,
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
        revision="rev-a", target=IDENTITY, probe_serial_hash="1" * 64,
        elf_path="build/app.elf", elf_sha256="e" * 64, build_id="b" * 64,
        inventory_digest="a" * 64, transport="mailbox", transport_config=MAILBOX_PROJECT_CONFIG,
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
        ("mailbox", {"probe_id": "probe-a", "target_id": "target-a", "transport": "mailbox", "config_digest": "d" * 64, "address": "0x20000000", "ring_size": "4096", "ram_bounds": "0x20000000+0x00010000"}),
        ("rtt", {"probe_id": "probe-a", "target_id": "target-a", "transport": "rtt", "config_digest": "d" * 64, "channel": "0", "control_block_address": "0x20000100", "ram_bounds": "0x20000000+0x00010000"}),
        ("uart", {"probe_id": "probe-a", "target_id": "target-a", "transport": "uart", "config_digest": "d" * 64, "port": "COM3", "baud": "115200", "data_bits": "8", "parity": "N", "stop_bits": "1", "flow_control": "xonxoff=0,rtscts=0,dsrdtr=0"}),
        ("semihosting", {"probe_id": "probe-a", "target_id": "target-a", "transport": "semihosting", "config_digest": "d" * 64, "elf_path": "C:\\work\\app.elf", "elf_sha256": "e" * 64, "host_file_policy": "deny"}),
    ],
)
def test_closed_transport_identity_accepts_each_task8_production_shape(transport, identity):
  binding = {"target": {"target_id": "target-a"}, "transport": transport}
  assert target_module._closed_transport_identity(identity, binding) == identity


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
