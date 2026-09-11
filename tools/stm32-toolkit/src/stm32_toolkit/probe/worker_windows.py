"""Bounded Windows stdio launcher for the probe worker.

The worker is started by a private ``multiprocessing`` spawn subclass because
CPython's Windows spawn launcher does not expose its child ``STARTUPINFO``.
Only the worker's private ``CreateProcess`` call is adapted; the stdlib
function and ``_winapi`` module remain untouched.
"""

from __future__ import annotations

import multiprocessing.popen_spawn_win32 as _spawn_win32
from multiprocessing.context import SpawnProcess as _SpawnProcess
import os
import subprocess
import sys
import types
from typing import Any


_ORIGINAL_POPEN_INIT = _spawn_win32.Popen.__init__
_ORIGINAL_WINAPI = _ORIGINAL_POPEN_INIT.__globals__.get("_winapi")
_GENERIC_READ = 0x80000000
_GENERIC_WRITE = 0x40000000
_FILE_SHARE_READ = 0x00000001
_FILE_SHARE_WRITE = 0x00000002
_OPEN_EXISTING = 3
_FILE_ATTRIBUTE_NORMAL = 0x00000080
_TERMINATE = 0x10000


def _unsupported_runtime() -> RuntimeError:
    return RuntimeError("unsupported CPython spawn runtime")


def _validate_private_runtime() -> None:
    """Reject an unrecognised private spawn implementation before launch."""
    if (
        sys.platform != "win32"
        or sys.implementation.name != "cpython"
        or tuple(sys.version_info[:2]) != (3, 12)
        or _ORIGINAL_WINAPI is None
    ):
        raise _unsupported_runtime()

    popen_type = getattr(_spawn_win32, "Popen", None)
    initializer = getattr(popen_type, "__init__", None)
    if (
        popen_type is not _spawn_win32.Popen
        or initializer is not _ORIGINAL_POPEN_INIT
        or not isinstance(initializer, types.FunctionType)
        or initializer.__module__ != _spawn_win32.__name__
    ):
        raise _unsupported_runtime()

    code = initializer.__code__
    required_names = {
        "get_preparation_data",
        "CreatePipe",
        "get_command_line",
        "get_executable",
        "CreateProcess",
        "CloseHandle",
        "set_spawning_popen",
        "dump",
        "Finalize",
    }
    if (
        code.co_argcount != 2
        or code.co_kwonlyargcount != 0
        or code.co_flags & 0x0C
        or tuple(code.co_varnames[:2]) != ("self", "process_obj")
        or not required_names.issubset(code.co_names)
        or initializer.__globals__.get("_winapi") is not _ORIGINAL_WINAPI
    ):
        raise _unsupported_runtime()


def _close_owned_handles(winapi: Any, handles: tuple[int, ...]) -> BaseException | None:
    first_error: BaseException | None = None
    for handle in handles:
        try:
            winapi.CloseHandle(handle)
        except BaseException as error:  # pragma: no cover - native close failure
            if first_error is None:
                first_error = error
    return first_error


def _open_null_stdio_handles(winapi: Any) -> tuple[int, ...]:
    handles: list[int] = []
    try:
        for access in (_GENERIC_READ, _GENERIC_WRITE, _GENERIC_WRITE):
            handle = winapi.CreateFile(
                r"\\.\NUL",
                access,
                _FILE_SHARE_READ | _FILE_SHARE_WRITE,
                0,
                _OPEN_EXISTING,
                _FILE_ATTRIBUTE_NORMAL,
                0,
            )
            if not isinstance(handle, int) or handle < 0:
                raise OSError("invalid NUL standard handle")
            handles.append(handle)
            os.set_handle_inheritable(handle, True)
    except BaseException as error:
        close_error = _close_owned_handles(winapi, tuple(handles))
        if close_error is not None:
            error.add_note("closing an owned NUL handle failed")
        raise
    return tuple(handles)


def _dispose_created_process(winapi: Any, result: tuple[int, int, int, int]) -> None:
    process_handle, thread_handle, *_ = result
    try:
        winapi.TerminateProcess(int(process_handle), _TERMINATE)
    except BaseException:  # pragma: no cover - native cleanup fallback
        pass
    try:
        winapi.WaitForSingleObject(int(process_handle), 1000)
    except BaseException:  # pragma: no cover - native cleanup fallback
        pass
    for handle in (thread_handle, process_handle):
        try:
            winapi.CloseHandle(handle)
        except BaseException:  # pragma: no cover - native cleanup fallback
            pass


def _create_process_with_null_stdio(
    winapi: Any,
    application_name: Any,
    command_line: Any,
    process_attributes: Any,
    thread_attributes: Any,
    _inherit_handles: Any,
    creation_flags: Any,
    environment: Any,
    current_directory: Any,
    _startup_info: Any,
) -> tuple[int, int, int, int]:
    handles = _open_null_stdio_handles(winapi)
    created: tuple[int, int, int, int] | None = None
    creation_error: BaseException | None = None
    try:
        startup_info = subprocess.STARTUPINFO(
            dwFlags=subprocess.STARTF_USESTDHANDLES,
            hStdInput=handles[0],
            hStdOutput=handles[1],
            hStdError=handles[2],
            lpAttributeList={"handle_list": list(handles)},
        )
        created = winapi.CreateProcess(
            application_name,
            command_line,
            process_attributes,
            thread_attributes,
            True,
            int(creation_flags) | int(winapi.CREATE_NO_WINDOW),
            environment,
            current_directory,
            startup_info,
        )
    except BaseException as error:
        creation_error = error

    close_error = _close_owned_handles(winapi, handles)
    if creation_error is not None:
        if close_error is not None:
            creation_error.add_note("closing an owned NUL handle failed")
        raise creation_error
    if close_error is not None:
        if created is not None:
            _dispose_created_process(winapi, created)
        raise close_error
    if created is None:
        raise RuntimeError("CreateProcess returned no process")
    return created


class _NarrowWinApiProxy:
    """Delegate CPython's private API while replacing only CreateProcess."""

    def __init__(self, original: Any) -> None:
        self._original = original

    def CreateProcess(self, *args: Any) -> tuple[int, int, int, int]:
        return _create_process_with_null_stdio(self._original, *args)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._original, name)


def _make_isolated_popen_init() -> types.FunctionType:
    source = _ORIGINAL_POPEN_INIT
    isolated_globals = dict(source.__globals__)
    isolated_globals["_winapi"] = _NarrowWinApiProxy(_ORIGINAL_WINAPI)
    return types.FunctionType(
        source.__code__,
        isolated_globals,
        source.__name__,
        source.__defaults__,
        source.__closure__,
    )


_PopenInit = _make_isolated_popen_init()


class _WorkerWindowsPopen(_spawn_win32.Popen):
    def __init__(self, process_obj: Any) -> None:
        _validate_private_runtime()
        _PopenInit(self, process_obj)


class WorkerWindowsSpawnProcess(_SpawnProcess):
    """Pickleable spawn process type used only by ProbeBackendWorker."""

    @staticmethod
    def _Popen(process_obj: Any) -> _WorkerWindowsPopen:
        return _WorkerWindowsPopen(process_obj)


__all__ = ["WorkerWindowsSpawnProcess"]
