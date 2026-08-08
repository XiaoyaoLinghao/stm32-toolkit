from __future__ import annotations

import os
import sqlite3
import stat
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, TypeVar

from stm32_toolkit.paths import WorkspacePaths


APPLICATION_ID = 0x53544D4D
SCHEMA_VERSION = 1
BUSY_TIMEOUT_MS = 250
MAX_DATABASE_BYTES = 512 * 1024 * 1024
_T = TypeVar("_T")

_SCHEMA_STATEMENTS = (
    """CREATE TABLE monitor_metadata (
        singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
        workspace_id TEXT NOT NULL,
        schema_version INTEGER NOT NULL
    )""",
    """CREATE TABLE watch_groups (
        group_id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        name_key TEXT NOT NULL UNIQUE,
        description TEXT NOT NULL,
        interval_ms INTEGER NOT NULL,
        revision INTEGER NOT NULL,
        created_at_utc TEXT NOT NULL,
        updated_at_utc TEXT NOT NULL
    )""",
    """CREATE TABLE group_items (
        group_id TEXT NOT NULL REFERENCES watch_groups(group_id) ON DELETE CASCADE,
        ordinal INTEGER NOT NULL,
        kind TEXT NOT NULL,
        selector TEXT NOT NULL,
        PRIMARY KEY (group_id, ordinal),
        UNIQUE (group_id, kind, selector)
    )""",
    """CREATE TABLE history_batches (
        batch_id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT NOT NULL,
        run_id TEXT NOT NULL,
        sequence INTEGER NOT NULL,
        captured_ns INTEGER NOT NULL,
        payload_json BLOB NOT NULL,
        payload_bytes INTEGER NOT NULL,
        UNIQUE (run_id, sequence)
    )""",
    "CREATE INDEX history_session_time ON history_batches(session_id, captured_ns, batch_id)",
    """CREATE TABLE history_values (
        batch_id INTEGER NOT NULL REFERENCES history_batches(batch_id) ON DELETE CASCADE,
        ordinal INTEGER NOT NULL,
        row_json BLOB NOT NULL,
        payload_bytes INTEGER NOT NULL,
        PRIMARY KEY (batch_id, ordinal)
    )""",
    """CREATE TABLE export_records (
        export_id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        format TEXT NOT NULL,
        relative_data_path TEXT NOT NULL,
        relative_manifest_path TEXT NOT NULL,
        sha256 TEXT NOT NULL,
        byte_count INTEGER NOT NULL,
        value_count INTEGER NOT NULL,
        created_at_utc TEXT NOT NULL
    )""",
)


@dataclass
class _WriterState:
    executor: ThreadPoolExecutor
    slots: threading.BoundedSemaphore
    references: int


_WRITER_REGISTRY_LOCK = threading.Lock()
_WRITERS: dict[str, _WriterState] = {}


class StorageFailure(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.public_message = message


def _is_redirect(path: Path) -> bool:
    metadata = os.lstat(path)
    attributes = getattr(metadata, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return stat.S_ISLNK(metadata.st_mode) or bool(attributes & reparse_flag)


def _identity(path: Path) -> tuple[int, int, int]:
    metadata = os.lstat(path)
    if _is_redirect(path) or not stat.S_ISREG(metadata.st_mode):
        raise StorageFailure("MONITOR_STORAGE_INVALID", "monitor storage is not a regular file")
    return metadata.st_dev, metadata.st_ino, metadata.st_size


class MonitorDatabase:
    """Workspace-bound SQLite access with one bounded mutation worker."""

    def __init__(self, paths: WorkspacePaths) -> None:
        if not isinstance(paths, WorkspacePaths):
            raise TypeError("paths must be WorkspacePaths")
        self.paths = paths
        self.path = paths.monitor_root / "monitor.sqlite3"
        self._closed = False
        self._close_lock = threading.Lock()
        self._writer_key = str(self.path).casefold()
        with _WRITER_REGISTRY_LOCK:
            writer = _WRITERS.get(self._writer_key)
            if writer is None:
                writer = _WriterState(
                    ThreadPoolExecutor(max_workers=1, thread_name_prefix="stm32-monitor-storage"),
                    threading.BoundedSemaphore(128),
                    0,
                )
                _WRITERS[self._writer_key] = writer
            writer.references += 1
            self._writer = writer

    def _require_path(self, path: Path) -> None:
        try:
            self.paths.data_root.relative_to(self.paths.project_root)
        except ValueError:
            pass
        else:
            raise StorageFailure("MONITOR_STORAGE_INVALID", "monitor state root must remain outside the project")
        resolved = path.resolve(strict=False)
        try:
            resolved.relative_to(self.paths.data_root)
            resolved.relative_to(self.paths.workspace_root)
        except ValueError as error:
            raise StorageFailure("MONITOR_STORAGE_INVALID", "monitor storage escaped its workspace") from error

        current = self.paths.data_root
        relative = path.relative_to(self.paths.data_root)
        for part in (None, *relative.parts):
            if part is not None:
                current /= part
            try:
                if _is_redirect(current):
                    raise StorageFailure("MONITOR_STORAGE_INVALID", "monitor storage contains a redirect")
            except FileNotFoundError:
                continue
            except OSError as error:
                raise StorageFailure("MONITOR_STORAGE_INVALID", "monitor storage path cannot be inspected") from error

    def _ensure_parent(self) -> None:
        self._require_path(self.paths.monitor_root)
        try:
            self.paths.monitor_root.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            raise StorageFailure("MONITOR_STORAGE_INVALID", "monitor storage directory cannot be created") from error
        self._require_path(self.paths.monitor_root)

    def _size(self) -> int:
        total = 0
        for suffix in ("", "-wal"):
            try:
                total += self.path.with_name(self.path.name + suffix).stat().st_size
            except FileNotFoundError:
                pass
            except OSError as error:
                raise StorageFailure("MONITOR_STORAGE_INVALID", "monitor storage size cannot be inspected") from error
        return total

    @staticmethod
    def _configure(connection: sqlite3.Connection) -> None:
        connection.execute("PRAGMA busy_timeout = 250")
        connection.execute("PRAGMA foreign_keys = ON")

    def _validate(self, connection: sqlite3.Connection, *, before: tuple[int, int, int]) -> None:
        after = _identity(self.path)
        if before[:2] != after[:2]:
            raise StorageFailure("MONITOR_STORAGE_INVALID", "monitor storage changed while it was opened")
        try:
            row = connection.execute("PRAGMA quick_check(1)").fetchone()
            if row is None or row[0] != "ok":
                raise StorageFailure("MONITOR_STORAGE_CORRUPT", "monitor storage failed integrity validation")
            application_id = connection.execute("PRAGMA application_id").fetchone()[0]
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if application_id != APPLICATION_ID:
                raise StorageFailure("MONITOR_STORAGE_INVALID", "monitor storage identity is invalid")
            if version > SCHEMA_VERSION:
                raise StorageFailure("MONITOR_STORAGE_VERSION_UNSUPPORTED", "monitor storage version is unsupported")
            if version != SCHEMA_VERSION:
                raise StorageFailure("MONITOR_STORAGE_INVALID", "monitor storage schema is invalid")
            metadata = connection.execute("SELECT workspace_id FROM monitor_metadata").fetchone()
            if metadata is None or metadata[0] != self.paths.workspace_id:
                raise StorageFailure("MONITOR_WORKSPACE_MISMATCH", "monitor storage belongs to another workspace")
        except sqlite3.DatabaseError as error:
            raise StorageFailure("MONITOR_STORAGE_CORRUPT", "monitor storage is corrupt") from error

    def _initialize(self, connection: sqlite3.Connection) -> None:
        connection.execute("BEGIN EXCLUSIVE")
        try:
            application_id = connection.execute("PRAGMA application_id").fetchone()[0]
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if application_id not in (0, APPLICATION_ID):
                raise StorageFailure("MONITOR_STORAGE_INVALID", "monitor storage identity is invalid")
            if version > SCHEMA_VERSION:
                raise StorageFailure("MONITOR_STORAGE_VERSION_UNSUPPORTED", "monitor storage version is unsupported")
            if version == 0:
                for statement in _SCHEMA_STATEMENTS:
                    connection.execute(statement)
                connection.execute(
                    "INSERT INTO monitor_metadata(singleton, workspace_id, schema_version) VALUES (1, ?, ?)",
                    (self.paths.workspace_id, SCHEMA_VERSION),
                )
                connection.execute(f"PRAGMA application_id = {APPLICATION_ID}")
                connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            connection.commit()
        except BaseException:
            if connection.in_transaction:
                connection.rollback()
            raise

    def _open_write(self) -> sqlite3.Connection:
        self._ensure_parent()
        if self._size() > MAX_DATABASE_BYTES:
            raise StorageFailure("MONITOR_STORAGE_FULL", "monitor storage reached its hard size limit")
        existed = self.path.exists()
        if existed:
            before = _identity(self.path)
        try:
            connection = sqlite3.connect(self.path, timeout=BUSY_TIMEOUT_MS / 1000, isolation_level=None)
        except sqlite3.DatabaseError as error:
            raise StorageFailure("MONITOR_STORAGE_CORRUPT", "monitor storage cannot be opened") from error
        try:
            self._configure(connection)
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("PRAGMA synchronous = FULL")
            connection.execute("PRAGMA wal_autocheckpoint = 256")
            if not existed:
                self._initialize(connection)
                before = _identity(self.path)
            self._validate(connection, before=before)
            return connection
        except BaseException:
            connection.close()
            raise

    def read(self, operation: Callable[[sqlite3.Connection], _T], *, empty: _T) -> _T:
        self._require_path(self.path)
        if not self.path.exists():
            return empty
        before = _identity(self.path)
        try:
            uri = self.path.as_uri() + "?mode=ro"
            connection = sqlite3.connect(uri, uri=True, timeout=BUSY_TIMEOUT_MS / 1000, isolation_level=None)
            self._configure(connection)
            self._validate(connection, before=before)
            return operation(connection)
        except StorageFailure:
            raise
        except sqlite3.OperationalError as error:
            if "locked" in str(error).lower() or "busy" in str(error).lower():
                raise StorageFailure("MONITOR_STORAGE_BUSY", "monitor storage is busy") from error
            raise StorageFailure("MONITOR_STORAGE_CORRUPT", "monitor storage cannot be read") from error
        except sqlite3.DatabaseError as error:
            raise StorageFailure("MONITOR_STORAGE_CORRUPT", "monitor storage is corrupt") from error
        finally:
            if "connection" in locals():
                connection.close()

    def write(self, operation: Callable[[sqlite3.Connection], _T]) -> _T:
        with self._close_lock:
            if self._closed:
                raise StorageFailure("MONITOR_STORAGE_INVALID", "monitor storage is closed")
        if not self._writer.slots.acquire(blocking=False):
            raise StorageFailure("MONITOR_STORAGE_BUSY", "monitor storage writer queue is full")

        def invoke() -> _T:
            try:
                connection = self._open_write()
                try:
                    result = operation(connection)
                    connection.execute("PRAGMA wal_checkpoint(PASSIVE)")
                    return result
                finally:
                    connection.close()
            except StorageFailure:
                raise
            except sqlite3.IntegrityError as error:
                raise StorageFailure("MONITOR_STORAGE_INVALID", "monitor storage rejected the mutation") from error
            except sqlite3.OperationalError as error:
                if "locked" in str(error).lower() or "busy" in str(error).lower():
                    raise StorageFailure("MONITOR_STORAGE_BUSY", "monitor storage is busy") from error
                raise StorageFailure("MONITOR_STORAGE_INVALID", "monitor storage mutation failed") from error
            except sqlite3.DatabaseError as error:
                raise StorageFailure("MONITOR_STORAGE_CORRUPT", "monitor storage is corrupt") from error
            finally:
                self._writer.slots.release()

        return self._writer.executor.submit(invoke).result()

    def close(self) -> None:
        with self._close_lock:
            if self._closed:
                return
            self._closed = True
        executor = None
        with _WRITER_REGISTRY_LOCK:
            self._writer.references -= 1
            if self._writer.references == 0:
                _WRITERS.pop(self._writer_key, None)
                executor = self._writer.executor
        if executor is not None:
            executor.shutdown(wait=True, cancel_futures=False)
