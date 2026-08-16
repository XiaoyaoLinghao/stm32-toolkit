from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
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


def valid_target_stream() -> bytes:
    identity = {
        "workspace_id": WORKSPACE_ID, "project_id": PROJECT_ID, "session_id": SESSION_ID,
        "build_id": "b" * 64, "elf_sha256": "e" * 64, "target_device": "target-a",
        "input_snapshot_sha256": "a" * 64, "git_commit": REVISION, "git_dirty": False,
    }
    bodies = [
        (1, {"mode": "target", "identity": identity, "case_ids": ["suite.case"], "inventory_digest": "a" * 64, "discovered_at_utc": "2026-08-16T00:00:00.000000Z"}),
        (2, {"run_id": "run-1", "started_at_utc": "2026-08-16T00:00:00.000000Z", "case_ids": ["suite.case"], "inventory_digest": "a" * 64}),
        (3, {"case_id": "suite.case", "started_at_utc": "2026-08-16T00:00:00.000000Z"}),
        (4, {"case_id": "suite.case", "state": "passed", "ended_at_utc": "2026-08-16T00:00:01.000000Z", "duration_ms": 1000, "message": None, "stdout": None, "stderr": None}),
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
    def identity(self): return {"target_id": "target-a", "transport": "mailbox"}


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
        inventory_digest="a" * 64, transport="mailbox", transport_config={"address": 0x20000000},
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
        transport_config={"target_id": "target-a"}, cases=("suite.case",), timeout_ms=1000, now=instant,
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
        build_id="b" * 64, inventory_digest="a" * 64, transport="mailbox", transport_config={},
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
        inventory_digest="a" * 64, transport="mailbox", transport_config={}, cases=("c",), timeout_ms=True,
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
      "transport": "mailbox", "transport_config": {}, "cases": ["suite.case"],
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
    digest = sha256(raw).hexdigest()
    corrupt_store._path(digest, "prepared").write_bytes(raw)
    with pytest.raises(ControlAuthorizationError) as corrupt:
      corrupt_store.consume(
          digest, operation="target.resume", arguments={}, workspace_id="workspace-a",
          session_id="session-a", identity=IDENTITY, state=STATE, now=instant,
      )
    assert corrupt.value.code == "PROBE_AUTHORIZATION_INVALID"


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
        "transport_config": {}, "cases": ["suite.case"], "timeout_ms": 1000,
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
        inventory_digest="a" * 64, transport="mailbox", transport_config={},
        cases=("suite.case",), timeout_ms=1000, now=instant,
    )
    with pytest.raises(Exception):
      await runner.run(
          prepared, prepared.action_digest, current_revision="rev-a",
          current_inventory_digest="a" * 64, now=instant,
      )
    assert not (tmp_path / "runs" / prepared.action_digest / "test-manifest.json").exists()

  run(scenario())
