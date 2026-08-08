"""Cancellation-safe, typed observation ownership for the Monitor service."""

from __future__ import annotations

import asyncio
import hashlib
import os
import re
import stat
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Awaitable, Callable

from stm32_toolkit import __version__
from stm32_toolkit.debug import (
    DebugBindingRequest,
    DebugFirmwareBinding,
    DebugReadReport,
    DwarfCatalog,
    RegisterSampleRequest,
    SvdSelection,
    VariableReadRequest,
    bind_debug_firmware,
    read_variables,
    sample_registers,
    select_svd,
)
from stm32_toolkit.paths import WorkspacePaths, require_safe_session_id
from stm32_toolkit.probe import (
    OperationLevel,
    ProbeServiceConfig,
    ProbeServiceSupervisor,
    PyOCDBackend,
)
from stm32_toolkit.probe.client import ProbeClient
from stm32_toolkit.probe.lease import ProbeLeaseManager
from stm32_toolkit.probe.protocol import PROBE_PROTOCOL_VERSION
from stm32_toolkit.project_model import load_project_model
from stm32_toolkit.result import OperationResult

_OPERATION = "stm32_monitor_observation_open"
_REVALIDATE_OPERATION = "stm32_monitor_observation_revalidate"
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)


@dataclass(frozen=True)
class MonitorObservationRequest:
    project_root: Path
    data_root: Path
    session_id: str
    probe_id: str
    expected_build_id: str
    expected_elf_sha256: str


class MonitorObservationError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _supervisor_factory(
    config: ProbeServiceConfig,
    lease_manager: object,
    backend_factory: Callable[[], object],
) -> object:
    return ProbeServiceSupervisor(
        config=config,
        lease_manager=lease_manager,
        backend_factory=backend_factory,
    )


@dataclass(frozen=True)
class MonitorObservationSeams:
    backend_factory: Callable[[], object] = PyOCDBackend
    lease_manager_factory: Callable[[Path], object] = ProbeLeaseManager
    supervisor_factory: Callable[[ProbeServiceConfig, object, Callable[[], object]], object] = _supervisor_factory
    client_factory: Callable[[object], object] = ProbeClient
    bind: Callable[[object, object], Awaitable[OperationResult]] = bind_debug_firmware
    catalog_from_binding: Callable[[object], object] = DwarfCatalog.from_binding
    svd_select: Callable[..., object] = select_svd
    read_variables: Callable[[object, object], Awaitable[OperationResult]] = read_variables
    sample_registers: Callable[[object, object], Awaitable[OperationResult]] = sample_registers


_DEFAULT_SEAMS = MonitorObservationSeams()


@dataclass(frozen=True)
class _OwnedOutcome:
    value: object | None
    error: BaseException | None
    cancellation: asyncio.CancelledError | None


async def _await_owned(task: asyncio.Future) -> _OwnedOutcome:
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
        return _OwnedOutcome(task.result(), None, cancellation)
    except BaseException as error:
        return _OwnedOutcome(None, error, cancellation)


async def _cleanup_resources(client: object | None, supervisor: object | None) -> None:
    failed = False
    fatal: BaseException | None = None
    if client is not None:
        try:
            close = getattr(client, "close")
            await close()
        except asyncio.CancelledError:
            failed = True
        except Exception:
            failed = True
        except BaseException as error:
            failed = True
            fatal = error
    if supervisor is not None:
        try:
            await supervisor.stop()
        except asyncio.CancelledError:
            failed = True
        except Exception:
            failed = True
        except BaseException as error:
            failed = True
            if fatal is None:
                fatal = error
    if fatal is not None:
        raise fatal
    if failed:
        raise MonitorObservationError(
            "MONITOR_CLEANUP_FAILED", "Monitor observation cleanup failed"
        )


def _is_redirect(path: Path, metadata: os.stat_result) -> bool:
    return path.is_symlink() or bool(
        int(getattr(metadata, "st_file_attributes", 0) or 0) & _REPARSE_POINT
    )


def _canonical_root(value: object, *, existing: bool) -> Path:
    if not isinstance(value, Path):
        raise ValueError
    lexical = value.expanduser().absolute()
    current = Path(lexical.anchor)
    for component in lexical.parts[1:] if lexical.anchor else lexical.parts:
        current /= component
        try:
            metadata = os.lstat(current)
        except FileNotFoundError:
            if existing:
                raise ValueError from None
            break
        if _is_redirect(current, metadata) or not stat.S_ISDIR(metadata.st_mode):
            raise ValueError
    canonical = lexical.resolve(strict=existing)
    if existing and (canonical != lexical or not canonical.is_dir()):
        raise ValueError
    return canonical


def _disjoint(project: Path, data: Path) -> None:
    try:
        data.relative_to(project)
    except ValueError:
        pass
    else:
        raise ValueError
    try:
        project.relative_to(data)
    except ValueError:
        return
    raise ValueError


def _safe_mkdir_chain(root: Path, destination: Path) -> None:
    relative = destination.relative_to(root)
    root.mkdir(parents=True, exist_ok=True)
    current = root
    for component in (None, *relative.parts):
        if component is not None:
            current /= component
        try:
            before = os.lstat(current)
        except FileNotFoundError:
            before = None
        if before is not None and (
            _is_redirect(current, before) or not stat.S_ISDIR(before.st_mode)
        ):
            raise ValueError
        current.mkdir(exist_ok=True)
        after = os.lstat(current)
        if _is_redirect(current, after) or not stat.S_ISDIR(after.st_mode):
            raise ValueError
        current.resolve(strict=True).relative_to(root.resolve(strict=True))


def _prepare(request: object) -> tuple[MonitorObservationRequest, object, WorkspacePaths]:
    if type(request) is not MonitorObservationRequest:
        raise ValueError
    project = _canonical_root(request.project_root, existing=True)
    data = _canonical_root(request.data_root, existing=False)
    _disjoint(project, data)
    if (
        _IDENTIFIER.fullmatch(request.probe_id) is None
        or _DIGEST.fullmatch(request.expected_build_id) is None
        or _DIGEST.fullmatch(request.expected_elf_sha256) is None
    ):
        raise ValueError
    session = require_safe_session_id(request.session_id)
    model = load_project_model(project)
    if (
        model.schema_version != 2
        or model.project_root != project
        or model.debug.backend != "pyocd"
        or not isinstance(model.debug.target, str)
        or _IDENTIFIER.fullmatch(model.debug.target) is None
    ):
        raise ValueError
    paths = WorkspacePaths.from_roots(
        data, project, model.logical_project_id, session
    )
    component = "probe-" + hashlib.sha256(request.probe_id.encode("utf-8")).hexdigest()[:24]
    paths = replace(paths, session_root=paths.session_root / "probes" / component)
    return request, model, paths


def _endpoint(endpoint: object, paths: WorkspacePaths, probe_id: str) -> None:
    port = getattr(endpoint, "port", None)
    token = getattr(endpoint, "token", None)
    if (
        getattr(endpoint, "protocol", None) != PROBE_PROTOCOL_VERSION
        or getattr(endpoint, "toolkit_version", None) != __version__
        or getattr(endpoint, "host", None) not in {"127.0.0.1", "::1"}
        or type(port) is not int
        or not 1 <= port <= 65_535
        or not isinstance(token, str)
        or _DIGEST.fullmatch(token) is None
        or getattr(endpoint, "workspace_id", None) != paths.workspace_id
        or getattr(endpoint, "session_id", None) != paths.session_id
        or getattr(endpoint, "probe_id", None) != probe_id
        or getattr(endpoint, "operation_level", None) is not OperationLevel.OBSERVE
        or not isinstance(getattr(endpoint, "lease_id", None), str)
        or _IDENTIFIER.fullmatch(getattr(endpoint, "lease_id", "")) is None
    ):
        raise MonitorObservationError(
            "MONITOR_PROVENANCE_CHANGED", "Monitor observation endpoint changed"
        )


def _failure_code(code: object) -> str:
    if code == "PROBE_BUSY":
        return "MONITOR_PROBE_BUSY"
    if isinstance(code, str) and (
        "FIRMWARE" in code or code in {"DEBUG_PLAN_CHANGED", "DEBUG_TARGET_MISMATCH"}
    ):
        return "MONITOR_FIRMWARE_CHANGED"
    if isinstance(code, str) and (code.startswith("DWARF_") or code.startswith("SVD_")):
        return "MONITOR_PROVENANCE_CHANGED"
    return "MONITOR_PROVENANCE_CHANGED"


def _failure_from_result(result: object) -> OperationResult:
    return OperationResult.failure(
        _OPERATION,
        _failure_code(getattr(result, "code", None)),
        "Monitor observation could not be established",
        {},
    )


def _same_binding(first: DebugFirmwareBinding, current: DebugFirmwareBinding) -> bool:
    left = first.to_dict()
    right = current.to_dict()
    left.pop("confirmedAtUtc", None)
    right.pop("confirmedAtUtc", None)
    return first.project_root == current.project_root and left == right


def _validate_binding(
    binding: object,
    request: MonitorObservationRequest,
    model: object,
    paths: WorkspacePaths,
    endpoint: object,
) -> DebugFirmwareBinding:
    if (
        type(binding) is not DebugFirmwareBinding
        or binding.project_root != paths.project_root
        or binding.workspace_id != paths.workspace_id
        or binding.observation_session_id != paths.session_id
        or binding.lease_id != getattr(endpoint, "lease_id", None)
        or binding.probe_id != request.probe_id
        or binding.debug_target != getattr(getattr(model, "debug", None), "target", None)
        or binding.target_device != getattr(getattr(model, "target", None), "device", None)
        or binding.logical_project_id != str(getattr(model, "logical_project_id", ""))
        or binding.build_id != request.expected_build_id
        or binding.elf_sha256 != request.expected_elf_sha256
    ):
        raise MonitorObservationError(
            "MONITOR_FIRMWARE_CHANGED", "Monitor firmware binding is invalid"
        )
    return binding


class MonitorObservationSession:
    def __init__(
        self,
        *,
        binding: DebugFirmwareBinding,
        catalog: DwarfCatalog,
        svd: SvdSelection | None,
        endpoint: object,
        client: object,
        supervisor: object,
        model: object,
        paths: WorkspacePaths,
        seams: MonitorObservationSeams,
    ) -> None:
        self.binding = binding
        self.catalog = catalog
        self.svd = svd
        self.endpoint = endpoint
        self.client = client
        self._supervisor = supervisor
        self._model = model
        self._paths = paths
        self._seams = seams
        self._close_task: asyncio.Task | None = None

    async def read_variables(
        self, expressions: tuple[str, ...]
    ) -> OperationResult[DebugReadReport]:
        return await self._seams.read_variables(
            VariableReadRequest(self.binding, self.catalog, expressions), self.client
        )

    async def sample_registers(
        self, paths: tuple[str, ...]
    ) -> OperationResult[DebugReadReport]:
        if self.svd is None:
            return OperationResult.failure(
                "stm32_debug_sample_registers",
                "SVD_SELECTION_REQUIRED",
                "An exact project SVD selection is required",
                {},
            )
        return await self._seams.sample_registers(
            RegisterSampleRequest(self.binding, self.svd, paths), self.client
        )

    async def revalidate(self) -> OperationResult[DebugFirmwareBinding]:
        try:
            _endpoint(self.endpoint, self._paths, self.binding.probe_id)
            _endpoint(self.client.endpoint, self._paths, self.binding.probe_id)
            result = await self._seams.bind(
                DebugBindingRequest(
                    self.binding.project_root,
                    self.binding.probe_id,
                    self.binding.debug_target,
                    self.binding.workspace_id,
                    self.binding.observation_session_id,
                    self.binding.lease_id,
                    self.binding.build_id,
                    self.binding.elf_sha256,
                ),
                self.client,
            )
            if not result.ok or type(result.data) is not DebugFirmwareBinding:
                return OperationResult.failure(
                    _REVALIDATE_OPERATION,
                    _failure_code(result.code),
                    "Monitor observation changed",
                    {},
                )
            current = _validate_binding(
                result.data,
                MonitorObservationRequest(
                    self.binding.project_root,
                    self._paths.data_root,
                    self.binding.observation_session_id,
                    self.binding.probe_id,
                    self.binding.build_id,
                    self.binding.elf_sha256,
                ),
                self._model,
                self._paths,
                self.endpoint,
            )
            if not _same_binding(self.binding, current):
                return OperationResult.failure(
                    _REVALIDATE_OPERATION,
                    "MONITOR_FIRMWARE_CHANGED",
                    "Monitor firmware identity changed",
                    {},
                )
            self.catalog.revalidate(current)
            if self.svd is not None:
                self.svd.revalidate(current, current.project_root)
            self.binding = current
            return OperationResult.success(_REVALIDATE_OPERATION, current)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            return OperationResult.failure(
                _REVALIDATE_OPERATION,
                _failure_code(getattr(error, "code", None)),
                "Monitor observation changed",
                {},
            )

    async def close(self) -> None:
        if self._close_task is None:
            self._close_task = asyncio.create_task(
                _cleanup_resources(self.client, self._supervisor)
            )
        outcome = await _await_owned(self._close_task)
        if outcome.error is not None:
            if not isinstance(outcome.error, (Exception, asyncio.CancelledError)):
                raise outcome.error
            raise MonitorObservationError(
                "MONITOR_CLEANUP_FAILED", "Monitor observation cleanup failed"
            )
        if outcome.cancellation is not None:
            raise outcome.cancellation


async def open_monitor_observation(
    request: object,
    *,
    _seams: MonitorObservationSeams = _DEFAULT_SEAMS,
) -> OperationResult[MonitorObservationSession]:
    try:
        typed, model, paths = _prepare(request)
    except Exception:
        return OperationResult.failure(
            _OPERATION,
            "MONITOR_REQUEST_INVALID",
            "Monitor observation request is invalid",
            {},
        )
    supervisor: object | None = None
    client: object | None = None
    cancelled: asyncio.CancelledError | None = None
    failure: OperationResult | None = None
    session: MonitorObservationSession | None = None
    fatal: BaseException | None = None
    try:
        _safe_mkdir_chain(paths.data_root, paths.session_root)
        config = ProbeServiceConfig(
            probe_id=typed.probe_id,
            workspace_id=paths.workspace_id,
            session_id=paths.session_id,
            operation_level=OperationLevel.OBSERVE,
            session_root=paths.session_root,
            project_root=paths.project_root,
        )
        supervisor = _seams.supervisor_factory(
            config,
            _seams.lease_manager_factory(paths.data_root),
            _seams.backend_factory,
        )
        endpoint = await supervisor.start()
        _endpoint(endpoint, paths, typed.probe_id)
        client = _seams.client_factory(endpoint)
        binding_result = await _seams.bind(
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
        if not binding_result.ok or type(binding_result.data) is not DebugFirmwareBinding:
            failure = _failure_from_result(binding_result)
        else:
            binding = _validate_binding(
                binding_result.data, typed, model, paths, endpoint
            )
            catalog = _seams.catalog_from_binding(binding)
            if type(catalog) is not DwarfCatalog:
                raise MonitorObservationError(
                    "MONITOR_PROVENANCE_CHANGED", "DWARF provenance is invalid"
                )
            svd: SvdSelection | None = None
            if model.debug.svd is not None:
                svd = _seams.svd_select(
                    paths.project_root,
                    model.target.device,
                    (Path(model.debug.svd),),
                    readable_regions=binding.memory_regions,
                )
                if type(svd) is not SvdSelection:
                    raise MonitorObservationError(
                        "MONITOR_PROVENANCE_CHANGED", "SVD provenance is invalid"
                    )
            _endpoint(endpoint, paths, typed.probe_id)
            _endpoint(getattr(client, "endpoint", None), paths, typed.probe_id)
            session = MonitorObservationSession(
                binding=binding,
                catalog=catalog,
                svd=svd,
                endpoint=endpoint,
                client=client,
                supervisor=supervisor,
                model=model,
                paths=paths,
                seams=_seams,
            )
    except asyncio.CancelledError as error:
        cancelled = error
    except Exception as error:
        failure = OperationResult.failure(
            _OPERATION,
            _failure_code(getattr(error, "code", None)),
            "Monitor observation could not be established",
            {},
        )
    except BaseException as error:
        fatal = error
    if session is not None:
        return OperationResult.success(_OPERATION, session)
    cleanup = asyncio.create_task(_cleanup_resources(client, supervisor))
    outcome = await _await_owned(cleanup)
    if outcome.error is not None:
        if not isinstance(outcome.error, (Exception, asyncio.CancelledError)):
            raise outcome.error
        return OperationResult.failure(
            _OPERATION,
            "MONITOR_CLEANUP_FAILED",
            "Monitor observation cleanup failed",
            {},
        )
    if fatal is not None:
        raise fatal
    if cancelled is not None:
        raise cancelled
    if outcome.cancellation is not None:
        raise outcome.cancellation
    assert failure is not None
    return failure


__all__ = [
    "MonitorObservationError",
    "MonitorObservationRequest",
    "MonitorObservationSeams",
    "MonitorObservationSession",
    "open_monitor_observation",
]
