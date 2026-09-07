from __future__ import annotations

import asyncio
import json
import pytest
from dataclasses import dataclass, replace
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
from typing import Mapping

from stm32_toolkit.evidence import EvidenceIdentity, canonical_json_bytes
from stm32_toolkit.paths import WorkspacePaths
from stm32_toolkit.probe.backend import (
    FlashBackendReport,
    ProbeAttachmentEvidence,
    ProbeBackendError,
    ProbeDescriptor,
)
from stm32_toolkit.probe.client import ProbeClient
from stm32_toolkit.probe.lease import ProbeLeaseManager
from stm32_toolkit.probe.model import OperationLevel
from stm32_toolkit.probe.pyocd_backend import PyOCDBackend
from stm32_toolkit.probe.supervisor import ProbeServiceConfig, ProbeServiceSupervisor
from stm32_toolkit.probe.service import ProbeServiceError
from stm32_toolkit.testing.model import calculate_inventory_digest
from stm32_toolkit.testing.protocol import TARGET_FRAME_V2, calculate_case_inventory_digest
from stm32_toolkit.testing.target import encode_frame
from stm32_toolkit.probe.worker import (
    NORMAL_CONNECTION_POLICY,
    UNDER_RESET_RECOVERY_CONNECTION_POLICY,
    ProbeWorkerConfig,
)
import stm32_toolkit.testing_workflows as workflows
from test_build_runner import prepare_project
from test_flash import _publish_current_debug_build


RAW_PROBE = "probe-r3-a"
CASES = ("suite.boot", "suite.sensor")


@dataclass
class _Board:
    flashed: bool = False


def _fixed_identity(
    build: Mapping[str, object], workspace: WorkspacePaths
) -> EvidenceIdentity:
    return EvidenceIdentity(
        workspace_id=workspace.workspace_id,
        project_id=str(build["logicalProjectId"]),
        session_id=workspace.session_id,
        build_id=str(build["buildId"]),
        elf_sha256=str(build["elfSha256"]),
        target_device=str(build["targetDevice"]),
        input_snapshot_sha256=str(build["inputSnapshotSha256"]),
        git_commit=str(build["gitHead"]),
        git_dirty=bool(build["gitDirty"]),
    )


def _fixed_stream(
    identity: EvidenceIdentity, digest: str, cases: tuple[str, ...] = CASES
) -> bytes:
    started = "2026-08-22T00:00:00.000000Z"
    ended = "2026-08-22T00:00:01.000000Z"
    bodies: list[tuple[int, dict[str, object]]] = [
        (1, {"mode": "target", "identity": identity.to_dict(), "case_ids": list(cases), "inventory_digest": digest, "discovered_at_utc": started}),
        (2, {"run_id": "physical-r3-run", "started_at_utc": started, "case_ids": list(cases), "inventory_digest": digest}),
    ]
    for case_id in cases:
        bodies.extend(
            [
                (3, {"case_id": case_id, "started_at_utc": started}),
                (4, {"case_id": case_id, "state": "passed", "ended_at_utc": ended, "duration_ms": 500, "message": None, "stdout": None, "stderr": None}),
            ]
        )
    frames = [
        encode_frame(kind, sequence, body)
        for sequence, (kind, body) in enumerate(bodies)
    ]
    terminal = {
        "state": "passed",
        "ended_at_utc": ended,
        "duration_ms": 1000,
        "inventory_digest": digest,
        "build_id": identity.build_id,
        "elf_sha256": identity.elf_sha256,
        "target_device": identity.target_device,
        "counts": {"passed": len(cases), "failed": 0, "skipped": 0, "error": 0, "timeout": 0},
        "event_stream_digest": sha256(b"".join(frames)).hexdigest(),
    }
    frames.append(encode_frame(5, len(frames), terminal))
    return b"".join(frames)


def _fixed_v2_stream(
    cases: tuple[str, ...] = CASES, *, case_state: str = "passed"
) -> bytes:
    case_digest = calculate_case_inventory_digest(cases)
    terminal_state = "failed" if case_state == "failed" else "passed"
    counts = {
        "passed": len(cases) if case_state == "passed" else 0,
        "failed": len(cases) if case_state == "failed" else 0,
        "skipped": 0,
        "error": 0,
        "timeout": 0,
    }
    frames = [
        encode_frame(
            1,
            0,
            {
                "mode": "target",
                "case_ids": list(cases),
                "case_inventory_digest": case_digest,
                "monotonic_ms": 0,
            },
            version=2,
        ),
        encode_frame(
            2,
            1,
            {
                "case_ids": list(cases),
                "case_inventory_digest": case_digest,
                "monotonic_ms": 1,
            },
            version=2,
        ),
    ]
    sequence = 2
    for case_id in cases:
        frames.extend(
            [
                encode_frame(
                    3, sequence, {"case_id": case_id, "monotonic_ms": sequence}, version=2
                ),
                encode_frame(
                    4,
                    sequence + 1,
                    {
                        "case_id": case_id,
                        "state": case_state,
                        "monotonic_ms": sequence + 1,
                        "message": None,
                    },
                    version=2,
                ),
            ]
        )
        sequence += 2
    frames.append(
        encode_frame(
            5,
            len(frames),
            {
                "state": terminal_state,
                "case_inventory_digest": case_digest,
                "counts": counts,
                "event_stream_digest": sha256(b"".join(frames)).hexdigest(),
                "monotonic_ms": sequence,
            },
            version=2,
        )
    )
    return b"".join(frames)


class _SourceChangeBackend:
    def __init__(
        self,
        *,
        board: _Board,
        physical_identity: Mapping[str, object],
        stream: bytes,
        flash_segment: bytes,
        events: list[tuple[object, ...]],
        fail_transport: bool = False,
        empty_reads: int = 0,
    ) -> None:
        self.board = board
        self.identity_value = dict(physical_identity)
        self.stream = stream
        self.flash_segment = flash_segment
        self.events = events
        self.fail_transport = fail_transport
        self.empty_reads = empty_reads
        self.level = ""
        self.running = False
        self.remaining = b""

    def preflight_target_capabilities(self, probe_id: str, level: object) -> None:
        self.level = str(getattr(level, "value", ""))
        self.events.append(("preflight", self.level, probe_id))

    def list_probes(self) -> tuple[ProbeDescriptor, ...]:
        return (ProbeDescriptor(RAW_PROBE, "ST", "ST-LINK", None),)

    def open_attach(
        self, probe_id: str, target: str, *, halt_on_connect: bool = False
    ) -> ProbeAttachmentEvidence:
        self.events.append(("attach", self.level, halt_on_connect))
        self.running = not halt_on_connect
        return ProbeAttachmentEvidence(probe_id, target, target, 1)

    def target_identity(self) -> Mapping[str, object]:
        self.events.append(("identity", self.level))
        return dict(self.identity_value)

    def target_state(self) -> Mapping[str, object]:
        self.events.append(("state", self.level, self.running))
        return {
            "state": "running" if self.running else "halted",
            "reason": "requested",
        }

    def resume(self) -> None:
        self.events.append(("resume", self.level))
        self.running = True

    def flash_elf(self, image: bytes) -> FlashBackendReport:
        self.events.append(("flash", self.level))
        self.board.flashed = True
        return FlashBackendReport(len(image), 1)

    def read_memory(self, address: int, length: int) -> bytes:
        assert self.board.flashed and address == 0x08000000
        self.events.append(("flash.readback", self.level))
        return self.flash_segment[:length]

    def open_target_transport(
        self, transport: str, config: Mapping[str, object], deadline_ms: int
    ) -> Mapping[str, object]:
        self.events.append(("transport.open", self.level, self.board.flashed))
        if not self.board.flashed:
            raise AssertionError("pre-flash Target transport is forbidden")
        if self.fail_transport:
            raise RuntimeError("post-flash transport unavailable")
        ram = config["ram"]
        normalized_ram = tuple((item["start"], item["size"]) for item in ram)
        digest = sha256(
            canonical_json_bytes(
                {"address": config["address"], "ring_size": config["size"], "ram": normalized_ram}
            )
        ).hexdigest()
        region = ram[0]
        self.remaining = self.stream
        self.events.append(("transport.identity", self.level))
        return {
            "transport_id": "transport-r3",
            "identity": {
                "probe_id": config["probe_id"],
                "target_id": config["target_id"],
                "transport": transport,
                "config_digest": digest,
                "address": f"0x{int(config['address']):08x}",
                "ring_size": str(config["size"]),
                "ram_bounds": f"0x{int(region['start']):08x}+0x{int(region['size']):08x}",
            },
        }

    def read_target_transport(
        self, transport_id: str, maximum: int, deadline_ms: int
    ) -> Mapping[str, object]:
        self.events.append(("transport.read", self.level))
        if self.empty_reads:
            self.empty_reads -= 1
            return {"data": b"", "eof": False}
        raw, self.remaining = self.remaining[:maximum], self.remaining[maximum:]
        return {"data": raw, "eof": not self.remaining}

    def close_target_transport(self, transport_id: str) -> Mapping[str, object]:
        self.events.append(("transport.close", self.level))
        return {"transport_id": transport_id, "closed": True}

    def close(self) -> None:
        self.events.append(("backend.close", self.level))


class _PostflashIdentityChangeBackend(_SourceChangeBackend):
    def target_identity(self) -> Mapping[str, object]:
        identity = dict(super().target_identity())
        if self.board.flashed and self.level == "modify":
            identity["target_id"] = "changed-after-flash"
        return identity


class _ResumeFailureBackend(_SourceChangeBackend):
    def __init__(self, *, resume_mode: str, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.resume_mode = resume_mode

    def resume(self) -> None:
        self.events.append(("resume", self.level))
        if self.resume_mode == "error":
            raise ProbeBackendError("PROBE_BACKEND_ERROR", "Target resume failed")
        # Keep the backend halted so Probe Service must reject a false running proof.


def _fixed_project(
    tmp_path: Path, *, protocol: str | None = None
) -> tuple[Path, Mapping[str, object]]:
    target = {
        "executable": "build/arm-debug/firmware.elf",
        "timeout_seconds": 10,
        "transport": {
            "kind": "memory-mailbox",
            "options": {"address": 0x20000000, "size": 4096},
        },
    }
    project = prepare_project(
        tmp_path,
        overrides={
            "schemaVersion": 3,
            "testing": {"target": target},
        },
    )
    if protocol is not None:
        manifest_path = project / ".stm32-project.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["testing"]["target"]["protocol"] = protocol
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return project, _publish_current_debug_build(project)


def test_target_support_profile_orders_task8_ram_before_capability_preflight() -> None:
    regions = (
        SimpleNamespace(name="IROM1", origin=0x08000000, length=0x100000, attributes="rx"),
        SimpleNamespace(name="IRAM1", origin=0x20000000, length=0x2EFF0, attributes="rwx"),
        SimpleNamespace(name="MAILBOX", origin=0x2002EFF0, length=0x1010, attributes="rw"),
        SimpleNamespace(name="IRAM2", origin=0x10000000, length=0x10000, attributes="rwx"),
    )
    model = SimpleNamespace(
        testing=SimpleNamespace(
            target=SimpleNamespace(
                transport=SimpleNamespace(
                    kind="memory-mailbox",
                    options=SimpleNamespace(address=0x2002EFF0, size=4096),
                )
            )
        ),
        debug=SimpleNamespace(target="stm32f429zgtx"),
        memory=SimpleNamespace(regions=regions),
    )
    facts = SimpleNamespace(
        target_device="stm32f429zgtx",
        elf_path="build/arm-debug/firmware.elf",
        elf_sha256="e" * 64,
    )
    profile = workflows._target_support_profile(
        model,
        facts,
        {"options": {"address": 0x2002EFF0, "size": 4096}},
    )

    try:
        PyOCDBackend(
            target_profile=profile,
            target_transport_factory=lambda *args: object(),
        ).preflight_target_capabilities(
            "probe-task8", OperationLevel.OBSERVE
        )
    except ProbeBackendError as error:
        pytest.fail(
            "existing capability preflight rejected production Target support profile "
            f"({error.code})"
        )

    assert profile["ram"] == [
        {"start": 0x10000000, "size": 0x10000},
        {"start": 0x20000000, "size": 0x2EFF0},
        {"start": 0x2002EFF0, "size": 0x1010},
    ]
    assert tuple(region.name for region in model.memory.regions) == (
        "IROM1",
        "IRAM1",
        "MAILBOX",
        "IRAM2",
    )


@pytest.mark.parametrize("recovery_under_reset", [False, True])
def test_target_prepare_persists_recovery_binding_without_programming(
    tmp_path: Path, recovery_under_reset: bool,
) -> None:
    project, build = _fixed_project(tmp_path)
    data_root = (tmp_path / "plugin-data").absolute()
    board = _Board()
    events: list[tuple[object, ...]] = []

    def backend_factory() -> _SourceChangeBackend:
        return _SourceChangeBackend(
            board=board,
            physical_identity={
                "board_id": str(build["targetDevice"]), "mcu": "stm32f407vg",
                "target_id": str(build["targetDevice"]),
                "probe_serial_hash": sha256(RAW_PROBE.encode()).hexdigest(),
            },
            stream=b"", flash_segment=b"", events=events,
        )

    context = workflows.TestingWorkflowContext(project, data_root, "recovery-prepare")
    prepared = asyncio.run(
        workflows.target_test_prepare(
            context,
            probe_id=RAW_PROBE,
            case_ids=CASES,
            recovery_under_reset=recovery_under_reset,
            _seams=workflows.TargetWorkflowSeams(backend_factory),
        )
    )

    assert prepared.ok is True, (prepared.to_dict(), events)
    workspace = WorkspacePaths.from_roots(
        data_root, project, build["logicalProjectId"], "recovery-prepare"
    )
    auth_runner = workflows.TargetTestRunner(
        workspace.session_root / "target-authorizations",
        object(), object(), lambda _: object(), owns_probe=False,
    )
    binding = auth_runner.load_prepared(
        prepared.data["authorized_action_digest"]
    ).binding
    assert binding["recovery_under_reset"] is recovery_under_reset
    assert board.flashed is False
    assert not [event for event in events if event[0] == "flash"]


@pytest.mark.parametrize("recovery_under_reset", [False, True])
def test_target_prepare_keeps_normal_observe_and_recovery_static(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    recovery_under_reset: bool,
) -> None:
    project, build = _fixed_project(tmp_path)
    data_root = (tmp_path / "plugin-data").absolute()
    board = _Board()
    events: list[tuple[object, ...]] = []

    def backend_factory() -> _SourceChangeBackend:
        return _SourceChangeBackend(
            board=board,
            physical_identity={
                "board_id": str(build["targetDevice"]), "mcu": "stm32f407vg",
                "target_id": str(build["targetDevice"]),
                "probe_serial_hash": sha256(RAW_PROBE.encode()).hexdigest(),
            },
            stream=b"", flash_segment=b"", events=events,
        )

    context = workflows.TestingWorkflowContext(
        project, data_root, "recovery-prepare-worker"
    )
    _state, _model, _facts, _transport, _protocol, _project_config, support = (
        workflows._target_state(context)
    )
    captured: list[ProbeWorkerConfig | None] = []
    real_supervisor = workflows._target_supervisor

    def capture_supervisor(
        context_arg: workflows.TestingWorkflowContext,
        state_arg: object,
        *,
        probe_id: str,
        level: object,
        support: Mapping[str, object],
        seams: workflows.TargetWorkflowSeams,
        worker_config: ProbeWorkerConfig | None = None,
    ) -> object:
        captured.append(worker_config)
        events.append(("supervisor", worker_config))
        return real_supervisor(
            context_arg,
            state_arg,
            probe_id=probe_id,
            level=level,
            support=support,
            seams=seams,
            worker_config=worker_config,
        )

    monkeypatch.setattr(workflows, "_target_supervisor", capture_supervisor)
    prepared = asyncio.run(
        workflows.target_test_prepare(
            context,
            probe_id=RAW_PROBE,
            case_ids=CASES,
            recovery_under_reset=recovery_under_reset,
            _seams=workflows.TargetWorkflowSeams(backend_factory),
        )
    )

    assert prepared.ok is True, (prepared.to_dict(), events)
    if recovery_under_reset:
        assert captured == []
        assert events == []
        assert board.flashed is False
        return
    assert captured == [None]
    supervisor_index = next(index for index, event in enumerate(events) if event[0] == "supervisor")
    attach_index = next(index for index, event in enumerate(events) if event[0] == "attach")
    assert supervisor_index < attach_index
    assert board.flashed is False


def test_recovery_prepare_is_static_only_and_binds_exact_facts(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    project, build = _fixed_project(tmp_path, protocol=TARGET_FRAME_V2)
    data_root = (tmp_path / "plugin-data").absolute()
    context = workflows.TestingWorkflowContext(project, data_root, "static-prepare")
    _state, model, facts, transport, _protocol, project_config, support = (
        workflows._target_state(context)
    )
    events: list[str] = []

    def forbidden_supervisor(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("recovery prepare must not construct a supervisor")

    def forbidden_backend() -> object:
        raise AssertionError("recovery prepare must not construct a backend")

    monkeypatch.setattr(workflows, "_target_supervisor", forbidden_supervisor)
    prepared = asyncio.run(
        workflows.target_test_prepare(
            context,
            probe_id=RAW_PROBE,
            case_ids=CASES,
            recovery_under_reset=True,
            _seams=workflows.TargetWorkflowSeams(forbidden_backend),
        )
    )

    assert prepared.ok is True, prepared.to_dict()
    workspace = WorkspacePaths.from_roots(
        data_root, project, build["logicalProjectId"], "static-prepare"
    )
    runner = workflows.TargetTestRunner(
        workspace.session_root / "target-authorizations",
        object(), object(), lambda _: object(), owns_probe=False,
    )
    binding = runner.load_prepared(prepared.data["authorized_action_digest"]).binding
    probe_hash = sha256(RAW_PROBE.encode("utf-8")).hexdigest()
    expected_target = {
        "board_id": facts.target_device,
        "mcu": str(model.debug.target),
        "target_id": facts.target_device,
        "probe_serial_hash": probe_hash,
    }
    expected_identity = EvidenceIdentity(
        workspace.workspace_id,
        str(model.logical_project_id),
        workspace.session_id,
        facts.build_id,
        facts.elf_sha256,
        facts.target_device,
        facts.input_snapshot_sha256,
        facts.git_commit,
        facts.git_dirty,
    )
    assert binding == {
        "build_id": facts.build_id,
        "case_inventory_digest": calculate_case_inventory_digest(CASES),
        "cases": list(CASES),
        "elf_path": facts.elf_path,
        "elf_sha256": facts.elf_sha256,
        "git_dirty": facts.git_dirty,
        "input_snapshot_sha256": facts.input_snapshot_sha256,
        "inventory_digest": calculate_inventory_digest(
            "target", expected_identity, CASES
        ),
        "project_id": str(model.logical_project_id),
        "protocol": TARGET_FRAME_V2,
        "probe_serial_hash": probe_hash,
        "recovery_under_reset": True,
        "revision": facts.git_commit,
        "session_id": workspace.session_id,
        "support_profile": support,
        "target": expected_target,
        "timeout_ms": int(model.testing.target.timeout_seconds) * 1000,
        "transport": transport,
        "transport_config": project_config,
        "workspace_id": workspace.workspace_id,
        "nonce": binding["nonce"],
        "prepared_at_utc": binding["prepared_at_utc"],
        "expires_at_utc": binding["expires_at_utc"],
    }
    assert events == []


@pytest.mark.parametrize(
    "probe_id",
    ["probe id", "-leading", "_leading", "中 probe", "probe\x00id", "a" * 129],
)
def test_recovery_prepare_rejects_nonportable_selector_before_authorization_or_service(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, probe_id: str,
) -> None:
    project, build = _fixed_project(tmp_path)
    data_root = (tmp_path / "plugin-data").absolute()
    context = workflows.TestingWorkflowContext(project, data_root, "invalid-selector")

    def forbidden_supervisor(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("invalid selector must fail before supervisor construction")

    def forbidden_backend() -> object:
        raise AssertionError("invalid selector must fail before backend construction")

    monkeypatch.setattr(workflows, "_target_supervisor", forbidden_supervisor)
    result = asyncio.run(
        workflows.target_test_prepare(
            context,
            probe_id=probe_id,
            case_ids=CASES,
            recovery_under_reset=True,
            _seams=workflows.TargetWorkflowSeams(forbidden_backend),
        )
    )

    assert result.ok is False and result.code == "TEST_PROTOCOL_INVALID"
    workspace = WorkspacePaths.from_roots(
        data_root, project, build["logicalProjectId"], "invalid-selector"
    )
    assert not (workspace.session_root / "target-authorizations").exists()


def test_recovery_prepare_rejects_static_drift_before_authorization_or_service(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    project, build = _fixed_project(tmp_path)
    data_root = (tmp_path / "plugin-data").absolute()
    context = workflows.TestingWorkflowContext(project, data_root, "static-drift")
    original_load = workflows.load_fresh_firmware_facts
    calls = 0

    def load_with_drift(root: Path) -> object:
        nonlocal calls
        facts = original_load(root)
        calls += 1
        return replace(facts, build_id=("f" * 64)) if calls >= 2 else facts

    def forbidden_supervisor(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("static drift must fail before supervisor construction")

    def forbidden_backend() -> object:
        raise AssertionError("static drift must fail before backend construction")

    monkeypatch.setattr(workflows, "load_fresh_firmware_facts", load_with_drift)
    monkeypatch.setattr(workflows, "_target_supervisor", forbidden_supervisor)
    result = asyncio.run(
        workflows.target_test_prepare(
            context,
            probe_id=RAW_PROBE,
            case_ids=CASES,
            recovery_under_reset=True,
            _seams=workflows.TargetWorkflowSeams(forbidden_backend),
        )
    )

    assert calls == 2
    assert result.ok is False and result.code == "TEST_INVENTORY_CHANGED"
    workspace = WorkspacePaths.from_roots(
        data_root, project, build["logicalProjectId"], "static-drift"
    )
    assert not (workspace.session_root / "target-authorizations").exists()


def test_target_supervisor_uses_the_frozen_worker_configuration(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    project, _build = _fixed_project(tmp_path)
    context = workflows.TestingWorkflowContext(
        project, (tmp_path / "plugin-data").absolute(), "worker-config"
    )
    state, _model, _facts, _transport, _protocol, _project_config, support = (
        workflows._target_state(context)
    )
    captured: list[dict[str, object]] = []

    class CapturingSupervisor:
        def __init__(self, **kwargs: object) -> None:
            captured.append(kwargs)

    monkeypatch.setattr(workflows, "ProbeServiceSupervisor", CapturingSupervisor)
    normal = ProbeWorkerConfig(target_profile={**dict(support), "probe_id": RAW_PROBE})
    recovery = normal.for_under_reset_recovery()

    workflows._target_supervisor(
        context,
        state,
        probe_id=RAW_PROBE,
        level=OperationLevel.MODIFY,
        support=support,
        seams=workflows.TargetWorkflowSeams(),
        worker_config=normal,
    )
    workflows._target_supervisor(
        context,
        state,
        probe_id=RAW_PROBE,
        level=OperationLevel.MODIFY,
        support=support,
        seams=workflows.TargetWorkflowSeams(),
        worker_config=recovery,
    )

    assert [item["worker_config"] for item in captured] == [normal, recovery]
    assert captured[0]["worker_config"].frequency_hz == 1_000_000
    assert captured[0]["worker_config"].connection_policy == NORMAL_CONNECTION_POLICY
    assert captured[1]["worker_config"].frequency_hz == 100_000
    assert (
        captured[1]["worker_config"].connection_policy
        == UNDER_RESET_RECOVERY_CONNECTION_POLICY
    )


@pytest.mark.parametrize("recovery_under_reset", [False, True])
def test_target_execute_derives_worker_configuration_from_bound_selection(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    recovery_under_reset: bool,
) -> None:
    project, build = _fixed_project(tmp_path)
    data_root = (tmp_path / "plugin-data").absolute()
    board = _Board()
    events: list[tuple[object, ...]] = []

    def backend_factory() -> _SourceChangeBackend:
        return _SourceChangeBackend(
            board=board,
            physical_identity={
                "board_id": str(build["targetDevice"]), "mcu": "stm32f407vg",
                "target_id": str(build["targetDevice"]),
                "probe_serial_hash": sha256(RAW_PROBE.encode()).hexdigest(),
            },
            stream=b"", flash_segment=b"", events=events,
        )

    context = workflows.TestingWorkflowContext(project, data_root, "worker-bound")
    prepared = asyncio.run(
        workflows.target_test_prepare(
            context,
            probe_id=RAW_PROBE,
            case_ids=CASES,
            recovery_under_reset=recovery_under_reset,
            _seams=workflows.TargetWorkflowSeams(backend_factory),
        )
    )
    assert prepared.ok is True, prepared.to_dict()
    captured: list[ProbeWorkerConfig] = []

    def capture_supervisor(*_args: object, **kwargs: object) -> object:
        captured.append(kwargs["worker_config"])
        raise ProbeServiceError("PROBE_SERVICE_UNAVAILABLE", "test seam")

    monkeypatch.setattr(workflows, "_target_supervisor", capture_supervisor)
    executed = asyncio.run(
        workflows.target_test_execute(
            context,
            probe_id=RAW_PROBE,
            authorized_action_digest=prepared.data["authorized_action_digest"],
            _seams=workflows.TargetWorkflowSeams(backend_factory),
        )
    )
    reused = asyncio.run(
        workflows.target_test_execute(
            context,
            probe_id=RAW_PROBE,
            authorized_action_digest=prepared.data["authorized_action_digest"],
            _seams=workflows.TargetWorkflowSeams(backend_factory),
        )
    )

    assert executed.ok is False and executed.code == "TEST_TRANSPORT_UNAVAILABLE"
    assert reused.ok is False and reused.code == "TEST_AUTHORIZATION_INVALID"
    _state, _model, _facts, _transport, _protocol, _project_config, support = (
        workflows._target_state(context)
    )
    normal = ProbeWorkerConfig(target_profile={**dict(support), "probe_id": RAW_PROBE})
    expected = normal.for_under_reset_recovery() if recovery_under_reset else normal
    assert captured == [expected]


@pytest.mark.parametrize("value", [pytest.param(None, id="missing"), "true", 1])
def test_target_execute_rejects_missing_or_non_boolean_recovery_before_service(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, value: object,
) -> None:
    project, build = _fixed_project(tmp_path)
    data_root = (tmp_path / "plugin-data").absolute()
    board = _Board()
    events: list[tuple[object, ...]] = []

    def backend_factory() -> _SourceChangeBackend:
        return _SourceChangeBackend(
            board=board,
            physical_identity={
                "board_id": str(build["targetDevice"]), "mcu": "stm32f407vg",
                "target_id": str(build["targetDevice"]),
                "probe_serial_hash": sha256(RAW_PROBE.encode()).hexdigest(),
            },
            stream=b"", flash_segment=b"", events=events,
        )

    context = workflows.TestingWorkflowContext(project, data_root, "invalid-binding")
    prepared = asyncio.run(
        workflows.target_test_prepare(
            context,
            probe_id=RAW_PROBE,
            case_ids=CASES,
            _seams=workflows.TargetWorkflowSeams(backend_factory),
        )
    )
    assert prepared.ok is True, prepared.to_dict()
    auth_runner = workflows.TargetTestRunner(
        WorkspacePaths.from_roots(
            data_root, project, build["logicalProjectId"], "invalid-binding"
        ).session_root / "target-authorizations",
        object(), object(), lambda _: object(), owns_probe=False,
    )
    loaded = auth_runner.load_prepared(prepared.data["authorized_action_digest"])
    binding = dict(loaded.binding)
    if value is None:
        binding.pop("recovery_under_reset", None)
    else:
        binding["recovery_under_reset"] = value

    class FakeAuthRunner:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def load_prepared(self, _digest: str) -> object:
            return loaded

        def consume_prepared(self, digest: str) -> object:
            return workflows.ConsumedTargetRun(digest, binding)

    service_calls: list[object] = []

    def forbidden_supervisor(*args: object, **kwargs: object) -> object:
        service_calls.append((args, kwargs))
        raise AssertionError("invalid binding must fail before supervisor construction")

    monkeypatch.setattr(workflows, "TargetTestRunner", FakeAuthRunner)
    monkeypatch.setattr(workflows, "_target_supervisor", forbidden_supervisor)
    result = asyncio.run(
        workflows.target_test_execute(
            context,
            probe_id=RAW_PROBE,
            authorized_action_digest=prepared.data["authorized_action_digest"],
        )
    )

    assert result.ok is False and result.code == "TEST_AUTHORIZATION_INVALID"
    assert service_calls == []
    assert board.flashed is False


@pytest.mark.parametrize("recovery_under_reset", [False, True])
def test_prepare_never_reads_old_inventory_and_execute_proves_fixed_after_flash(
    tmp_path: Path, recovery_under_reset: bool,
) -> None:
    project, build = _fixed_project(tmp_path)
    data_root = (tmp_path / "plugin-data").absolute()
    workspace = WorkspacePaths.from_roots(
        data_root, project, build["logicalProjectId"], "session-r3"
    )
    fixed_identity = _fixed_identity(build, workspace)
    expected_digest = calculate_inventory_digest("target", fixed_identity, CASES)
    board = _Board()
    events: list[tuple[object, ...]] = []
    flash_segment = (project / "build/arm-debug/firmware.elf").read_bytes()[84:404]

    def backend_factory() -> _SourceChangeBackend:
        return _SourceChangeBackend(
            board=board,
            physical_identity={
                "board_id": str(build["targetDevice"]),
                "mcu": "stm32f407vg",
                "target_id": str(build["targetDevice"]),
                "probe_serial_hash": sha256(RAW_PROBE.encode()).hexdigest(),
            },
            stream=_fixed_stream(fixed_identity, expected_digest),
            flash_segment=flash_segment,
            events=events,
            empty_reads=1,
        )

    prepare = getattr(workflows, "target_test_prepare", None)
    execute = getattr(workflows, "target_test_execute", None)
    seams_type = getattr(workflows, "TargetWorkflowSeams", None)
    assert callable(prepare) and callable(execute) and seams_type is not None
    seams = seams_type(_test_backend_factory=backend_factory)
    context = workflows.TestingWorkflowContext(project, data_root, "session-r3")

    prepared = asyncio.run(
        prepare(
            context,
            probe_id=RAW_PROBE,
            case_ids=CASES,
            recovery_under_reset=recovery_under_reset,
            _seams=seams,
        )
    )
    assert prepared.ok is True, (prepared.to_dict(), events)
    assert prepared.data["inventory_digest"] == expected_digest
    assert board.flashed is False
    assert not [event for event in events if event[0] == "transport.open"]
    assert not [event for event in events if event[:2] == ("preflight", "modify")]

    executed = asyncio.run(
        execute(
            workflows.TestingWorkflowContext(project, data_root, "session-r3"),
            probe_id=RAW_PROBE,
            authorized_action_digest=prepared.data["authorized_action_digest"],
            _seams=seams,
        )
    )
    assert executed.ok is True, (executed.to_dict(), events)
    assert [event for event in events if event[:2] == ("flash", "modify")] == [
        ("flash", "modify")
    ]
    assert [event for event in events if event[0] == "transport.open"] == [
        ("transport.open", "modify", True)
    ]
    flash_index = next(
        index for index, event in enumerate(events) if event[:2] == ("flash", "modify")
    )
    postflash_identity_index = next(
        index
        for index, event in enumerate(events)
        if index > flash_index and event == ("identity", "modify")
    )
    resume_indices = [
        index for index, event in enumerate(events) if event[:2] == ("resume", "modify")
    ]
    open_index = next(index for index, event in enumerate(events) if event[0] == "transport.open")
    assert len(resume_indices) == 1
    assert postflash_identity_index < resume_indices[0] < open_index
    shown = workflows.test_show(
        workflows.TestingWorkflowContext(project, data_root, "session-r3"),
        run_id=executed.data["run"]["run_id"],
    )
    assert shown.ok is True
    assert shown.data["execution_source"] == "physical"
    assert len([event for event in events if event[:2] == ("transport.read", "modify")]) >= 2
    manifests = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in (workspace.workspace_root / "evidence/manifests").glob("*.json")
    ]
    operations = [manifest["operation"] for manifest in manifests]
    assert operations.count("target-test-physical") == 1
    assert "target-test-run" not in operations
    physical = next(
        manifest for manifest in manifests if manifest["operation"] == "target-test-physical"
    )
    assert set(physical["metadata"]) == {
        "action_digest", "execution_source", "flash_session_id",
        "import_session_id", "import_workspace_id", "intent_digest", "inventory_digest",
        "lease_id", "origin_session_id", "origin_workspace_id",
        "physical_transport_evidence", "probe_id", "target_id",
        "transport_config_digest",
    }
    public_bytes = json.dumps(
        {"prepared": prepared.to_dict(), "executed": executed.to_dict(), "shown": shown.to_dict()},
        sort_keys=True,
    ).encode()
    durable_bytes = b"".join(
        path.read_bytes()
        for path in data_root.rglob("*")
        if path.is_file()
    ) + (project / "artifacts/migration/flash-result.json").read_bytes()
    assert RAW_PROBE.encode() not in public_bytes + durable_bytes
    assert str(project).encode() not in public_bytes + durable_bytes


def test_postflash_identity_mismatch_consumes_parent_without_resume_or_testrun(
    tmp_path: Path,
) -> None:
    project, build = _fixed_project(tmp_path)
    data_root = (tmp_path / "plugin-data").absolute()
    workspace = WorkspacePaths.from_roots(
        data_root, project, build["logicalProjectId"], "postflash-identity"
    )
    fixed_identity = _fixed_identity(build, workspace)
    expected_digest = calculate_inventory_digest("target", fixed_identity, CASES)
    board = _Board()
    events: list[tuple[object, ...]] = []
    segment = (project / "build/arm-debug/firmware.elf").read_bytes()[84:404]

    def backend_factory() -> _PostflashIdentityChangeBackend:
        return _PostflashIdentityChangeBackend(
            board=board,
            physical_identity={
                "board_id": str(build["targetDevice"]),
                "mcu": "stm32f407vg",
                "target_id": str(build["targetDevice"]),
                "probe_serial_hash": sha256(RAW_PROBE.encode()).hexdigest(),
            },
            stream=_fixed_stream(fixed_identity, expected_digest),
            flash_segment=segment,
            events=events,
        )

    seams = workflows.TargetWorkflowSeams(_test_backend_factory=backend_factory)
    context = workflows.TestingWorkflowContext(project, data_root, "postflash-identity")
    prepared = asyncio.run(
        workflows.target_test_prepare(
            context, probe_id=RAW_PROBE, case_ids=CASES, _seams=seams
        )
    )
    assert prepared.ok is True, (prepared.to_dict(), events)

    failed = asyncio.run(
        workflows.target_test_execute(
            context,
            probe_id=RAW_PROBE,
            authorized_action_digest=prepared.data["authorized_action_digest"],
            _seams=seams,
        )
    )
    assert failed.ok is False and failed.code == "TEST_IDENTITY_MISMATCH"
    assert board.flashed is True
    assert [event for event in events if event[:2] == ("flash", "modify")] == [
        ("flash", "modify")
    ]
    assert not [event for event in events if event[:2] == ("resume", "modify")]
    assert not [event for event in events if event[0] == "transport.open"]
    assert workflows.test_show(context, run_id="physical-r3-run").ok is False
    assert not list((workspace.workspace_root / "evidence/manifests").glob("*.json"))

    reused = asyncio.run(
        workflows.target_test_execute(
            context,
            probe_id=RAW_PROBE,
            authorized_action_digest=prepared.data["authorized_action_digest"],
            _seams=seams,
        )
    )
    assert reused.ok is False and reused.code == "TEST_AUTHORIZATION_INVALID"
    assert len([event for event in events if event[:2] == ("flash", "modify")]) == 1
    assert not [event for event in events if event[:2] == ("resume", "modify")]
    assert not [event for event in events if event[0] == "transport.open"]


@pytest.mark.parametrize("resume_mode", ["error", "non-running"])
def test_postflash_resume_failure_consumes_parent_without_transport_or_testrun(
    tmp_path: Path, resume_mode: str,
) -> None:
    project, build = _fixed_project(tmp_path)
    data_root = (tmp_path / "plugin-data").absolute()
    workspace = WorkspacePaths.from_roots(
        data_root, project, build["logicalProjectId"], f"postflash-resume-{resume_mode}"
    )
    fixed_identity = _fixed_identity(build, workspace)
    expected_digest = calculate_inventory_digest("target", fixed_identity, CASES)
    board = _Board()
    events: list[tuple[object, ...]] = []
    segment = (project / "build/arm-debug/firmware.elf").read_bytes()[84:404]

    def backend_factory() -> _ResumeFailureBackend:
        return _ResumeFailureBackend(
            resume_mode=resume_mode,
            board=board,
            physical_identity={
                "board_id": str(build["targetDevice"]),
                "mcu": "stm32f407vg",
                "target_id": str(build["targetDevice"]),
                "probe_serial_hash": sha256(RAW_PROBE.encode()).hexdigest(),
            },
            stream=_fixed_stream(fixed_identity, expected_digest),
            flash_segment=segment,
            events=events,
        )

    seams = workflows.TargetWorkflowSeams(_test_backend_factory=backend_factory)
    context = workflows.TestingWorkflowContext(
        project, data_root, f"postflash-resume-{resume_mode}"
    )
    prepared = asyncio.run(
        workflows.target_test_prepare(
            context, probe_id=RAW_PROBE, case_ids=CASES, _seams=seams
        )
    )
    assert prepared.ok is True, (prepared.to_dict(), events)

    failed = asyncio.run(
        workflows.target_test_execute(
            context,
            probe_id=RAW_PROBE,
            authorized_action_digest=prepared.data["authorized_action_digest"],
            _seams=seams,
        )
    )
    assert failed.ok is False and failed.code == "TEST_EXECUTION_FAILED"
    assert board.flashed is True
    assert [event for event in events if event[:2] == ("flash", "modify")] == [
        ("flash", "modify")
    ]
    assert [event for event in events if event[:2] == ("resume", "modify")] == [
        ("resume", "modify")
    ]
    assert not [event for event in events if event[0] == "transport.open"]
    assert workflows.test_show(context, run_id="physical-r3-run").ok is False
    assert not list((workspace.workspace_root / "evidence/manifests").glob("*.json"))

    reused = asyncio.run(
        workflows.target_test_execute(
            context,
            probe_id=RAW_PROBE,
            authorized_action_digest=prepared.data["authorized_action_digest"],
            _seams=seams,
        )
    )
    assert reused.ok is False and reused.code == "TEST_AUTHORIZATION_INVALID"
    assert len([event for event in events if event[:2] == ("flash", "modify")]) == 1
    assert len([event for event in events if event[:2] == ("resume", "modify")]) == 1
    assert not [event for event in events if event[0] == "transport.open"]


def test_v2_physical_execution_binds_protocol_digests_and_publishes_after_flash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    project, build = _fixed_project(tmp_path, protocol="stm32-target-frame/2")
    data_root = (tmp_path / "plugin-data").absolute()
    workspace = WorkspacePaths.from_roots(
        data_root, project, build["logicalProjectId"], "session-r3-v2"
    )
    identity = _fixed_identity(build, workspace)
    expected_digest = calculate_inventory_digest("target", identity, CASES)
    case_digest = calculate_case_inventory_digest(CASES)
    board = _Board()
    events: list[tuple[object, ...]] = []
    flash_segment = (project / "build/arm-debug/firmware.elf").read_bytes()[84:404]

    def backend_factory() -> _SourceChangeBackend:
        return _SourceChangeBackend(
            board=board,
            physical_identity={
                "board_id": str(build["targetDevice"]),
                "mcu": "stm32f407vg",
                "target_id": str(build["targetDevice"]),
                "probe_serial_hash": sha256(RAW_PROBE.encode()).hexdigest(),
            },
            stream=_fixed_v2_stream(),
            flash_segment=flash_segment,
            events=events,
        )

    real_publish = workflows.TestRunPublisher.publish_target_physical

    def record_publish(self, manifest, run_envelope):
        events.append(("publish",))
        return real_publish(self, manifest, run_envelope)

    monkeypatch.setattr(workflows.TestRunPublisher, "publish_target_physical", record_publish)
    seams = workflows.TargetWorkflowSeams(_test_backend_factory=backend_factory)
    context = workflows.TestingWorkflowContext(project, data_root, "session-r3-v2")
    prepared = asyncio.run(
        workflows.target_test_prepare(context, probe_id=RAW_PROBE, case_ids=CASES, _seams=seams)
    )

    assert prepared.ok is True, prepared.to_dict()
    assert prepared.data["protocol"] == "stm32-target-frame/2"
    assert prepared.data["case_inventory_digest"] == case_digest
    assert prepared.data["inventory_digest"] == expected_digest
    assert board.flashed is False

    executed = asyncio.run(
        workflows.target_test_execute(
            context,
            probe_id=RAW_PROBE,
            authorized_action_digest=prepared.data["authorized_action_digest"],
            _seams=seams,
        )
    )

    assert executed.ok is True, (executed.to_dict(), events)
    assert board.flashed is True
    flash_index = next(index for index, event in enumerate(events) if event[:2] == ("flash", "modify"))
    readback_index = next(
        index for index, event in enumerate(events) if event[:2] == ("flash.readback", "modify")
    )
    postflash_identity_index = next(
        index
        for index, event in enumerate(events)
        if index > flash_index and event == ("identity", "modify")
    )
    open_index = next(index for index, event in enumerate(events) if event[0] == "transport.open")
    transport_identity_index = next(
        index for index, event in enumerate(events)
        if event[:2] == ("transport.identity", "modify")
    )
    read_index = next(index for index, event in enumerate(events) if event[0] == "transport.read")
    publish_index = next(index for index, event in enumerate(events) if event == ("publish",))
    assert (
        flash_index
        < readback_index
        < postflash_identity_index
        < open_index
        < transport_identity_index
        < read_index
        < publish_index
    )
    shown = workflows.test_show(context, run_id=executed.data["run"]["run_id"])
    assert shown.ok is True
    assert shown.data["execution_source"] == "physical"
    assert shown.data["physical_transport_evidence"] is True


def test_v2_failed_terminal_run_still_publishes_only_after_physical_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    project, build = _fixed_project(tmp_path, protocol="stm32-target-frame/2")
    data_root = (tmp_path / "plugin-data").absolute()
    workspace = WorkspacePaths.from_roots(
        data_root, project, build["logicalProjectId"], "session-r3-v2-failed"
    )
    identity = _fixed_identity(build, workspace)
    expected_digest = calculate_inventory_digest("target", identity, CASES)
    case_digest = calculate_case_inventory_digest(CASES)
    board = _Board()
    events: list[tuple[object, ...]] = []
    flash_segment = (project / "build/arm-debug/firmware.elf").read_bytes()[84:404]

    def backend_factory() -> _SourceChangeBackend:
        return _SourceChangeBackend(
            board=board,
            physical_identity={
                "board_id": str(build["targetDevice"]),
                "mcu": "stm32f407vg",
                "target_id": str(build["targetDevice"]),
                "probe_serial_hash": sha256(RAW_PROBE.encode()).hexdigest(),
            },
            stream=_fixed_v2_stream(case_state="failed"),
            flash_segment=flash_segment,
            events=events,
        )

    real_publish = workflows.TestRunPublisher.publish_target_physical

    def record_publish(self, manifest, run_envelope):
        events.append(("publish",))
        return real_publish(self, manifest, run_envelope)

    monkeypatch.setattr(workflows.TestRunPublisher, "publish_target_physical", record_publish)
    seams = workflows.TargetWorkflowSeams(_test_backend_factory=backend_factory)
    context = workflows.TestingWorkflowContext(project, data_root, "session-r3-v2-failed")
    prepared = asyncio.run(
        workflows.target_test_prepare(
            context, probe_id=RAW_PROBE, case_ids=CASES, _seams=seams
        )
    )
    assert prepared.ok is True
    assert prepared.data["protocol"] == "stm32-target-frame/2"
    assert prepared.data["case_inventory_digest"] == case_digest
    assert prepared.data["inventory_digest"] == expected_digest

    executed = asyncio.run(
        workflows.target_test_execute(
            context,
            probe_id=RAW_PROBE,
            authorized_action_digest=prepared.data["authorized_action_digest"],
            _seams=seams,
        )
    )

    assert executed.ok is True, (executed.to_dict(), events)
    shown = workflows.test_show(context, run_id=executed.data["run"]["run_id"])
    assert shown.ok is True
    assert shown.data["run"]["state"] == "failed"
    assert shown.data["execution_source"] == "physical"
    assert shown.data["physical_transport_evidence"] is True
    assert board.flashed is True
    assert any(event[:2] == ("flash.readback", "modify") for event in events)
    assert any(event[:2] == ("transport.identity", "modify") for event in events)
    assert events.index(("transport.read", "modify")) < events.index(("publish",))


def test_case_ids_are_mandatory_and_authorization_is_single_use(tmp_path: Path) -> None:
    project, build = _fixed_project(tmp_path)
    data_root = (tmp_path / "plugin-data").absolute()
    workspace = WorkspacePaths.from_roots(
        data_root, project, build["logicalProjectId"], "session-r3"
    )
    identity = _fixed_identity(build, workspace)
    digest = calculate_inventory_digest("target", identity, CASES)
    board = _Board()
    events: list[tuple[object, ...]] = []
    segment = (project / "build/arm-debug/firmware.elf").read_bytes()[84:404]

    def factory() -> _SourceChangeBackend:
        return _SourceChangeBackend(
            board=board,
            physical_identity={
                "board_id": str(build["targetDevice"]), "mcu": "stm32f407vg",
                "target_id": str(build["targetDevice"]),
                "probe_serial_hash": sha256(RAW_PROBE.encode()).hexdigest(),
            },
            stream=_fixed_stream(identity, digest), flash_segment=segment, events=events,
        )

    seams = workflows.TargetWorkflowSeams(factory)
    context = workflows.TestingWorkflowContext(project, data_root, "session-r3")
    invalid = asyncio.run(
        workflows.target_test_prepare(context, probe_id=RAW_PROBE, case_ids=(), _seams=seams)
    )
    assert invalid.ok is False
    assert events == []
    prepared = asyncio.run(
        workflows.target_test_prepare(context, probe_id=RAW_PROBE, case_ids=CASES, _seams=seams)
    )
    first = asyncio.run(
        workflows.target_test_execute(
            context, probe_id=RAW_PROBE,
            authorized_action_digest=prepared.data["authorized_action_digest"], _seams=seams,
        )
    )
    second = asyncio.run(
        workflows.target_test_execute(
            context, probe_id=RAW_PROBE,
            authorized_action_digest=prepared.data["authorized_action_digest"], _seams=seams,
        )
    )
    assert first.ok is True
    assert second.ok is False and second.code == "TEST_AUTHORIZATION_INVALID"
    assert len([event for event in events if event[:2] == ("flash", "modify")]) == 1


@pytest.mark.parametrize("case_ids", [tuple(reversed(CASES)), ("suite.\udcff",)])
def test_prepare_rejects_noncanonical_case_order_before_observe_or_authorization(
    tmp_path: Path, case_ids: tuple[str, ...],
) -> None:
    project, build = _fixed_project(tmp_path)
    data_root = (tmp_path / "plugin-data").absolute()

    def factory() -> _SourceChangeBackend:
        raise AssertionError("noncanonical cases must fail before backend construction")

    context = workflows.TestingWorkflowContext(project, data_root, "session-r3")
    result = asyncio.run(
        workflows.target_test_prepare(
            context,
            probe_id=RAW_PROBE,
            case_ids=case_ids,
            _seams=workflows.TargetWorkflowSeams(factory),
        )
    )

    assert result.ok is False and result.code == "TEST_PROTOCOL_INVALID"
    workspace = WorkspacePaths.from_roots(
        data_root, project, build["logicalProjectId"], "session-r3"
    )
    assert not (workspace.session_root / "target-authorizations").exists()


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("FIRMWARE_INPUT_CHANGED", "TEST_INVENTORY_CHANGED"),
        ("FIRMWARE_IDENTITY_MISMATCH", "TEST_IDENTITY_MISMATCH"),
        ("FLASH_PLAN_CHANGED", "TEST_INVENTORY_CHANGED"),
        ("FLASH_IMAGE_INVALID", "TEST_INVENTORY_CHANGED"),
    ],
)
def test_physical_prepare_projects_only_frozen_firmware_fact_failures(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    code: str,
    expected: str,
) -> None:
    project, _build = _fixed_project(tmp_path)
    data_root = (tmp_path / "plugin-data").absolute()

    class FactsFailure(Exception):
        pass

    error = FactsFailure("private facts failure")
    error.code = code
    monkeypatch.setattr(
        workflows, "load_fresh_firmware_facts", lambda _root: (_ for _ in ()).throw(error)
    )
    result = asyncio.run(
        workflows.target_test_prepare(
            workflows.TestingWorkflowContext(project, data_root, "session-r3"),
            probe_id=RAW_PROBE,
            case_ids=CASES,
        )
    )

    assert result.ok is False and result.code == expected


def test_postflash_contradiction_consumes_and_creates_no_testrun_root(tmp_path: Path) -> None:
    project, build = _fixed_project(tmp_path)
    data_root = (tmp_path / "plugin-data").absolute()
    workspace = WorkspacePaths.from_roots(
        data_root, project, build["logicalProjectId"], "session-r3"
    )
    identity = _fixed_identity(build, workspace)
    expected = calculate_inventory_digest("target", identity, CASES)
    board = _Board()
    events: list[tuple[object, ...]] = []
    segment = (project / "build/arm-debug/firmware.elf").read_bytes()[84:404]

    def factory() -> _SourceChangeBackend:
        return _SourceChangeBackend(
            board=board,
            physical_identity={
                "board_id": str(build["targetDevice"]), "mcu": "stm32f407vg",
                "target_id": str(build["targetDevice"]),
                "probe_serial_hash": sha256(RAW_PROBE.encode()).hexdigest(),
            },
            stream=_fixed_stream(identity, "f" * 64), flash_segment=segment, events=events,
        )

    seams = workflows.TargetWorkflowSeams(factory)
    context = workflows.TestingWorkflowContext(project, data_root, "session-r3")
    prepared = asyncio.run(
        workflows.target_test_prepare(context, probe_id=RAW_PROBE, case_ids=CASES, _seams=seams)
    )
    assert prepared.data["inventory_digest"] == expected
    failed = asyncio.run(
        workflows.target_test_execute(
            context, probe_id=RAW_PROBE,
            authorized_action_digest=prepared.data["authorized_action_digest"], _seams=seams,
        )
    )
    reused = asyncio.run(
        workflows.target_test_execute(
            context, probe_id=RAW_PROBE,
            authorized_action_digest=prepared.data["authorized_action_digest"], _seams=seams,
        )
    )
    assert failed.ok is False and reused.code == "TEST_AUTHORIZATION_INVALID"
    assert workflows.test_show(context, run_id="physical-r3-run").ok is False
    flash_bytes = (project / "artifacts/migration/flash-result.json").read_bytes()
    assert RAW_PROBE.encode() not in flash_bytes
    assert sha256(RAW_PROBE.encode()).hexdigest().encode() in flash_bytes


@pytest.mark.parametrize("failure", ["old-identity", "extra", "missing", "digest", "transport"])
def test_all_postflash_contract_failures_stay_consumed(
    tmp_path: Path, failure: str
) -> None:
    project, build = _fixed_project(tmp_path)
    data_root = (tmp_path / "plugin-data").absolute()
    workspace = WorkspacePaths.from_roots(
        data_root, project, build["logicalProjectId"], "session-r3"
    )
    fixed = _fixed_identity(build, workspace)
    expected = calculate_inventory_digest("target", fixed, CASES)
    observed_identity = fixed
    observed_cases = CASES
    observed_digest = expected
    if failure == "old-identity":
        observed_identity = EvidenceIdentity(
            fixed.workspace_id, fixed.project_id, fixed.session_id, "0" * 64,
            fixed.elf_sha256, fixed.target_device, fixed.input_snapshot_sha256,
            fixed.git_commit, fixed.git_dirty,
        )
    elif failure == "extra":
        observed_cases = (*CASES, "suite.extra")
    elif failure == "missing":
        observed_cases = CASES[:1]
    elif failure == "digest":
        observed_digest = "f" * 64
    board = _Board()
    events: list[tuple[object, ...]] = []
    segment = (project / "build/arm-debug/firmware.elf").read_bytes()[84:404]

    def factory() -> _SourceChangeBackend:
        return _SourceChangeBackend(
            board=board,
            physical_identity={
                "board_id": str(build["targetDevice"]), "mcu": "stm32f407vg",
                "target_id": str(build["targetDevice"]),
                "probe_serial_hash": sha256(RAW_PROBE.encode()).hexdigest(),
            },
            stream=_fixed_stream(observed_identity, observed_digest, observed_cases),
            flash_segment=segment, events=events,
            fail_transport=failure == "transport",
        )

    seams = workflows.TargetWorkflowSeams(factory)
    context = workflows.TestingWorkflowContext(project, data_root, "session-r3")
    prepared = asyncio.run(
        workflows.target_test_prepare(context, probe_id=RAW_PROBE, case_ids=CASES, _seams=seams)
    )
    failed = asyncio.run(
        workflows.target_test_execute(
            context, probe_id=RAW_PROBE,
            authorized_action_digest=prepared.data["authorized_action_digest"], _seams=seams,
        )
    )
    reused = asyncio.run(
        workflows.target_test_execute(
            context, probe_id=RAW_PROBE,
            authorized_action_digest=prepared.data["authorized_action_digest"], _seams=seams,
        )
    )
    assert failed.ok is False
    assert reused.code == "TEST_AUTHORIZATION_INVALID"
    assert workflows.test_show(context, run_id="physical-r3-run").ok is False
    assert len([event for event in events if event[:2] == ("flash", "modify")]) == 1


def test_static_source_drift_is_consumed_before_any_modify_work(tmp_path: Path) -> None:
    project, build = _fixed_project(tmp_path)
    data_root = (tmp_path / "plugin-data").absolute()
    events: list[tuple[object, ...]] = []
    board = _Board()
    segment = (project / "build/arm-debug/firmware.elf").read_bytes()[84:404]

    def factory() -> _SourceChangeBackend:
        workspace = WorkspacePaths.from_roots(
            data_root, project, build["logicalProjectId"], "session-r3"
        )
        identity = _fixed_identity(build, workspace)
        digest = calculate_inventory_digest("target", identity, CASES)
        return _SourceChangeBackend(
            board=board,
            physical_identity={
                "board_id": str(build["targetDevice"]), "mcu": "stm32f407vg",
                "target_id": str(build["targetDevice"]),
                "probe_serial_hash": sha256(RAW_PROBE.encode()).hexdigest(),
            },
            stream=_fixed_stream(identity, digest), flash_segment=segment, events=events,
        )

    seams = workflows.TargetWorkflowSeams(factory)
    context = workflows.TestingWorkflowContext(project, data_root, "session-r3")
    prepared = asyncio.run(
        workflows.target_test_prepare(context, probe_id=RAW_PROBE, case_ids=CASES, _seams=seams)
    )
    (project / "Src/main.c").write_bytes(b"int changed;\n")
    failed = asyncio.run(
        workflows.target_test_execute(
            context, probe_id=RAW_PROBE,
            authorized_action_digest=prepared.data["authorized_action_digest"], _seams=seams,
        )
    )
    reused = asyncio.run(
        workflows.target_test_execute(
            context, probe_id=RAW_PROBE,
            authorized_action_digest=prepared.data["authorized_action_digest"], _seams=seams,
        )
    )
    assert failed.code == "TEST_INVENTORY_CHANGED"
    assert reused.code == "TEST_AUTHORIZATION_INVALID"
    assert not [event for event in events if event[:2] == ("preflight", "modify")]


@pytest.mark.parametrize(
    ("transport", "project_transport", "required"),
    [
        ("mailbox", {"kind": "memory-mailbox", "options": {"address": 0x20000000, "size": 4096}}, {"address", "size", "ram", "target_id", "probe_id"}),
        ("rtt", {"kind": "rtt", "options": {"channel": 0}}, {"channel", "control_block_address", "ram", "target_id", "probe_id"}),
        ("uart", {"kind": "uart", "options": {"port": "COM9", "baud": 115200}}, {"port", "baud", "data_bits", "parity", "stop_bits", "target_id", "probe_id"}),
        ("semihosting", {"kind": "semihosting", "options": {}}, {"elf_path", "elf_sha256", "host_files", "target_id", "probe_id"}),
    ],
)
def test_probe_service_derives_all_runtime_transport_configs(
    tmp_path: Path, transport: str, project_transport: Mapping[str, object], required: set[str]
) -> None:
    project = prepare_project(
        tmp_path,
        overrides={
            "schemaVersion": 3,
            "testing": {
                "target": {
                    "executable": "build/arm-debug/firmware.elf",
                    "timeout_seconds": 10,
                    "transport": project_transport,
                }
            },
        },
    )
    build = _publish_current_debug_build(project)
    data_root = (tmp_path / "plugin-data").absolute()
    workspace = WorkspacePaths.from_roots(
        data_root, project, build["logicalProjectId"], "transport-session"
    )
    workspace.ensure()
    opened: list[Mapping[str, object]] = []

    class Backend:
        def preflight_target_capabilities(self, probe_id: str, level: object) -> None:
            pass

        def list_probes(self) -> tuple[ProbeDescriptor, ...]:
            return (ProbeDescriptor(RAW_PROBE, "ST", "ST-LINK", None),)

        def open_attach(self, probe_id: str, target: str, *, halt_on_connect: bool = False) -> ProbeAttachmentEvidence:
            return ProbeAttachmentEvidence(probe_id, target, target, 1)

        def target_identity(self) -> Mapping[str, object]:
            return {
                "board_id": str(build["targetDevice"]), "mcu": "stm32f407vg",
                "target_id": str(build["targetDevice"]),
                "probe_serial_hash": sha256(RAW_PROBE.encode()).hexdigest(),
            }

        def open_target_transport(self, name: str, config: Mapping[str, object], deadline_ms: int) -> Mapping[str, object]:
            assert name == transport
            opened.append(dict(config))
            return {"transport_id": "transport-one", "identity": {"transport": name}}

        def close_target_transport(self, transport_id: str) -> Mapping[str, object]:
            return {"transport_id": transport_id, "closed": True}

        def close(self) -> None:
            pass

    async def scenario() -> None:
        supervisor = ProbeServiceSupervisor(
            config=ProbeServiceConfig(
                RAW_PROBE, workspace.workspace_id, workspace.session_id,
                OperationLevel.MODIFY, workspace.session_root, project,
            ),
            lease_manager=ProbeLeaseManager(data_root), backend_factory=Backend,
        )
        client: ProbeClient | None = None
        try:
            client = ProbeClient(await supervisor.start())
            await client.attach(RAW_PROBE, "stm32f407vg")
            result = await client.target_transport_open(transport, project_transport, 1000)
            await client.target_transport_close(str(result["transport_id"]))
        finally:
            if client is not None:
                await client.close()
            await supervisor.stop()

    asyncio.run(scenario())
    assert len(opened) == 1 and set(opened[0]) == required
    assert opened[0]["probe_id"] == sha256(RAW_PROBE.encode()).hexdigest()
    if transport == "semihosting":
        assert Path(str(opened[0]["elf_path"])).is_absolute()


def test_probe_service_orders_unsorted_project_ram_for_mailbox_without_memory_io(
    tmp_path: Path,
) -> None:
    project_transport = {
        "kind": "memory-mailbox",
        "options": {"address": 0x2002EFF0, "size": 4096},
    }
    project = prepare_project(
        tmp_path,
        overrides={
            "schemaVersion": 3,
            "memory": {
                "source": "manual",
                "regions": [
                    {
                        "name": "IROM1",
                        "origin": 0x08000000,
                        "length": 0x100000,
                        "attributes": "r-x",
                    },
                    {
                        "name": "IRAM1",
                        "origin": 0x20000000,
                        "length": 0x2EFF0,
                        "attributes": "rwx",
                    },
                    {
                        "name": "MAILBOX",
                        "origin": 0x2002EFF0,
                        "length": 0x1010,
                        "attributes": "rw-",
                    },
                    {
                        "name": "IRAM2",
                        "origin": 0x10000000,
                        "length": 0x10000,
                        "attributes": "rwx",
                    },
                ],
            },
            "testing": {
                "target": {
                    "executable": "build/arm-debug/firmware.elf",
                    "timeout_seconds": 10,
                    "transport": project_transport,
                }
            },
        },
    )
    build = _publish_current_debug_build(project)
    data_root = (tmp_path / "plugin-data").absolute()
    workspace = WorkspacePaths.from_roots(
        data_root, project, build["logicalProjectId"], "service-ram-order"
    )
    workspace.ensure()
    events: list[tuple[object, ...]] = []
    opened: list[Mapping[str, object]] = []

    class Backend:
        def preflight_target_capabilities(self, probe_id: str, level: object) -> None:
            events.append(("preflight",))

        def list_probes(self) -> tuple[ProbeDescriptor, ...]:
            return (ProbeDescriptor(RAW_PROBE, "ST", "ST-LINK", None),)

        def open_attach(
            self, probe_id: str, target: str, *, halt_on_connect: bool = False
        ) -> ProbeAttachmentEvidence:
            events.append(("attach", probe_id, target, halt_on_connect))
            return ProbeAttachmentEvidence(probe_id, target, target, 1)

        def target_identity(self) -> Mapping[str, object]:
            return {
                "board_id": str(build["targetDevice"]),
                "mcu": "stm32f407vg",
                "target_id": str(build["targetDevice"]),
                "probe_serial_hash": sha256(RAW_PROBE.encode()).hexdigest(),
            }

        def read_memory(self, address: int, length: int) -> bytes:
            events.append(("read_memory", address, length))
            raise AssertionError("mailbox transport open must not read target memory")

        def write_memory(self, address: int, data: bytes) -> None:
            events.append(("write_memory", address, data))
            raise AssertionError("mailbox transport open must not write target memory")

        def open_target_transport(
            self, name: str, config: Mapping[str, object], deadline_ms: int
        ) -> Mapping[str, object]:
            assert name == "mailbox"
            opened.append(dict(config))
            return {"transport_id": "transport-one", "identity": {"transport": name}}

        def close_target_transport(self, transport_id: str) -> Mapping[str, object]:
            return {"transport_id": transport_id, "closed": True}

        def close(self) -> None:
            pass

    backend = Backend()

    async def scenario() -> None:
        supervisor = ProbeServiceSupervisor(
            config=ProbeServiceConfig(
                RAW_PROBE,
                workspace.workspace_id,
                workspace.session_id,
                OperationLevel.MODIFY,
                workspace.session_root,
                project,
            ),
            lease_manager=ProbeLeaseManager(data_root),
            backend_factory=lambda: backend,
        )
        client: ProbeClient | None = None
        try:
            client = ProbeClient(await supervisor.start())
            await client.attach(RAW_PROBE, "stm32f407vg")
            result = await client.target_transport_open(
                "mailbox", project_transport, 1000
            )
            await client.target_transport_close(str(result["transport_id"]))
        finally:
            if client is not None:
                await client.close()
            await supervisor.stop()

    asyncio.run(scenario())
    assert len(opened) == 1
    assert opened[0]["ram"] == [
        {"start": 0x10000000, "size": 0x10000},
        {"start": 0x20000000, "size": 0x2EFF0},
        {"start": 0x2002EFF0, "size": 0x1010},
    ]
    assert not [
        event for event in events if event[0] in {"read_memory", "write_memory"}
    ]


def test_busy_prepare_reports_owner_without_stealing_the_live_lease(tmp_path: Path) -> None:
    project, build = _fixed_project(tmp_path)
    data_root = (tmp_path / "plugin-data").absolute()
    blocking = WorkspacePaths.from_roots(
        data_root, project, build["logicalProjectId"], "blocking-session"
    )
    blocking.ensure()
    board = _Board()
    events: list[tuple[object, ...]] = []
    segment = (project / "build/arm-debug/firmware.elf").read_bytes()[84:404]

    def factory() -> _SourceChangeBackend:
        return _SourceChangeBackend(
            board=board,
            physical_identity={
                "board_id": str(build["targetDevice"]), "mcu": "stm32f407vg",
                "target_id": str(build["targetDevice"]),
                "probe_serial_hash": sha256(RAW_PROBE.encode()).hexdigest(),
            },
            stream=b"", flash_segment=segment, events=events,
        )

    async def scenario() -> None:
        blocker = ProbeServiceSupervisor(
            config=ProbeServiceConfig(
                RAW_PROBE, blocking.workspace_id, blocking.session_id,
                OperationLevel.OBSERVE, blocking.session_root, project,
            ),
            lease_manager=ProbeLeaseManager(data_root), backend_factory=factory,
        )
        client: ProbeClient | None = None
        try:
            client = ProbeClient(await blocker.start())
            result = await workflows.target_test_prepare(
                workflows.TestingWorkflowContext(project, data_root, "session-r3"),
                probe_id=RAW_PROBE, case_ids=CASES,
                _seams=workflows.TargetWorkflowSeams(factory),
            )
            assert result.ok is False and result.code == "PROBE_BUSY"
            await client.attach(RAW_PROBE, "stm32f407vg")
            assert (await client.target_identity())["probe_serial_hash"] == sha256(RAW_PROBE.encode()).hexdigest()
        finally:
            if client is not None:
                await client.close()
            await blocker.stop()

    asyncio.run(scenario())
