"""Authoritative one-shot hardware workflows bound to one Schema-v2 project.

The public requests deliberately contain no target, SVD, ELF path, address,
size, endpoint, lease, or token.  Those values are derived from the current
project/firmware evidence and remain private to the transient Probe Service.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import re
import stat
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from stm32_toolkit.debug import (
    DebugBindingRequest,
    DwarfCatalog,
    FaultAnalysisRequest,
    RegisterReadRequest,
    SampleVariablesRequest,
    VariableReadRequest,
    analyze_fault,
    bind_debug_firmware,
    read_registers,
    read_variables,
    sample_variables,
    select_svd,
)
from stm32_toolkit.paths import WorkspacePaths, require_safe_session_id
from stm32_toolkit.probe import (
    DebugHandoffRequest,
    FlashRequest,
    OperationLevel,
    ProbeServiceConfig,
    ProbeServiceSupervisor,
    PyOCDBackend,
    begin_debug_handoff,
    end_debug_handoff,
    flash_firmware,
)
from stm32_toolkit.probe.backend import ProbeBackendError
from stm32_toolkit.probe.client import ProbeClient, ProbeClientError
from stm32_toolkit.probe.lease import ProbeLeaseError, ProbeLeaseManager
from stm32_toolkit.probe.service import ProbeServiceError
from stm32_toolkit.project_model import ProjectManifestError, ProjectModel, load_project_model
from stm32_toolkit.result import OperationResult

_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_ERROR_CODE = re.compile(r"^[A-Z][A-Z0-9_]{1,63}$")
_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
_MAX_PROBES = 64
_MAX_ITEMS = 256
_FORBIDDEN_RESULT_KEYS = frozenset(
    {
        "token",
        "leaseid",
        "endpoint",
        "endpointurl",
        "recordpath",
        "projectroot",
        "dataroot",
        "sessionroot",
        "workspaceroot",
    }
)


@dataclass(frozen=True)
class ProbeListWorkflowRequest:
    project_root: Path
    data_root: Path
    session_id: str


@dataclass(frozen=True)
class FlashWorkflowRequest:
    project_root: Path
    data_root: Path
    session_id: str
    probe_id: str
    expected_build_id: str
    expected_elf_sha256: str
    authorized: object


@dataclass(frozen=True)
class HandoffBeginWorkflowRequest:
    project_root: Path
    data_root: Path
    session_id: str
    probe_id: str
    expected_build_id: str
    expected_elf_sha256: str
    authorized: object
    previous_watch_selection: tuple[str, ...] = ()


@dataclass(frozen=True)
class HandoffEndWorkflowRequest:
    project_root: Path
    data_root: Path
    session_id: str
    probe_id: str
    ticket: object


@dataclass(frozen=True)
class VariableReadWorkflowRequest:
    project_root: Path
    data_root: Path
    session_id: str
    probe_id: str
    expected_build_id: str
    expected_elf_sha256: str
    expressions: tuple[str, ...]


@dataclass(frozen=True)
class VariableSampleWorkflowRequest:
    project_root: Path
    data_root: Path
    session_id: str
    probe_id: str
    expected_build_id: str
    expected_elf_sha256: str
    expressions: tuple[str, ...]
    interval_ms: int
    count: int | None = None
    duration_ms: int | None = None


@dataclass(frozen=True)
class RegisterReadWorkflowRequest:
    project_root: Path
    data_root: Path
    session_id: str
    probe_id: str
    expected_build_id: str
    expected_elf_sha256: str
    paths: tuple[str, ...]
    acknowledge_access_risk: object = False


@dataclass(frozen=True)
class FaultWorkflowRequest:
    project_root: Path
    data_root: Path
    session_id: str
    probe_id: str
    expected_build_id: str
    expected_elf_sha256: str


def _supervisor_factory(
    config: ProbeServiceConfig,
    lease_manager: object,
    backend_factory: Callable[[], object],
) -> ProbeServiceSupervisor:
    return ProbeServiceSupervisor(
        config=config,
        lease_manager=lease_manager,
        backend_factory=backend_factory,
    )


@dataclass(frozen=True)
class HardwareWorkflowSeams:
    """Narrow injectable construction/accepted-contract seams for software gates."""

    backend_factory: Callable[[], object] = PyOCDBackend
    lease_manager_factory: Callable[[Path], object] = ProbeLeaseManager
    supervisor_factory: Callable[[ProbeServiceConfig, object, Callable[[], object]], object] = _supervisor_factory
    client_factory: Callable[[object], object] = ProbeClient
    flash: Callable[[object, object], Awaitable[OperationResult[Any]]] = flash_firmware
    handoff_begin: Callable[[object, object, object], Awaitable[OperationResult[Any]]] = begin_debug_handoff
    handoff_end: Callable[[object, object, Callable[[object], object]], Awaitable[OperationResult[Any]]] = end_debug_handoff
    bind: Callable[[object, object], Awaitable[OperationResult[Any]]] = bind_debug_firmware
    read_variables: Callable[[object, object], Awaitable[OperationResult[Any]]] = read_variables
    sample_variables: Callable[[object, object], Awaitable[OperationResult[Any]]] = sample_variables
    read_registers: Callable[[object, object], Awaitable[OperationResult[Any]]] = read_registers
    analyze_fault: Callable[[object, object], Awaitable[OperationResult[Any]]] = analyze_fault
    catalog_from_binding: Callable[[object], object] = DwarfCatalog.from_binding
    svd_select: Callable[..., object] = select_svd


_DEFAULT_SEAMS = HardwareWorkflowSeams()


class _WorkflowFailure(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _fail(code: str, message: str) -> _WorkflowFailure:
    return _WorkflowFailure(code, message)


def _operation_failure(operation: str, error: _WorkflowFailure) -> OperationResult[None]:
    return OperationResult.failure(operation, error.code, error.message, {})


def _safe_root(value: object, field: str, *, must_exist: bool) -> Path:
    if not isinstance(value, Path):
        raise _fail("HARDWARE_INPUT_INVALID", f"{field} is invalid")
    try:
        root = value.expanduser().resolve(strict=must_exist)
    except (OSError, RuntimeError, ValueError):
        raise _fail("HARDWARE_INPUT_INVALID", f"{field} is invalid") from None
    if must_exist and not root.is_dir():
        raise _fail("HARDWARE_INPUT_INVALID", f"{field} is invalid")
    return root


def _safe_external_data_root(value: object, project_root: Path) -> Path:
    """Resolve one machine-owned root without following existing redirects."""

    if not isinstance(value, Path):
        raise _fail("HARDWARE_INPUT_INVALID", "data root is invalid")
    try:
        lexical = value.expanduser().absolute()
        current = Path(lexical.anchor)
        components = lexical.parts[1:] if lexical.anchor else lexical.parts
        for component in components:
            current /= component
            try:
                metadata = os.lstat(current)
            except FileNotFoundError:
                break
            if _redirect(current, metadata) or not stat.S_ISDIR(metadata.st_mode):
                raise OSError("unsafe data root")
        canonical = lexical.resolve(strict=False)
    except (OSError, RuntimeError, ValueError):
        raise _fail("HARDWARE_INPUT_INVALID", "data root is invalid") from None
    try:
        canonical.relative_to(project_root)
    except ValueError:
        return canonical
    raise _fail(
        "HARDWARE_INPUT_INVALID",
        "data root must remain outside the project root",
    )


def _prepare(
    request: object,
    expected_type: type[object],
    *,
    require_probe: bool,
    require_pins: bool,
    require_svd: bool = False,
) -> tuple[object, ProjectModel, WorkspacePaths]:
    if type(request) is not expected_type:
        raise _fail("HARDWARE_INPUT_INVALID", "Hardware workflow input is invalid")
    project_root = _safe_root(getattr(request, "project_root", None), "project root", must_exist=True)
    data_root = _safe_external_data_root(
        getattr(request, "data_root", None), project_root
    )
    try:
        session_id = require_safe_session_id(getattr(request, "session_id", None))
        model = load_project_model(project_root)
    except (ProjectManifestError, TypeError, ValueError):
        raise _fail("HARDWARE_INPUT_INVALID", "Hardware workflow input is invalid") from None
    if (
        model.schema_version != 2
        or model.project_root != project_root
        or model.debug.backend != "pyocd"
        or not isinstance(model.debug.target, str)
        or _IDENTIFIER.fullmatch(model.debug.target) is None
    ):
        raise _fail("HARDWARE_INPUT_INVALID", "A Schema-v2 PyOCD target is required")
    if require_svd and (
        not isinstance(model.debug.svd, str)
        or not model.debug.svd
        or "\\" in model.debug.svd
    ):
        raise _fail("SVD_SELECTION_REQUIRED", "An exact project SVD selection is required")
    if require_probe:
        probe = getattr(request, "probe_id", None)
        if not isinstance(probe, str) or _IDENTIFIER.fullmatch(probe) is None:
            raise _fail("HARDWARE_INPUT_INVALID", "Probe selector is invalid")
    if require_pins:
        if _DIGEST.fullmatch(getattr(request, "expected_build_id", "")) is None or _DIGEST.fullmatch(
            getattr(request, "expected_elf_sha256", "")
        ) is None:
            raise _fail("HARDWARE_INPUT_INVALID", "Firmware identity pins are invalid")
    try:
        paths = WorkspacePaths.from_roots(
            data_root,
            project_root,
            model.logical_project_id,
            session_id,
        )
    except (OSError, RuntimeError, TypeError, ValueError):
        raise _fail("HARDWARE_INPUT_INVALID", "Hardware workflow roots are invalid") from None
    if require_probe:
        component = "probe-" + hashlib.sha256(probe.encode("utf-8")).hexdigest()[:24]
        paths = replace(
            paths,
            session_root=paths.session_root / "probes" / component,
        )
    return request, model, paths


def _redirect(path: Path, metadata: os.stat_result) -> bool:
    return path.is_symlink() or bool(
        getattr(metadata, "st_file_attributes", 0) & _REPARSE_POINT
    )


def _ensure_session_root(paths: WorkspacePaths) -> None:
    """Create only the transient session chain, rejecting redirects at each step."""

    base_session_root = paths.workspace_root / "sessions" / paths.session_id
    try:
        suffix = paths.session_root.relative_to(base_session_root)
    except ValueError:
        raise _fail(
            "HARDWARE_RUNTIME_PATH_UNSAFE",
            "Hardware runtime path is unavailable or unsafe",
        ) from None
    chain = [
        paths.data_root,
        paths.data_root / "projects",
        paths.workspace_root,
        paths.workspace_root / "sessions",
        base_session_root,
    ]
    current = base_session_root
    for component in suffix.parts:
        current /= component
        chain.append(current)
    try:
        # ``data_root`` may itself contain multiple not-yet-created
        # components.  ``resolve(strict=False)`` in ``WorkspacePaths`` has
        # already canonicalized every existing prefix; create the missing
        # suffix before validating each owned component again below.
        paths.data_root.mkdir(parents=True, exist_ok=True)
        for directory in chain:
            directory.resolve(strict=False).relative_to(paths.data_root)
            try:
                before = os.lstat(directory)
            except FileNotFoundError:
                before = None
            if before is not None and (
                _redirect(directory, before) or not stat.S_ISDIR(before.st_mode)
            ):
                raise OSError("unsafe runtime component")
            directory.mkdir(exist_ok=True)
            after = os.lstat(directory)
            if _redirect(directory, after) or not stat.S_ISDIR(after.st_mode):
                raise OSError("unsafe runtime component")
            directory.resolve(strict=True).relative_to(paths.data_root.resolve(strict=True))
    except (OSError, RuntimeError, ValueError):
        raise _fail(
            "HARDWARE_RUNTIME_PATH_UNSAFE",
            "Hardware runtime path is unavailable or unsafe",
        ) from None


def _items(value: object) -> tuple[str, ...]:
    if (
        type(value) is not tuple
        or not 1 <= len(value) <= _MAX_ITEMS
        or len(set(value)) != len(value)
        or any(
            not isinstance(item, str)
            or not item
            or len(item) > 512
            or "\x00" in item
            for item in value
        )
    ):
        raise _fail("HARDWARE_INPUT_INVALID", "Hardware item selection is invalid")
    return value


def _make_supervisor(
    paths: WorkspacePaths,
    probe_id: str,
    level: OperationLevel,
    seams: HardwareWorkflowSeams,
) -> object:
    config = ProbeServiceConfig(
        probe_id=probe_id,
        workspace_id=paths.workspace_id,
        session_id=paths.session_id,
        operation_level=level,
        session_root=paths.session_root,
        project_root=paths.project_root,
    )
    lease_manager = seams.lease_manager_factory(paths.data_root)
    return seams.supervisor_factory(config, lease_manager, seams.backend_factory)


def _validate_endpoint(endpoint: object, paths: WorkspacePaths, probe_id: str, level: OperationLevel) -> None:
    if (
        getattr(endpoint, "workspace_id", None) != paths.workspace_id
        or getattr(endpoint, "session_id", None) != paths.session_id
        or getattr(endpoint, "probe_id", None) != probe_id
        or getattr(endpoint, "operation_level", None) is not level
        or not isinstance(getattr(endpoint, "lease_id", None), str)
    ):
        raise _fail("HARDWARE_SERVICE_INVALID", "Probe Service identity is invalid")


@dataclass(frozen=True)
class _OwnedOutcome:
    value: object | None
    error: BaseException | None
    cancellation: asyncio.CancelledError | None


async def _await_owned(task: asyncio.Future[object]) -> _OwnedOutcome:
    """Finish one owned task despite repeated cancellation of its caller."""

    cancellation: asyncio.CancelledError | None = None
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError as error:
            if cancellation is None:
                cancellation = error
        except BaseException:
            break
    try:
        value = task.result()
    except BaseException as error:
        return _OwnedOutcome(None, error, cancellation)
    return _OwnedOutcome(value, None, cancellation)


@dataclass(frozen=True)
class _CleanupOutcome:
    failed: bool
    cancellation: asyncio.CancelledError | None
    fatal: BaseException | None


def _merge_cancellation(
    current: asyncio.CancelledError | None,
    incoming: asyncio.CancelledError | None,
) -> asyncio.CancelledError | None:
    return current if current is not None else incoming


async def _cleanup(clients: list[object], supervisor: object | None) -> _CleanupOutcome:
    failed = False
    cancellation: asyncio.CancelledError | None = None
    fatal: BaseException | None = None

    def record_error(error: BaseException) -> None:
        nonlocal failed, fatal
        failed = True
        if not isinstance(error, (Exception, asyncio.CancelledError)) and fatal is None:
            fatal = error

    async def finish(awaitable: object) -> None:
        nonlocal failed, cancellation, fatal
        try:
            task = asyncio.ensure_future(awaitable)
        except BaseException as error:
            outcome = _OwnedOutcome(None, error, None)
        else:
            outcome = await _await_owned(task)
        cancellation = _merge_cancellation(cancellation, outcome.cancellation)
        error = outcome.error
        if error is None:
            return
        record_error(error)

    for client in reversed(clients):
        close = getattr(client, "close", None)
        if close is None:
            failed = True
            continue
        try:
            awaitable = close()
        except BaseException as error:
            record_error(error)
            continue
        await finish(awaitable)
    if supervisor is not None:
        try:
            awaitable = supervisor.stop()
        except BaseException as error:
            record_error(error)
        else:
            await finish(awaitable)
    return _CleanupOutcome(failed, cancellation, fatal)


def _sanitize(value: object, roots: tuple[Path, ...]) -> object:
    if isinstance(value, Mapping):
        return {
            str(key): _sanitize(item, roots)
            for key, item in value.items()
            if isinstance(key, str) and key.lower() not in _FORBIDDEN_RESULT_KEYS
        }
    if isinstance(value, (tuple, list)):
        return [_sanitize(item, roots) for item in value]
    if isinstance(value, str):
        folded = value.casefold()
        for root in roots:
            text = str(root)
            if text and text.casefold() in folded:
                return "redacted"
    return value


def _public_result(result: object, paths: WorkspacePaths) -> OperationResult[object]:
    if not isinstance(result, OperationResult):
        return OperationResult.failure(
            "hardware-workflow",
            "HARDWARE_INTERNAL_ERROR",
            "Hardware workflow failed",
            {},
        )
    payload = result.to_dict()
    roots = (
        paths.project_root,
        paths.data_root,
        paths.workspace_root,
        paths.session_root,
    )
    details = _sanitize(payload.get("details", {}), roots)
    if not isinstance(details, Mapping):
        details = {}
    if not result.ok:
        return OperationResult.failure(result.operation, result.code, result.message, details)
    return OperationResult.success(result.operation, _sanitize(payload.get("data"), roots))


_KNOWN_STABLE_EXCEPTIONS = (
    ProbeBackendError,
    ProbeClientError,
    ProbeLeaseError,
    ProbeServiceError,
)


def _stable_exception_result(operation: str, error: BaseException) -> OperationResult[None]:
    if not isinstance(error, _KNOWN_STABLE_EXCEPTIONS):
        return OperationResult.failure(
            operation,
            "HARDWARE_INTERNAL_ERROR",
            "Hardware workflow failed",
            {},
        )
    code = getattr(error, "code", None)
    message = getattr(error, "message", None)
    details = getattr(error, "details", {})
    if (
        isinstance(code, str)
        and _ERROR_CODE.fullmatch(code) is not None
        and isinstance(message, str)
        and 0 < len(message) <= 512
        and isinstance(details, Mapping)
    ):
        return OperationResult.failure(operation, code, message, details)
    return OperationResult.failure(
        operation,
        "HARDWARE_INTERNAL_ERROR",
        "Hardware workflow failed",
        {},
    )


async def _one_shot(
    *,
    operation: str,
    paths: WorkspacePaths,
    probe_id: str,
    level: OperationLevel,
    seams: HardwareWorkflowSeams,
    action: Callable[[object, object], Awaitable[OperationResult[Any]]],
) -> OperationResult[object]:
    supervisor: object | None = None
    clients: list[object] = []
    cancelled: asyncio.CancelledError | None = None
    fatal: BaseException | None = None
    result: OperationResult[Any] | None = None
    try:
        _ensure_session_root(paths)
        supervisor = _make_supervisor(paths, probe_id, level, seams)
        endpoint = await supervisor.start()
        _validate_endpoint(endpoint, paths, probe_id, level)
        client = seams.client_factory(endpoint)
        clients.append(client)
        result = await action(supervisor, client)
    except asyncio.CancelledError as error:
        cancelled = error
    except _WorkflowFailure as error:
        result = _operation_failure(operation, error)
    except Exception as error:
        result = _stable_exception_result(operation, error)
    except BaseException as error:
        fatal = error
    cleanup = await _cleanup(clients, supervisor)
    if cleanup.fatal is not None:
        raise cleanup.fatal
    if cleanup.failed:
        return OperationResult.failure(
            operation,
            "HARDWARE_CLEANUP_FAILED",
            "Hardware workflow cleanup failed",
            {},
        )
    if fatal is not None:
        raise fatal
    cancellation = _merge_cancellation(cancelled, cleanup.cancellation)
    if cancellation is not None:
        raise cancellation
    assert result is not None
    return _public_result(result, paths)


async def probe_list_workflow(
    request: object,
    *,
    _seams: HardwareWorkflowSeams = _DEFAULT_SEAMS,
) -> OperationResult[object]:
    operation = "stm32_probe_list"
    try:
        _, _, paths = _prepare(
            request, ProbeListWorkflowRequest, require_probe=False, require_pins=False
        )
    except _WorkflowFailure as error:
        return _operation_failure(operation, error)
    backend: object | None = None
    cancelled: asyncio.CancelledError | None = None
    fatal: BaseException | None = None
    result: OperationResult[object] | None = None
    close_failed = False
    try:
        backend = _seams.backend_factory()
        listing = asyncio.create_task(asyncio.to_thread(backend.list_probes))
        listed = await _await_owned(listing)
        cancelled = _merge_cancellation(cancelled, listed.cancellation)
        if listed.error is not None:
            if isinstance(listed.error, (Exception, asyncio.CancelledError)):
                result = OperationResult.failure(
                    operation,
                    "PROBE_ENUMERATION_FAILED",
                    "Debug probe enumeration failed",
                    {},
                )
            else:
                fatal = listed.error
        else:
            descriptors = listed.value
            if (
                type(descriptors) is not tuple
                or len(descriptors) > _MAX_PROBES
                or any(not isinstance(item, object) or not hasattr(item, "to_dict") for item in descriptors)
            ):
                raise _fail("PROBE_ENUMERATION_FAILED", "Debug probe enumeration failed")
            ordered = sorted(descriptors, key=lambda item: item.probe_id)
            result = OperationResult.success(
                operation,
                {
                    "workspaceId": paths.workspace_id,
                    "sessionId": paths.session_id,
                    "probes": [item.to_dict() for item in ordered],
                },
            )
    except _WorkflowFailure as error:
        result = _operation_failure(operation, error)
    except Exception:
        result = OperationResult.failure(
            operation,
            "PROBE_ENUMERATION_FAILED",
            "Debug probe enumeration failed",
            {},
        )
    except BaseException as error:
        fatal = error
    if backend is not None:
        try:
            closing = asyncio.create_task(asyncio.to_thread(backend.close))
            closed = await _await_owned(closing)
            cancelled = _merge_cancellation(cancelled, closed.cancellation)
            if closed.error is not None:
                if isinstance(closed.error, (Exception, asyncio.CancelledError)):
                    close_failed = True
                else:
                    fatal = closed.error
        except BaseException as error:
            close_failed = True
            if not isinstance(error, (Exception, asyncio.CancelledError)):
                fatal = error
    if close_failed:
        return OperationResult.failure(
            operation,
            "HARDWARE_CLEANUP_FAILED",
            "Hardware workflow cleanup failed",
            {},
        )
    if fatal is not None:
        raise fatal
    if cancelled is not None:
        raise cancelled
    assert result is not None
    return _public_result(result, paths)


async def flash_workflow(
    request: object,
    *,
    _seams: HardwareWorkflowSeams = _DEFAULT_SEAMS,
) -> OperationResult[object]:
    operation = "stm32_flash"
    try:
        typed, model, paths = _prepare(
            request, FlashWorkflowRequest, require_probe=True, require_pins=True
        )
        if typed.authorized is not True:
            raise _fail("AUTHORIZATION_REQUIRED", "Explicit flash authorization is required")
    except _WorkflowFailure as error:
        return _operation_failure(operation, error)

    async def action(supervisor: object, client: object) -> OperationResult[Any]:
        return await _seams.flash(
            FlashRequest(
                paths.project_root,
                typed.probe_id,
                model.debug.target,
                typed.expected_build_id,
                typed.expected_elf_sha256,
                True,
            ),
            client,
        )

    return await _one_shot(
        operation=operation,
        paths=paths,
        probe_id=typed.probe_id,
        level=OperationLevel.MODIFY,
        seams=_seams,
        action=action,
    )


async def handoff_begin_workflow(
    request: object,
    *,
    _seams: HardwareWorkflowSeams = _DEFAULT_SEAMS,
) -> OperationResult[object]:
    operation = "stm32_debug_handoff_begin"
    try:
        typed, _, paths = _prepare(
            request, HandoffBeginWorkflowRequest, require_probe=True, require_pins=True
        )
        if typed.authorized is not True:
            raise _fail("AUTHORIZATION_REQUIRED", "Explicit handoff authorization is required")
        selection = typed.previous_watch_selection
        if type(selection) is not tuple or len(selection) > _MAX_ITEMS or any(
            not isinstance(item, str) or not item or len(item) > 512 for item in selection
        ):
            raise _fail("HARDWARE_INPUT_INVALID", "Watch selection is invalid")
    except _WorkflowFailure as error:
        return _operation_failure(operation, error)

    async def action(supervisor: object, client: object) -> OperationResult[Any]:
        return await _seams.handoff_begin(
            DebugHandoffRequest(
                paths.project_root,
                typed.expected_build_id,
                typed.expected_elf_sha256,
                True,
                selection,
            ),
            supervisor,
            client,
        )

    return await _one_shot(
        operation=operation,
        paths=paths,
        probe_id=typed.probe_id,
        level=OperationLevel.OBSERVE,
        seams=_seams,
        action=action,
    )


async def handoff_end_workflow(
    request: object,
    *,
    _seams: HardwareWorkflowSeams = _DEFAULT_SEAMS,
) -> OperationResult[object]:
    operation = "stm32_debug_handoff_end"
    try:
        typed, _, paths = _prepare(
            request, HandoffEndWorkflowRequest, require_probe=True, require_pins=False
        )
        if not isinstance(typed.ticket, str) or _DIGEST.fullmatch(typed.ticket) is None:
            raise _fail("HARDWARE_INPUT_INVALID", "Debug handoff ticket is invalid")
        _ensure_session_root(paths)
        supervisor = _make_supervisor(
            paths, typed.probe_id, OperationLevel.OBSERVE, _seams
        )
    except _WorkflowFailure as error:
        return _operation_failure(operation, error)
    clients: list[object] = []

    def client_factory(endpoint: object) -> object:
        _validate_endpoint(endpoint, paths, typed.probe_id, OperationLevel.OBSERVE)
        client = _seams.client_factory(endpoint)
        clients.append(client)
        return client

    cancelled: asyncio.CancelledError | None = None
    fatal: BaseException | None = None
    result: OperationResult[Any] | None = None
    try:
        result = await _seams.handoff_end(typed.ticket, supervisor, client_factory)
    except asyncio.CancelledError as error:
        cancelled = error
    except Exception as error:
        result = _stable_exception_result(operation, error)
    except BaseException as error:
        fatal = error
    cleanup = await _cleanup(clients, supervisor)
    if cleanup.fatal is not None:
        raise cleanup.fatal
    if cleanup.failed:
        return OperationResult.failure(
            operation,
            "HARDWARE_CLEANUP_FAILED",
            "Hardware workflow cleanup failed",
            {},
        )
    if fatal is not None:
        raise fatal
    cancellation = _merge_cancellation(cancelled, cleanup.cancellation)
    if cancellation is not None:
        raise cancellation
    assert result is not None
    return _public_result(result, paths)


async def _bind_and_run(
    *,
    operation: str,
    typed: object,
    model: ProjectModel,
    paths: WorkspacePaths,
    seams: HardwareWorkflowSeams,
    build_request: Callable[[object], object],
    accepted: Callable[[object, object], Awaitable[OperationResult[Any]]],
) -> OperationResult[object]:
    async def action(supervisor: object, client: object) -> OperationResult[Any]:
        endpoint = getattr(client, "endpoint", None)
        binding_result = await seams.bind(
            DebugBindingRequest(
                paths.project_root,
                typed.probe_id,
                model.debug.target,
                paths.workspace_id,
                paths.session_id,
                endpoint.lease_id,
                typed.expected_build_id,
                typed.expected_elf_sha256,
            ),
            client,
        )
        if not binding_result.ok or binding_result.data is None:
            return binding_result
        return await accepted(build_request(binding_result.data), client)

    return await _one_shot(
        operation=operation,
        paths=paths,
        probe_id=typed.probe_id,
        level=OperationLevel.OBSERVE,
        seams=seams,
        action=action,
    )


async def variable_read_workflow(
    request: object,
    *,
    _seams: HardwareWorkflowSeams = _DEFAULT_SEAMS,
) -> OperationResult[object]:
    operation = "stm32_variable_read"
    try:
        typed, model, paths = _prepare(
            request, VariableReadWorkflowRequest, require_probe=True, require_pins=True
        )
        expressions = _items(typed.expressions)
    except _WorkflowFailure as error:
        return _operation_failure(operation, error)
    return await _bind_and_run(
        operation=operation,
        typed=typed,
        model=model,
        paths=paths,
        seams=_seams,
        build_request=lambda binding: VariableReadRequest(
            binding, _seams.catalog_from_binding(binding), expressions
        ),
        accepted=_seams.read_variables,
    )


async def variable_sample_workflow(
    request: object,
    *,
    _seams: HardwareWorkflowSeams = _DEFAULT_SEAMS,
) -> OperationResult[object]:
    operation = "stm32_variable_sample"
    try:
        typed, model, paths = _prepare(
            request, VariableSampleWorkflowRequest, require_probe=True, require_pins=True
        )
        expressions = _items(typed.expressions)
        if (
            type(typed.interval_ms) is not int
            or typed.interval_ms < 1
            or typed.interval_ms > 3_600_000
            or (typed.count is not None and (type(typed.count) is not int or not 1 <= typed.count <= 10_000))
            or (
                typed.duration_ms is not None
                and (type(typed.duration_ms) is not int or not 1 <= typed.duration_ms <= 3_600_000)
            )
            or (typed.count is None and typed.duration_ms is None)
        ):
            raise _fail("HARDWARE_INPUT_INVALID", "Finite sample request is invalid")
    except _WorkflowFailure as error:
        return _operation_failure(operation, error)
    return await _bind_and_run(
        operation=operation,
        typed=typed,
        model=model,
        paths=paths,
        seams=_seams,
        build_request=lambda binding: SampleVariablesRequest(
            binding,
            _seams.catalog_from_binding(binding),
            expressions,
            typed.interval_ms,
            typed.count,
            typed.duration_ms,
        ),
        accepted=_seams.sample_variables,
    )


async def register_read_workflow(
    request: object,
    *,
    _seams: HardwareWorkflowSeams = _DEFAULT_SEAMS,
) -> OperationResult[object]:
    operation = "stm32_register_read"
    try:
        typed, model, paths = _prepare(
            request,
            RegisterReadWorkflowRequest,
            require_probe=True,
            require_pins=True,
            require_svd=True,
        )
        paths_requested = _items(typed.paths)
        if type(typed.acknowledge_access_risk) is not bool:
            raise _fail("HARDWARE_INPUT_INVALID", "Register access acknowledgement is invalid")
    except _WorkflowFailure as error:
        return _operation_failure(operation, error)

    def build(binding: object) -> RegisterReadRequest:
        selection = _seams.svd_select(
            paths.project_root,
            model.target.device,
            (Path(model.debug.svd),),
            readable_regions=binding.memory_regions,
        )
        return RegisterReadRequest(
            binding,
            selection,
            paths_requested,
            typed.acknowledge_access_risk,
        )

    return await _bind_and_run(
        operation=operation,
        typed=typed,
        model=model,
        paths=paths,
        seams=_seams,
        build_request=build,
        accepted=_seams.read_registers,
    )


async def fault_workflow(
    request: object,
    *,
    _seams: HardwareWorkflowSeams = _DEFAULT_SEAMS,
) -> OperationResult[object]:
    operation = "stm32_fault_analyze"
    try:
        typed, model, paths = _prepare(
            request, FaultWorkflowRequest, require_probe=True, require_pins=True
        )
    except _WorkflowFailure as error:
        return _operation_failure(operation, error)
    return await _bind_and_run(
        operation=operation,
        typed=typed,
        model=model,
        paths=paths,
        seams=_seams,
        build_request=FaultAnalysisRequest,
        accepted=_seams.analyze_fault,
    )


__all__ = [
    "FaultWorkflowRequest",
    "FlashWorkflowRequest",
    "HandoffBeginWorkflowRequest",
    "HandoffEndWorkflowRequest",
    "HardwareWorkflowSeams",
    "ProbeListWorkflowRequest",
    "RegisterReadWorkflowRequest",
    "VariableReadWorkflowRequest",
    "VariableSampleWorkflowRequest",
    "fault_workflow",
    "flash_workflow",
    "handoff_begin_workflow",
    "handoff_end_workflow",
    "probe_list_workflow",
    "register_read_workflow",
    "variable_read_workflow",
    "variable_sample_workflow",
]
