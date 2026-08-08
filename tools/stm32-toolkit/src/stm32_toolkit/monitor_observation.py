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


async def _cleanup_resources(
    client: object | None,
    supervisor: object | None,
    root_guard: "_DirectoryGuard | None" = None,
) -> None:
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
    if root_guard is not None:
        try:
            root_guard.close()
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


def _windows_directory_handle(path: Path) -> int:
    import ctypes
    from ctypes import wintypes

    class _FileTime(ctypes.Structure):
        _fields_ = (("low", wintypes.DWORD), ("high", wintypes.DWORD))

    class _FileInformation(ctypes.Structure):
        _fields_ = (
            ("attributes", wintypes.DWORD),
            ("creation", _FileTime),
            ("last_access", _FileTime),
            ("last_write", _FileTime),
            ("volume_serial", wintypes.DWORD),
            ("size_high", wintypes.DWORD),
            ("size_low", wintypes.DWORD),
            ("links", wintypes.DWORD),
            ("index_high", wintypes.DWORD),
            ("index_low", wintypes.DWORD),
        )

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = kernel32.CreateFileW
    create_file.argtypes = (
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    )
    create_file.restype = wintypes.HANDLE
    handle = create_file(
        str(path),
        0x0080,  # FILE_READ_ATTRIBUTES
        0x0001 | 0x0002,  # share read/write, intentionally not delete/rename
        None,
        3,  # OPEN_EXISTING
        0x02000000 | 0x00200000,  # BACKUP_SEMANTICS | OPEN_REPARSE_POINT
        None,
    )
    invalid = ctypes.c_void_p(-1).value
    if handle in (None, invalid):
        raise OSError(ctypes.get_last_error(), "directory handle is unavailable")
    get_information = kernel32.GetFileInformationByHandle
    get_information.argtypes = (wintypes.HANDLE, ctypes.POINTER(_FileInformation))
    get_information.restype = wintypes.BOOL
    information = _FileInformation()
    if not get_information(handle, ctypes.byref(information)):
        error = ctypes.get_last_error()
        try:
            _close_windows_handle(int(handle))
        except OSError:
            pass
        raise OSError(error, "directory identity is unavailable")
    if not information.attributes & 0x0010 or information.attributes & _REPARSE_POINT:
        try:
            _close_windows_handle(int(handle))
        except OSError:
            pass
        raise OSError("directory is redirected or invalid")
    return int(handle)


def _close_windows_handle(handle: int) -> None:
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = (wintypes.HANDLE,)
    close_handle.restype = wintypes.BOOL
    if not close_handle(wintypes.HANDLE(handle)):
        raise OSError(ctypes.get_last_error(), "directory handle could not be closed")


def _ancestor_identities(path: Path) -> tuple[tuple[Path, int, int], ...]:
    identities: list[tuple[Path, int, int]] = []
    current = Path(path.anchor)
    components = path.parts[1:] if path.anchor else path.parts
    candidates = (
        current,
        *(
            current.joinpath(*components[:index])
            for index in range(1, len(components) + 1)
        ),
    )
    for candidate in candidates:
        try:
            metadata = os.lstat(candidate)
        except FileNotFoundError:
            break
        if _is_redirect(candidate, metadata) or not stat.S_ISDIR(metadata.st_mode):
            raise ValueError
        identities.append((candidate, int(metadata.st_dev), int(metadata.st_ino)))
    return tuple(identities)


def _verify_ancestor_identities(
    identities: tuple[tuple[Path, int, int], ...]
) -> None:
    for path, device, inode in identities:
        metadata = os.lstat(path)
        if (
            _is_redirect(path, metadata)
            or not stat.S_ISDIR(metadata.st_mode)
            or (int(metadata.st_dev), int(metadata.st_ino)) != (device, inode)
        ):
            raise ValueError


class _DirectoryGuard:
    def __init__(
        self,
        identities: tuple[tuple[Path, int, int], ...],
    ) -> None:
        self._identities = identities
        self._windows_handles: list[int] = []
        self._posix_descriptors: list[int] = []
        try:
            if os.name == "nt":
                for path, _, _ in identities:
                    self._windows_handles.append(_windows_directory_handle(path))
            else:
                flags = (
                    os.O_RDONLY
                    | getattr(os, "O_DIRECTORY", 0)
                    | getattr(os, "O_NOFOLLOW", 0)
                )
                for path, _, _ in identities:
                    self._posix_descriptors.append(os.open(path, flags))
            self.verify()
        except BaseException:
            try:
                self.close()
            except BaseException:
                pass
            raise

    @classmethod
    def capture(cls, destination: Path) -> "_DirectoryGuard":
        identities = _ancestor_identities(destination)
        if not identities or identities[-1][0] != destination:
            raise ValueError
        return cls(identities)

    def verify(self) -> None:
        for index, (path, device, inode) in enumerate(self._identities):
            named = os.lstat(path)
            if (
                _is_redirect(path, named)
                or not stat.S_ISDIR(named.st_mode)
                or (int(named.st_dev), int(named.st_ino)) != (device, inode)
            ):
                raise ValueError
            if self._posix_descriptors:
                descriptor = self._posix_descriptors[index]
                metadata = os.fstat(descriptor)
                if (
                    not stat.S_ISDIR(metadata.st_mode)
                    or (int(metadata.st_dev), int(metadata.st_ino)) != (device, inode)
                ):
                    raise ValueError

    def directory_descriptor(self, path: Path) -> int | None:
        if self._windows_handles:
            try:
                self.verify()
            except (OSError, RuntimeError, ValueError):
                raise MonitorObservationError(
                    "MONITOR_REQUEST_INVALID", "Monitor data root identity changed"
                ) from None
            return None
        for index, (candidate, _, _) in enumerate(self._identities):
            if candidate == path:
                descriptor = self._posix_descriptors[index]
                metadata = os.fstat(descriptor)
                if not stat.S_ISDIR(metadata.st_mode):
                    raise ValueError
                return descriptor
        raise ValueError

    def close(self) -> None:
        error: BaseException | None = None
        while self._posix_descriptors:
            descriptor = self._posix_descriptors.pop()
            try:
                os.close(descriptor)
            except BaseException as caught:
                if error is None:
                    error = caught
        while self._windows_handles:
            handle = self._windows_handles.pop()
            try:
                _close_windows_handle(handle)
            except BaseException as caught:
                if error is None:
                    error = caught
        if error is not None:
            raise error


def _safe_mkdir_windows(
    root: Path,
    destination: Path,
    identities: tuple[tuple[Path, int, int], ...],
) -> _DirectoryGuard:
    relative = destination.relative_to(root)
    target = root.joinpath(*relative.parts)
    anchor = Path(target.anchor)
    expected = {path: (device, inode) for path, device, inode in identities}
    observed: list[tuple[Path, int, int]] = []
    handles: list[int] = []
    guard: _DirectoryGuard | None = None
    error: BaseException | None = None
    current = anchor
    try:
        handles.append(_windows_directory_handle(current))
        anchor_metadata = os.lstat(current)
        if current in expected and (
            int(anchor_metadata.st_dev), int(anchor_metadata.st_ino)
        ) != expected[current]:
            raise ValueError
        observed.append(
            (current, int(anchor_metadata.st_dev), int(anchor_metadata.st_ino))
        )
        components = target.parts[1:] if target.anchor else target.parts
        for component in components:
            current /= component
            if current not in expected:
                try:
                    current.mkdir()
                except FileExistsError:
                    pass
            handles.append(_windows_directory_handle(current))
            metadata = os.lstat(current)
            if current in expected and (
                int(metadata.st_dev), int(metadata.st_ino)
            ) != expected[current]:
                raise ValueError
            observed.append((current, int(metadata.st_dev), int(metadata.st_ino)))
        if target != destination:
            raise ValueError
        guard = _DirectoryGuard(tuple(observed))
    except BaseException as caught:
        error = caught
    close_error: BaseException | None = None
    for handle in reversed(handles):
        try:
            _close_windows_handle(handle)
        except BaseException as caught:
            if close_error is None:
                close_error = caught
    if error is not None:
        raise error
    if close_error is not None:
        assert guard is not None
        try:
            guard.close()
        except BaseException:
            pass
        raise close_error
    assert guard is not None
    return guard


def _safe_mkdir_posix(
    root: Path,
    destination: Path,
    identities: tuple[tuple[Path, int, int], ...] = (),
    *,
    capture_guard: bool = False,
) -> _DirectoryGuard | None:
    relative = destination.relative_to(root)
    target = root.joinpath(*relative.parts)
    anchor = Path(target.anchor or ".")
    expected = {path: (device, inode) for path, device, inode in identities}
    observed: list[tuple[Path, int, int]] = []
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(anchor, flags)
    descriptors = [descriptor]
    guard: _DirectoryGuard | None = None
    error: BaseException | None = None
    try:
        anchor_metadata = os.fstat(descriptor)
        if anchor in expected and (
            int(anchor_metadata.st_dev), int(anchor_metadata.st_ino)
        ) != expected[anchor]:
            raise ValueError
        observed.append(
            (anchor, int(anchor_metadata.st_dev), int(anchor_metadata.st_ino))
        )
        current = anchor
        components = target.parts[1:] if target.anchor else target.parts
        for component in components:
            current /= component
            if current not in expected:
                try:
                    os.mkdir(component, dir_fd=descriptor)
                except FileExistsError:
                    pass
            next_descriptor = os.open(component, flags, dir_fd=descriptor)
            descriptors.append(next_descriptor)
            metadata = os.fstat(next_descriptor)
            if not stat.S_ISDIR(metadata.st_mode) or (
                current in expected
                and (int(metadata.st_dev), int(metadata.st_ino)) != expected[current]
            ):
                raise ValueError
            observed.append((current, int(metadata.st_dev), int(metadata.st_ino)))
            descriptor = next_descriptor
        if capture_guard:
            guard = _DirectoryGuard(tuple(observed))
    except BaseException as caught:
        error = caught
    close_error: BaseException | None = None
    for owned_descriptor in reversed(descriptors):
        try:
            os.close(owned_descriptor)
        except BaseException as caught:
            if close_error is None:
                close_error = caught
    if error is not None:
        raise error
    if close_error is not None:
        if guard is not None:
            try:
                guard.close()
            except BaseException:
                pass
        raise close_error
    return guard


def _safe_mkdir_chain(
    root: Path,
    destination: Path,
    identities: tuple[tuple[Path, int, int], ...] = (),
) -> _DirectoryGuard:
    _verify_ancestor_identities(identities)
    if os.name == "nt":
        return _safe_mkdir_windows(root, destination, identities)
    guard = _safe_mkdir_posix(
        root, destination, identities, capture_guard=True
    )
    assert guard is not None
    return guard


def _prepare(
    request: object,
) -> tuple[
    MonitorObservationRequest,
    object,
    WorkspacePaths,
    tuple[tuple[Path, int, int], ...],
]:
    if type(request) is not MonitorObservationRequest:
        raise ValueError
    project = _canonical_root(request.project_root, existing=True)
    data = _canonical_root(request.data_root, existing=False)
    data_identities = _ancestor_identities(data)
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
    return request, model, paths, data_identities


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
    if code in {"MONITOR_REQUEST_INVALID", "MONITOR_CLEANUP_FAILED"}:
        return code
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


def _verify_root_guard(root_guard: _DirectoryGuard) -> None:
    try:
        root_guard.verify()
    except (OSError, RuntimeError, ValueError):
        raise MonitorObservationError(
            "MONITOR_REQUEST_INVALID", "Monitor data root identity changed"
        ) from None


def _guard_backend_factory(
    root_guard: _DirectoryGuard,
    backend_factory: Callable[[], object],
) -> Callable[[], object]:
    def guarded() -> object:
        _verify_root_guard(root_guard)
        try:
            backend = backend_factory()
        except BaseException:
            _verify_root_guard(root_guard)
            raise
        try:
            _verify_root_guard(root_guard)
        except BaseException as error:
            try:
                getattr(backend, "close")()
            except BaseException:
                raise MonitorObservationError(
                    "MONITOR_CLEANUP_FAILED",
                    "Monitor observation cleanup failed",
                ) from None
            raise error
        return backend

    return guarded


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
        root_guard: _DirectoryGuard,
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
        self._root_guard = root_guard
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
            _verify_root_guard(self._root_guard)
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
                _cleanup_resources(
                    self.client, self._supervisor, self._root_guard
                )
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
        typed, model, paths, data_identities = _prepare(request)
    except Exception:
        return OperationResult.failure(
            _OPERATION,
            "MONITOR_REQUEST_INVALID",
            "Monitor observation request is invalid",
            {},
        )
    supervisor: object | None = None
    client: object | None = None
    root_guard: _DirectoryGuard | None = None
    cancelled: asyncio.CancelledError | None = None
    failure: OperationResult | None = None
    session: MonitorObservationSession | None = None
    fatal: BaseException | None = None
    try:
        try:
            root_guard = _safe_mkdir_chain(
                paths.data_root,
                paths.session_root,
                data_identities,
            )
        except (OSError, RuntimeError, ValueError):
            raise MonitorObservationError(
                "MONITOR_REQUEST_INVALID",
                "Monitor observation runtime root is invalid",
            ) from None
        _verify_root_guard(root_guard)
        config = ProbeServiceConfig(
            probe_id=typed.probe_id,
            workspace_id=paths.workspace_id,
            session_id=paths.session_id,
            operation_level=OperationLevel.OBSERVE,
            session_root=paths.session_root,
            project_root=paths.project_root,
            _runtime_root_authority=root_guard,
        )
        lease_manager = _seams.lease_manager_factory(paths.data_root)
        _verify_root_guard(root_guard)
        supervisor = _seams.supervisor_factory(
            config,
            lease_manager,
            _guard_backend_factory(root_guard, _seams.backend_factory),
        )
        _verify_root_guard(root_guard)
        endpoint = await supervisor.start()
        _verify_root_guard(root_guard)
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
                root_guard=root_guard,
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
    cleanup = asyncio.create_task(
        _cleanup_resources(client, supervisor, root_guard)
    )
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
