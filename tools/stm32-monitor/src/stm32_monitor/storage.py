from __future__ import annotations

import os
import sqlite3
import stat
import threading
from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError as FutureTimeout
from dataclasses import dataclass
from pathlib import Path
from time import monotonic_ns as _monotonic_ns
from typing import Callable, TypeVar

from stm32_toolkit.paths import WorkspacePaths


APPLICATION_ID = 0x53544D4D
SCHEMA_VERSION = 1
BUSY_TIMEOUT_MS = 250
MAX_DATABASE_BYTES = 512 * 1024 * 1024
INTEGRITY_CHECK_INTERVAL_NS = 60 * 1_000_000_000
_T = TypeVar("_T")

_SCHEMA_STATEMENTS = (
    """CREATE TABLE monitor_metadata (
        singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
        workspace_id TEXT NOT NULL,
        schema_version INTEGER NOT NULL
    )""",
    """CREATE TABLE monitor_history_accounting (
        singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
        logical_bytes INTEGER NOT NULL CHECK (typeof(logical_bytes) = 'integer' AND logical_bytes >= 0)
    )""",
    "INSERT INTO monitor_history_accounting(singleton, logical_bytes) VALUES (1, 0)",
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
    "CREATE INDEX history_retention_time ON history_batches(captured_ns, batch_id)",
    """CREATE TABLE history_values (
        batch_id INTEGER NOT NULL REFERENCES history_batches(batch_id) ON DELETE CASCADE,
        ordinal INTEGER NOT NULL,
        row_json BLOB NOT NULL,
        payload_bytes INTEGER NOT NULL,
        PRIMARY KEY (batch_id, ordinal)
    )""",
    """CREATE TRIGGER history_batches_account_insert AFTER INSERT ON history_batches
       BEGIN UPDATE monitor_history_accounting SET logical_bytes = logical_bytes + NEW.payload_bytes WHERE singleton = 1; END""",
    """CREATE TRIGGER history_batches_account_delete AFTER DELETE ON history_batches
       BEGIN UPDATE monitor_history_accounting SET logical_bytes = logical_bytes - OLD.payload_bytes WHERE singleton = 1; END""",
    """CREATE TRIGGER history_values_account_insert AFTER INSERT ON history_values
       BEGIN UPDATE monitor_history_accounting SET logical_bytes = logical_bytes + NEW.payload_bytes WHERE singleton = 1; END""",
    """CREATE TRIGGER history_values_account_delete AFTER DELETE ON history_values
       BEGIN UPDATE monitor_history_accounting SET logical_bytes = logical_bytes - OLD.payload_bytes WHERE singleton = 1; END""",
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


class _BoundedConnection(sqlite3.Connection):
    """Connection whose explicit commits pass the monitor storage admission gate."""

    _monitor_before_commit: Callable[[sqlite3.Connection], None] | None = None

    def commit(self) -> None:
        callback = self._monitor_before_commit
        if callback is not None and self.in_transaction:
            try:
                callback(self)
            except BaseException:
                super().rollback()
                raise
        super().commit()


def _is_redirect(path: Path) -> bool:
    metadata = os.lstat(path)
    return _metadata_is_redirect(metadata)


def _metadata_is_redirect(metadata: os.stat_result) -> bool:
    attributes = getattr(metadata, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return stat.S_ISLNK(metadata.st_mode) or bool(attributes & reparse_flag)


def _identity(path: Path) -> tuple[int, int, int]:
    metadata = os.lstat(path)
    if (
        _metadata_is_redirect(metadata)
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_nlink != 1
    ):
        raise StorageFailure("MONITOR_STORAGE_INVALID", "monitor storage is not a private regular file")
    return metadata.st_dev, metadata.st_ino, metadata.st_size


def _opened_identity(path: Path) -> tuple[int, int, int]:
    try:
        with path.open("rb", buffering=0) as stream:
            metadata = os.fstat(stream.fileno())
    except OSError as error:
        raise StorageFailure("MONITOR_STORAGE_INVALID", "monitor storage cannot be opened safely") from error
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
        raise StorageFailure("MONITOR_STORAGE_INVALID", "monitor storage is not a private regular file")
    return metadata.st_dev, metadata.st_ino, metadata.st_size


def _directory_identity(path: Path) -> tuple[int, int]:
    try:
        metadata = os.lstat(path)
        redirected = _is_redirect(path)
    except FileNotFoundError:
        raise
    except OSError as error:
        raise StorageFailure("MONITOR_STORAGE_INVALID", "monitor storage path cannot be inspected") from error
    if redirected or not stat.S_ISDIR(metadata.st_mode):
        raise StorageFailure("MONITOR_STORAGE_INVALID", "monitor storage contains an unsafe directory")
    return metadata.st_dev, metadata.st_ino


class MonitorDatabase:
    """Workspace-bound SQLite access with one bounded mutation worker."""

    def __init__(self, paths: WorkspacePaths) -> None:
        if not isinstance(paths, WorkspacePaths):
            raise TypeError("paths must be WorkspacePaths")
        self.paths = paths
        self.path = paths.monitor_root / "monitor.sqlite3"
        self._closed = False
        self._admission_lock = threading.RLock()
        self._accepted: set[Future[object]] = set()
        self._trusted_lock = threading.RLock()
        self._trusted_failure: StorageFailure | None = None
        try:
            self._trusted_directories = list(self._capture_directory_chain(paths.monitor_root))
        except StorageFailure as error:
            self._trusted_directories = []
            self._trusted_failure = error
        self._integrity_lock = threading.Lock()
        self._integrity_identity: tuple[int, int] | None = None
        self._last_integrity_ns = 0
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

    def _capture_directory_chain(self, target: Path) -> tuple[tuple[Path, tuple[int, int]], ...]:
        anchor = self.paths.data_root
        while True:
            try:
                anchor_identity = _directory_identity(anchor)
                break
            except FileNotFoundError:
                parent = anchor.parent
                anchor = parent
        snapshot: list[tuple[Path, tuple[int, int]]] = [(anchor, anchor_identity)]
        current = anchor
        for part in target.relative_to(anchor).parts:
            current /= part
            try:
                snapshot.append((current, _directory_identity(current)))
            except FileNotFoundError:
                break
        return tuple(snapshot)

    def _revalidate_trusted_directories(self) -> None:
        with self._trusted_lock:
            if self._trusted_failure is not None:
                raise self._trusted_failure
            for path, identity in self._trusted_directories:
                try:
                    current = _directory_identity(path)
                except FileNotFoundError as error:
                    raise StorageFailure(
                        "MONITOR_STORAGE_INVALID", "monitor storage directory changed"
                    ) from error
                if current != identity:
                    raise StorageFailure("MONITOR_STORAGE_INVALID", "monitor storage directory changed")

    def _remember_directory(self, path: Path) -> None:
        identity = _directory_identity(path)
        with self._trusted_lock:
            for known_path, known_identity in self._trusted_directories:
                if known_path == path:
                    if known_identity != identity:
                        raise StorageFailure(
                            "MONITOR_STORAGE_INVALID", "monitor storage directory changed"
                        )
                    return
            self._trusted_directories.append((path, identity))

    def _adopt_existing_directories(self, target: Path) -> None:
        self._revalidate_trusted_directories()
        with self._trusted_lock:
            current = self._trusted_directories[-1][0]
        try:
            relative = target.relative_to(current)
        except ValueError:
            try:
                current.relative_to(target)
            except ValueError as error:
                raise StorageFailure(
                    "MONITOR_STORAGE_INVALID", "monitor storage directory chain is invalid"
                ) from error
            return
        for part in relative.parts:
            current /= part
            try:
                self._remember_directory(current)
            except FileNotFoundError:
                break

    def _require_path(self, path: Path) -> None:
        self._revalidate_trusted_directories()
        try:
            self.paths.data_root.relative_to(self.paths.project_root)
        except ValueError:
            pass
        else:
            raise StorageFailure("MONITOR_STORAGE_INVALID", "monitor state root must remain outside the project")
        try:
            path.relative_to(self.paths.data_root)
            path.relative_to(self.paths.workspace_root)
        except ValueError as error:
            raise StorageFailure("MONITOR_STORAGE_INVALID", "monitor storage escaped its workspace") from error

        anchor = self.paths.data_root
        while True:
            try:
                _directory_identity(anchor)
                break
            except FileNotFoundError:
                parent = anchor.parent
                if parent == anchor:
                    raise StorageFailure("MONITOR_STORAGE_INVALID", "monitor storage has no safe ancestor")
                anchor = parent
        current = anchor
        for part in path.relative_to(anchor).parts:
            current /= part
            try:
                metadata = os.lstat(current)
            except FileNotFoundError:
                continue
            except OSError as error:
                raise StorageFailure("MONITOR_STORAGE_INVALID", "monitor storage path cannot be inspected") from error
            if _metadata_is_redirect(metadata):
                raise StorageFailure("MONITOR_STORAGE_INVALID", "monitor storage contains a redirect")
            if current != path and not stat.S_ISDIR(metadata.st_mode):
                raise StorageFailure("MONITOR_STORAGE_INVALID", "monitor storage contains a non-directory")

    def _directory_snapshot(self, target: Path) -> tuple[tuple[Path, tuple[int, int]], ...]:
        anchor = target
        missing: list[Path] = []
        while True:
            try:
                anchor_identity = _directory_identity(anchor)
                break
            except FileNotFoundError:
                missing.append(anchor)
                parent = anchor.parent
                if parent == anchor:
                    raise StorageFailure("MONITOR_STORAGE_INVALID", "monitor storage has no safe ancestor")
                anchor = parent
        snapshot: list[tuple[Path, tuple[int, int]]] = [(anchor, anchor_identity)]
        current = anchor
        for path in reversed(missing):
            current = path
            try:
                snapshot.append((current, _directory_identity(current)))
            except FileNotFoundError:
                break
        return tuple(snapshot)

    @staticmethod
    def _revalidate_directories(snapshot: tuple[tuple[Path, tuple[int, int]], ...]) -> None:
        for path, identity in snapshot:
            if _directory_identity(path) != identity:
                raise StorageFailure("MONITOR_STORAGE_INVALID", "monitor storage directory changed")

    def _ensure_parent(self) -> None:
        self._require_path(self.paths.monitor_root)
        while True:
            try:
                _directory_identity(self.paths.monitor_root)
                break
            except FileNotFoundError:
                missing: list[Path] = []
                current = self.paths.monitor_root
                while True:
                    try:
                        _directory_identity(current)
                        break
                    except FileNotFoundError:
                        missing.append(current)
                        parent = current.parent
                        if parent == current:
                            raise StorageFailure("MONITOR_STORAGE_INVALID", "monitor storage has no safe ancestor")
                        current = parent
                for directory in reversed(missing):
                    self._revalidate_trusted_directories()
                    snapshot = self._directory_snapshot(directory.parent)
                    self._revalidate_directories(snapshot)
                    try:
                        directory.mkdir(parents=False, exist_ok=False)
                    except OSError as error:
                        raise StorageFailure("MONITOR_STORAGE_INVALID", "monitor storage directory cannot be created") from error
                    self._revalidate_directories(snapshot)
                    self._remember_directory(directory)
        self._adopt_existing_directories(self.paths.monitor_root)
        self._require_path(self.paths.monitor_root)

    def ensure_directory(self, target: Path) -> None:
        """Create an owned monitor subdirectory one verified component at a time."""
        self._ensure_parent()
        self._require_path(target)
        try:
            relative = target.relative_to(self.paths.monitor_root)
        except ValueError as error:
            raise StorageFailure(
                "MONITOR_STORAGE_INVALID", "monitor storage escaped its workspace"
            ) from error
        current = self.paths.monitor_root
        self._remember_directory(current)
        for part in relative.parts:
            current /= part
            self._revalidate_trusted_directories()
            try:
                self._remember_directory(current)
                continue
            except FileNotFoundError:
                pass
            snapshot = self._directory_snapshot(current.parent)
            self._revalidate_directories(snapshot)
            try:
                current.mkdir(mode=0o700, parents=False, exist_ok=False)
            except FileExistsError:
                self._remember_directory(current)
            except OSError as error:
                raise StorageFailure(
                    "MONITOR_STORAGE_INVALID", "monitor storage directory cannot be created"
                ) from error
            self._revalidate_directories(snapshot)
            self._remember_directory(current)
        self._require_path(target)

    def _storage_files(self) -> tuple[Path, Path, Path]:
        return tuple(self.path.with_name(self.path.name + suffix) for suffix in ("", "-wal", "-shm"))  # type: ignore[return-value]

    def _inspect_storage_files(self) -> dict[Path, tuple[int, int, int]]:
        identities: dict[Path, tuple[int, int, int]] = {}
        for path in self._storage_files():
            try:
                named = _identity(path)
            except FileNotFoundError:
                continue
            except OSError as error:
                raise StorageFailure("MONITOR_STORAGE_INVALID", "monitor storage file cannot be inspected") from error
            try:
                opened = _opened_identity(path)
                after = _identity(path)
            except FileNotFoundError:
                if path == self.path:
                    raise StorageFailure("MONITOR_STORAGE_INVALID", "monitor storage file changed during inspection")
                continue
            except OSError as error:
                raise StorageFailure("MONITOR_STORAGE_INVALID", "monitor storage file cannot be inspected") from error
            if named[:2] != opened[:2] or named[:2] != after[:2]:
                raise StorageFailure("MONITOR_STORAGE_INVALID", "monitor storage file changed during inspection")
            identities[path] = named
        return identities

    def _size(self, connection: sqlite3.Connection | None = None) -> int:
        total = 0
        for suffix in ("", "-wal"):
            try:
                total += self.path.with_name(self.path.name + suffix).stat().st_size
            except FileNotFoundError:
                pass
            except OSError as error:
                raise StorageFailure("MONITOR_STORAGE_INVALID", "monitor storage size cannot be inspected") from error
        if connection is None:
            return total
        try:
            page_size = connection.execute("PRAGMA page_size").fetchone()[0]
            page_count = connection.execute("PRAGMA page_count").fetchone()[0]
            main_size = self.path.stat().st_size
            wal_path = self.path.with_name(self.path.name + "-wal")
            try:
                wal_size = wal_path.stat().st_size
            except FileNotFoundError:
                wal_size = 0
            projected = max(main_size, page_size * page_count) + wal_size
            baseline = getattr(connection, "_monitor_change_baseline", connection.total_changes)
            if connection.total_changes > baseline:
                projected = max(projected, total + page_size + 24)
            return max(total, projected)
        except (OSError, sqlite3.DatabaseError, TypeError, ValueError) as error:
            raise StorageFailure(
                "MONITOR_STORAGE_INVALID", "monitor storage size cannot be inspected"
            ) from error

    @staticmethod
    def _configure(connection: sqlite3.Connection, *, busy_timeout_ms: int) -> None:
        connection.execute(f"PRAGMA busy_timeout = {busy_timeout_ms}")
        connection.execute("PRAGMA foreign_keys = ON")

    def _validate(
        self,
        connection: sqlite3.Connection,
        *,
        before: tuple[int, int, int],
        full_integrity: bool = True,
    ) -> None:
        after = _identity(self.path)
        if before[:2] != after[:2]:
            raise StorageFailure("MONITOR_STORAGE_INVALID", "monitor storage changed while it was opened")
        try:
            if full_integrity:
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
            accounting = connection.execute(
                "SELECT logical_bytes FROM monitor_history_accounting WHERE singleton = 1"
            ).fetchone()
            if (
                accounting is None
                or type(accounting[0]) is not int
                or accounting[0] < 0
            ):
                raise StorageFailure("MONITOR_STORAGE_CORRUPT", "monitor storage accounting is invalid")
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

    def _preflight_existing(self, *, busy_timeout_ms: int) -> tuple[int, int, int]:
        self._require_path(self.path)
        directory_snapshot = self._directory_snapshot(self.path.parent)
        files = self._inspect_storage_files()
        before = files.get(self.path)
        if before is None:
            raise StorageFailure("MONITOR_STORAGE_INVALID", "monitor storage database is missing")
        try:
            uri = self.path.as_uri() + "?mode=ro&immutable=1"
            connection = sqlite3.connect(
                uri,
                uri=True,
                timeout=busy_timeout_ms / 1000,
                isolation_level=None,
            )
        except sqlite3.DatabaseError as error:
            raise StorageFailure("MONITOR_STORAGE_CORRUPT", "monitor storage cannot be opened") from error
        try:
            self._configure(connection, busy_timeout_ms=busy_timeout_ms)
            with self._integrity_lock:
                now_ns = _monotonic_ns()
                full_integrity = (
                    self._integrity_identity != before[:2]
                    or now_ns - self._last_integrity_ns >= INTEGRITY_CHECK_INTERVAL_NS
                )
                self._validate(
                    connection,
                    before=before,
                    full_integrity=full_integrity,
                )
                if full_integrity:
                    self._integrity_identity = before[:2]
                    self._last_integrity_ns = now_ns
        finally:
            connection.close()
        self._revalidate_directories(directory_snapshot)
        after_files = self._inspect_storage_files()
        after = after_files.get(self.path)
        if after is None or before[:2] != after[:2]:
            raise StorageFailure("MONITOR_STORAGE_INVALID", "monitor storage changed during validation")
        return after

    def _create_database_file(self) -> tuple[int, int, int]:
        if self._inspect_storage_files():
            raise StorageFailure("MONITOR_STORAGE_INVALID", "monitor storage files already exist")
        directory_snapshot = self._directory_snapshot(self.path.parent)
        try:
            with self.path.open("xb", buffering=0) as stream:
                metadata = os.fstat(stream.fileno())
                opened = (metadata.st_dev, metadata.st_ino, metadata.st_size)
        except FileExistsError as error:
            raise StorageFailure("MONITOR_STORAGE_INVALID", "monitor storage appeared during creation") from error
        except OSError as error:
            raise StorageFailure("MONITOR_STORAGE_INVALID", "monitor storage cannot be created") from error
        self._revalidate_directories(directory_snapshot)
        named = _identity(self.path)
        if opened != named:
            raise StorageFailure("MONITOR_STORAGE_INVALID", "monitor storage changed during creation")
        return named

    def _ensure_sidecars(self) -> None:
        directory_snapshot = self._directory_snapshot(self.path.parent)
        for sidecar in self._storage_files()[1:]:
            try:
                _identity(sidecar)
            except FileNotFoundError:
                self._revalidate_directories(directory_snapshot)
                try:
                    with sidecar.open("xb", buffering=0) as stream:
                        metadata = os.fstat(stream.fileno())
                        opened = (metadata.st_dev, metadata.st_ino, metadata.st_size)
                except FileExistsError as error:
                    raise StorageFailure("MONITOR_STORAGE_INVALID", "monitor storage sidecar appeared during creation") from error
                except OSError as error:
                    raise StorageFailure("MONITOR_STORAGE_INVALID", "monitor storage sidecar cannot be created") from error
                self._revalidate_directories(directory_snapshot)
                named = _identity(sidecar)
                if named != opened:
                    raise StorageFailure("MONITOR_STORAGE_INVALID", "monitor storage sidecar changed during creation")
            else:
                self._inspect_storage_files()

    def _open_write(self, *, busy_timeout_ms: int = BUSY_TIMEOUT_MS) -> sqlite3.Connection:
        self._ensure_parent()
        if self._size() > MAX_DATABASE_BYTES:
            raise StorageFailure("MONITOR_STORAGE_FULL", "monitor storage reached its hard size limit")
        try:
            _identity(self.path)
        except FileNotFoundError:
            existed = False
        else:
            existed = True
        if existed:
            before = self._preflight_existing(busy_timeout_ms=busy_timeout_ms)
        else:
            before = self._create_database_file()
        try:
            connection = sqlite3.connect(
                self.path,
                timeout=busy_timeout_ms / 1000,
                isolation_level="DEFERRED",
                factory=_BoundedConnection,
            )
        except sqlite3.DatabaseError as error:
            raise StorageFailure("MONITOR_STORAGE_CORRUPT", "monitor storage cannot be opened") from error
        try:
            self._configure(connection, busy_timeout_ms=busy_timeout_ms)
            self._revalidate_trusted_directories()
            if _identity(self.path)[:2] != before[:2]:
                raise StorageFailure("MONITOR_STORAGE_INVALID", "monitor storage changed while it was opened")
            if not existed:
                self._initialize(connection)
                before = _identity(self.path)
            self._validate(connection, before=before, full_integrity=not existed)
            self._ensure_sidecars()
            self._revalidate_trusted_directories()
            if _identity(self.path)[:2] != before[:2]:
                raise StorageFailure("MONITOR_STORAGE_INVALID", "monitor storage changed while it was opened")
            journal = connection.execute("PRAGMA journal_mode = WAL").fetchone()
            if journal is None or str(journal[0]).lower() != "wal":
                raise StorageFailure("MONITOR_STORAGE_INVALID", "monitor storage journal mode is invalid")
            self._inspect_storage_files()
            connection.execute("PRAGMA synchronous = FULL")
            connection.execute("PRAGMA wal_autocheckpoint = 256").fetchone()
            cast_connection = connection
            cast_connection._monitor_change_baseline = connection.total_changes  # type: ignore[attr-defined]
            cast_connection._monitor_before_commit = self._before_commit  # type: ignore[attr-defined]
            return connection
        except BaseException:
            connection.close()
            raise

    def read(self, operation: Callable[[sqlite3.Connection], _T], *, empty: _T) -> _T:
        self._require_path(self.path)
        try:
            before = _identity(self.path)
        except FileNotFoundError:
            if self._inspect_storage_files():
                raise StorageFailure("MONITOR_STORAGE_INVALID", "orphan monitor storage sidecar exists")
            return empty
        before = self._preflight_existing(busy_timeout_ms=BUSY_TIMEOUT_MS)
        try:
            uri = self.path.as_uri() + "?mode=ro&immutable=1"
            connection = sqlite3.connect(uri, uri=True, timeout=BUSY_TIMEOUT_MS / 1000, isolation_level=None)
            self._configure(connection, busy_timeout_ms=BUSY_TIMEOUT_MS)
            self._validate(connection, before=before, full_integrity=False)
            return operation(connection)
        except StorageFailure:
            raise
        except sqlite3.OperationalError as error:
            if "locked" in str(error).lower() or "busy" in str(error).lower():
                raise StorageFailure("MONITOR_STORAGE_BUSY", "monitor storage is busy") from error
            raise StorageFailure("MONITOR_STORAGE_CORRUPT", "monitor storage cannot be read") from error
        except sqlite3.DatabaseError as error:
            raise StorageFailure("MONITOR_STORAGE_CORRUPT", "monitor storage is corrupt") from error
        except (TypeError, ValueError, OverflowError) as error:
            raise StorageFailure("MONITOR_STORAGE_CORRUPT", "monitor storage contains invalid data") from error
        finally:
            if "connection" in locals():
                connection.close()

    def _before_commit(self, connection: sqlite3.Connection) -> None:
        self._revalidate_trusted_directories()
        self._inspect_storage_files()
        if self._size(connection) > MAX_DATABASE_BYTES:
            raise StorageFailure("MONITOR_STORAGE_FULL", "monitor storage reached its hard size limit")

    def _invoke(
        self,
        operation: Callable[[sqlite3.Connection], _T],
        *,
        busy_timeout_ms: int,
        cancel_event: threading.Event,
    ) -> _T:
        try:
            connection = self._open_write(busy_timeout_ms=busy_timeout_ms)
            try:
                connection.set_progress_handler(
                    lambda: 1 if cancel_event.is_set() else 0,
                    1,
                )
                if cancel_event.is_set():
                    raise StorageFailure("MONITOR_STORAGE_BUSY", "monitor storage is busy")
                result = operation(connection)
                if connection.in_transaction:
                    connection.commit()
                self._inspect_storage_files()
                return result
            finally:
                connection.close()
        except StorageFailure:
            raise
        except sqlite3.IntegrityError as error:
            raise StorageFailure("MONITOR_STORAGE_INVALID", "monitor storage rejected the mutation") from error
        except sqlite3.OperationalError as error:
            if (
                cancel_event.is_set()
                or "interrupted" in str(error).lower()
                or "locked" in str(error).lower()
                or "busy" in str(error).lower()
            ):
                raise StorageFailure("MONITOR_STORAGE_BUSY", "monitor storage is busy") from error
            raise StorageFailure("MONITOR_STORAGE_INVALID", "monitor storage mutation failed") from error
        except sqlite3.DatabaseError as error:
            raise StorageFailure("MONITOR_STORAGE_CORRUPT", "monitor storage is corrupt") from error
        except OverflowError as error:
            raise StorageFailure("MONITOR_STORAGE_INVALID", "monitor storage rejected the mutation") from error

    def _submit(
        self,
        operation: Callable[[sqlite3.Connection], _T],
        *,
        busy_timeout_ms: int,
    ) -> tuple[Future[_T], threading.Event]:
        with self._admission_lock:
            if self._closed:
                raise StorageFailure("MONITOR_STORAGE_INVALID", "monitor storage is closed")
            if not self._writer.slots.acquire(blocking=False):
                raise StorageFailure("MONITOR_STORAGE_BUSY", "monitor storage writer queue is full")
            try:
                cancel_event = threading.Event()
                future = self._writer.executor.submit(
                    self._invoke,
                    operation,
                    busy_timeout_ms=busy_timeout_ms,
                    cancel_event=cancel_event,
                )
            except RuntimeError as error:
                self._writer.slots.release()
                raise StorageFailure("MONITOR_STORAGE_INVALID", "monitor storage writer is unavailable") from error
            self._accepted.add(future)

            def complete(done: Future[object]) -> None:
                self._writer.slots.release()
                with self._admission_lock:
                    self._accepted.discard(done)

            future.add_done_callback(complete)
            return future, cancel_event

    def write(self, operation: Callable[[sqlite3.Connection], _T]) -> _T:
        future, _ = self._submit(operation, busy_timeout_ms=BUSY_TIMEOUT_MS)
        return future.result()

    def try_write(
        self,
        operation: Callable[[sqlite3.Connection], _T],
        *,
        timeout_ms: int = 50,
    ) -> _T:
        if not isinstance(timeout_ms, int) or isinstance(timeout_ms, bool) or not 1 <= timeout_ms <= BUSY_TIMEOUT_MS:
            raise StorageFailure("MONITOR_STORAGE_INVALID", "monitor storage timeout is invalid")
        future, cancel_event = self._submit(operation, busy_timeout_ms=timeout_ms)
        def invoke() -> _T:
            return future.result(timeout=timeout_ms / 1000)
        try:
            return invoke()
        except FutureTimeout as error:
            cancel_event.set()
            future.cancel()
            raise StorageFailure("MONITOR_STORAGE_BUSY", "monitor storage is busy") from error

    def close(self) -> None:
        with self._admission_lock:
            if self._closed:
                return
            self._closed = True
            accepted = tuple(self._accepted)
        for future in accepted:
            try:
                future.result()
            except BaseException:
                pass
        executor = None
        with _WRITER_REGISTRY_LOCK:
            self._writer.references -= 1
            if self._writer.references == 0:
                _WRITERS.pop(self._writer_key, None)
                executor = self._writer.executor
        if executor is not None:
            executor.shutdown(wait=True, cancel_futures=False)
