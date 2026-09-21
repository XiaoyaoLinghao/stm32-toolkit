from __future__ import annotations

import asyncio
import re
import time
from copy import deepcopy
from pathlib import Path

import pytest
from stm32_toolkit.evidence import EvidenceIdentity
from stm32_toolkit.testing import target as target_module
from stm32_toolkit.testing.model import calculate_inventory_digest
from stm32_toolkit.testing.transports import MailboxTransport
from test_target_runner import (
    IDENTITY,
    MAILBOX_PROJECT_CONFIG,
    PROBE_HASH,
    TARGET_SUPPORT,
    V2_CASE_ID,
    V2_CASE_INVENTORY_DIGEST,
    FakeProbeClient,
    _target_evidence_identity,
    _v2_target_stream,
)

MAILBOX_BASE = int(MAILBOX_PROJECT_CONFIG["options"]["address"])
MAILBOX_RING_SIZE = int(MAILBOX_PROJECT_CONFIG["options"]["size"])
V2_PROTOCOL = "stm32-target-frame/2"


class _ImmutableMailboxReader:
    """Test-owned read-only mailbox image with the production header shape."""

    def __init__(self, payload: bytes) -> None:
        if not payload or len(payload) > MAILBOX_RING_SIZE:
            raise ValueError("mailbox fixture does not fit the bounded ring")
        self.image = bytes(payload)
        self.header = len(self.image).to_bytes(8, "little") + (0).to_bytes(8, "little")
        self.reads: list[tuple[int, int, float]] = []
        self.served_bytes = 0
        self.close_calls = 0

    def read_memory(self, address: int, size: int, deadline: float) -> bytes:
        self.reads.append((address, size, deadline))
        if address == MAILBOX_BASE:
            if size != len(self.header):
                raise AssertionError("mailbox header was not read at its public base")
            return self.header
        offset = address - MAILBOX_BASE - len(self.header)
        if offset < 0 or offset + size > len(self.image):
            raise AssertionError("mailbox reader received an out-of-image read")
        self.served_bytes = max(self.served_bytes, offset + size)
        return self.image[offset : offset + size]

    def eof(self) -> bool:
        return self.served_bytes == len(self.image)

    def close(self) -> None:
        self.close_calls += 1


class _PublicMailboxTransport:
    """Compose the real public MailboxTransport methods without private access."""

    def __init__(self, reader: _ImmutableMailboxReader) -> None:
        self.reader = reader
        self._transport = MailboxTransport(reader, TARGET_SUPPORT)
        self.events: list[str] = []
        self.identities: list[dict[str, str]] = []

    def open(self, config, deadline):
        self.events.append("open")
        return self._transport.open(config, deadline)

    async def read_async(self, maximum, deadline):
        self.events.append("read")
        return await self._transport.read_async(maximum, deadline)

    def identity(self):
        self.events.append("identity")
        value = dict(self._transport.identity())
        self.identities.append(value)
        return value

    def eof(self) -> bool:
        return self.reader.eof()

    async def close_async(self):
        self.events.append("close")
        return await self._transport.close_async()


class _ForbiddenFlash:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    async def run(self, *args: object, **kwargs: object) -> None:
        self.calls.append((args, kwargs))
        raise AssertionError("discover must not dispatch Target flash")


def _tree_snapshot(root: Path) -> dict[str, tuple[str, bytes | None]]:
    paths = sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix())
    snapshot: dict[str, tuple[str, bytes | None]] = {}
    for path in paths:
        relative = path.relative_to(root).as_posix()
        if path.is_dir():
            snapshot[relative] = ("directory", None)
        elif path.is_file():
            snapshot[relative] = ("file", path.read_bytes())
        else:
            snapshot[relative] = ("other", None)
    return snapshot


def _expected_firmware(host_identity: EvidenceIdentity) -> dict[str, object]:
    return {
        "build_id": host_identity.build_id,
        "elf_sha256": host_identity.elf_sha256,
        "revision": host_identity.git_commit,
        "inventory_digest": calculate_inventory_digest(
            "target", host_identity, (V2_CASE_ID,)
        ),
        "case_inventory_digest": V2_CASE_INVENTORY_DIGEST,
        "case_ids": [V2_CASE_ID],
    }


def _run_start_frame() -> bytes:
    return target_module.encode_frame(
        2,
        0,
        {
            "case_ids": [V2_CASE_ID],
            "case_inventory_digest": V2_CASE_INVENTORY_DIGEST,
            "monotonic_ms": 0,
        },
        version=2,
    )


def _fixture_for_variant(
    variant: str, host_identity: EvidenceIdentity
) -> tuple[bytes, dict[str, object], str, str, str | None, str | None]:
    inventory_frame, _ = _v2_target_stream()
    expected = _expected_firmware(host_identity)
    if variant == "first-run-start":
        return (
            _run_start_frame(),
            expected,
            "Target discovery is unavailable",
            "TEST_EVENT_SEQUENCE_INVALID",
            "Target discovery must begin with an inventory frame",
            "TEST_EVENT_SEQUENCE_INVALID",
        )
    if variant == "truncated-inventory":
        return (
            inventory_frame[:-1],
            expected,
            "Target discovery is unavailable",
            "TEST_EVENT_SEQUENCE_INVALID",
            "Target discovery must return one complete v2 inventory frame",
            "TEST_EVENT_SEQUENCE_INVALID",
        )
    if variant == "case-ids-mismatch":
        expected["case_ids"] = ["suite.other"]
        return (
            inventory_frame,
            expected,
            "Target discovery is unavailable",
            "TEST_INVENTORY_CHANGED",
            "Configured target inventory is unavailable",
            "TEST_INVENTORY_CHANGED",
        )
    if variant == "inventory-digest-mismatch":
        expected["inventory_digest"] = "f" * 64
        return (
            inventory_frame,
            expected,
            "Target discovery is unavailable",
            "TEST_INVENTORY_CHANGED",
            "Configured target inventory is unavailable",
            "TEST_INVENTORY_CHANGED",
        )
    if variant == "build-id-mismatch":
        expected["build_id"] = "d" * 64
        return (
            inventory_frame,
            expected,
            "Configured target firmware is unavailable",
            "TEST_TRANSPORT_UNAVAILABLE",
            None,
            None,
        )
    raise AssertionError(f"unknown discovery variant: {variant}")


def _make_runner(
    tmp_path: Path, payload: bytes
) -> tuple[
    target_module.TargetTestRunner,
    _ImmutableMailboxReader,
    _PublicMailboxTransport,
    FakeProbeClient,
    _ForbiddenFlash,
    Path,
    dict[str, tuple[str, bytes | None]],
    list[str],
]:
    reader = _ImmutableMailboxReader(payload)
    transport = _PublicMailboxTransport(reader)
    probe = FakeProbeClient()
    flash = _ForbiddenFlash()
    root = tmp_path / "target-discovery-root"
    root.mkdir()
    factory_calls: list[str] = []

    def factory(name: str) -> object:
        factory_calls.append(name)
        assert name == "mailbox"
        return transport

    runner = target_module.TargetTestRunner(root, probe, flash, factory)
    return (
        runner,
        reader,
        transport,
        probe,
        flash,
        root,
        _tree_snapshot(root),
        factory_calls,
    )


async def _discover(
    runner: target_module.TargetTestRunner,
    host_identity: EvidenceIdentity,
    expected_firmware: dict[str, object],
) -> dict[str, object]:
    return await runner.discover(
        transport="mailbox",
        transport_config=deepcopy(MAILBOX_PROJECT_CONFIG),
        support_profile=deepcopy(TARGET_SUPPORT),
        deadline=time.monotonic() + 1.0,
        expected_identity=dict(IDENTITY),
        expected_firmware=expected_firmware,
        protocol=V2_PROTOCOL,
        host_identity=host_identity.to_dict(),
    )


def _assert_cleanup_and_no_write(
    reader: _ImmutableMailboxReader,
    transport: _PublicMailboxTransport,
    probe: FakeProbeClient,
    flash: _ForbiddenFlash,
    root: Path,
    before: dict[str, tuple[str, bytes | None]],
    factory_calls: list[str],
) -> None:
    assert reader.close_calls == 1
    assert transport.events.count("close") == 1
    assert probe.calls.count(("close",)) == 1
    assert probe.closed
    assert flash.calls == []
    assert factory_calls == ["mailbox"]
    assert _tree_snapshot(root) == before


def _assert_wrapped_failure(
    caught: pytest.ExceptionInfo[target_module.TargetRunError],
    *,
    public_message: str,
    cause_code: str,
    cause_message: str | None,
) -> None:
    error = caught.value
    assert error.code == "TEST_TRANSPORT_UNAVAILABLE"
    assert error.message == public_message
    assert error.details == {}
    assert error.cleanup_notes == []
    cause = error.__cause__
    if cause_message is None:
        assert cause is None
        return
    assert cause is not None
    assert getattr(cause, "code", None) == cause_code
    assert getattr(cause, "message", None) == cause_message


def test_public_v2_discover_accepts_mapping_with_real_mailbox_and_sync_probe_close(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        host_identity = _target_evidence_identity()
        inventory_frame, _ = _v2_target_stream()
        (
            runner,
            reader,
            transport,
            probe,
            flash,
            root,
            before,
            factory_calls,
        ) = _make_runner(tmp_path, inventory_frame)
        expected = _expected_firmware(host_identity)

        discovered = await _discover(runner, host_identity, expected)

        assert discovered["protocol"] == V2_PROTOCOL
        assert discovered["raw"] == inventory_frame
        assert discovered["case_inventory_digest"] == V2_CASE_INVENTORY_DIGEST
        assert discovered["inventory"] == {
            "mode": "target",
            "identity": host_identity.to_dict(),
            "case_ids": [V2_CASE_ID],
            "inventory_digest": expected["inventory_digest"],
            "discovered_at_utc": discovered["inventory"]["discovered_at_utc"],
        }
        assert discovered["identity"] == transport.identities[0]
        assert set(discovered["identity"]) == {
            "probe_id",
            "target_id",
            "transport",
            "config_digest",
        }
        assert discovered["identity"]["probe_id"] == PROBE_HASH
        assert discovered["identity"]["target_id"] == IDENTITY["target_id"]
        assert discovered["identity"]["transport"] == "mailbox"
        assert re.fullmatch(r"[0-9a-f]{64}", discovered["identity"]["config_digest"])
        assert transport.identities == [
            transport.identities[0],
            transport.identities[0],
        ]
        assert transport.events == ["open", "identity", "read", "identity", "close"]
        assert reader.header == len(inventory_frame).to_bytes(8, "little") + (
            0
        ).to_bytes(8, "little")
        assert reader.image == inventory_frame
        assert reader.served_bytes == len(inventory_frame)
        assert probe.calls == [("identity",), ("close",)]
        _assert_cleanup_and_no_write(
            reader, transport, probe, flash, root, before, factory_calls
        )

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "variant",
    [
        "first-run-start",
        "truncated-inventory",
        "case-ids-mismatch",
        "inventory-digest-mismatch",
        "build-id-mismatch",
    ],
)
def test_public_v2_discover_rejects_invalid_handshake_without_authority_or_evidence(
    tmp_path: Path, variant: str
) -> None:
    async def scenario() -> None:
        host_identity = _target_evidence_identity()
        payload, expected, public_message, cause_code, cause_message, _ = (
            _fixture_for_variant(variant, host_identity)
        )
        (
            runner,
            reader,
            transport,
            probe,
            flash,
            root,
            before,
            factory_calls,
        ) = _make_runner(tmp_path, payload)

        with pytest.raises(target_module.TargetRunError) as caught:
            await _discover(runner, host_identity, expected)

        _assert_wrapped_failure(
            caught,
            public_message=public_message,
            cause_code=cause_code,
            cause_message=cause_message,
        )
        _assert_cleanup_and_no_write(
            reader, transport, probe, flash, root, before, factory_calls
        )

    asyncio.run(scenario())
