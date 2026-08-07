"""Bind read-only debug operations to one proven current firmware image."""

from __future__ import annotations

import asyncio
import re
import stat
from pathlib import Path
from typing import Mapping

from stm32_toolkit import __version__
from stm32_toolkit.build.identity import utc_now_rfc3339
from stm32_toolkit.probe.flash import _load_fresh_firmware, _verify_segments
from stm32_toolkit.probe.handoff import (
    _load_flash_result,
    _validate_attachment,
    _validate_flash,
)
from stm32_toolkit.probe.model import OperationLevel, PROBE_PROTOCOL_VERSION
from stm32_toolkit.result import OperationResult

from .model import DebugBindingRequest, DebugFirmwareBinding, MemoryRegionBinding

_OPERATION = "stm32_debug_bind"
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class _BindingFailure(Exception):
    def __init__(
        self, code: str, message: str, details: Mapping[str, object] | None = None
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = dict(details or {})


def _fail(code: str, message: str, **details: object) -> _BindingFailure:
    return _BindingFailure(code, message, details)


def _request(request: object) -> tuple[DebugBindingRequest, Path]:
    if not isinstance(request, DebugBindingRequest):
        raise _fail("DEBUG_REQUEST_INVALID", "Debug binding request is invalid", field="request")
    if not isinstance(request.project_root, Path):
        raise _fail("DEBUG_REQUEST_INVALID", "Debug binding request is invalid", field="projectRoot")
    expanded = request.project_root.expanduser().absolute()
    try:
        root = request.project_root.expanduser().resolve(strict=True)
        info = root.stat()
    except (OSError, RuntimeError):
        raise _fail("DEBUG_REQUEST_INVALID", "Debug binding request is invalid", field="projectRoot") from None
    if expanded != root or not stat.S_ISDIR(info.st_mode):
        raise _fail("DEBUG_REQUEST_INVALID", "Debug binding request is invalid", field="projectRoot", rule="canonical")
    for field, value in (
        ("probeId", request.probe_id),
        ("target", request.target),
        ("workspaceId", request.workspace_id),
        ("observationSessionId", request.observation_session_id),
        ("leaseId", request.lease_id),
    ):
        if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
            raise _fail("DEBUG_REQUEST_INVALID", "Debug binding request is invalid", field=field)
    for field, value in (
        ("expectedBuildId", request.expected_build_id),
        ("expectedElfSha256", request.expected_elf_sha256),
    ):
        if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
            raise _fail("DEBUG_REQUEST_INVALID", "Debug binding request is invalid", field=field)
    return request, root


def _endpoint(request: DebugBindingRequest, client: object) -> None:
    endpoint = getattr(client, "endpoint", None)
    level = getattr(endpoint, "operation_level", None)
    level_value = getattr(level, "value", level)
    token = getattr(endpoint, "token", None)
    port = getattr(endpoint, "port", None)
    if (
        endpoint is None
        or getattr(endpoint, "protocol", None) != PROBE_PROTOCOL_VERSION
        or getattr(endpoint, "toolkit_version", None) != __version__
        or getattr(endpoint, "host", None) not in {"127.0.0.1", "::1"}
        or type(port) is not int
        or not 1 <= port <= 65_535
        or not isinstance(token, str)
        or _SHA256.fullmatch(token) is None
        or getattr(endpoint, "workspace_id", None) != request.workspace_id
        or getattr(endpoint, "session_id", None) != request.observation_session_id
        or getattr(endpoint, "lease_id", None) != request.lease_id
        or getattr(endpoint, "probe_id", None) != request.probe_id
        or level_value != OperationLevel.OBSERVE.value
    ):
        raise _fail(
            "DEBUG_ENDPOINT_MISMATCH",
            "Probe client endpoint does not match the debug binding request",
        )


def _firmware(root: Path, *, changed: bool = False):
    try:
        return _load_fresh_firmware(root)
    except Exception:
        if changed:
            raise _fail(
                "DEBUG_FIRMWARE_CHANGED",
                "Firmware evidence changed during debug binding",
            ) from None
        raise _fail(
            "DEBUG_FIRMWARE_INVALID",
            "A complete current debug firmware identity is required",
        ) from None


def _flash(root: Path, firmware: object, request: DebugBindingRequest, *, changed: bool = False) -> dict[str, object]:
    try:
        result = _load_flash_result(root)
        source_session = result.get("sessionId")
        if not isinstance(source_session, str) or _IDENTIFIER.fullmatch(source_session) is None:
            raise ValueError("invalid flash session")
        _validate_flash(
            result,
            firmware,
            probe=request.probe_id,
            workspace=request.workspace_id,
            session=source_session,
            target=request.target,
        )
        return result
    except Exception:
        if changed:
            raise _fail(
                "DEBUG_FIRMWARE_CHANGED",
                "Flash evidence changed during debug binding",
            ) from None
        try:
            _load_flash_result(root)
        except Exception:
            raise _fail(
                "DEBUG_FLASH_REQUIRED", "A current successful flash result is required"
            ) from None
        raise _fail(
            "DEBUG_FLASH_MISMATCH",
            "Flash result does not match the debug binding request",
        ) from None


def _same_firmware(before: object, after: object) -> bool:
    before_identity = getattr(before, "identity")
    after_identity = getattr(after, "identity")
    fields = (
        "buildId",
        "elfSha256",
        "mapSha256",
        "inputSnapshotSha256",
        "gitHead",
        "gitDirty",
        "targetDevice",
        "elfPath",
        "mapPath",
    )
    return all(before_identity.get(field) == after_identity.get(field) for field in fields)


async def bind_debug_firmware(
    request: object, client: object
) -> OperationResult[DebugFirmwareBinding]:
    """Prove one observation client is attached to the exact current image."""

    try:
        typed, root = _request(request)
        _endpoint(typed, client)
        firmware = _firmware(root)
        identity = firmware.identity
        if (
            typed.expected_build_id != identity.get("buildId")
            or typed.expected_elf_sha256 != identity.get("elfSha256")
        ):
            raise _fail(
                "DEBUG_PLAN_CHANGED",
                "Selected firmware identity changed",
            )
        if typed.target != firmware.model.debug.target:
            raise _fail(
                "DEBUG_TARGET_MISMATCH",
                "Debug target does not match the current project",
            )
        flash = _flash(root, firmware, typed)
        try:
            attachment = await client.attach(typed.probe_id, typed.target)
            _validate_attachment(attachment, typed.probe_id, typed.target)
        except asyncio.CancelledError:
            raise
        except Exception:
            raise _fail(
                "DEBUG_TARGET_MISMATCH",
                "Connected target does not match the debug binding request",
            ) from None
        try:
            await _verify_segments(client, firmware.segments)
        except asyncio.CancelledError:
            raise
        except Exception:
            raise _fail(
                "DEBUG_READBACK_MISMATCH",
                "Target memory does not match the current firmware image",
            ) from None

        current = _firmware(root, changed=True)
        current_flash = _flash(root, current, typed, changed=True)
        if not _same_firmware(firmware, current) or current_flash != flash:
            raise _fail(
                "DEBUG_FIRMWARE_CHANGED",
                "Firmware evidence changed during debug binding",
            )
        regions = tuple(
            MemoryRegionBinding(
                region.name,
                region.origin,
                region.length,
                region.attributes,
            )
            for region in current.model.memory.regions
            if "r" in region.attributes
        )
        binding = DebugFirmwareBinding(
            logical_project_id=str(current.model.logical_project_id),
            workspace_id=typed.workspace_id,
            observation_session_id=typed.observation_session_id,
            flash_session_id=str(current_flash["sessionId"]),
            lease_id=typed.lease_id,
            probe_id=typed.probe_id,
            target_device=current.model.target.device,
            debug_target=typed.target,
            build_id=str(current.identity["buildId"]),
            elf_sha256=str(current.identity["elfSha256"]),
            elf_size=len(current.elf_data),
            elf_path=current.elf_path,
            input_snapshot_sha256=str(current.identity["inputSnapshotSha256"]),
            git_head=str(current.identity["gitHead"]),
            git_dirty=bool(current.identity["gitDirty"]),
            confirmed_at_utc=utc_now_rfc3339(),
            memory_regions=regions,
            project_root=root,
        )
        return OperationResult.success(_OPERATION, binding)
    except asyncio.CancelledError:
        raise
    except _BindingFailure as error:
        return OperationResult.failure(
            _OPERATION, error.code, error.message, error.details
        )
    except Exception:
        return OperationResult.failure(
            _OPERATION,
            "DEBUG_INTERNAL_ERROR",
            "Debug firmware binding failed",
            {},
        )


__all__ = ["bind_debug_firmware"]
