"""Private Windows Job ownership for the trusted source compiler adapter.

The compiler starts suspended, is assigned to an unnamed non-inheritable Job,
then its unique initial thread is resumed. Closing the Job kills descendants
even when the driver itself has already exited.
"""

from __future__ import annotations

import ctypes
import threading
from ctypes import wintypes


_KERNEL32 = ctypes.WinDLL("kernel32", use_last_error=True)
_HANDLE = wintypes.HANDLE
_DWORD = wintypes.DWORD
_SIZE_T = ctypes.c_size_t
_KILL_ON_JOB_CLOSE = 0x2000
_EXTENDED_LIMIT_INFORMATION = 9
_SNAP_THREAD = 0x00000004
_INVALID_HANDLE = ctypes.c_void_p(-1).value
_THREAD_SUSPEND_RESUME = 0x0002
_THREAD_QUERY_LIMITED_INFORMATION = 0x0800


class _BasicLimitInformation(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_longlong),
        ("PerJobUserTimeLimit", ctypes.c_longlong),
        ("LimitFlags", _DWORD),
        ("MinimumWorkingSetSize", _SIZE_T),
        ("MaximumWorkingSetSize", _SIZE_T),
        ("ActiveProcessLimit", _DWORD),
        ("Affinity", _SIZE_T),
        ("PriorityClass", _DWORD),
        ("SchedulingClass", _DWORD),
    ]


class _IoCounters(ctypes.Structure):
    _fields_ = [(name, ctypes.c_ulonglong) for name in (
        "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
        "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]


class _ExtendedLimitInformation(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _BasicLimitInformation),
        ("IoInfo", _IoCounters),
        ("ProcessMemoryLimit", _SIZE_T),
        ("JobMemoryLimit", _SIZE_T),
        ("PeakProcessMemoryUsed", _SIZE_T),
        ("PeakJobMemoryUsed", _SIZE_T),
    ]


class _ThreadEntry(ctypes.Structure):
    _fields_ = [
        ("dwSize", _DWORD), ("cntUsage", _DWORD), ("th32ThreadID", _DWORD),
        ("th32OwnerProcessID", _DWORD), ("tpBasePri", wintypes.LONG),
        ("tpDeltaPri", wintypes.LONG), ("dwFlags", _DWORD),
    ]


_CREATE_JOB = _KERNEL32.CreateJobObjectW
_CREATE_JOB.argtypes = (ctypes.c_void_p, wintypes.LPCWSTR)
_CREATE_JOB.restype = _HANDLE
_SET_JOB_INFORMATION = _KERNEL32.SetInformationJobObject
_SET_JOB_INFORMATION.argtypes = (_HANDLE, ctypes.c_int, ctypes.c_void_p, _DWORD)
_SET_JOB_INFORMATION.restype = wintypes.BOOL
_ASSIGN_PROCESS = _KERNEL32.AssignProcessToJobObject
_ASSIGN_PROCESS.argtypes = (_HANDLE, _HANDLE)
_ASSIGN_PROCESS.restype = wintypes.BOOL
_TERMINATE_JOB = _KERNEL32.TerminateJobObject
_TERMINATE_JOB.argtypes = (_HANDLE, ctypes.c_uint)
_TERMINATE_JOB.restype = wintypes.BOOL
_CLOSE_HANDLE = _KERNEL32.CloseHandle
_CLOSE_HANDLE.argtypes = (_HANDLE,)
_CLOSE_HANDLE.restype = wintypes.BOOL
_SNAPSHOT = _KERNEL32.CreateToolhelp32Snapshot
_SNAPSHOT.argtypes = (_DWORD, _DWORD)
_SNAPSHOT.restype = _HANDLE
_THREAD_FIRST = _KERNEL32.Thread32First
_THREAD_FIRST.argtypes = (_HANDLE, ctypes.POINTER(_ThreadEntry))
_THREAD_FIRST.restype = wintypes.BOOL
_THREAD_NEXT = _KERNEL32.Thread32Next
_THREAD_NEXT.argtypes = (_HANDLE, ctypes.POINTER(_ThreadEntry))
_THREAD_NEXT.restype = wintypes.BOOL
_OPEN_THREAD = _KERNEL32.OpenThread
_OPEN_THREAD.argtypes = (_DWORD, wintypes.BOOL, _DWORD)
_OPEN_THREAD.restype = _HANDLE
_GET_THREAD_PROCESS = _KERNEL32.GetProcessIdOfThread
_GET_THREAD_PROCESS.argtypes = (_HANDLE,)
_GET_THREAD_PROCESS.restype = _DWORD
_RESUME_THREAD = _KERNEL32.ResumeThread
_RESUME_THREAD.argtypes = (_HANDLE,)
_RESUME_THREAD.restype = _DWORD


def _native_failure(action: str) -> OSError:
    return OSError(ctypes.get_last_error(), f"Windows source compiler {action} failed")


def _initial_thread(process_id: int) -> int:
    snapshot = _SNAPSHOT(_SNAP_THREAD, 0)
    if snapshot in (None, _INVALID_HANDLE):
        raise _native_failure("thread snapshot")
    try:
        entry = _ThreadEntry()
        entry.dwSize = ctypes.sizeof(_ThreadEntry)
        matches: list[int] = []
        ctypes.set_last_error(0)
        if _THREAD_FIRST(snapshot, ctypes.byref(entry)):
            while True:
                if entry.th32OwnerProcessID == process_id:
                    matches.append(entry.th32ThreadID)
                entry.dwSize = ctypes.sizeof(_ThreadEntry)
                ctypes.set_last_error(0)
                if not _THREAD_NEXT(snapshot, ctypes.byref(entry)):
                    if ctypes.get_last_error() != 18:  # ERROR_NO_MORE_FILES
                        raise _native_failure("enumerate initial thread")
                    break
        elif ctypes.get_last_error() != 18:
            raise _native_failure("enumerate initial thread")
        if len(matches) != 1:
            raise OSError("Windows source compiler initial thread was not unique")
        thread = _OPEN_THREAD(_THREAD_SUSPEND_RESUME | _THREAD_QUERY_LIMITED_INFORMATION,
                              False, matches[0])
        if not thread:
            raise _native_failure("open initial thread")
        if _GET_THREAD_PROCESS(thread) != process_id:
            _CLOSE_HANDLE(thread)
            raise OSError("Windows source compiler initial thread changed owner")
        return thread
    finally:
        _CLOSE_HANDLE(snapshot)


class OwnedWindowsJob:
    """An adapter-owned Job handle, never an inherited or caller-owned handle."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._handle: int | None = _CREATE_JOB(None, None)
        if not self._handle:
            raise _native_failure("create job")
        try:
            limits = _ExtendedLimitInformation()
            limits.BasicLimitInformation.LimitFlags = _KILL_ON_JOB_CLOSE
            if not _SET_JOB_INFORMATION(self._handle, _EXTENDED_LIMIT_INFORMATION,
                                        ctypes.byref(limits), ctypes.sizeof(limits)):
                raise _native_failure("set job limit")
        except BaseException:
            self.close()
            raise

    def assign(self, process_handle: int) -> None:
        with self._lock:
            if self._handle is None or not _ASSIGN_PROCESS(self._handle, process_handle):
                raise _native_failure("assign process")

    @property
    def closed(self) -> bool:
        with self._lock:
            return self._handle is None

    @staticmethod
    def resume_initial_thread(process_id: int) -> None:
        thread = _initial_thread(process_id)
        try:
            if _RESUME_THREAD(thread) != 1:
                raise _native_failure("resume initial thread")
        finally:
            _CLOSE_HANDLE(thread)

    def close(self) -> None:
        with self._lock:
            handle = self._handle
            if handle is not None:
                termination_error = None
                if not _TERMINATE_JOB(handle, 1):
                    termination_error = _native_failure("terminate job")
                if not _CLOSE_HANDLE(handle):
                    raise _native_failure("close job")
                self._handle = None
                if termination_error is not None:
                    raise termination_error
