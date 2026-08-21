"""Closed Target replay descriptors and auditable frozen stream fixtures."""

from __future__ import annotations

from dataclasses import fields
from hashlib import sha256
import os
from pathlib import Path

import pytest

from stm32_toolkit.testing import (
    TARGET_REPLAY_TRANSPORT,
    TargetReplayDescriptor,
    canonical_replay_json_bytes,
    calculate_replay_id,
    load_target_replay_fixture,
)
from stm32_toolkit.testing.model import TestInventory as Inventory, TestProtocolError as ProtocolError
from stm32_toolkit.testing.target import TargetFrameDecoder


FIXTURES = Path(__file__).parent / "fixtures" / "vs03" / "target"


def _fixture(name: str):
    return load_target_replay_fixture(FIXTURES / f"{name}.json", FIXTURES / f"{name}.hex")


def test_target_replay_descriptor_is_closed_immutable_and_self_identifying():
    fixture = _fixture("failed-before")
    descriptor = fixture.descriptor

    assert [field.name for field in fields(TargetReplayDescriptor)] == [
        "schema", "replay_id", "scenario_role", "source",
        "physical_transport_evidence", "identity", "inventory_digest",
        "stream", "stream_format", "expected_terminal_state",
    ]
    assert descriptor.replay_id == calculate_replay_id(descriptor)
    assert TargetReplayDescriptor.from_value(descriptor.to_dict()) == descriptor
    assert canonical_replay_json_bytes(descriptor.to_dict()) + b"\n" == (
        FIXTURES / "failed-before.json"
    ).read_bytes()

    copied = descriptor.to_dict()
    copied["identity"]["build_id"] = "0" * 64
    assert descriptor.identity.build_id != copied["identity"]["build_id"]

    for mutation in (
        {**descriptor.to_dict(), "unknown": True},
        {**descriptor.to_dict(), "physical_transport_evidence": True},
        {**descriptor.to_dict(), "replay_id": "0" * 64},
        {**descriptor.to_dict(), "expected_terminal_state": "passed"},
    ):
        with pytest.raises(ProtocolError):
            TargetReplayDescriptor.from_value(mutation)
    with pytest.raises(ProtocolError):
        canonical_replay_json_bytes({"tuple": (1,)})


def test_frozen_stream_pair_shares_case_scope_but_declares_distinct_firmware_identity():
    before = _fixture("failed-before")
    after = _fixture("fixed-after")

    assert before.descriptor.scenario_role == "failed-before"
    assert after.descriptor.scenario_role == "fixed-after"
    assert before.descriptor.expected_terminal_state == "failed"
    assert after.descriptor.expected_terminal_state == "passed"
    assert before.descriptor.source == after.descriptor.source == "toolkit-generated-protocol-replay"
    assert TARGET_REPLAY_TRANSPORT == "replay"
    assert before.descriptor.physical_transport_evidence is False
    assert after.descriptor.physical_transport_evidence is False
    assert before.descriptor.inventory_digest != after.descriptor.inventory_digest
    assert before.descriptor.identity.workspace_id == after.descriptor.identity.workspace_id
    assert before.descriptor.identity.project_id == after.descriptor.identity.project_id
    assert before.descriptor.identity.session_id == after.descriptor.identity.session_id
    assert before.descriptor.identity.target_device == after.descriptor.identity.target_device
    assert before.descriptor.identity.input_snapshot_sha256 != after.descriptor.identity.input_snapshot_sha256
    assert before.descriptor.identity.build_id != after.descriptor.identity.build_id
    assert before.descriptor.identity.elf_sha256 != after.descriptor.identity.elf_sha256
    assert before.descriptor.identity.git_commit != after.descriptor.identity.git_commit
    assert before.stream_bytes != after.stream_bytes

    before_decoder = TargetFrameDecoder()
    after_decoder = TargetFrameDecoder()
    before_frames = before_decoder.feed(before.stream_bytes)
    after_frames = after_decoder.feed(after.stream_bytes)
    before_decoder.finish()
    after_decoder.finish()
    assert before_frames[0].payload["case_ids"] == after_frames[0].payload["case_ids"]
    assert before_frames[1].payload["case_ids"] == after_frames[1].payload["case_ids"]
    assert before_frames[0].payload["inventory_digest"] == before.descriptor.inventory_digest
    assert after_frames[0].payload["inventory_digest"] == after.descriptor.inventory_digest
    for fixture, frames in ((before, before_frames), (after, after_frames)):
        inventory = Inventory(
            mode=frames[0].payload["mode"],
            identity=fixture.descriptor.identity,
            case_ids=tuple(frames[0].payload["case_ids"]),
            inventory_digest=fixture.descriptor.inventory_digest,
            discovered_at_utc=frames[0].payload["discovered_at_utc"],
        )
        assert inventory.inventory_digest == fixture.descriptor.inventory_digest
    assert before_frames[-1].payload["state"] == "failed"
    assert after_frames[-1].payload["state"] == "passed"

    for fixture in (before, after):
        assert fixture.descriptor.stream.kind == "target-replay-stream"
        assert fixture.descriptor.stream.media_type == "application/octet-stream"
        assert fixture.descriptor.stream.relative_path == f"{fixture.descriptor.scenario_role}.bin"
        hex_source = FIXTURES / f"{fixture.descriptor.scenario_role}.hex"
        assert hex_source.suffix == ".hex"
        assert hex_source.name != fixture.descriptor.stream.relative_path
        assert fixture.stream_bytes == bytes.fromhex(
            hex_source.read_text(encoding="ascii")
        )
        assert fixture.descriptor.stream.size_bytes == len(fixture.stream_bytes)
        assert fixture.descriptor.stream.sha256 == sha256(fixture.stream_bytes).hexdigest()

        inventory_identity = before_frames[0].payload["identity"] if fixture is before else after_frames[0].payload["identity"]
        assert inventory_identity == fixture.descriptor.identity.to_dict()
        terminal = before_frames[-1].payload if fixture is before else after_frames[-1].payload
        assert {
            key: terminal[key]
            for key in ("build_id", "elf_sha256", "target_device")
        } == {
            key: fixture.descriptor.identity.to_dict()[key]
            for key in ("build_id", "elf_sha256", "target_device")
        }


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("relative_path", "failed-before.hex"),
        ("media_type", "text/plain"),
    ),
)
def test_descriptor_rejects_non_binary_stream_artifact_contract(field: str, value: str):
    descriptor = _fixture("failed-before").descriptor
    payload = descriptor.to_dict()
    payload["stream"] = {**payload["stream"], field: value}
    payload["replay_id"] = calculate_replay_id(payload)

    with pytest.raises(ProtocolError):
        TargetReplayDescriptor.from_value(payload)


def test_from_value_does_not_shortcut_descriptor_subclass():
    descriptor = _fixture("failed-before").descriptor

    class DescriptorSubclass(TargetReplayDescriptor):
        pass

    subclass = DescriptorSubclass(
        **{field.name: getattr(descriptor, field.name) for field in fields(TargetReplayDescriptor)}
    )
    with pytest.raises(ProtocolError):
        TargetReplayDescriptor.from_value(subclass)


def test_fixture_loader_rejects_binary_artifact_path_as_hex_input(tmp_path: Path):
    descriptor = tmp_path / "failed-before.json"
    binary_artifact_path = tmp_path / "failed-before.bin"
    descriptor.write_bytes((FIXTURES / descriptor.name).read_bytes())
    binary_artifact_path.write_bytes((FIXTURES / "failed-before.hex").read_bytes())

    with pytest.raises(ProtocolError):
        load_target_replay_fixture(descriptor, binary_artifact_path)


def test_fixture_loader_rejects_digest_size_hex_and_file_type_tampering(tmp_path: Path):
    source_descriptor = FIXTURES / "failed-before.json"
    source_stream = FIXTURES / "failed-before.hex"
    descriptor = tmp_path / source_descriptor.name
    stream = tmp_path / source_stream.name
    descriptor.write_bytes(source_descriptor.read_bytes())
    stream.write_bytes(source_stream.read_bytes())

    stream.write_text("00", encoding="ascii")
    with pytest.raises(ProtocolError):
        load_target_replay_fixture(descriptor, stream)

    stream.write_bytes(source_stream.read_bytes())
    with pytest.raises(ProtocolError):
        load_target_replay_fixture(descriptor, stream, max_stream_bytes=1)

    hardlink = tmp_path / "hardlink.hex"
    try:
        os.link(stream, hardlink)
    except (OSError, NotImplementedError):
        hardlink = None
    if hardlink is not None:
        with pytest.raises(ProtocolError):
            load_target_replay_fixture(descriptor, hardlink)

    redirected = tmp_path / "redirected.json"
    try:
        redirected.symlink_to(descriptor)
    except (OSError, NotImplementedError):
        redirected = None
    if redirected is not None:
        with pytest.raises(ProtocolError):
            load_target_replay_fixture(redirected, stream)
