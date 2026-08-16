"""Handle-bound external result creation and authoritative evidence ingestion."""

from __future__ import annotations

import os
from pathlib import Path
import stat
import tempfile

from stm32_toolkit.evidence import ArtifactRef
from stm32_toolkit.evidence.store import EvidenceStore

from .model import MAX_RUN_STREAM_BYTES, protocol_error


_IS_WINDOWS = os.name == "nt"


def _unsafe(message: str, error: BaseException | None = None):
    failure = protocol_error("TEST_RESULTS_UNSAFE", message)
    if error is None:
        raise failure
    raise failure from error


if _IS_WINDOWS:  # pragma: no branch - the Windows acceptance owner exercises this branch
    import ctypes
    import msvcrt
    from ctypes import wintypes

    _GENERIC_READ = 0x80000000
    _GENERIC_WRITE = 0x40000000
    _FILE_SHARE_READ = 0x1
    _FILE_SHARE_WRITE = 0x2
    _CREATE_NEW = 1
    _OPEN_EXISTING = 3
    _FILE_ATTRIBUTE_NORMAL = 0x80
    _FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
    _FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000
    _FILE_ATTRIBUTE_DIRECTORY = 0x10
    _FILE_ATTRIBUTE_REPARSE_POINT = 0x400
    _DUPLICATE_SAME_ACCESS = 0x2
    _INVALID_HANDLE = ctypes.c_void_p(-1).value

    class _ByHandleInfo(ctypes.Structure):
        _fields_ = [
            ("dwFileAttributes", wintypes.DWORD),
            ("ftCreationTime", wintypes.FILETIME),
            ("ftLastAccessTime", wintypes.FILETIME),
            ("ftLastWriteTime", wintypes.FILETIME),
            ("dwVolumeSerialNumber", wintypes.DWORD),
            ("nFileSizeHigh", wintypes.DWORD),
            ("nFileSizeLow", wintypes.DWORD),
            ("nNumberOfLinks", wintypes.DWORD),
            ("nFileIndexHigh", wintypes.DWORD),
            ("nFileIndexLow", wintypes.DWORD),
        ]

    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _kernel32.CreateFileW.argtypes = (
        wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
        wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
    )
    _kernel32.CreateFileW.restype = wintypes.HANDLE
    _kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    _kernel32.DuplicateHandle.argtypes = (
        wintypes.HANDLE, wintypes.HANDLE, wintypes.HANDLE, ctypes.POINTER(wintypes.HANDLE),
        wintypes.DWORD, wintypes.BOOL, wintypes.DWORD,
    )
    _kernel32.DuplicateHandle.restype = wintypes.BOOL
    _kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    _kernel32.CloseHandle.restype = wintypes.BOOL
    _kernel32.GetFileInformationByHandle.argtypes = (wintypes.HANDLE, ctypes.POINTER(_ByHandleInfo))
    _kernel32.GetFileInformationByHandle.restype = wintypes.BOOL
    _kernel32.GetFinalPathNameByHandleW.argtypes = (
        wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD,
    )
    _kernel32.GetFinalPathNameByHandleW.restype = wintypes.DWORD


def _windows_info(handle: int):  # pragma: no cover - covered on Windows
    info = _ByHandleInfo()
    if not _kernel32.GetFileInformationByHandle(handle, ctypes.byref(info)):
        raise ctypes.WinError(ctypes.get_last_error())
    identity = (
        info.dwVolumeSerialNumber,
        (info.nFileIndexHigh << 32) | info.nFileIndexLow,
    )
    size = (info.nFileSizeHigh << 32) | info.nFileSizeLow
    return info.dwFileAttributes, identity, size


def _windows_final_path(handle: int) -> Path:  # pragma: no cover - covered on Windows
    size = _kernel32.GetFinalPathNameByHandleW(handle, None, 0, 0)
    if not size:
        raise ctypes.WinError(ctypes.get_last_error())
    buffer = ctypes.create_unicode_buffer(size + 1)
    written = _kernel32.GetFinalPathNameByHandleW(handle, buffer, len(buffer), 0)
    if not written or written >= len(buffer):
        raise ctypes.WinError(ctypes.get_last_error())
    value = buffer.value
    if value.startswith("\\\\?\\UNC\\"):
        value = "\\\\" + value[8:]
    elif value.startswith("\\\\?\\"):
        value = value[4:]
    return Path(value)


def _open_windows(path: Path, *, directory: bool, create: bool, write: bool = False) -> int:
    access = _GENERIC_READ | (_GENERIC_WRITE if write else 0)
    flags = _FILE_FLAG_OPEN_REPARSE_POINT | (
        _FILE_FLAG_BACKUP_SEMANTICS if directory else _FILE_ATTRIBUTE_NORMAL
    )
    handle = _kernel32.CreateFileW(
        str(path), access, _FILE_SHARE_READ | _FILE_SHARE_WRITE, None,
        _CREATE_NEW if create else _OPEN_EXISTING, flags, None,
    )
    if handle == _INVALID_HANDLE:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        attributes, _identity, _size = _windows_info(handle)
        is_directory = bool(attributes & _FILE_ATTRIBUTE_DIRECTORY)
        if is_directory != directory or attributes & _FILE_ATTRIBUTE_REPARSE_POINT:
            raise OSError("opened result path has an unsafe file type")
        if os.path.normcase(str(_windows_final_path(handle))) != os.path.normcase(str(path.absolute())):
            raise OSError("opened result final path differs from its lexical path")
        return int(handle)
    except BaseException:
        _kernel32.CloseHandle(handle)
        raise


def _duplicate_descriptor(handle: int, *, write: bool) -> int:
    if not _IS_WINDOWS:  # pragma: no cover - exercised by the Linux acceptance owner
        return os.dup(handle)  # pragma: no cover
    duplicate = wintypes.HANDLE()
    process = _kernel32.GetCurrentProcess()
    if not _kernel32.DuplicateHandle(
        process, handle, process, ctypes.byref(duplicate), 0, False, _DUPLICATE_SAME_ACCESS
    ):
        raise ctypes.WinError(ctypes.get_last_error())
    flags = os.O_BINARY | (os.O_RDWR if write else os.O_RDONLY)
    try:
        return msvcrt.open_osfhandle(duplicate.value, flags)
    except BaseException:
        _kernel32.CloseHandle(duplicate)
        raise


def _close_handle(handle: int) -> None:
    if _IS_WINDOWS:
        _kernel32.CloseHandle(handle)
    else:  # pragma: no cover - exercised by the Linux acceptance owner
        os.close(handle)


def _handle_identity(handle: int) -> tuple[int, int, int]:
    if _IS_WINDOWS:
        _attributes, identity, size = _windows_info(handle)
        return identity[0], identity[1], size
    info = os.fstat(handle)  # pragma: no cover - exercised by the Linux acceptance owner
    return info.st_dev, info.st_ino, info.st_size  # pragma: no cover


def _path_identity(path: Path, *, directory: bool) -> tuple[int, int, int]:
    if _IS_WINDOWS:
        handle = _open_windows(path, directory=directory, create=False)
    else:  # pragma: no cover - exercised by the Linux acceptance owner
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        if directory:
            flags |= os.O_DIRECTORY
        handle = os.open(path, flags)
    try:
        return _handle_identity(handle)
    finally:
        _close_handle(handle)


class TestArtifactCollector:
    """Preserve native bytes outside the workspace under pinned directory handles."""

    def __init__(
        self,
        results_root: Path,
        evidence_store: EvidenceStore,
        *,
        project_root: Path,
    ) -> None:
        if not isinstance(results_root, Path) or not isinstance(project_root, Path):
            raise TypeError("results_root and project_root must be Paths")
        if not isinstance(evidence_store, EvidenceStore):
            raise TypeError("evidence_store must be an EvidenceStore")
        self.results_root = results_root.absolute()
        self.project_root = project_root.resolve(strict=True)
        if self.results_root.parent == self.results_root:
            _unsafe("test results root cannot be a filesystem root")
        if self.results_root == self.project_root or self.project_root in self.results_root.parents:
            _unsafe("test results root must be outside the workspace")
        try:
            parent_handle = self._open_directory(self.results_root.parent)
        except OSError as exc:
            _unsafe("test results parent is not a regular non-reparse directory", exc)
        try:
            try:
                os.mkdir(self.results_root)
            except FileExistsError:
                pass
            self._root_handle = self._open_directory(self.results_root)
        except OSError as exc:
            _unsafe("test results root is not a regular non-reparse directory", exc)
        finally:
            _close_handle(parent_handle)
        resolved_results = self.results_root.resolve(strict=True)
        if resolved_results != self.results_root or (
            resolved_results == self.project_root or self.project_root in resolved_results.parents
        ):
            _close_handle(self._root_handle)
            self._root_handle = None
            _unsafe("test results root must be a direct external directory")
        self._root_identity = _handle_identity(self._root_handle)
        self._directories: dict[Path, tuple[int, tuple[int, int, int]]] = {}
        self.evidence_store = evidence_store

    @staticmethod
    def _open_directory(path: Path) -> int:
        if _IS_WINDOWS:
            return _open_windows(path, directory=True, create=False)
        flags = os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0)  # pragma: no cover
        descriptor = os.open(path, flags)  # pragma: no cover
        if not stat.S_ISDIR(os.fstat(descriptor).st_mode):  # pragma: no cover
            os.close(descriptor)  # pragma: no cover
            raise OSError("result path is not a directory")  # pragma: no cover
        return descriptor  # pragma: no cover

    def _directory(self, directory: Path) -> tuple[int, tuple[int, int, int]]:
        if not isinstance(directory, Path) or directory.parent != self.results_root:
            _unsafe("result directory is not collector-owned")
        registered = self._directories.get(directory)
        if registered is None:
            _unsafe("result directory is not collector-owned")
        handle, identity = registered
        try:
            current = os.lstat(directory)
        except OSError as exc:
            _unsafe("result directory is missing", exc)
        if not stat.S_ISDIR(current.st_mode) or (
            getattr(current, "st_file_attributes", 0) & 0x400
        ):
            _unsafe("result directory is not a regular directory")
        try:
            current_identity = _path_identity(directory, directory=True)
        except OSError as exc:
            _unsafe("result directory identity could not be verified", exc)
        if current_identity[:2] != identity[:2] or _handle_identity(handle)[:2] != identity[:2]:
            _unsafe("result directory identity changed")
        return registered

    def new_directory(self, prefix: str) -> Path:
        if not prefix or any(character not in "abcdefghijklmnopqrstuvwxyz0123456789-" for character in prefix):
            _unsafe("result directory prefix is invalid")
        try:
            directory = Path(tempfile.mkdtemp(prefix=f"{prefix}-", dir=self.results_root))
            handle = self._open_directory(directory)
        except OSError as exc:
            _unsafe("result directory could not be created safely", exc)
        identity = _handle_identity(handle)
        self._directories[directory] = (handle, identity)
        return directory

    def output_path(self, directory: Path, name: str) -> Path:
        self._directory(directory)
        if not isinstance(name, str) or not name or Path(name).name != name or "/" in name or "\\" in name:
            _unsafe("result filename is invalid")
        result = directory / name
        if result.exists() or result.is_symlink():
            _unsafe("result path already exists")
        return result

    def _open_child(self, directory: Path, name: str, *, create: bool, write: bool) -> tuple[Path, int]:
        directory_handle, _identity = self._directory(directory)
        path = self.output_path(directory, name) if create else directory / name
        try:
            if _IS_WINDOWS:
                handle = _open_windows(path, directory=False, create=create, write=write)
            else:  # pragma: no cover - exercised by the Linux acceptance owner
                flags = (os.O_RDWR if write else os.O_RDONLY) | getattr(os, "O_NOFOLLOW", 0)
                if create:
                    flags |= os.O_CREAT | os.O_EXCL
                handle = os.open(name, flags, 0o600, dir_fd=directory_handle)
                if not stat.S_ISREG(os.fstat(handle).st_mode):
                    raise OSError("native result is not a regular file")
            return path, handle
        except OSError as exc:
            _unsafe("native result child could not be opened safely", exc)

    def _ingest_pinned(
        self, path: Path, handle: int, *, kind: str, media_type: str, stream_limit: bool
    ) -> ArtifactRef:
        before = _handle_identity(handle)
        if stream_limit and before[2] > MAX_RUN_STREAM_BYTES:
            raise protocol_error("TEST_STREAM_TOO_LARGE", "raw event stream exceeds 64 MiB")
        try:
            current = _path_identity(path, directory=False)
            if current[:2] != before[:2]:
                _unsafe("native result identity differs from its pinned handle")
            artifact = self.evidence_store.ingest_file(path, kind=kind, media_type=media_type)
            after = _path_identity(path, directory=False)
            if (
                after[:2] != before[:2]
                or _handle_identity(handle) != before
            ):
                _unsafe("native result changed while it was ingested")
            return artifact
        except (OSError, ValueError) as exc:
            _unsafe("native result changed while it was ingested", exc)

    def write_and_ingest(
        self,
        directory: Path,
        name: str,
        data: bytes,
        *,
        kind: str,
        media_type: str,
    ) -> ArtifactRef:
        if not isinstance(data, bytes):
            raise TypeError("artifact data must be bytes")
        path, handle = self._open_child(directory, name, create=True, write=True)
        try:
            descriptor = _duplicate_descriptor(handle, write=True)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            return self._ingest_pinned(
                path, handle, kind=kind, media_type=media_type, stream_limit=False
            )
        except (OSError, ValueError) as exc:
            _unsafe("native result could not be written safely", exc)
        finally:
            _close_handle(handle)

    def ingest_existing(
        self,
        path: Path,
        *,
        kind: str,
        media_type: str,
        stream_limit: bool = False,
    ) -> ArtifactRef:
        if not isinstance(path, Path) or path.parent.parent != self.results_root:
            _unsafe("native result is not collector-owned")
        directory = path.parent
        self._directory(directory)
        try:
            path, handle = self._open_child(directory, path.name, create=False, write=False)
        except Exception as exc:
            raise protocol_error("TEST_NATIVE_RESULT_INVALID", "native result is missing") from exc
        try:
            return self._ingest_pinned(
                path, handle, kind=kind, media_type=media_type, stream_limit=stream_limit
            )
        finally:
            _close_handle(handle)

    def __del__(self) -> None:
        for handle, _identity in getattr(self, "_directories", {}).values():
            _close_handle(handle)
        root = getattr(self, "_root_handle", None)
        if isinstance(root, int):
            _close_handle(root)
