"""Identity-bound sector programming with exact target readback evidence."""

from __future__ import annotations

import asyncio
import io
import json
import os
import re
import stat
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Mapping

from elftools.elf.elffile import ELFFile
from elftools.elf.segments import Segment

from stm32_toolkit import __version__
from stm32_toolkit.build.identity import (
    BuildError,
    atomic_write_json,
    compute_build_id,
    git_evidence,
    model_artifact_paths,
    snapshot_project_inputs,
    utc_now_rfc3339,
    validate_elf,
    validate_identity_document,
)
from stm32_toolkit.project_model import ProjectModel, load_project_model
from stm32_toolkit.result import OperationResult

from .backend import FlashBackendReport

_OPERATION = "stm32_flash"
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_TARGET_CANONICAL = re.compile(r"[^a-z0-9]")
_IDENTITY_REL = "build/arm-debug/firmware-identity.json"
_RESULT_REL = "artifacts/migration/build-result.json"
_FLASH_RESULT_REL = "artifacts/migration/flash-result.json"
_IDENTITY_LIMIT = 8 * 1024 * 1024
_RESULT_LIMIT = 8 * 1024 * 1024
_ELF_LIMIT = 64 * 1024 * 1024
_MAP_LIMIT = 32 * 1024 * 1024
_READ_CHUNK = 65_536
_REPARSE_POINT = 0x400

_BUILD_RESULT_FIELDS = {
    "schemaVersion",
    "status",
    "stage",
    "code",
    "buildId",
    "gitHead",
    "gitDirty",
    "inputSnapshotSha256",
    "targetDevice",
    "preset",
    "startedAtUtc",
    "finishedAtUtc",
    "durationMs",
    "artifacts",
    "memory",
    "warnings",
}


@dataclass(frozen=True)
class FlashRequest:
    project_root: Path
    probe_id: str
    target: str
    expected_build_id: str
    expected_elf_sha256: str
    authorized: bool
    timeout_ms: int = 30_000


@dataclass(frozen=True)
class FlashSegment:
    address: int
    data: bytes


@dataclass(frozen=True)
class FlashReport:
    build_id: str
    elf_sha256: str
    elf_size: int
    target_device: str
    debug_target: str
    probe_id: str
    workspace_id: str
    session_id: str
    verified_bytes: int
    backend_bytes_programmed: int | None
    backend_sectors_programmed: int | None
    started_at_utc: str
    finished_at_utc: str
    flash_result_path: str = _FLASH_RESULT_REL

    def to_dict(self) -> dict[str, object]:
        return {
            "buildId": self.build_id,
            "elfSha256": self.elf_sha256,
            "elfSize": self.elf_size,
            "targetDevice": self.target_device,
            "debugTarget": self.debug_target,
            "probeId": self.probe_id,
            "workspaceId": self.workspace_id,
            "sessionId": self.session_id,
            "verifiedBytes": self.verified_bytes,
            "backendBytesProgrammed": self.backend_bytes_programmed,
            "backendSectorsProgrammed": self.backend_sectors_programmed,
            "startedAtUtc": self.started_at_utc,
            "finishedAtUtc": self.finished_at_utc,
            "flashResultPath": self.flash_result_path,
        }


@dataclass(frozen=True)
class _FreshFirmware:
    root: Path
    model: ProjectModel
    identity: Mapping[str, object]
    elf_path: str
    elf_data: bytes
    segments: tuple[FlashSegment, ...]


class _FlashFailure(Exception):
    def __init__(
        self, code: str, message: str, details: Mapping[str, object] | None = None
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = dict(details or {})


def _failure(error: _FlashFailure) -> OperationResult[None]:
    return OperationResult.failure(_OPERATION, error.code, error.message, error.details)


def _fail(code: str, message: str, **details: object) -> _FlashFailure:
    return _FlashFailure(code, message, details)


def _request_root(request: FlashRequest) -> Path:
    if not isinstance(request.project_root, Path):
        raise _fail("FLASH_REQUEST_INVALID", "Flash request is invalid", field="projectRoot", rule="type")
    try:
        root = request.project_root.expanduser().resolve(strict=True)
    except (OSError, RuntimeError):
        raise _fail("FLASH_REQUEST_INVALID", "Flash request is invalid", field="projectRoot", rule="value") from None
    if not root.is_dir():
        raise _fail("FLASH_REQUEST_INVALID", "Flash request is invalid", field="projectRoot", rule="value")
    return root


def _validate_request(request: object) -> tuple[FlashRequest, Path]:
    if not isinstance(request, FlashRequest):
        raise _fail("FLASH_REQUEST_INVALID", "Flash request is invalid", field="request", rule="type")
    if type(request.authorized) is not bool or request.authorized is not True:
        raise _fail("AUTHORIZATION_REQUIRED", "Firmware programming requires explicit authorization")
    root = _request_root(request)
    for field, value in (("probeId", request.probe_id), ("target", request.target)):
        if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
            raise _fail("FLASH_REQUEST_INVALID", "Flash request is invalid", field=field, rule="value")
    for field, value in (
        ("expectedBuildId", request.expected_build_id),
        ("expectedElfSha256", request.expected_elf_sha256),
    ):
        if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
            raise _fail("FLASH_REQUEST_INVALID", "Flash request is invalid", field=field, rule="value")
    if (
        isinstance(request.timeout_ms, bool)
        or not isinstance(request.timeout_ms, int)
        or not 1 <= request.timeout_ms <= 30_000
    ):
        raise _fail("FLASH_REQUEST_INVALID", "Flash request is invalid", field="timeoutMs", rule="range")
    return request, root


def _is_redirect(info: os.stat_result) -> bool:
    attributes = int(getattr(info, "st_file_attributes", 0))
    return stat.S_ISLNK(info.st_mode) or bool(attributes & _REPARSE_POINT)


def _secure_file(root: Path, rel: str, limit: int) -> bytes:
    parts = rel.split("/")
    if not parts or any(not part or part in (".", "..") for part in parts):
        raise _fail("FIRMWARE_EVIDENCE_INVALID", "Firmware evidence is invalid", path=rel, rule="path")
    current = root
    for index, part in enumerate(parts):
        current = current / part
        try:
            info = os.lstat(current)
        except FileNotFoundError:
            raise _fail("FIRMWARE_EVIDENCE_INVALID", "Firmware evidence is invalid", path=rel, rule="missing") from None
        except OSError:
            raise _fail("FIRMWARE_EVIDENCE_INVALID", "Firmware evidence is invalid", path=rel, rule="inspection") from None
        if _is_redirect(info):
            raise _fail("FIRMWARE_EVIDENCE_INVALID", "Firmware evidence is invalid", path=rel, rule="redirect")
        if index < len(parts) - 1 and not stat.S_ISDIR(info.st_mode):
            raise _fail("FIRMWARE_EVIDENCE_INVALID", "Firmware evidence is invalid", path=rel, rule="path")
        if index == len(parts) - 1 and not stat.S_ISREG(info.st_mode):
            raise _fail("FIRMWARE_EVIDENCE_INVALID", "Firmware evidence is invalid", path=rel, rule="regularFile")
    try:
        with current.open("rb") as handle:
            data = handle.read(limit + 1)
    except OSError:
        raise _fail("FIRMWARE_EVIDENCE_INVALID", "Firmware evidence is invalid", path=rel, rule="unreadable") from None
    if len(data) > limit:
        raise _fail("FIRMWARE_EVIDENCE_INVALID", "Firmware evidence is invalid", path=rel, rule="size")
    return data


def _reject_duplicate_json(pairs: list[tuple[str, object]]) -> dict[str, object]:
    document: dict[str, object] = {}
    for key, value in pairs:
        if key in document:
            raise ValueError("duplicate JSON field")
        document[key] = value
    return document


def _reject_json_constant(value: str) -> object:
    raise ValueError("non-finite JSON number")


def _json_document(root: Path, rel: str, limit: int) -> dict[str, object]:
    data = _secure_file(root, rel, limit)
    try:
        value = json.loads(
            data.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_json,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        raise _fail("FIRMWARE_EVIDENCE_INVALID", "Firmware evidence is invalid", path=rel, rule="json") from None
    if not isinstance(value, dict):
        raise _fail("FIRMWARE_EVIDENCE_INVALID", "Firmware evidence is invalid", path=rel, rule="type")
    return value


def _artifact_record(result: Mapping[str, object], kind: str) -> Mapping[str, object]:
    artifacts = result.get("artifacts")
    if not isinstance(artifacts, list):
        raise _fail("FIRMWARE_EVIDENCE_INVALID", "Firmware evidence is invalid", path=_RESULT_REL, rule="artifacts")
    matches = [item for item in artifacts if isinstance(item, dict) and item.get("kind") == kind]
    if len(matches) != 1:
        raise _fail("FIRMWARE_EVIDENCE_INVALID", "Firmware evidence is invalid", path=_RESULT_REL, rule="artifacts")
    record = matches[0]
    if set(record) != {"kind", "path", "sha256", "size"}:
        raise _fail("FIRMWARE_EVIDENCE_INVALID", "Firmware evidence is invalid", path=_RESULT_REL, rule="artifacts")
    return record


def _flash_segments(data: bytes, model: ProjectModel, rel: str) -> tuple[FlashSegment, ...]:
    try:
        elf = ELFFile(io.BytesIO(data))
        segments: list[FlashSegment] = []
        aggregate = 0
        for raw in elf.iter_segments():
            segment: Segment = raw
            if segment.header.p_type != "PT_LOAD" or int(segment.header.p_filesz) == 0:
                continue
            address = int(segment.header.p_paddr)
            size = int(segment.header.p_filesz)
            payload = bytes(segment.data())
            if len(payload) != size or address < 0 or address + size > 0x1_0000_0000:
                raise ValueError
            if not any(
                "x" in region.attributes
                and "w" not in region.attributes
                and region.origin <= address
                and address + size <= region.origin + region.length
                for region in model.memory.regions
            ):
                raise _fail("FLASH_IMAGE_INVALID", "Firmware image is not confined to executable memory", path=rel, rule="region")
            aggregate += size
            if aggregate > _ELF_LIMIT:
                raise _fail("FLASH_IMAGE_INVALID", "Firmware image exceeds the programming limit", path=rel, rule="size")
            segments.append(FlashSegment(address, payload))
    except _FlashFailure:
        raise
    except Exception:
        raise _fail("FLASH_IMAGE_INVALID", "Firmware image is invalid", path=rel, rule="segments") from None
    segments.sort(key=lambda item: item.address)
    if not segments:
        raise _fail("FLASH_IMAGE_INVALID", "Firmware image is invalid", path=rel, rule="segments")
    for previous, current in zip(segments, segments[1:]):
        if previous.address + len(previous.data) > current.address:
            raise _fail("FLASH_IMAGE_INVALID", "Firmware image contains overlapping segments", path=rel, rule="overlap")
    return tuple(segments)


def _load_fresh_firmware(root: Path) -> _FreshFirmware:
    try:
        model = load_project_model(root)
    except Exception:
        raise _fail("FIRMWARE_EVIDENCE_INVALID", "Project model is invalid", path=".stm32-project.json", rule="model") from None
    if model.debug.backend != "pyocd" or not model.debug.target:
        raise _fail("FIRMWARE_IDENTITY_MISMATCH", "Project has no supported debug target", field="debug.backend", rule="value")

    identity = _json_document(root, _IDENTITY_REL, _IDENTITY_LIMIT)
    result = _json_document(root, _RESULT_REL, _RESULT_LIMIT)
    if set(result) != _BUILD_RESULT_FIELDS or result.get("schemaVersion") != 1:
        raise _fail("FIRMWARE_EVIDENCE_INVALID", "Build result is invalid", path=_RESULT_REL, rule="fields")
    try:
        validate_identity_document(identity)
    except BuildError:
        raise _fail("FIRMWARE_EVIDENCE_INVALID", "Firmware identity is invalid", path=_IDENTITY_REL, rule="schema") from None
    if compute_build_id(identity) != identity.get("buildId"):
        raise _fail("FIRMWARE_EVIDENCE_INVALID", "Firmware identity is invalid", path=_IDENTITY_REL, rule="buildId")
    if (
        result.get("status") != "success"
        or result.get("stage") != "complete"
        or result.get("code") != "OK"
    ):
        raise _fail("FIRMWARE_BUILD_REQUIRED", "A current successful debug build is required", path=_RESULT_REL, rule="status")
    if identity.get("preset") != "arm-debug" or result.get("preset") != "arm-debug":
        raise _fail("FIRMWARE_IDENTITY_MISMATCH", "Firmware preset does not match the debug workflow", field="preset", rule="value")
    if identity.get("toolkitVersion") != __version__:
        raise _fail("FIRMWARE_IDENTITY_MISMATCH", "Firmware Toolkit version is incompatible", field="toolkitVersion", rule="current")
    if identity.get("logicalProjectId") != str(model.logical_project_id):
        raise _fail("FIRMWARE_IDENTITY_MISMATCH", "Firmware project identity does not match", field="logicalProjectId", rule="project")

    expected_pairs = (
        ("buildId", identity.get("buildId")),
        ("gitHead", identity.get("gitHead")),
        ("gitDirty", identity.get("gitDirty")),
        ("inputSnapshotSha256", identity.get("inputSnapshotSha256")),
        ("targetDevice", identity.get("targetDevice")),
    )
    if any(result.get(field) != expected for field, expected in expected_pairs):
        raise _fail("FIRMWARE_IDENTITY_MISMATCH", "Build result and firmware identity disagree", field="buildResult", rule="identity")
    if identity.get("targetDevice") != model.target.device:
        raise _fail("FIRMWARE_IDENTITY_MISMATCH", "Firmware target does not match the project", field="targetDevice", rule="project")

    try:
        snapshot = snapshot_project_inputs(model)
        git = git_evidence(root)
    except BuildError:
        raise _fail("FIRMWARE_EVIDENCE_INVALID", "Current source evidence is unavailable", path=".stm32-project.json", rule="freshness") from None
    if snapshot.sha256 != identity.get("inputSnapshotSha256"):
        raise _fail("FIRMWARE_INPUT_CHANGED", "Project inputs changed after the selected build", field="inputSnapshotSha256", rule="current")
    if git.head != identity.get("gitHead") or git.dirty != identity.get("gitDirty"):
        raise _fail("FIRMWARE_INPUT_CHANGED", "Git evidence changed after the selected build", field="gitHead", rule="current")

    expected_elf_rel, expected_map_rel = model_artifact_paths(model, "arm-debug")
    elf_rel = identity.get("elfPath")
    map_rel = identity.get("mapPath")
    if elf_rel != expected_elf_rel or map_rel != expected_map_rel:
        raise _fail("FIRMWARE_IDENTITY_MISMATCH", "Firmware paths do not match the project", field="elfPath", rule="project")
    elf_data = _secure_file(root, str(elf_rel), _ELF_LIMIT)
    map_data = _secure_file(root, map_rel, _MAP_LIMIT)
    if len(elf_data) != identity.get("elfSize") or sha256(elf_data).hexdigest() != identity.get("elfSha256"):
        raise _fail("FIRMWARE_INPUT_CHANGED", "ELF changed after the selected build", field="elfSha256", rule="current")
    if sha256(map_data).hexdigest() != identity.get("mapSha256"):
        raise _fail("FIRMWARE_INPUT_CHANGED", "MAP changed after the selected build", field="mapSha256", rule="current")
    elf_record = _artifact_record(result, "elf")
    map_record = _artifact_record(result, "map")
    if (
        elf_record.get("path") != elf_rel
        or elf_record.get("sha256") != identity.get("elfSha256")
        or elf_record.get("size") != len(elf_data)
        or map_record.get("path") != map_rel
        or map_record.get("sha256") != identity.get("mapSha256")
        or map_record.get("size") != len(map_data)
    ):
        raise _fail("FIRMWARE_IDENTITY_MISMATCH", "Build artifacts disagree with firmware identity", field="artifacts", rule="identity")
    try:
        elf_evidence = validate_elf(root.joinpath(*str(elf_rel).split("/")), model)
    except BuildError:
        raise _fail("FLASH_IMAGE_INVALID", "Firmware ELF is invalid", path=str(elf_rel), rule="format") from None
    if elf_evidence.sha256 != identity.get("elfSha256"):
        raise _fail("FIRMWARE_INPUT_CHANGED", "ELF changed after validation", field="elfSha256", rule="current")
    if (
        elf_evidence.entry_point != identity.get("entryPoint")
        or elf_evidence.vector_address != identity.get("vectorAddress")
        or elf_evidence.reset_handler_address != identity.get("resetHandlerAddress")
    ):
        raise _fail("FIRMWARE_IDENTITY_MISMATCH", "ELF structure disagrees with firmware identity", field="elf", rule="identity")
    segments = _flash_segments(elf_data, model, str(elf_rel))
    return _FreshFirmware(root, model, identity, str(elf_rel), elf_data, segments)


def _canonical_target(value: str) -> str:
    return _TARGET_CANONICAL.sub("", value.casefold())


def _client_identity(client: object, request: FlashRequest) -> tuple[str, str]:
    endpoint = getattr(client, "endpoint", None)
    workspace_id = getattr(endpoint, "workspace_id", None)
    session_id = getattr(endpoint, "session_id", None)
    endpoint_probe_id = getattr(endpoint, "probe_id", None)
    level = getattr(endpoint, "operation_level", None)
    level_value = getattr(level, "value", level)
    if (
        not isinstance(workspace_id, str)
        or _IDENTIFIER.fullmatch(workspace_id) is None
        or not isinstance(session_id, str)
        or _IDENTIFIER.fullmatch(session_id) is None
        or endpoint_probe_id != request.probe_id
        or level_value != "modify"
    ):
        raise _fail("PROBE_ENDPOINT_INVALID", "Probe endpoint does not match the flash request")
    return workspace_id, session_id


def _validate_attachment(attachment: object, request: FlashRequest) -> None:
    probe_id = getattr(attachment, "probe_id", None)
    requested = getattr(attachment, "requested_target", None)
    resolved = getattr(attachment, "resolved_part_number", None)
    core_count = getattr(attachment, "core_count", None)
    if (
        probe_id != request.probe_id
        or requested != request.target
        or not isinstance(resolved, str)
        or _canonical_target(resolved) != _canonical_target(request.target)
        or core_count != 1
    ):
        raise _fail("FIRMWARE_IDENTITY_MISMATCH", "Connected target does not match the project", field="connectedTarget", rule="identity")


async def _verify_segments(client: object, segments: tuple[FlashSegment, ...]) -> int:
    verified = 0
    for segment in segments:
        offset = 0
        while offset < len(segment.data):
            length = min(_READ_CHUNK, len(segment.data) - offset)
            actual = await client.read_memory(segment.address + offset, length)
            expected = segment.data[offset : offset + length]
            if type(actual) is not bytes or actual != expected:
                raise _fail("FLASH_VERIFY_FAILED", "Programmed firmware readback did not match", address=segment.address + offset, length=length)
            verified += length
            offset += length
    return verified


def _remove_stale_result(root: Path) -> None:
    path = root.joinpath(*_FLASH_RESULT_REL.split("/"))
    try:
        path.unlink(missing_ok=True)
    except OSError:
        raise _fail("FLASH_EVIDENCE_FAILED", "Stale flash evidence could not be removed", path=_FLASH_RESULT_REL, rule="remove") from None


async def flash_firmware(request: object, client: object) -> OperationResult[FlashReport]:
    """Program and prove one caller-confirmed current firmware image."""

    try:
        typed, root = _validate_request(request)
        firmware = _load_fresh_firmware(root)
        if typed.expected_build_id != firmware.identity.get("buildId"):
            raise _fail("FLASH_PLAN_CHANGED", "Selected firmware build changed", field="expectedBuildId", rule="current")
        if typed.expected_elf_sha256 != firmware.identity.get("elfSha256"):
            raise _fail("FLASH_PLAN_CHANGED", "Selected firmware ELF changed", field="expectedElfSha256", rule="current")
        if typed.target != firmware.model.debug.target:
            raise _fail("FIRMWARE_IDENTITY_MISMATCH", "Flash target does not match the project", field="target", rule="project")
        workspace_id, session_id = _client_identity(client, typed)
        started = utc_now_rfc3339()
        attachment = await client.attach(typed.probe_id, typed.target)
        _validate_attachment(attachment, typed)
        _remove_stale_result(root)
        backend: FlashBackendReport = await client.program_verified_elf(
            firmware.elf_path,
            typed.expected_elf_sha256,
            len(firmware.elf_data),
            timeout_ms=typed.timeout_ms,
        )
        if not isinstance(backend, FlashBackendReport):
            raise _fail("PROBE_RESPONSE_INVALID", "Probe Service programming response is invalid")
        verified = await _verify_segments(client, firmware.segments)
        current = _load_fresh_firmware(root)
        if (
            current.identity.get("buildId") != firmware.identity.get("buildId")
            or current.identity.get("elfSha256") != firmware.identity.get("elfSha256")
        ):
            raise _fail("FIRMWARE_INPUT_CHANGED", "Firmware evidence changed during programming", field="buildId", rule="current")
        finished = utc_now_rfc3339()
        report = FlashReport(
            build_id=str(firmware.identity["buildId"]),
            elf_sha256=str(firmware.identity["elfSha256"]),
            elf_size=len(firmware.elf_data),
            target_device=firmware.model.target.device,
            debug_target=typed.target,
            probe_id=typed.probe_id,
            workspace_id=workspace_id,
            session_id=session_id,
            verified_bytes=verified,
            backend_bytes_programmed=backend.bytes_programmed,
            backend_sectors_programmed=backend.sectors_programmed,
            started_at_utc=started,
            finished_at_utc=finished,
        )
        document = {
            "schemaVersion": 1,
            "status": "success",
            "code": "OK",
            "toolkitVersion": __version__,
            **report.to_dict(),
            "elfPath": firmware.elf_path,
            "gitHead": firmware.identity["gitHead"],
            "gitDirty": firmware.identity["gitDirty"],
            "inputSnapshotSha256": firmware.identity["inputSnapshotSha256"],
            "operationLevel": "modify",
            "authorized": True,
        }
        try:
            atomic_write_json(root.joinpath(*_FLASH_RESULT_REL.split("/")), document)
        except Exception:
            _remove_stale_result(root)
            raise _fail("FLASH_EVIDENCE_FAILED", "Flash evidence could not be committed", path=_FLASH_RESULT_REL, rule="write") from None
        return OperationResult.success(_OPERATION, report)
    except asyncio.CancelledError:
        raise
    except _FlashFailure as error:
        return _failure(error)
    except Exception as error:
        code = getattr(error, "code", None)
        message = getattr(error, "message", None)
        details = getattr(error, "details", None)
        if isinstance(code, str) and isinstance(message, str):
            return OperationResult.failure(
                _OPERATION,
                code,
                message,
                details if isinstance(details, Mapping) else {},
            )
        return OperationResult.failure(
            _OPERATION,
            "FLASH_INTERNAL_ERROR",
            "Firmware programming failed",
            {},
        )


__all__ = ["FlashReport", "FlashRequest", "flash_firmware"]
