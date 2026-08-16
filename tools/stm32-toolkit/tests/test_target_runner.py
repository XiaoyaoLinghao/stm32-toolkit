from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
import time

import pytest

from stm32_toolkit.probe import client as probe_client
from stm32_toolkit.testing import target as target_module

ProbeClientError = probe_client.ProbeClientError


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


def test_control_prepare_binds_snapshot_and_execute_consumes_before_denial(tmp_path: Path):
  async def scenario():
    probe = FakeProbeClient()
    auth = getattr(probe_client, "ControlAuthorizationClient")(tmp_path / "control", probe)
    prepared = await auth.prepare(
        workspace_id="workspace-a", project_id="project-a", session_id="session-a",
        revision="rev-a", target=IDENTITY, firmware={"build_id": "b" * 64, "elf_sha256": "e" * 64},
        operation="target.resume", arguments={}, now=datetime(2026, 8, 16, tzinfo=timezone.utc),
    )
    assert len(prepared.nonce) == 64
    assert prepared.expires_at_utc <= datetime(2026, 8, 16, tzinfo=timezone.utc) + timedelta(minutes=5)
    assert probe.calls == [("identity",), ("state",)]

    with pytest.raises(ProbeClientError) as denied:
        await auth.execute(prepared, "0" * 64, now=datetime(2026, 8, 16, tzinfo=timezone.utc))
    assert denied.value.code == "PROBE_AUTHORIZATION_INVALID"
    assert probe.closed

    with pytest.raises(ProbeClientError) as reused:
        await auth.execute(prepared, prepared.action_digest, now=datetime(2026, 8, 16, tzinfo=timezone.utc))
    assert reused.value.code == "PROBE_AUTHORIZATION_INVALID"
  run(scenario())


class FakeFlashWorkflow:
    def __init__(self) -> None:
        self.calls = []

    async def run_authorized(self, **binding):
        self.calls.append(binding)
        return {"status": "success"}


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


def test_target_runner_success_persists_three_manifests_and_guarded_flash(tmp_path: Path):
  async def scenario():
    probe = FakeProbeClient()
    flash = FakeFlashWorkflow()
    transport = FakeTransport([b"raw", b""])
    runner = target_module.TargetTestRunner(tmp_path / "runs", probe, flash, lambda name: transport)
    instant = datetime.now(timezone.utc)
    prepared = await runner.prepare(
        workspace_id="workspace-a", project_id="project-a", session_id="session-a", revision="rev-a",
        target=IDENTITY, probe_serial_hash="1" * 64, elf_path="build/app.elf", elf_sha256="e" * 64,
        build_id="b" * 64, inventory_digest="a" * 64, transport="mailbox",
        transport_config={"target_id": "target-a"}, cases=("suite.case",), timeout_ms=1000, now=instant,
    )
    before_deadline = time.monotonic()
    result = await runner.run(
        prepared, prepared.action_digest, current_revision="rev-a", current_inventory_digest="a" * 64, now=instant,
    )
    run_root = tmp_path / "runs" / prepared.action_digest
    assert result["schema"] == "stm32-target-evidence/1"
    assert (run_root / "target-stream.bin").read_bytes() == b"raw"
    assert (run_root / "test-manifest.json").is_file()
    assert (run_root / "evidence-manifest.json").is_file()
    assert len(flash.calls) == 1
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
  run(scenario())


def test_control_authorization_rejects_naive_invalid_and_changed_snapshot(tmp_path: Path):
  async def scenario():
    probe = FakeProbeClient()
    auth = probe_client.ControlAuthorizationClient(tmp_path / "control", probe)
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
    prepared = await auth.prepare(**common, now=datetime(2026, 8, 16, tzinfo=timezone.utc))
    probe.state["state"] = "running"
    with pytest.raises(ProbeClientError) as changed:
      await auth.execute(prepared, prepared.action_digest, now=datetime(2026, 8, 16, tzinfo=timezone.utc))
    assert changed.value.code == "PROBE_IDENTITY_MISMATCH"
    assert probe.closed
  run(scenario())
