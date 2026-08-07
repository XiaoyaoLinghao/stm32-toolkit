from __future__ import annotations

import json
import asyncio
import os
import stat
from dataclasses import FrozenInstanceError
from pathlib import Path
from types import SimpleNamespace

import pytest

from stm32_toolkit import __version__
from stm32_toolkit.build.identity import atomic_write_json, utc_now_rfc3339
from stm32_toolkit.debug.firmware import bind_debug_firmware
from stm32_toolkit.debug import firmware as firmware_mod
from stm32_toolkit.debug import model as model_mod
from stm32_toolkit.debug.model import (
    DebugBindingRequest,
    DebugFirmwareBinding,
    DebugReadItem,
    DebugReadReport,
    FaultReport,
    FloatEvidence,
    IntegerEvidence,
    MemoryRegionBinding,
    RegisterEvidence,
    SampleReport,
    SvdSelectionEvidence,
    TypedLocation,
    TypedValue,
)
from stm32_toolkit.probe.backend import ProbeAttachmentEvidence
from stm32_toolkit.probe.model import OperationLevel, PROBE_PROTOCOL_VERSION
from test_build_runner import prepare_project
from test_flash import _elf_with_flash_segment, _publish_current_debug_build


def _flash_result(identity: dict[str, object], *, session: str = "flash-session") -> dict[str, object]:
    return {
        "schemaVersion": 1,
        "status": "success",
        "code": "OK",
        "toolkitVersion": __version__,
        "buildId": identity["buildId"],
        "elfSha256": identity["elfSha256"],
        "elfSize": identity["elfSize"],
        "targetDevice": identity["targetDevice"],
        "debugTarget": "stm32f407vg",
        "probeId": "probe-123",
        "workspaceId": "workspace-a",
        "sessionId": session,
        "verifiedBytes": 320,
        "backendBytesProgrammed": None,
        "backendSectorsProgrammed": None,
        "startedAtUtc": utc_now_rfc3339(),
        "finishedAtUtc": utc_now_rfc3339(),
        "flashResultPath": "artifacts/migration/flash-result.json",
        "elfPath": "build/arm-debug/firmware.elf",
        "gitHead": identity["gitHead"],
        "gitDirty": identity["gitDirty"],
        "inputSnapshotSha256": identity["inputSnapshotSha256"],
        "operationLevel": "modify",
        "authorized": True,
    }


class BindingClient:
    def __init__(self, image: bytes) -> None:
        self.endpoint = SimpleNamespace(
            protocol=PROBE_PROTOCOL_VERSION,
            toolkit_version=__version__,
            host="127.0.0.1",
            port=43123,
            token="11" * 32,
            workspace_id="workspace-a",
            session_id="observe-session",
            lease_id="lease-observe",
            probe_id="probe-123",
            operation_level=OperationLevel.OBSERVE,
        )
        self.image = image
        self.events: list[tuple[object, ...]] = []
        self.resolved_target = "STM32F407VG"
        self.after_read = None
        self.attach_error: BaseException | None = None
        self.read_error: BaseException | None = None

    async def attach(self, probe_id: str, target: str) -> ProbeAttachmentEvidence:
        self.events.append(("attach", probe_id, target))
        if self.attach_error is not None:
            raise self.attach_error
        return ProbeAttachmentEvidence(
            probe_id=probe_id,
            requested_target=target,
            resolved_part_number=self.resolved_target,
            core_count=1,
        )

    async def read_memory(self, address: int, length: int) -> bytes:
        self.events.append(("read", address, length))
        if self.read_error is not None:
            raise self.read_error
        if callable(self.after_read):
            callback, self.after_read = self.after_read, None
            callback()
        offset = address - 0x08000000
        return self.image[offset : offset + length]


@pytest.fixture
def binding_env(tmp_path: Path):
    root = prepare_project(tmp_path / "project")
    identity = _publish_current_debug_build(root)
    atomic_write_json(root / "artifacts" / "migration" / "flash-result.json", _flash_result(identity))
    image = _elf_with_flash_segment()[84 : 84 + 320]
    client = BindingClient(image)
    request = DebugBindingRequest(
        project_root=root,
        probe_id="probe-123",
        target="stm32f407vg",
        workspace_id="workspace-a",
        observation_session_id="observe-session",
        lease_id="lease-observe",
        expected_build_id=str(identity["buildId"]),
        expected_elf_sha256=str(identity["elfSha256"]),
    )
    return root, identity, client, request


def _snapshot(root: Path) -> tuple[dict[str, tuple[bytes, int, int]], str]:
    files: dict[str, tuple[bytes, int, int]] = {}
    for path in sorted(root.rglob("*")):
        if ".git" in path.parts or not path.is_file():
            continue
        info = path.stat()
        files[path.relative_to(root).as_posix()] = (
            path.read_bytes(),
            info.st_mtime_ns,
            stat.S_IMODE(info.st_mode),
        )
    import subprocess

    porcelain = subprocess.run(
        ["git", "status", "--porcelain=v1", "-z"],
        cwd=root,
        check=True,
        capture_output=True,
    ).stdout.decode("utf-8")
    return files, porcelain


def test_models_are_frozen_deeply_json_safe_and_lossless():
    integer = IntegerEvidence(decimal="-9223372036854775808", raw_hex="0x8000000000000000", bit_width=64, signed=True)
    floating = FloatEvidence.symbolic("negativeInfinity", raw_hex="0xff800000", bit_width=32)
    location = TypedLocation("counter", 0x20000000, 8, "long long", "integer", 64, True, "RAM")
    value = TypedValue("counter", "long long", integer.to_dict(), integer.raw_hex, 64)
    assert integer.to_dict()["decimal"] == "-9223372036854775808"
    assert floating.to_dict()["value"] == "negativeInfinity"
    assert json.dumps({"location": location.to_dict(), "value": value.to_dict(), "float": floating.to_dict()}, allow_nan=False)
    with pytest.raises(FrozenInstanceError):
        integer.decimal = "0"  # type: ignore[misc]
    with pytest.raises(TypeError):
        value.value["decimal"] = "0"  # type: ignore[index]


def test_debug_package_exports_task_one_contracts_without_importing_pyocd():
    import sys
    import stm32_toolkit.debug as debug

    assert debug.DebugBindingRequest is DebugBindingRequest
    assert debug.bind_debug_firmware is bind_debug_firmware
    assert debug.SvdSelectionEvidence is SvdSelectionEvidence
    assert "pyocd" not in sys.modules


@pytest.mark.parametrize(
    "factory",
    [
        lambda: IntegerEvidence("1", "0x01", True, False),
        lambda: FloatEvidence.symbolic("NaN", raw_hex="0x7fc00000", bit_width=32),
        lambda: TypedLocation("x", True, 1, "u8", "integer", 8, False, "RAM"),
        lambda: MemoryRegionBinding("RAM", 0x20000000, True, "rwx"),
    ],
)
def test_models_reject_booleans_as_integers_and_noncanonical_symbols(factory):
    with pytest.raises((TypeError, ValueError)):
        factory()


def _model_binding(**updates: object) -> DebugFirmwareBinding:
    values: dict[str, object] = {
        "logical_project_id": "12345678-1234-1234-1234-123456789abc",
        "workspace_id": "workspace-a",
        "observation_session_id": "observe-session",
        "flash_session_id": "flash-session",
        "lease_id": "lease-a",
        "probe_id": "probe-123",
        "target_device": "STM32F407VGTx",
        "debug_target": "stm32f407vg",
        "build_id": "1" * 64,
        "elf_sha256": "2" * 64,
        "elf_size": 320,
        "elf_path": "build/arm-debug/firmware.elf",
        "input_snapshot_sha256": "3" * 64,
        "git_head": "4" * 40,
        "git_dirty": False,
        "confirmed_at_utc": "2026-08-08T01:02:03.000004Z",
        "memory_regions": (MemoryRegionBinding("FLASH", 0x08000000, 1024, "r-x"),),
        "project_root": Path(__file__).resolve().parents[3],
    }
    values.update(updates)
    return DebugFirmwareBinding(**values)  # type: ignore[arg-type]


def test_all_shared_reports_are_frozen_json_documents():
    binding = _model_binding()
    value = TypedValue("x", "uint32_t", {"nested": [True, None, 3, 1.25]}, "0x00000003", 32)
    ok = DebugReadItem("x", "ok", value)
    failed = DebugReadItem("y", "error", code="DEBUG_VALUE_UNAVAILABLE")
    read = DebugReadReport(binding, (ok, failed), binding.confirmed_at_utc)
    svd = SvdSelectionEvidence("STM32F407VGTx", "svd/STM32F407.svd", "5" * 64)
    register = RegisterEvidence("GPIOA.ODR", 0x40020014, 4, "read-write", "read-clear")
    sample = SampleReport(binding, 50, 100, ({"items": [ok.to_dict()]},), 9.5, 1, 2)
    fault = FaultReport(binding, "halted", {"pc": "0x08000100"}, {"cfsr": 0}, None, {"pc": "Reset_Handler"}, binding.confirmed_at_utc)
    document = {
        "read": read.to_dict(),
        "svd": svd.to_dict(),
        "register": register.to_dict(),
        "sample": sample.to_dict(),
        "fault": fault.to_dict(),
    }
    assert json.dumps(document, allow_nan=False)
    with pytest.raises(TypeError):
        sample.samples[0]["items"] = []  # type: ignore[index]
    with pytest.raises(TypeError):
        fault.registers["pc"] = "changed"  # type: ignore[index]


def test_binding_internal_project_root_is_canonical_compared_and_never_serialized(tmp_path: Path):
    root = (tmp_path / "project").resolve()
    root.mkdir()
    binding = _model_binding(project_root=root)
    assert binding.project_root == root
    assert "project_root" not in repr(binding)
    assert "projectRoot" not in binding.to_dict()
    assert binding != _model_binding(project_root=tmp_path.resolve())
    with pytest.raises((TypeError, ValueError)):
        _model_binding(project_root=Path("relative"))
    with pytest.raises((TypeError, ValueError)):
        _model_binding(project_root=tmp_path / "missing")


@pytest.mark.parametrize(
    "item",
    [
        DebugReadItem("x", "ok", TypedValue("x", "u8", 1, "0x01", 8)),
        DebugReadItem("x", "error", code="DEBUG_UNAVAILABLE"),
    ],
)
def test_read_item_xor_contract_accepts_only_coherent_variants(item: DebugReadItem):
    assert json.dumps(item.to_dict(), allow_nan=False)


@pytest.mark.parametrize(
    "factory",
    [
        lambda: DebugReadItem("x", "ok"),
        lambda: DebugReadItem("x", "ok", TypedValue("x", "u8", 1, "0x01", 8), "ERROR"),
        lambda: DebugReadItem("x", "error"),
        lambda: DebugReadItem("x", "error", TypedValue("x", "u8", 1, "0x01", 8), "ERROR"),
        lambda: DebugReadItem("x", "other", code="ERROR"),
        lambda: DebugReadItem("bad\x00", "error", code="ERROR"),
        lambda: DebugReadItem("x", "error", code="bad code"),
        lambda: DebugReadItem("x", "ok", TypedValue("y", "u8", 1, "0x01", 8)),
        lambda: DebugReadReport(object(), (), "2026-08-08T01:02:03.000004Z"),
        lambda: DebugReadReport(_model_binding(), [], "2026-08-08T01:02:03.000004Z"),
        lambda: DebugReadReport(_model_binding(), (), "invalid"),
        lambda: RegisterEvidence("GPIOA.IDR", 0, 4, "write-only"),
        lambda: RegisterEvidence("GPIOA.IDR", 0, 4, "read-only", "bad-effect"),
        lambda: SampleReport(object(), 100, 100, (), 1.0, 0, 0),
        lambda: SampleReport(_model_binding(), 100, 100, [], 1.0, 0, 0),
        lambda: SampleReport(_model_binding(), 100, 100, ({1: "bad"},), 1.0, 0, 0),
        lambda: SampleReport(_model_binding(), 100, 100, (1,), 1.0, 0, 0),
        lambda: FaultReport(object(), "halted", {}, {}, None, {}, "2026-08-08T01:02:03.000004Z"),
        lambda: FaultReport(_model_binding(), "running", {}, {}, None, {}, "2026-08-08T01:02:03.000004Z"),
        lambda: FaultReport(_model_binding(), "halted", [], {}, None, {}, "2026-08-08T01:02:03.000004Z"),
        lambda: FaultReport(_model_binding(), "halted", {}, {}, None, {}, "invalid"),
        lambda: FaultReport(_model_binding(), "halted", {}, {}, None, {}, "2026-08-08T01:02:03.000004Z", "halt"),
        lambda: TypedValue("x", "u16", 1, "0x01", 16),
        lambda: TypedLocation("x", 0, 1, "u16", "integer", 16, False, "RAM"),
        lambda: _model_binding(project_root="bad"),
        lambda: _model_binding(project_root=Path(".")),
        lambda: IntegerEvidence("1", "0x01", 8, 1),
        lambda: IntegerEvidence("0", "0x1ff", 8, False),
    ],
)
def test_report_and_strong_value_invariants_fail_closed(factory):
    with pytest.raises((TypeError, ValueError)):
        factory()


def test_deep_json_budgets_fail_before_mutable_output(monkeypatch):
    monkeypatch.setattr(model_mod, "_MAX_JSON_NODES", 3)
    with pytest.raises(ValueError, match="node budget"):
        TypedValue("x", "array", [1, 2, 3], "0x000000", 24)
    monkeypatch.setattr(model_mod, "_MAX_JSON_NODES", 200_000)
    monkeypatch.setattr(model_mod, "_MAX_JSON_STRING_CHARS", 3)
    with pytest.raises(ValueError, match="string budget"):
        TypedValue("x", "text", "long", "0x00", 8)


def test_deep_json_nesting_is_bounded():
    value: object = 0
    for _ in range(66):
        value = [value]
    with pytest.raises(ValueError, match="nesting budget"):
        TypedValue("x", "nested", value, "0x00", 8)


@pytest.mark.parametrize(
    "factory",
    [
        lambda: MemoryRegionBinding("bad path", 0, 1, "r"),
        lambda: MemoryRegionBinding("RAM", 0xFFFFFFFF, 2, "r"),
        lambda: MemoryRegionBinding("RAM", 0, 1, "q"),
        lambda: _model_binding(build_id="bad"),
        lambda: _model_binding(git_head=""),
        lambda: _model_binding(git_dirty=1),
        lambda: _model_binding(elf_size=0),
        lambda: _model_binding(elf_path="../firmware.elf"),
        lambda: _model_binding(confirmed_at_utc="today"),
        lambda: _model_binding(memory_regions=[]),
        lambda: IntegerEvidence("01", "0x01", 8, False),
        lambda: IntegerEvidence("1", "01", 8, False),
        lambda: IntegerEvidence("1", "0x0001", 8, False),
        lambda: IntegerEvidence("256", "0xff", 8, False),
        lambda: IntegerEvidence("-1", "0xff", 8, False),
        lambda: IntegerEvidence("1", "0x02", 8, False),
        lambda: FloatEvidence(1.0, "0x00000000", 48),
        lambda: FloatEvidence(float("nan"), "0x7fc00000", 32),
        lambda: FloatEvidence(1.0, "bad", 32),
        lambda: FloatEvidence(1.0, "0x00", 32),
        lambda: TypedLocation("", 0, 1, "u8", "integer", 8, False, "RAM"),
        lambda: TypedLocation("x", 0, 1, "u8", "integer", 8, 1, "RAM"),
        lambda: TypedLocation("x", 0, 1, "", "integer", 8, False, "RAM"),
        lambda: TypedValue("", "u8", 1, "0x01", 8),
        lambda: TypedValue("x", "", 1, "0x01", 8),
        lambda: TypedValue("x", "u8", float("inf"), "0x01", 8),
        lambda: TypedValue("x", "u8", {1: "bad"}, "0x01", 8),
        lambda: TypedValue("x", "u8", object(), "0x01", 8),
        lambda: TypedValue("x", "u8", 1, "bad", 8),
        lambda: SvdSelectionEvidence("bad target", "svd/a.svd", "1" * 64),
        lambda: SvdSelectionEvidence("target", "../a.svd", "1" * 64),
        lambda: SvdSelectionEvidence("target", "svd/a.svd", "bad"),
        lambda: RegisterEvidence("", 0, 4, "read"),
        lambda: RegisterEvidence("GPIOA.ODR", 0, 9, "read"),
        lambda: SampleReport(_model_binding(), True, 100, (), 1.0, 0, 0),
        lambda: SampleReport(_model_binding(), 100, 99, (), 1.0, 0, 0),
        lambda: SampleReport(_model_binding(), 100, 100, (), float("nan"), 0, 0),
    ],
)
def test_model_invalid_boundaries_fail_closed(factory):
    with pytest.raises((TypeError, ValueError)):
        factory()


def test_bind_records_distinct_observation_and_flash_sessions_and_is_read_only(binding_env):
    root, identity, client, request = binding_env
    before = _snapshot(root)
    result = asyncio.run(bind_debug_firmware(request, client))
    after = _snapshot(root)
    assert result.ok is True
    binding = result.data
    assert isinstance(binding, DebugFirmwareBinding)
    assert binding.workspace_id == "workspace-a"
    assert binding.observation_session_id == "observe-session"
    assert binding.flash_session_id == "flash-session"
    assert binding.build_id == identity["buildId"]
    assert binding.elf_sha256 == identity["elfSha256"]
    assert binding.elf_path == "build/arm-debug/firmware.elf"
    assert binding.project_root == root.resolve()
    assert "projectRoot" not in binding.to_dict()
    assert binding.to_dict()["observationSessionId"] != binding.to_dict()["flashSessionId"]
    assert before == after
    assert client.events[0] == ("attach", "probe-123", "stm32f407vg")
    assert sum(event[2] for event in client.events if event[0] == "read") == 320


@pytest.mark.parametrize("field", ["expected_build_id", "expected_elf_sha256"])
def test_caller_pins_fail_before_hardware(binding_env, field: str):
    _, _, client, request = binding_env
    object.__setattr__(request, field, "0" * 64)
    result = asyncio.run(bind_debug_firmware(request, client))
    assert result.ok is False
    assert result.code == "DEBUG_PLAN_CHANGED"
    assert client.events == []


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("protocol", "wrong"),
        ("toolkit_version", "0.0.0"),
        ("port", True),
        ("port", 0),
        ("token", 123),
        ("token", "g" * 64),
        ("workspace_id", "wrong"),
        ("observation_session_id", "wrong"),
        ("lease_id", "wrong"),
        ("probe_id", "wrong"),
        ("operation_level", OperationLevel.MODIFY),
        ("host", "0.0.0.0"),
    ],
)
def test_exact_client_endpoint_is_required_before_hardware(binding_env, field: str, value: object):
    _, _, client, request = binding_env
    if hasattr(request, field):
        object.__setattr__(request, field, value)
    else:
        setattr(client.endpoint, field, value)
    result = asyncio.run(bind_debug_firmware(request, client))
    assert result.ok is False
    assert result.code == "DEBUG_ENDPOINT_MISMATCH"
    assert client.events == []


def test_attachment_and_readback_mismatch_fail_closed(binding_env):
    _, _, client, request = binding_env
    client.resolved_target = "STM32F429ZI"
    result = asyncio.run(bind_debug_firmware(request, client))
    assert result.ok is False and result.code == "DEBUG_TARGET_MISMATCH"
    client.resolved_target = "STM32F407VG"
    client.events.clear()
    client.image = b"\x00" * len(client.image)
    result = asyncio.run(bind_debug_firmware(request, client))
    assert result.ok is False and result.code == "DEBUG_READBACK_MISMATCH"


def test_disk_change_during_readback_is_rejected(binding_env):
    root, _, client, request = binding_env
    map_path = root / "build" / "arm-debug" / "firmware.map"
    client.after_read = lambda: map_path.write_bytes(map_path.read_bytes() + b"changed")
    result = asyncio.run(bind_debug_firmware(request, client))
    assert result.ok is False
    assert result.code == "DEBUG_FIRMWARE_CHANGED"


def test_flash_must_match_workspace_probe_target_and_current_firmware(binding_env):
    root, identity, client, request = binding_env
    document = _flash_result(identity)
    document["workspaceId"] = "other-workspace"
    atomic_write_json(root / "artifacts" / "migration" / "flash-result.json", document)
    result = asyncio.run(bind_debug_firmware(request, client))
    assert result.ok is False
    assert result.code == "DEBUG_FLASH_MISMATCH"
    assert client.events == []


def test_invalid_request_and_noncanonical_project_root_are_stable(binding_env, tmp_path: Path):
    root, _, client, request = binding_env
    assert asyncio.run(bind_debug_firmware(object(), client)).code == "DEBUG_REQUEST_INVALID"
    if os.name != "nt":
        alias = tmp_path / "alias"
        alias.symlink_to(root, target_is_directory=True)
        object.__setattr__(request, "project_root", alias)
        assert asyncio.run(bind_debug_firmware(request, client)).code == "DEBUG_REQUEST_INVALID"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("project_root", "not-a-path"),
        ("project_root", Path("missing-project")),
        ("probe_id", "bad probe"),
        ("expected_build_id", "bad"),
    ],
)
def test_request_fields_are_bounded_before_endpoint(binding_env, field: str, value: object):
    _, _, client, request = binding_env
    object.__setattr__(request, field, value)
    result = asyncio.run(bind_debug_firmware(request, client))
    assert result.code == "DEBUG_REQUEST_INVALID"
    assert client.events == []


def test_missing_or_invalid_firmware_and_flash_evidence_are_stable(binding_env, monkeypatch):
    root, identity, client, request = binding_env
    flash_path = root / "artifacts" / "migration" / "flash-result.json"
    flash_path.unlink()
    assert asyncio.run(bind_debug_firmware(request, client)).code == "DEBUG_FLASH_REQUIRED"
    atomic_write_json(flash_path, _flash_result(identity, session="bad session"))
    assert asyncio.run(bind_debug_firmware(request, client)).code == "DEBUG_FLASH_MISMATCH"
    monkeypatch.setattr(firmware_mod, "_load_fresh_firmware", lambda root: (_ for _ in ()).throw(RuntimeError()))
    assert asyncio.run(bind_debug_firmware(request, client)).code == "DEBUG_FIRMWARE_INVALID"


def test_project_target_pin_fails_before_attach(binding_env):
    _, _, client, request = binding_env
    object.__setattr__(request, "target", "stm32f429zi")
    result = asyncio.run(bind_debug_firmware(request, client))
    assert result.code == "DEBUG_TARGET_MISMATCH"
    assert client.events == []


@pytest.mark.parametrize("phase", ["attach", "read"])
def test_cancellation_propagates(binding_env, phase: str):
    _, _, client, request = binding_env
    setattr(client, f"{phase}_error", asyncio.CancelledError())
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(bind_debug_firmware(request, client))


def test_changed_flash_after_readback_and_unexpected_internal_error_are_stable(binding_env, monkeypatch):
    _, _, client, request = binding_env
    real_flash = firmware_mod._flash
    calls = 0

    def changed_flash(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise firmware_mod._fail("DEBUG_FIRMWARE_CHANGED", "changed")
        return real_flash(*args, **kwargs)

    monkeypatch.setattr(firmware_mod, "_flash", changed_flash)
    assert asyncio.run(bind_debug_firmware(request, client)).code == "DEBUG_FIRMWARE_CHANGED"
    monkeypatch.setattr(firmware_mod, "_flash", real_flash)
    monkeypatch.setattr(firmware_mod, "DebugFirmwareBinding", lambda **kwargs: (_ for _ in ()).throw(RuntimeError()))
    assert asyncio.run(bind_debug_firmware(request, client)).code == "DEBUG_INTERNAL_ERROR"
