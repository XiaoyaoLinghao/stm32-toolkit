from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest
from stm32_toolkit.evidence.store import EvidenceStore
from stm32_toolkit.probe.model import OperationLevel
from stm32_toolkit.probe.service import ProbeEndpoint
from stm32_toolkit.result import OperationResult
from stm32_toolkit.testing import target as target_module
from stm32_toolkit.testing.artifacts import TestArtifactCollector
from stm32_toolkit.testing.model import (
    TestProtocolError as ProtocolError,
)
from stm32_toolkit.testing.model import (
    calculate_inventory_digest,
)
from test_target_protocol import (
    H0,
    H1,
    H2,
    TARGET,
    frozen_schema_payloads,
    valid_run_bytes,
)
from test_target_runner import (
    IDENTITY,
    MAILBOX_PROJECT_CONFIG,
    PROBE_HASH,
    PROJECT_ID,
    REVISION,
    SESSION_ID,
    TARGET_SUPPORT,
    V2_CASE_ID,
    V2_CASE_INVENTORY_DIGEST,
    WORKSPACE_ID,
    FakeProbeClient,
    FakeTransport,
    _target_evidence_identity,
    _v2_target_stream,
)


def _assert_protocol_error(code: str, message: str, function) -> None:
    with pytest.raises(ProtocolError) as caught:
        function()
    assert caught.value.code == code
    assert caught.value.message == message


def test_public_decoder_and_validator_reject_external_frames_without_mutation() -> None:
    payload = frozen_schema_payloads()[1]
    _assert_protocol_error(
        "TEST_FRAME_VERSION_INVALID",
        "target frame version is unsupported",
        lambda: target_module.encode_frame(1, 0, payload, version=3),
    )
    _assert_protocol_error(
        "TEST_FRAME_VERSION_INVALID",
        "target frame version is unsupported",
        lambda: target_module.TargetFrameDecoder(expected_version=3),
    )

    corrupted = bytearray(target_module.encode_frame(1, 0, payload))
    corrupted[-1] ^= 0x01
    decoder = target_module.TargetFrameDecoder()
    decoder.feed(bytes(corrupted))
    _assert_protocol_error(
        "TEST_FRAME_CRC_INVALID",
        "target frame CRC is invalid",
        decoder.finish,
    )

    invalid_raw = target_module.TargetFrame(1, 0, {}, b"")
    validator = target_module.TargetRunValidator(
        target_module.TargetRunBinding(H0, H1, H2, TARGET)
    )
    _assert_protocol_error(
        "TEST_EVENT_PAYLOAD_INVALID",
        "frame raw bytes are invalid",
        lambda: validator.accept(invalid_raw),
    )

    frames = target_module.TargetFrameDecoder().feed(valid_run_bytes())
    incomplete = target_module.TargetRunValidator(
        target_module.TargetRunBinding(H0, H1, H2, TARGET)
    )
    incomplete.accept(frames[0])
    incomplete.accept(frames[1])
    incomplete.accept(frames[-1])
    _assert_protocol_error(
        "TEST_EVENT_SEQUENCE_INVALID",
        "target run did not complete every selected case",
        incomplete.finish,
    )


class _PublicTransportClient:
    def __init__(self) -> None:
        self.calls: list[tuple[object, ...]] = []

    async def target_transport_open(
        self, transport: str, config: object, remaining: int
    ) -> dict[str, object]:
        self.calls.append(("open", transport, config, remaining))
        return {
            "transport_id": "transport-1",
            "identity": {"transport": transport},
        }

    async def target_transport_read(
        self, transport_id: str, maximum: int, remaining: int
    ) -> tuple[bytes, bool]:
        self.calls.append(("read", transport_id, maximum, remaining))
        raise AssertionError("a closed facade must not call the provider read")

    async def target_transport_close(self, transport_id: str) -> None:
        self.calls.append(("close", transport_id))


def _probe_v2_endpoint(tmp_path: Path) -> ProbeEndpoint:
    return ProbeEndpoint(
        protocol="stm32-toolkit-probe/2",
        toolkit_version="1.0.0",
        host="127.0.0.1",
        port=1,
        token="t" * 64,
        workspace_id=WORKSPACE_ID,
        session_id=SESSION_ID,
        lease_id="lease-1",
        probe_id="probe-1",
        operation_level=OperationLevel.OBSERVE,
        record_path=tmp_path / "endpoint.json",
    )


def test_public_transport_facade_preserves_call_order_and_identity_boundary(
    tmp_path: Path,
) -> None:
    client = _PublicTransportClient()
    transport = target_module.ProbeClientTargetTransport(
        client, MAILBOX_PROJECT_CONFIG, "mailbox"
    )
    _assert_protocol_error(
        "TEST_TRANSPORT_UNAVAILABLE",
        "Target transport is not open",
        transport.identity,
    )

    async def scenario() -> None:
        deadline = time.monotonic() + 1.0
        await transport.open(MAILBOX_PROJECT_CONFIG, deadline)
        assert transport.identity() == {"transport": "mailbox"}
        await transport.close_async()
        assert await transport.read_async(1024, deadline) == b""

    asyncio.run(scenario())
    assert [call[0] for call in client.calls] == ["open", "close"]

    endpoint = _probe_v2_endpoint(tmp_path)
    with pytest.raises(TypeError, match="^Mailbox target identity is invalid$"):
        target_module.ProbeV2MemoryReader(endpoint, {"target_id": "target-a"})


async def _make_v2_runner(
    tmp_path: Path,
    transport: FakeTransport,
    *,
    with_collector: bool = True,
) -> tuple[
    target_module.TargetTestRunner,
    target_module.PreparedTargetRun,
    datetime,
    FakeProbeClient,
    list[object],
    EvidenceStore,
    target_module.GuardedTargetFlashAdapter,
]:
    project = tmp_path / "project"
    project.mkdir(parents=True)
    evidence_store = EvidenceStore((tmp_path / "evidence").absolute())
    collector = None
    if with_collector:
        collector = TestArtifactCollector(
            (tmp_path / "results").absolute(),
            evidence_store,
            project_root=project,
        )
    workflow_calls: list[object] = []

    async def workflow(request: object) -> OperationResult[object]:
        workflow_calls.append(request)
        return OperationResult.success("stm32_flash", {"status": "success"})

    probe = FakeProbeClient()
    probe.identity = dict(IDENTITY)
    flash = target_module.GuardedTargetFlashAdapter(
        project_root=project,
        data_root=(tmp_path / "data").absolute(),
        session_id=SESSION_ID,
        probe_id="probe-a",
        workflow=workflow,
    )
    runner = target_module.TargetTestRunner(
        (tmp_path / "runs").absolute(),
        probe,
        flash,
        lambda _name: transport,
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
        timeout_ms=1_000,
        now=instant,
    )
    return runner, prepared, instant, probe, workflow_calls, evidence_store, flash


@pytest.mark.parametrize(
    ("variant", "expected_code", "expected_message"),
    [
        (
            "oversize",
            "TEST_STREAM_TOO_LARGE",
            "Target output exceeds the run limit",
        ),
        (
            "nonboolean-eof",
            "TEST_TRANSPORT_UNAVAILABLE",
            "Target transport output is invalid",
        ),
        (
            "no-collector",
            "TEST_EVIDENCE_FAILED",
            "Target Evidence collector is required",
        ),
    ],
)
def test_public_runner_rejects_external_output_after_guarded_prefix(
    tmp_path: Path,
    variant: str,
    expected_code: str,
    expected_message: str,
) -> None:
    async def scenario() -> None:
        _inventory, stream = _v2_target_stream()
        if variant == "oversize":
            transport = FakeTransport(
                [b"x" * (target_module.MAX_RUN_STREAM_BYTES + 1)]
            )
            with_collector = True
        elif variant == "nonboolean-eof":
            class NonBooleanEofTransport(FakeTransport):
                def eof(self) -> object:
                    return "unknown"

            transport = NonBooleanEofTransport([])
            with_collector = True
        else:
            transport = FakeTransport([stream])
            with_collector = False

        (
            runner,
            prepared,
            instant,
            probe,
            workflow_calls,
            evidence_store,
            flash,
        ) = await _make_v2_runner(
            tmp_path / variant,
            transport,
            with_collector=with_collector,
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

        assert caught.value.code == expected_code
        assert caught.value.message == expected_message
        assert isinstance(flash, target_module.GuardedTargetFlashAdapter)
        assert len(workflow_calls) == 1
        assert [call[0] for call in transport.calls] == [
            "open",
            "read",
            "close",
        ]
        assert probe.closed
        assert not (evidence_store.root / "manifests").exists()

    asyncio.run(scenario())
