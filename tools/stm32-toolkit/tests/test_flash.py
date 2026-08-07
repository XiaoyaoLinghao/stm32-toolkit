from __future__ import annotations

import asyncio
import hashlib
import json
import struct
from pathlib import Path
from types import SimpleNamespace

import pytest

from stm32_toolkit.build.identity import (
    atomic_write_json,
    build_identity_document,
    compute_build_id,
    git_evidence,
    snapshot_project_inputs,
    utc_now_rfc3339,
    validate_elf,
)
from stm32_toolkit.build.runner import build_result_document
from stm32_toolkit.probe.backend import FlashBackendReport
from stm32_toolkit.probe import flash as flash_mod
from stm32_toolkit.probe.flash import FlashRequest, flash_firmware
from stm32_toolkit.project_model import load_project_model
from test_build_runner import build_elf_bytes, build_map_text, prepare_project


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _elf_with_flash_segment(*, text_size: int = 256) -> bytes:
    """Add one PT_LOAD header to the shared valid ELF fixture.

    The fixture's first two sections are contiguous `.isr_vector` (64 bytes)
    and `.text` (256 bytes) beginning immediately after the ELF header.
    """

    original = build_elf_bytes(alloc_sections=(), text_size=text_size)
    old_shoff = struct.unpack_from("<I", original, 32)[0]
    shnum = struct.unpack_from("<H", original, 48)[0]
    shentsize = struct.unpack_from("<H", original, 46)[0]
    assert shentsize == 40

    image = bytearray(original)
    image[52:52] = b"\x00" * 32
    new_shoff = old_shoff + 32
    struct.pack_into("<I", image, 28, 52)
    struct.pack_into("<I", image, 32, new_shoff)
    struct.pack_into("<H", image, 42, 32)
    struct.pack_into("<H", image, 44, 1)
    struct.pack_into(
        "<IIIIIIII",
        image,
        52,
        1,  # PT_LOAD
        84,  # file offset after the inserted program header
        0x08000000,
        0x08000000,
        64 + text_size,
        64 + text_size,
        5,  # PF_R | PF_X
        4,
    )
    for index in range(1, shnum):
        header = new_shoff + index * shentsize
        section_offset = struct.unpack_from("<I", image, header + 16)[0]
        if section_offset >= 52:
            struct.pack_into("<I", image, header + 16, section_offset + 32)
    return bytes(image)


def _publish_current_debug_build(
    root: Path, *, with_segment: bool = True, text_size: int = 256
) -> dict:
    model = load_project_model(root)
    snapshot = snapshot_project_inputs(model)
    git = git_evidence(root)
    elf_data = (
        _elf_with_flash_segment(text_size=text_size)
        if with_segment
        else build_elf_bytes(alloc_sections=(), text_size=text_size)
    )
    map_data = build_map_text(
        sections=(
            (".isr_vector", 0x08000000, 0x40, None),
            (".text", 0x08000040, 0x100, None),
        )
    ).encode("utf-8")
    elf_path = root / "build" / "arm-debug" / "firmware.elf"
    map_path = root / "build" / "arm-debug" / "firmware.map"
    elf_path.parent.mkdir(parents=True, exist_ok=True)
    elf_path.write_bytes(elf_data)
    map_path.write_bytes(map_data)
    elf = validate_elf(elf_path, model)
    identity = build_identity_document(
        model=model,
        preset="arm-debug",
        git=git,
        snapshot=snapshot,
        elf=elf,
        elf_size=len(elf_data),
        elf_sha256=_sha256(elf_data),
        map_size=len(map_data),
        map_sha256=_sha256(map_data),
        built_at_utc=utc_now_rfc3339(),
    )
    identity_path = root / "build" / "arm-debug" / "firmware-identity.json"
    atomic_write_json(identity_path, identity)
    result = build_result_document(
        status="success",
        stage="complete",
        code="OK",
        build_id=str(identity["buildId"]),
        git_head=str(identity["gitHead"]),
        git_dirty=bool(identity["gitDirty"]),
        input_snapshot_sha256=str(identity["inputSnapshotSha256"]),
        target_device=str(identity["targetDevice"]),
        preset="arm-debug",
        started_at_utc=utc_now_rfc3339(),
        finished_at_utc=utc_now_rfc3339(),
        duration_ms=1,
        artifacts=[
            {
                "kind": "elf",
                "path": "build/arm-debug/firmware.elf",
                "sha256": _sha256(elf_data),
                "size": len(elf_data),
            },
            {
                "kind": "map",
                "path": "build/arm-debug/firmware.map",
                "sha256": _sha256(map_data),
                "size": len(map_data),
            },
        ],
        memory=[],
        warnings=[],
    )
    atomic_write_json(root / "artifacts" / "migration" / "build-result.json", result)
    return identity


class RecordingFlashClient:
    def __init__(
        self,
        image: bytes,
        *,
        endpoint_probe_id: str = "probe-123",
        endpoint_level: str = "modify",
        resolved_target: str = "STM32F407VG",
    ) -> None:
        self.endpoint = SimpleNamespace(
            workspace_id="workspace-a",
            session_id="session-a",
            probe_id=endpoint_probe_id,
            operation_level=endpoint_level,
        )
        self.image = image
        self.resolved_target = resolved_target
        self.events: list[tuple[object, ...]] = []

    async def attach(self, probe_id: str, target: str) -> object:
        self.events.append(("attach", probe_id, target))
        return SimpleNamespace(
            probe_id=probe_id,
            requested_target=target,
            resolved_part_number=self.resolved_target,
            core_count=1,
        )

    async def program_verified_elf(
        self,
        elf_path: str,
        elf_sha256: str,
        elf_size: int,
        *,
        timeout_ms: int = 30000,
    ) -> FlashBackendReport:
        self.events.append(
            ("program", elf_path, elf_sha256, elf_size, timeout_ms)
        )
        return FlashBackendReport(bytes_programmed=None, sectors_programmed=None)

    async def read_memory(self, address: int, length: int) -> bytes:
        self.events.append(("read", address, length))
        offset = address - 0x08000000
        return self.image[offset : offset + length]


def _request(root: Path, identity: dict, **overrides: object) -> FlashRequest:
    fields: dict[str, object] = {
        "project_root": root,
        "probe_id": "probe-123",
        "target": "stm32f407vg",
        "expected_build_id": identity["buildId"],
        "expected_elf_sha256": identity["elfSha256"],
        "authorized": True,
    }
    fields.update(overrides)
    return FlashRequest(**fields)  # type: ignore[arg-type]


@pytest.mark.parametrize("authorized", [False, "true", 1, None, [], {}])
def test_flash_requires_exact_boolean_authorization(
    tmp_path: Path, authorized: object
) -> None:
    root = prepare_project(tmp_path)
    identity = _publish_current_debug_build(root)
    client = RecordingFlashClient(_elf_with_flash_segment()[84 : 84 + 320])

    result = asyncio.run(
        flash_firmware(
            _request(root, identity, authorized=authorized), client  # type: ignore[arg-type]
        )
    )

    assert result.ok is False
    assert result.code == "AUTHORIZATION_REQUIRED"
    assert client.events == []


def test_flash_rejects_caller_identity_changed_before_probe_use(
    tmp_path: Path,
) -> None:
    root = prepare_project(tmp_path)
    identity = _publish_current_debug_build(root)
    client = RecordingFlashClient(_elf_with_flash_segment()[84 : 84 + 320])

    result = asyncio.run(
        flash_firmware(_request(root, identity, expected_build_id="0" * 64), client)
    )

    assert result.ok is False
    assert result.code == "FLASH_PLAN_CHANGED"
    assert result.details == {"field": "expectedBuildId", "rule": "current"}
    assert client.events == []


def test_flash_rejects_project_debug_target_mismatch_before_probe_use(
    tmp_path: Path,
) -> None:
    root = prepare_project(tmp_path)
    identity = _publish_current_debug_build(root)
    client = RecordingFlashClient(_elf_with_flash_segment()[84 : 84 + 320])

    result = asyncio.run(
        flash_firmware(_request(root, identity, target="stm32f429zi"), client)
    )

    assert result.ok is False
    assert result.code == "FIRMWARE_IDENTITY_MISMATCH"
    assert result.details == {"field": "target", "rule": "project"}
    assert client.events == []


def test_flash_programs_exact_elf_reads_back_segments_and_commits_result(
    tmp_path: Path,
) -> None:
    root = prepare_project(tmp_path)
    identity = _publish_current_debug_build(root)
    segment = _elf_with_flash_segment()[84 : 84 + 320]
    client = RecordingFlashClient(segment)

    result = asyncio.run(flash_firmware(_request(root, identity), client))

    assert result.ok is True
    assert result.data is not None
    payload = result.to_dict()["data"]
    assert payload["buildId"] == identity["buildId"]
    assert payload["elfSha256"] == identity["elfSha256"]
    assert payload["verifiedBytes"] == 320
    assert payload["flashResultPath"] == "artifacts/migration/flash-result.json"
    assert client.events[0] == ("attach", "probe-123", "stm32f407vg")
    assert client.events[1][0:2] == ("program", "build/arm-debug/firmware.elf")
    assert client.events[2] == ("read", 0x08000000, 320)

    document = json.loads(
        (root / "artifacts" / "migration" / "flash-result.json").read_text(
            encoding="utf-8"
        )
    )
    assert document["status"] == "success"
    assert document["operationLevel"] == "modify"
    assert document["authorized"] is True
    assert document["workspaceId"] == "workspace-a"
    assert document["sessionId"] == "session-a"
    assert document["probeId"] == "probe-123"
    assert document["debugTarget"] == "stm32f407vg"


def test_flash_readback_mismatch_never_retains_success_evidence(
    tmp_path: Path,
) -> None:
    root = prepare_project(tmp_path)
    identity = _publish_current_debug_build(root)
    result_path = root / "artifacts" / "migration" / "flash-result.json"
    result_path.write_text('{"status":"success"}\n', encoding="utf-8")
    client = RecordingFlashClient(b"\xff" * 320)

    result = asyncio.run(flash_firmware(_request(root, identity), client))

    assert result.ok is False
    assert result.code == "FLASH_VERIFY_FAILED"
    assert not result_path.exists()


def test_flash_rejects_elf_without_programmable_load_segment(
    tmp_path: Path,
) -> None:
    root = prepare_project(tmp_path)
    identity = _publish_current_debug_build(root, with_segment=False)
    client = RecordingFlashClient(b"")

    result = asyncio.run(flash_firmware(_request(root, identity), client))

    assert result.ok is False
    assert result.code == "FLASH_IMAGE_INVALID"
    assert result.details == {"path": "build/arm-debug/firmware.elf", "rule": "segments"}
    assert client.events == []


def test_flash_rejects_duplicate_identity_fields(tmp_path: Path) -> None:
    root = prepare_project(tmp_path)
    identity = _publish_current_debug_build(root)
    identity_path = root / "build" / "arm-debug" / "firmware-identity.json"
    original = identity_path.read_bytes()
    identity_path.write_bytes(b'{"schemaVersion":1,' + original[1:])
    client = RecordingFlashClient(_elf_with_flash_segment()[84 : 84 + 320])

    result = asyncio.run(flash_firmware(_request(root, identity), client))

    assert result.ok is False
    assert result.code == "FIRMWARE_EVIDENCE_INVALID"
    assert result.details == {
        "path": "build/arm-debug/firmware-identity.json",
        "rule": "json",
    }
    assert client.events == []


def test_flash_rejects_current_source_snapshot_change(tmp_path: Path) -> None:
    root = prepare_project(tmp_path)
    identity = _publish_current_debug_build(root)
    (root / "Src" / "main.c").write_bytes(b"int changed;\n")
    client = RecordingFlashClient(_elf_with_flash_segment()[84 : 84 + 320])

    result = asyncio.run(flash_firmware(_request(root, identity), client))

    assert result.ok is False
    assert result.code == "FIRMWARE_INPUT_CHANGED"
    assert client.events == []


def test_flash_rejects_current_map_change(tmp_path: Path) -> None:
    root = prepare_project(tmp_path)
    identity = _publish_current_debug_build(root)
    (root / "build" / "arm-debug" / "firmware.map").write_bytes(b"changed\n")
    client = RecordingFlashClient(_elf_with_flash_segment()[84 : 84 + 320])

    result = asyncio.run(flash_firmware(_request(root, identity), client))

    assert result.ok is False
    assert result.code == "FIRMWARE_INPUT_CHANGED"
    assert result.details == {"field": "mapSha256", "rule": "current"}
    assert client.events == []


@pytest.mark.parametrize(
    ("field", "value", "expected_field"),
    [
        ("toolkitVersion", "0.2.0", "toolkitVersion"),
        ("logicalProjectId", "87654321-4321-8765-4321-876543218765", "logicalProjectId"),
        ("entryPoint", 0x08000101, "elf"),
    ],
)
def test_flash_rejects_self_consistent_forged_identity_fields(
    tmp_path: Path, field: str, value: object, expected_field: str
) -> None:
    root = prepare_project(tmp_path)
    prior = _publish_current_debug_build(root)
    identity_path = root / "build" / "arm-debug" / "firmware-identity.json"
    identity = json.loads(identity_path.read_text(encoding="utf-8"))
    identity[field] = value
    identity["buildId"] = compute_build_id(identity)
    atomic_write_json(identity_path, identity)
    result_path = root / "artifacts" / "migration" / "build-result.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    result["buildId"] = identity["buildId"]
    atomic_write_json(result_path, result)
    client = RecordingFlashClient(_elf_with_flash_segment()[84 : 84 + 320])

    outcome = asyncio.run(flash_firmware(_request(root, prior), client))

    assert outcome.ok is False
    assert outcome.code == "FIRMWARE_IDENTITY_MISMATCH"
    assert outcome.details == {"field": expected_field, "rule": "identity" if field == "entryPoint" else ("current" if field == "toolkitVersion" else "project")}
    assert client.events == []


def test_flash_rejects_deterministic_reparse_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = prepare_project(tmp_path)
    identity = _publish_current_debug_build(root)
    target = root / "build" / "arm-debug" / "firmware-identity.json"
    original_lstat = flash_mod.os.lstat

    class ReparseStat:
        def __init__(self, value: object) -> None:
            self._value = value
            self.st_mode = value.st_mode
            self.st_file_attributes = 0x400

    def injected_lstat(path: object) -> object:
        value = original_lstat(path)
        if Path(path) == target:
            return ReparseStat(value)
        return value

    monkeypatch.setattr(flash_mod.os, "lstat", injected_lstat)
    client = RecordingFlashClient(_elf_with_flash_segment()[84 : 84 + 320])

    result = asyncio.run(flash_firmware(_request(root, identity), client))

    assert result.ok is False
    assert result.code == "FIRMWARE_EVIDENCE_INVALID"
    assert result.details == {
        "path": "build/arm-debug/firmware-identity.json",
        "rule": "redirect",
    }
    assert client.events == []


def test_flash_rejects_endpoint_probe_or_level_mismatch(tmp_path: Path) -> None:
    root = prepare_project(tmp_path)
    identity = _publish_current_debug_build(root)
    segment = _elf_with_flash_segment()[84 : 84 + 320]
    for client in (
        RecordingFlashClient(segment, endpoint_probe_id="probe-other"),
        RecordingFlashClient(segment, endpoint_level="control"),
    ):
        result = asyncio.run(flash_firmware(_request(root, identity), client))
        assert result.ok is False
        assert result.code == "PROBE_ENDPOINT_INVALID"
        assert client.events == []


def test_flash_rejects_resolved_target_identity_mismatch(tmp_path: Path) -> None:
    root = prepare_project(tmp_path)
    identity = _publish_current_debug_build(root)
    client = RecordingFlashClient(
        _elf_with_flash_segment()[84 : 84 + 320],
        resolved_target="STM32F429ZI",
    )

    result = asyncio.run(flash_firmware(_request(root, identity), client))

    assert result.ok is False
    assert result.code == "FIRMWARE_IDENTITY_MISMATCH"
    assert result.details == {"field": "connectedTarget", "rule": "identity"}
    assert client.events == [("attach", "probe-123", "stm32f407vg")]


def test_flash_readback_is_chunked_to_protocol_limit(tmp_path: Path) -> None:
    root = prepare_project(tmp_path)
    text_size = 70_000
    identity = _publish_current_debug_build(root, text_size=text_size)
    image = _elf_with_flash_segment(text_size=text_size)[84 : 84 + 64 + text_size]
    client = RecordingFlashClient(image)

    result = asyncio.run(flash_firmware(_request(root, identity), client))

    assert result.ok is True
    reads = [event for event in client.events if event[0] == "read"]
    assert reads == [
        ("read", 0x08000000, 65_536),
        ("read", 0x08010000, 4_528),
    ]


def test_flash_disk_change_during_programming_never_commits_success(tmp_path: Path) -> None:
    root = prepare_project(tmp_path)
    identity = _publish_current_debug_build(root)
    segment = _elf_with_flash_segment()[84 : 84 + 320]

    class MutatingClient(RecordingFlashClient):
        async def program_verified_elf(
            self,
            elf_path: str,
            elf_sha256: str,
            elf_size: int,
            *,
            timeout_ms: int = 30000,
        ) -> FlashBackendReport:
            report = await super().program_verified_elf(
                elf_path, elf_sha256, elf_size, timeout_ms=timeout_ms
            )
            (root / "build" / "arm-debug" / "firmware.elf").write_bytes(b"changed")
            return report

    result = asyncio.run(
        flash_firmware(_request(root, identity), MutatingClient(segment))
    )

    assert result.ok is False
    assert result.code == "FIRMWARE_INPUT_CHANGED"
    assert not (root / "artifacts" / "migration" / "flash-result.json").exists()


def test_flash_caller_cancellation_propagates_and_invalidates_old_result(
    tmp_path: Path,
) -> None:
    root = prepare_project(tmp_path)
    identity = _publish_current_debug_build(root)
    result_path = root / "artifacts" / "migration" / "flash-result.json"
    result_path.write_text('{"status":"success"}\n', encoding="utf-8")

    class CancellingClient(RecordingFlashClient):
        async def program_verified_elf(
            self,
            elf_path: str,
            elf_sha256: str,
            elf_size: int,
            *,
            timeout_ms: int = 30000,
        ) -> FlashBackendReport:
            raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(
            flash_firmware(
                _request(root, identity),
                CancellingClient(_elf_with_flash_segment()[84 : 84 + 320]),
            )
        )
    assert not result_path.exists()


def test_flash_request_validation_fails_before_evidence_or_probe_use(
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    file_root = tmp_path / "file"
    file_root.write_text("x", encoding="utf-8")
    valid = {
        "project_root": root,
        "probe_id": "probe-123",
        "target": "stm32f407vg",
        "expected_build_id": "1" * 64,
        "expected_elf_sha256": "2" * 64,
        "authorized": True,
        "timeout_ms": 30_000,
    }
    cases = [
        ("not-a-request", "request"),
        (FlashRequest(**{**valid, "project_root": "bad"}), "projectRoot"),  # type: ignore[arg-type]
        (FlashRequest(**{**valid, "project_root": tmp_path / "missing"}), "projectRoot"),
        (FlashRequest(**{**valid, "project_root": file_root}), "projectRoot"),
        (FlashRequest(**{**valid, "probe_id": "bad/probe"}), "probeId"),
        (FlashRequest(**{**valid, "target": ""}), "target"),
        (FlashRequest(**{**valid, "expected_build_id": "A" * 64}), "expectedBuildId"),
        (FlashRequest(**{**valid, "expected_elf_sha256": "short"}), "expectedElfSha256"),
        (FlashRequest(**{**valid, "timeout_ms": True}), "timeoutMs"),
        (FlashRequest(**{**valid, "timeout_ms": 30_001}), "timeoutMs"),
    ]
    client = RecordingFlashClient(b"")
    for request, field in cases:
        result = asyncio.run(flash_firmware(request, client))
        assert result.code == "FLASH_REQUEST_INVALID"
        assert result.details["field"] == field
    assert client.events == []


def test_secure_evidence_reader_classifies_path_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (root / "large.bin").write_bytes(b"abc")
    (root / "directory").mkdir()

    cases = [
        ("../escape", 10, "path"),
        ("missing.bin", 10, "missing"),
        ("directory", 10, "regularFile"),
        ("large.bin", 2, "size"),
    ]
    for rel, limit, rule in cases:
        with pytest.raises(flash_mod._FlashFailure) as error:
            flash_mod._secure_file(root, rel, limit)
        assert error.value.details["rule"] == rule

    original_lstat = flash_mod.os.lstat

    def denied_lstat(path: object) -> object:
        if Path(path).name == "large.bin":
            raise PermissionError
        return original_lstat(path)

    monkeypatch.setattr(flash_mod.os, "lstat", denied_lstat)
    with pytest.raises(flash_mod._FlashFailure) as inspection:
        flash_mod._secure_file(root, "large.bin", 10)
    assert inspection.value.details["rule"] == "inspection"


def test_json_and_artifact_documents_fail_closed(
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (root / "nan.json").write_text('{"value":NaN}', encoding="utf-8")
    (root / "list.json").write_text("[]", encoding="utf-8")
    for rel, rule in (("nan.json", "json"), ("list.json", "type")):
        with pytest.raises(flash_mod._FlashFailure) as error:
            flash_mod._json_document(root, rel, 100)
        assert error.value.details["rule"] == rule

    invalid_results = [
        {"artifacts": None},
        {"artifacts": []},
        {"artifacts": [{"kind": "elf", "path": "x", "sha256": "0" * 64, "size": 1}] * 2},
        {"artifacts": [{"kind": "elf", "path": "x", "sha256": "0" * 64, "size": 1, "extra": 1}]},
    ]
    for result in invalid_results:
        with pytest.raises(flash_mod._FlashFailure) as error:
            flash_mod._artifact_record(result, "elf")
        assert error.value.details["rule"] == "artifacts"


def test_flash_segment_parser_rejects_nonload_region_size_and_overlap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = prepare_project(tmp_path)
    model = load_project_model(root)

    class FakeSegment:
        def __init__(self, kind: str, address: int, payload: bytes, size: int | None = None):
            self.header = SimpleNamespace(
                p_type=kind,
                p_paddr=address,
                p_filesz=len(payload) if size is None else size,
            )
            self._payload = payload

        def data(self) -> bytes:
            return self._payload

    def install(*segments: FakeSegment) -> None:
        monkeypatch.setattr(
            flash_mod,
            "ELFFile",
            lambda _: SimpleNamespace(iter_segments=lambda: iter(segments)),
        )

    install(FakeSegment("PT_NOTE", 0, b"x"), FakeSegment("PT_LOAD", 0, b""))
    with pytest.raises(flash_mod._FlashFailure) as empty:
        flash_mod._flash_segments(b"elf", model, "firmware.elf")
    assert empty.value.details["rule"] == "segments"

    install(FakeSegment("PT_LOAD", 0x20000000, b"x"))
    with pytest.raises(flash_mod._FlashFailure) as region:
        flash_mod._flash_segments(b"elf", model, "firmware.elf")
    assert region.value.details["rule"] == "region"

    install(FakeSegment("PT_LOAD", 0x08000000, b"x", size=2))
    with pytest.raises(flash_mod._FlashFailure) as malformed:
        flash_mod._flash_segments(b"elf", model, "firmware.elf")
    assert malformed.value.details["rule"] == "segments"

    install(FakeSegment("PT_LOAD", 0x08000000, b"abcd"))
    monkeypatch.setattr(flash_mod, "_ELF_LIMIT", 3)
    with pytest.raises(flash_mod._FlashFailure) as oversize:
        flash_mod._flash_segments(b"elf", model, "firmware.elf")
    assert oversize.value.details["rule"] == "size"
    monkeypatch.setattr(flash_mod, "_ELF_LIMIT", 64 * 1024 * 1024)

    install(
        FakeSegment("PT_LOAD", 0x08000000, b"abcd"),
        FakeSegment("PT_LOAD", 0x08000002, b"efgh"),
    )
    with pytest.raises(flash_mod._FlashFailure) as overlap:
        flash_mod._flash_segments(b"elf", model, "firmware.elf")
    assert overlap.value.details["rule"] == "overlap"


def test_flash_rejects_failed_or_mismatched_build_result(tmp_path: Path) -> None:
    root = prepare_project(tmp_path)
    identity = _publish_current_debug_build(root)
    path = root / "artifacts" / "migration" / "build-result.json"
    client = RecordingFlashClient(_elf_with_flash_segment()[84 : 84 + 320])

    original = json.loads(path.read_text(encoding="utf-8"))
    failed = {**original, "status": "failure", "stage": "build", "code": "BUILD_FAILED"}
    atomic_write_json(path, failed)
    result = asyncio.run(flash_firmware(_request(root, identity), client))
    assert result.code == "FIRMWARE_BUILD_REQUIRED"

    mismatched = {**original, "gitHead": "0" * 40}
    atomic_write_json(path, mismatched)
    result = asyncio.run(flash_firmware(_request(root, identity), client))
    assert result.code == "FIRMWARE_IDENTITY_MISMATCH"

    extra = {**original, "extra": True}
    atomic_write_json(path, extra)
    result = asyncio.run(flash_firmware(_request(root, identity), client))
    assert result.code == "FIRMWARE_EVIDENCE_INVALID"
    assert client.events == []


def test_flash_rejects_git_only_change_and_artifact_record_mismatch(
    tmp_path: Path,
) -> None:
    root = prepare_project(tmp_path)
    identity = _publish_current_debug_build(root)
    client = RecordingFlashClient(_elf_with_flash_segment()[84 : 84 + 320])
    (root / "untracked.txt").write_text("dirty", encoding="utf-8")
    dirty = asyncio.run(flash_firmware(_request(root, identity), client))
    assert dirty.code == "FIRMWARE_INPUT_CHANGED"
    assert dirty.details == {"field": "gitHead", "rule": "current"}
    (root / "untracked.txt").unlink()

    result_path = root / "artifacts" / "migration" / "build-result.json"
    document = json.loads(result_path.read_text(encoding="utf-8"))
    document["artifacts"][0]["sha256"] = "0" * 64
    atomic_write_json(result_path, document)
    mismatch = asyncio.run(flash_firmware(_request(root, identity), client))
    assert mismatch.code == "FIRMWARE_IDENTITY_MISMATCH"
    assert mismatch.details == {"field": "artifacts", "rule": "identity"}
    assert client.events == []


def test_flash_expected_elf_pin_and_backend_response_are_strict(tmp_path: Path) -> None:
    root = prepare_project(tmp_path)
    identity = _publish_current_debug_build(root)
    segment = _elf_with_flash_segment()[84 : 84 + 320]
    client = RecordingFlashClient(segment)
    changed = asyncio.run(
        flash_firmware(
            _request(root, identity, expected_elf_sha256="0" * 64), client
        )
    )
    assert changed.code == "FLASH_PLAN_CHANGED"
    assert changed.details == {"field": "expectedElfSha256", "rule": "current"}

    class BadResponseClient(RecordingFlashClient):
        async def program_verified_elf(self, *args: object, **kwargs: object) -> object:
            self.events.append(("program-bad",))
            return {"bytesProgrammed": 1}

    invalid = asyncio.run(
        flash_firmware(_request(root, identity), BadResponseClient(segment))
    )
    assert invalid.code == "PROBE_RESPONSE_INVALID"


def test_flash_atomic_commit_and_structured_client_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = prepare_project(tmp_path)
    identity = _publish_current_debug_build(root)
    segment = _elf_with_flash_segment()[84 : 84 + 320]

    original_write = flash_mod.atomic_write_json

    def fail_flash_result(path: Path, document: object) -> None:
        if path.name == "flash-result.json":
            raise PermissionError("private path")
        original_write(path, document)

    monkeypatch.setattr(flash_mod, "atomic_write_json", fail_flash_result)
    failed_write = asyncio.run(
        flash_firmware(_request(root, identity), RecordingFlashClient(segment))
    )
    assert failed_write.code == "FLASH_EVIDENCE_FAILED"
    assert not (root / "artifacts" / "migration" / "flash-result.json").exists()

    class StableError(Exception):
        code = "PROBE_BUSY"
        message = "Probe is busy"
        details = {"probeId": "probe-123"}

    class FailingAttach(RecordingFlashClient):
        async def attach(self, probe_id: str, target: str) -> object:
            raise StableError

    stable = asyncio.run(
        flash_firmware(_request(root, identity), FailingAttach(segment))
    )
    assert stable.code == "PROBE_BUSY"
    assert stable.details == {"probeId": "probe-123"}

    class CrashingAttach(RecordingFlashClient):
        async def attach(self, probe_id: str, target: str) -> object:
            raise RuntimeError("private detail")

    internal = asyncio.run(
        flash_firmware(_request(root, identity), CrashingAttach(segment))
    )
    assert internal.code == "FLASH_INTERNAL_ERROR"
    assert "private detail" not in json.dumps(internal.to_dict())
