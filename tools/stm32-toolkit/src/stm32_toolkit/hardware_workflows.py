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
    DebugFirmwareBinding,
    DwarfCatalog,
    FaultAnalysisRequest,
    RegisterReadRequest,
    SampleVariablesRequest,
    SvdSelection,
    VariableReadRequest,
    analyze_fault,
    bind_debug_firmware,
    read_registers,
    read_variables,
    sample_variables,
    select_svd,
)
from stm32_toolkit.debug.firmware import _svd_readable_regions_from_model
from stm32_toolkit.debug.svd import SvdError
from stm32_toolkit.paths import WorkspacePaths, require_safe_session_id
from stm32_toolkit.probe import (
    DebugHandoffRequest,
    FlashRequest,
    OperationLevel,
    ProbeServiceConfig,
    ProbeServiceSupervisor,
    begin_debug_handoff,
    end_debug_handoff,
    flash_firmware,
)
from stm32_toolkit.probe.backend import ProbeBackendError
from stm32_toolkit.probe.client import (
    ControlAuthorizationClient,
    ProbeClient,
    ProbeClientError,
)
from stm32_toolkit.probe.lease import ProbeLeaseError, ProbeLeaseManager
from stm32_toolkit.probe.service import ProbeServiceError, _service_error_fields
from stm32_toolkit.probe.service import ProbeServiceCleanupError
from stm32_toolkit.probe.attach_diagnostics import (
    CleanupFragment,
    append_cleanup,
    extract_attach_diagnostic,
    make_cleanup_entry,
)
from stm32_toolkit.probe.handoff import _canonical_target
from stm32_toolkit.probe.worker import ProbeBackendWorker, ProbeWorkerConfig
from stm32_toolkit.project_model import ProjectManifestError, ProjectModel, load_project_model
from stm32_toolkit.result import OperationResult

_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_ERROR_CODE = re.compile(r"^[A-Z][A-Z0-9_]{1,63}$")
_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
_MAX_PROBES = 64
_MAX_ITEMS = 256
_CONTROLLED_SNAPSHOT_RECOVERY_SECONDS = 45.0
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
    recovery_under_reset: object = False


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
    halt_for_analysis: object = False


def _supervisor_factory(
    config: ProbeServiceConfig,
    lease_manager: object,
    backend_contract: object,
) -> ProbeServiceSupervisor:
    if type(backend_contract) is ProbeWorkerConfig:
        return ProbeServiceSupervisor(
            config=config,
            lease_manager=lease_manager,
            worker_config=backend_contract,
        )
    return ProbeServiceSupervisor(
        config=config,
        lease_manager=lease_manager,
        backend_factory=backend_contract,
    )


@dataclass(frozen=True)
class HardwareWorkflowSeams:
    """Narrow injectable construction/accepted-contract seams for software gates."""

    worker_config: ProbeWorkerConfig = ProbeWorkerConfig()
    _test_backend_factory: Callable[[], object] | None = None
    lease_manager_factory: Callable[[Path], object] = ProbeLeaseManager
    supervisor_factory: Callable[[ProbeServiceConfig, object, object], object] = _supervisor_factory
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
        model.schema_version not in (2, 3)
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
    *,
    worker_config: ProbeWorkerConfig | None = None,
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
    backend_contract: object = (
        seams.worker_config if worker_config is None else worker_config
    )
    if seams._test_backend_factory is not None:
        backend_contract = seams._test_backend_factory
    elif worker_config is None and level is OperationLevel.OBSERVE:
        backend_contract = seams.worker_config.for_observation()
    return seams.supervisor_factory(config, lease_manager, backend_contract)


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
    fragment: CleanupFragment


def _merge_cancellation(
    current: asyncio.CancelledError | None,
    incoming: asyncio.CancelledError | None,
) -> asyncio.CancelledError | None:
    return current if current is not None else incoming


def _workflow_cleanup_failure(stage: str, error: BaseException) -> dict[str, str]:
    reason, source_code = _service_error_fields(error)
    return make_cleanup_entry(
        stage, "failed", reason=reason, source_code=source_code
    )


async def _cleanup(clients: list[object], supervisor: object | None) -> _CleanupOutcome:
    failed = False
    cancellation: asyncio.CancelledError | None = None
    fatal: BaseException | None = None
    entries: list[dict[str, str]] = []
    client_attempted = bool(clients)
    client_failed = False
    client_error: BaseException | None = None

    def record_error(error: BaseException) -> None:
        nonlocal failed, fatal
        failed = True
        if not isinstance(error, (Exception, asyncio.CancelledError)) and fatal is None:
            fatal = error

    async def finish(awaitable: object) -> _OwnedOutcome:
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
            return outcome
        record_error(error)
        return outcome

    for client in reversed(clients):
        close = getattr(client, "close", None)
        if close is None:
            failed = True
            client_failed = True
            if client_error is None:
                client_error = RuntimeError("client close is unavailable")
            continue
        try:
            awaitable = close()
        except BaseException as error:
            record_error(error)
            client_failed = True
            if client_error is None:
                client_error = error
            continue
        outcome = await finish(awaitable)
        client_failed = client_failed or outcome.error is not None
        if client_error is None and outcome.error is not None:
            client_error = outcome.error
    if client_attempted:
        if client_failed:
            entries.append(
                _workflow_cleanup_failure(
                    "workflow-client-close", client_error or RuntimeError()
                )
            )
        else:
            entries.append(make_cleanup_entry("workflow-client-close", "succeeded"))
    if supervisor is not None:
        try:
            awaitable = supervisor.stop()
        except BaseException as error:
            record_error(error)
            if isinstance(error, ProbeServiceCleanupError):
                entries.extend(error.cleanup_fragment.to_list())
            entries.append(
                _workflow_cleanup_failure("workflow-service-stop", error)
            )
        else:
            try:
                task = asyncio.ensure_future(awaitable)
            except BaseException as error:
                record_error(error)
                entries.append(
                    _workflow_cleanup_failure("workflow-service-stop", error)
                )
            else:
                outcome = await _await_owned(task)
                cancellation = _merge_cancellation(cancellation, outcome.cancellation)
                if outcome.error is not None:
                    record_error(outcome.error)
                    if isinstance(outcome.error, ProbeServiceCleanupError):
                        entries.extend(outcome.error.cleanup_fragment.to_list())
                    entries.append(
                        _workflow_cleanup_failure(
                            "workflow-service-stop", outcome.error
                        )
                    )
                else:
                    if isinstance(outcome.value, CleanupFragment):
                        entries.extend(outcome.value.to_list())
                    entries.append(
                        make_cleanup_entry("workflow-service-stop", "succeeded")
                    )
    return _CleanupOutcome(
        failed, cancellation, fatal, CleanupFragment.from_entries(entries)
    )


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
    controlled_snapshot = details.get("controlledSnapshot")
    if not isinstance(controlled_snapshot, Mapping):
        if not result.ok:
            return OperationResult.failure(
                result.operation, result.code, result.message, details
            )
        return OperationResult.success(
            result.operation, _sanitize(payload.get("data"), roots)
        )
    return OperationResult(
        result.protocol,
        result.ok,
        result.operation,
        result.code,
        result.message,
        _sanitize(payload.get("data"), roots) if result.ok else None,
        details,
    )


def _result_with_details(
    result: OperationResult[Any], details: Mapping[str, object]
) -> OperationResult[Any]:
    return OperationResult(
        result.protocol,
        result.ok,
        result.operation,
        result.code,
        result.message,
        result.data,
        details,
    )


def _with_controlled_cleanup(
    result: OperationResult[Any],
    cleanup: _CleanupOutcome,
) -> OperationResult[Any]:
    details = result.details
    if not isinstance(details, Mapping):
        return result
    snapshot = details.get("controlledSnapshot")
    if not isinstance(snapshot, Mapping):
        return result
    controlled = dict(snapshot)
    controlled["cleanup"] = {
        "outcome": "failed" if cleanup.failed else "succeeded",
        "stages": cleanup.fragment.to_list(),
    }
    return _result_with_details(
        result,
        {**dict(details), "controlledSnapshot": controlled},
    )


_KNOWN_STABLE_EXCEPTIONS = (
    ProbeBackendError,
    ProbeClientError,
    ProbeLeaseError,
    ProbeServiceError,
    SvdError,
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
    worker_config: ProbeWorkerConfig | None = None,
) -> OperationResult[object]:
    supervisor: object | None = None
    clients: list[object] = []
    cancelled: asyncio.CancelledError | None = None
    fatal: BaseException | None = None
    result: OperationResult[Any] | None = None
    try:
        _ensure_session_root(paths)
        supervisor = _make_supervisor(
            paths,
            probe_id,
            level,
            seams,
            worker_config=worker_config,
        )
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
    diagnostic = extract_attach_diagnostic(
        result.details if isinstance(result, OperationResult) else None
    )
    if diagnostic is not None and isinstance(result, OperationResult) and not result.ok:
        merged = append_cleanup(diagnostic, cleanup.fragment)
        if merged is not None:
            result = OperationResult.failure(
                result.operation,
                result.code,
                result.message,
                {
                    **(
                        dict(result.details)
                        if isinstance(result.details, Mapping)
                        else {}
                    ),
                    "attachDiagnostic": merged,
                },
            )
    if isinstance(result, OperationResult):
        result = _with_controlled_cleanup(result, cleanup)
    if cleanup.failed:
        details: dict[str, object] = {}
        controlled_result = (
            isinstance(result, OperationResult)
            and isinstance(result.details, Mapping)
            and isinstance(result.details.get("controlledSnapshot"), Mapping)
        )
        if controlled_result:
            assert isinstance(result, OperationResult)
            details.update(dict(result.details))
        if (
            controlled_result
            and isinstance(result, OperationResult)
            and "initiatingCode" not in details
        ):
            details["initiatingCode"] = result.code
        if diagnostic is not None:
            merged = extract_attach_diagnostic(
                result.details if isinstance(result, OperationResult) else None
            )
            if merged is not None:
                details["attachDiagnostic"] = merged
        return _public_result(
            OperationResult.failure(
                operation,
                "HARDWARE_CLEANUP_FAILED",
                "Hardware workflow cleanup failed",
                details,
            ),
            paths,
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
        backend = (
            _seams._test_backend_factory()
            if _seams._test_backend_factory is not None
            else ProbeBackendWorker(config=_seams.worker_config)
        )
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
        if type(typed.recovery_under_reset) is not bool:
            raise _fail("HARDWARE_INPUT_INVALID", "Flash recovery selection is invalid")
    except _WorkflowFailure as error:
        return _operation_failure(operation, error)

    selected_seams = _seams
    if typed.recovery_under_reset:
        selected_seams = replace(
            _seams,
            worker_config=_seams.worker_config.for_under_reset_recovery(),
        )

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
        seams=selected_seams,
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


def _new_controlled_snapshot() -> dict[str, object]:
    return {
        "mode": "halt-for-analysis",
        "beforeState": None,
        "analysisState": None,
        "afterState": None,
        "halt": {"dispatched": False, "outcome": "not-started"},
        "resume": {"dispatched": False, "outcome": "not-started"},
        "cleanup": {"outcome": "pending", "stages": []},
    }


def _controlled_result(
    result: OperationResult[Any], snapshot: Mapping[str, object]
) -> OperationResult[Any]:
    details = dict(result.details) if isinstance(result.details, Mapping) else {}
    return _result_with_details(
        result,
        {**details, "controlledSnapshot": dict(snapshot)},
    )


def _controlled_error(
    operation: str, error: BaseException, snapshot: Mapping[str, object]
) -> OperationResult[Any]:
    if isinstance(error, _WorkflowFailure):
        result: OperationResult[Any] = OperationResult.failure(
            operation, error.code, error.message, {}
        )
    elif isinstance(error, asyncio.TimeoutError):
        result = OperationResult.failure(
            operation,
            "PROBE_TIMEOUT",
            "Probe control operation timed out",
            {},
        )
    else:
        result = _stable_exception_result(operation, error)
    return _controlled_result(result, snapshot)


def _controlled_identity_expectation(
    binding: DebugFirmwareBinding, worker_config: ProbeWorkerConfig
) -> dict[str, object]:
    profile = worker_config.target_profile()
    return {
        "board_id": profile.get("board_id", binding.debug_target),
        "mcu": profile.get("mcu", binding.target_device),
        "target_id": profile.get("target_id", binding.debug_target),
        "probe_serial_hash": hashlib.sha256(
            binding.probe_id.encode("utf-8")
        ).hexdigest(),
    }


def _validate_controlled_identity(
    value: object,
    binding: DebugFirmwareBinding,
    expected: Mapping[str, object],
) -> dict[str, object]:
    fields = {"board_id", "mcu", "target_id", "probe_serial_hash"}
    if not isinstance(expected, Mapping) or set(expected) != fields:
        raise _fail(
            "FAULT_TARGET_MISMATCH",
            "Connected target does not match the Fault binding",
        )
    if (
        not isinstance(value, Mapping)
        or set(value) != fields
        or any(
            not isinstance(value[field], str) or not value[field]
            for field in ("board_id", "mcu", "target_id")
        )
        or not isinstance(value["probe_serial_hash"], str)
        or _DIGEST.fullmatch(value["probe_serial_hash"]) is None
        or any(
            not isinstance(expected[field], str) or not expected[field]
            for field in ("board_id", "mcu", "target_id")
        )
        or not isinstance(expected["probe_serial_hash"], str)
        or _DIGEST.fullmatch(expected["probe_serial_hash"]) is None
        or value["probe_serial_hash"] != expected["probe_serial_hash"]
        or value["board_id"] != expected["board_id"]
        or value["target_id"] != expected["target_id"]
        or _canonical_target(value["mcu"])
        != _canonical_target(binding.target_device)
        or _canonical_target(value["mcu"])
        != _canonical_target(expected["mcu"])
    ):
        raise _fail(
            "FAULT_TARGET_MISMATCH",
            "Connected target does not match the Fault binding",
        )
    return dict(value)


def _validate_controlled_state(value: object) -> dict[str, object]:
    allowed_states = {"running", "halted", "reset", "faulted"}
    allowed_reasons = {"requested", "breakpoint", "watchpoint", "fault", "exception", "reset"}
    if (
        not isinstance(value, Mapping)
        or set(value) != {"state", "reason"}
        or value["state"] not in allowed_states
        or value["reason"] not in allowed_reasons
    ):
        raise _fail(
            "PROBE_RESPONSE_INVALID",
            "Probe target state response is invalid",
        )
    return dict(value)


@dataclass(frozen=True)
class _ControlledCallOutcome:
    value: object | None
    error: BaseException | None
    cancellation: asyncio.CancelledError | None


async def _controlled_call(
    factory: Callable[[], Awaitable[object]], *, deadline: float | None = None
) -> _ControlledCallOutcome:
    try:
        if deadline is not None:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                return _ControlledCallOutcome(None, asyncio.TimeoutError(), None)
        awaitable = factory()
        if deadline is not None:
            awaitable = asyncio.wait_for(awaitable, timeout=remaining)
        task = asyncio.ensure_future(awaitable)
    except BaseException as error:
        return _ControlledCallOutcome(None, error, None)
    outcome = await _await_owned(task)
    cancellation = outcome.cancellation
    error = outcome.error
    if isinstance(error, asyncio.CancelledError):
        cancellation = _merge_cancellation(cancellation, error)
        error = None
    return _ControlledCallOutcome(outcome.value, error, cancellation)


def _control_authorization_binding(
    binding: DebugFirmwareBinding,
    identity_snapshot: Mapping[str, object],
    operation: str,
) -> dict[str, object]:
    return {
        "workspace_id": binding.workspace_id,
        "project_id": binding.logical_project_id,
        "session_id": binding.observation_session_id,
        "revision": binding.git_head,
        "target": dict(identity_snapshot),
        "firmware": {
            "build_id": binding.build_id,
            "elf_sha256": binding.elf_sha256,
        },
        "operation": operation,
        "arguments": {},
    }


async def _prepare_control_authorization(
    supervisor: object,
    client: object,
    binding: DebugFirmwareBinding,
    identity_snapshot: Mapping[str, object],
    operation: str,
    *,
    deadline: float | None = None,
) -> _ControlledCallOutcome:
    def prepare() -> Awaitable[object]:
        store = getattr(supervisor, "control_authorizations", None)
        authorizer = ControlAuthorizationClient(store, client)
        return authorizer.prepare(
            **_control_authorization_binding(binding, identity_snapshot, operation)
        )

    return await _controlled_call(prepare, deadline=deadline)


async def _controlled_fault_action(
    supervisor: object,
    client: object,
    *,
    typed: FaultWorkflowRequest,
    model: ProjectModel,
    paths: WorkspacePaths,
    seams: HardwareWorkflowSeams,
    worker_config: ProbeWorkerConfig,
) -> OperationResult[Any]:
    operation = "stm32_fault_analyze"
    snapshot = _new_controlled_snapshot()
    cancelled: asyncio.CancelledError | None = None

    async def call(
        factory: Callable[[], Awaitable[object]], *, deadline: float | None = None
    ) -> _ControlledCallOutcome:
        nonlocal cancelled
        outcome = await _controlled_call(factory, deadline=deadline)
        cancelled = _merge_cancellation(cancelled, outcome.cancellation)
        return outcome

    endpoint = getattr(client, "endpoint", None)
    bind_outcome = await call(
        lambda: seams.bind(
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
            expected_operation_level=OperationLevel.CONTROL,
        )
    )
    if bind_outcome.error is not None:
        if cancelled is not None:
            raise cancelled
        return _controlled_error(operation, bind_outcome.error, snapshot)
    if cancelled is not None:
        raise cancelled
    binding_result = bind_outcome.value
    if not isinstance(binding_result, OperationResult):
        return _controlled_error(
            operation,
            RuntimeError("debug binding returned an invalid result"),
            snapshot,
        )
    if not binding_result.ok or binding_result.data is None:
        return _controlled_result(binding_result, snapshot)
    binding = binding_result.data
    if type(binding) is not DebugFirmwareBinding:
        return _controlled_error(
            operation,
            _fail("DEBUG_BINDING_INVALID", "Debug binding is invalid"),
            snapshot,
        )
    expected_identity = _controlled_identity_expectation(binding, worker_config)

    identity_outcome = await call(lambda: client.target_identity())
    if identity_outcome.error is not None:
        if cancelled is not None:
            raise cancelled
        return _controlled_error(operation, identity_outcome.error, snapshot)
    try:
        identity_snapshot = _validate_controlled_identity(
            identity_outcome.value, binding, expected_identity
        )
    except _WorkflowFailure as error:
        return _controlled_error(operation, error, snapshot)
    if cancelled is not None:
        raise cancelled

    state_outcome = await call(lambda: client.target_state())
    if state_outcome.error is not None:
        if cancelled is not None:
            raise cancelled
        return _controlled_error(operation, state_outcome.error, snapshot)
    try:
        before_state = _validate_controlled_state(state_outcome.value)
    except _WorkflowFailure as error:
        return _controlled_error(operation, error, snapshot)
    snapshot["beforeState"] = dict(before_state)
    if before_state["state"] != "running":
        return _controlled_error(
            operation,
            _fail(
                "FAULT_TARGET_NOT_RUNNING",
                "Controlled Fault analysis requires a running target",
            ),
            snapshot,
        )
    if cancelled is not None:
        raise cancelled

    halt_prepared = await _prepare_control_authorization(
        supervisor, client, binding, identity_snapshot, "target.halt"
    )
    cancelled = _merge_cancellation(cancelled, halt_prepared.cancellation)
    if halt_prepared.error is not None:
        if cancelled is not None:
            raise cancelled
        snapshot["halt"] = {"dispatched": False, "outcome": "failed"}
        return _controlled_error(operation, halt_prepared.error, snapshot)
    if cancelled is not None:
        raise cancelled
    prepared = halt_prepared.value
    if prepared is None or not hasattr(prepared, "action_digest"):
        snapshot["halt"] = {"dispatched": False, "outcome": "failed"}
        return _controlled_error(
            operation,
            RuntimeError("halt authorization is invalid"),
            snapshot,
        )

    snapshot["halt"] = {"dispatched": True, "outcome": "unknown"}
    halt_outcome = await call(
        lambda: client.target_control("target.halt", {}, prepared.action_digest)
    )
    if halt_outcome.error is not None:
        initiating = _controlled_error(operation, halt_outcome.error, snapshot)
    else:
        try:
            response = _validate_controlled_state(halt_outcome.value)
            if response != {"state": "halted", "reason": "requested"}:
                raise _fail(
                    "PROBE_RESPONSE_INVALID",
                    "Probe target halt response is invalid",
                )
            snapshot["halt"] = {"dispatched": True, "outcome": "succeeded"}
            initiating = None
        except _WorkflowFailure as error:
            initiating = _controlled_error(operation, error, snapshot)
    if cancelled is not None:
        initiating = initiating or OperationResult.failure(
            operation,
            "HARDWARE_CANCELLED",
            "Controlled Fault analysis was cancelled",
            {},
        )

    if initiating is None:
        halted_state_outcome = await call(lambda: client.target_state())
        if halted_state_outcome.error is not None:
            initiating = _controlled_error(operation, halted_state_outcome.error, snapshot)
        else:
            try:
                halted_state = _validate_controlled_state(halted_state_outcome.value)
                snapshot["analysisState"] = dict(halted_state)
                if halted_state["state"] != "halted":
                    raise _fail(
                        "FAULT_TARGET_NOT_HALTED",
                        "Target must remain halted before Fault analysis",
                    )
            except _WorkflowFailure as error:
                initiating = _controlled_error(operation, error, snapshot)

    if initiating is None and cancelled is None:
        analysis_outcome = await call(
            lambda: seams.analyze_fault(
                FaultAnalysisRequest(binding),
                client,
                expected_operation_level=OperationLevel.CONTROL,
                target_identity_snapshot=identity_snapshot,
            )
        )
        if analysis_outcome.error is not None:
            initiating = _controlled_error(operation, analysis_outcome.error, snapshot)
        elif not isinstance(analysis_outcome.value, OperationResult):
            initiating = _controlled_error(
                operation,
                RuntimeError("Fault analyzer returned an invalid result"),
                snapshot,
            )
        else:
            initiating = _controlled_result(analysis_outcome.value, snapshot)
    elif initiating is None:
        initiating = OperationResult.failure(
            operation,
            "HARDWARE_CANCELLED",
            "Controlled Fault analysis was cancelled",
            {},
        )
        initiating = _controlled_result(initiating, snapshot)

    recovery_deadline = (
        asyncio.get_running_loop().time() + _CONTROLLED_SNAPSHOT_RECOVERY_SECONDS
    )
    recovery_identity = await call(
        lambda: client.target_identity(), deadline=recovery_deadline
    )
    recovery_state = await call(
        lambda: client.target_state(), deadline=recovery_deadline
    )
    restoration_failed = False
    current_identity: dict[str, object] | None = None
    current_state: dict[str, object] | None = None
    try:
        if recovery_identity.error is None:
            current_identity = _validate_controlled_identity(
                recovery_identity.value, binding, expected_identity
            )
        else:
            raise recovery_identity.error
        if current_identity != identity_snapshot:
            raise _fail(
                "FAULT_TARGET_CHANGED",
                "Connected target identity changed during Fault recovery",
            )
        if recovery_state.error is None:
            current_state = _validate_controlled_state(recovery_state.value)
        else:
            raise recovery_state.error
    except _WorkflowFailure:
        restoration_failed = True
    except BaseException:
        restoration_failed = True

    if not restoration_failed and current_state is not None:
        if current_state["state"] == "running":
            snapshot["afterState"] = dict(current_state)
            snapshot["resume"] = {
                "dispatched": False,
                "outcome": "already-satisfied",
            }
        elif current_state["state"] == "halted":
            resume_prepared = await _prepare_control_authorization(
                supervisor,
                client,
                binding,
                identity_snapshot,
                "target.resume",
                deadline=recovery_deadline,
            )
            cancelled = _merge_cancellation(cancelled, resume_prepared.cancellation)
            if resume_prepared.error is not None:
                restoration_failed = True
                snapshot["resume"] = {
                    "dispatched": False,
                    "outcome": "failed",
                }
            else:
                resume_authorization = resume_prepared.value
                if resume_authorization is None or not hasattr(
                    resume_authorization, "action_digest"
                ):
                    restoration_failed = True
                    snapshot["resume"] = {
                        "dispatched": False,
                        "outcome": "failed",
                    }
                else:
                    snapshot["resume"] = {
                        "dispatched": True,
                        "outcome": "unknown",
                    }
                    resume_outcome = await call(
                        lambda: client.target_control(
                            "target.resume",
                            {},
                            resume_authorization.action_digest,
                        ),
                        deadline=recovery_deadline,
                    )
                    if resume_outcome.error is not None:
                        restoration_failed = True
                    else:
                        try:
                            resume_response = resume_outcome.value
                            if resume_response != {"state": "running"}:
                                raise _fail(
                                    "PROBE_RESPONSE_INVALID",
                                    "Probe target resume response is invalid",
                                )
                        except _WorkflowFailure:
                            restoration_failed = True
                        else:
                            after_outcome = await call(
                                lambda: client.target_state(),
                                deadline=recovery_deadline,
                            )
                            if after_outcome.error is not None:
                                restoration_failed = True
                            else:
                                try:
                                    after_state = _validate_controlled_state(
                                        after_outcome.value
                                    )
                                except _WorkflowFailure:
                                    restoration_failed = True
                                else:
                                    snapshot["afterState"] = dict(after_state)
                                    if after_state["state"] == "running":
                                        snapshot["resume"] = {
                                            "dispatched": True,
                                            "outcome": "succeeded",
                                        }
                                    else:
                                        restoration_failed = True
                    if restoration_failed and snapshot["resume"]["outcome"] == "unknown":
                        snapshot["resume"] = {
                            "dispatched": True,
                            "outcome": "failed",
                        }
        else:
            restoration_failed = True
            snapshot["resume"] = {"dispatched": False, "outcome": "unknown"}
    else:
        snapshot["resume"] = {"dispatched": False, "outcome": "unknown"}

    if restoration_failed:
        details = dict(initiating.details) if isinstance(initiating.details, Mapping) else {}
        details["controlledSnapshot"] = dict(snapshot)
        details["initiatingCode"] = initiating.code
        return OperationResult.failure(
            operation,
            "HARDWARE_CLEANUP_FAILED",
            "Hardware workflow cleanup failed",
            details,
        )
    if cancelled is not None:
        raise cancelled
    return _controlled_result(initiating, snapshot)


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

    try:
        selection = _seams.svd_select(
            paths.project_root,
            model.target.device,
            (Path(model.debug.svd),),
            readable_regions=_svd_readable_regions_from_model(model),
            svd_device=model.debug.svd_device,
        )
    except asyncio.CancelledError:
        raise
    except Exception as error:
        return _stable_exception_result(operation, error)

    def build(binding: object) -> RegisterReadRequest:
        if type(binding) is DebugFirmwareBinding:
            if type(selection) is not SvdSelection:
                raise SvdError(
                    "SVD_PROVENANCE_MISMATCH",
                    "SVD selection provenance is invalid",
                )
            selection.revalidate(binding, paths.project_root)
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
        if type(typed.halt_for_analysis) is not bool:
            raise _fail("HARDWARE_INPUT_INVALID", "Fault halt selection is invalid")
    except _WorkflowFailure as error:
        return _operation_failure(operation, error)
    if typed.halt_for_analysis:
        worker_config = _seams.worker_config.for_observation()

        async def action(supervisor: object, client: object) -> OperationResult[Any]:
            return await _controlled_fault_action(
                supervisor,
                client,
                typed=typed,
                model=model,
                paths=paths,
                seams=_seams,
                worker_config=worker_config,
            )

        return await _one_shot(
            operation=operation,
            paths=paths,
            probe_id=typed.probe_id,
            level=OperationLevel.CONTROL,
            seams=_seams,
            action=action,
            worker_config=worker_config,
        )
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
