from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from stm32_toolkit.testing import target as target_module
from stm32_toolkit.testing.protocol import calculate_case_inventory_digest
from test_target_runner import (
    IDENTITY,
    MAILBOX_PROJECT_CONFIG,
    PROBE_HASH,
    PROJECT_ID,
    REVISION,
    SESSION_ID,
    TARGET_RUN_INVENTORY_DIGEST,
    TARGET_SUPPORT,
    V2_CASE_ID,
    V2_CASE_INVENTORY_DIGEST,
    WORKSPACE_ID,
    FakeFlashWorkflow,
    FakeProbeClient,
)

PREPARE_AT = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)
INPUT_SNAPSHOT_SHA256 = "9" * 64


def _valid_binding(transport: str) -> dict[str, object]:
    transport_configs = {
        "mailbox": MAILBOX_PROJECT_CONFIG,
        "rtt": {
            "kind": "rtt",
            "options": {"channel": 0, "controlBlockAddress": 0x20000100},
        },
        "uart": {"kind": "uart", "options": {"port": "COM3", "baud": 115200}},
        "semihosting": {"kind": "semihosting", "options": {}},
    }
    return {
        "workspace_id": WORKSPACE_ID,
        "project_id": PROJECT_ID,
        "session_id": SESSION_ID,
        "revision": REVISION,
        "target": deepcopy(IDENTITY),
        "probe_serial_hash": PROBE_HASH,
        "elf_path": "build/app.elf",
        "elf_sha256": "e" * 64,
        "build_id": "b" * 64,
        "inventory_digest": TARGET_RUN_INVENTORY_DIGEST,
        "protocol": "stm32-target-frame/2",
        "case_inventory_digest": V2_CASE_INVENTORY_DIGEST,
        "git_dirty": False,
        "input_snapshot_sha256": INPUT_SNAPSHOT_SHA256,
        "transport": transport,
        "transport_config": deepcopy(transport_configs[transport]),
        "support_profile": deepcopy(TARGET_SUPPORT),
        "cases": (V2_CASE_ID,),
        "timeout_ms": 1_000,
    }


def _invalid_binding(case_id: str) -> tuple[dict[str, object], str, str]:
    if case_id == "malformed-case-inventory-digest":
        binding = _valid_binding("mailbox")
        binding["case_inventory_digest"] = "not-a-digest"
        return binding, "TEST_PROTOCOL_INVALID", "case_inventory_digest is invalid"
    if case_id == "different-valid-case-inventory-digest":
        binding = _valid_binding("mailbox")
        binding["case_inventory_digest"] = calculate_case_inventory_digest(
            ["suite.other"]
        )
        return binding, "TEST_INVENTORY_CHANGED", "Target case inventory changed"
    if case_id == "non-boolean-git-dirty":
        binding = _valid_binding("mailbox")
        binding["git_dirty"] = 0
        return binding, "TEST_PROTOCOL_INVALID", "git_dirty is invalid"
    if case_id == "malformed-input-snapshot-digest":
        binding = _valid_binding("mailbox")
        binding["input_snapshot_sha256"] = "not-a-digest"
        return binding, "TEST_PROTOCOL_INVALID", "Target run binding is invalid"
    if case_id == "rtt-channel-mismatch":
        binding = _valid_binding("rtt")
        binding["transport_config"] = {
            "kind": "rtt",
            "options": {"channel": 1, "controlBlockAddress": 0x20000100},
        }
        return binding, "TEST_PROTOCOL_INVALID", "Target run binding is invalid"
    if case_id == "uart-baud-mismatch":
        binding = _valid_binding("uart")
        binding["transport_config"] = {
            "kind": "uart",
            "options": {"port": "COM3", "baud": 9600},
        }
        return binding, "TEST_PROTOCOL_INVALID", "Target run binding is invalid"
    if case_id == "semihosting-runtime-elf-mismatch":
        binding = _valid_binding("semihosting")
        support = deepcopy(binding["support_profile"])
        assert isinstance(support, dict)
        runtime = deepcopy(support["semihosting_runtime"])
        assert isinstance(runtime, dict)
        runtime["elf_sha256"] = "f" * 64
        support["semihosting_runtime"] = runtime
        binding["support_profile"] = support
        return binding, "TEST_PROTOCOL_INVALID", "Target run binding is invalid"
    raise AssertionError(f"unknown target-prepare identity case: {case_id}")


def _persisted_snapshot(root: Path) -> dict[str, tuple[str, bytes | None]]:
    if not root.exists():
        return {}
    snapshot: dict[str, tuple[str, bytes | None]] = {}
    paths = sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix())
    for path in paths:
        relative = path.relative_to(root).as_posix()
        if path.is_dir():
            snapshot[relative] = ("directory", None)
        elif path.is_file():
            snapshot[relative] = ("file", path.read_bytes())
        else:
            snapshot[relative] = ("other", None)
    return snapshot


@pytest.mark.parametrize(
    "case_id",
    [
        "malformed-case-inventory-digest",
        "different-valid-case-inventory-digest",
        "non-boolean-git-dirty",
        "malformed-input-snapshot-digest",
        "rtt-channel-mismatch",
        "uart-baud-mismatch",
        "semihosting-runtime-elf-mismatch",
    ],
)
def test_public_target_prepare_rejects_identity_without_authority_mutation(
    tmp_path: Path, case_id: str
) -> None:
    async def scenario() -> None:
        invalid_binding, expected_code, expected_message = _invalid_binding(case_id)
        transport_factory_calls: list[str] = []

        def transport_factory(name: str) -> object:
            transport_factory_calls.append(name)
            return object()

        probe = FakeProbeClient()
        flash = FakeFlashWorkflow()
        root = (tmp_path / "target-authority").absolute()
        runner = target_module.TargetTestRunner(
            root, probe, flash, transport_factory
        )
        valid_binding = _valid_binding(str(invalid_binding["transport"]))
        control = await runner.prepare(now=PREPARE_AT, **valid_binding)
        loaded_control = runner.load_prepared(control.action_digest)
        assert dict(loaded_control.binding) == dict(control.binding)
        before_invalid = _persisted_snapshot(root)

        with pytest.raises(target_module.TargetRunError) as caught:
            await runner.prepare(now=PREPARE_AT, **invalid_binding)

        assert caught.value.code == expected_code
        assert caught.value.message == expected_message
        assert _persisted_snapshot(root) == before_invalid
        assert probe.calls == []
        assert flash.calls == []
        assert transport_factory_calls == []

        reloaded_control = runner.load_prepared(control.action_digest)
        assert dict(reloaded_control.binding) == dict(valid_binding)
        follow_up = await runner.prepare(
            now=PREPARE_AT + timedelta(seconds=1), **valid_binding
        )
        assert follow_up.nonce != control.nonce
        assert follow_up.action_digest != control.action_digest
        reloaded_follow_up = runner.load_prepared(follow_up.action_digest)
        assert dict(reloaded_follow_up.binding) == dict(valid_binding)
        assert reloaded_follow_up.binding["input_snapshot_sha256"] == INPUT_SNAPSHOT_SHA256
        assert reloaded_follow_up.binding["case_inventory_digest"] == V2_CASE_INVENTORY_DIGEST
        assert reloaded_follow_up.binding["protocol"] == "stm32-target-frame/2"

    asyncio.run(scenario())
