from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
import stat
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO, Iterator, cast
from uuid import UUID, uuid4

from stm32_toolkit.paths import WorkspacePaths, require_safe_session_id

from .history import (
    MAX_EXPORT_HISTORY_VALUES,
    HistoryQuery,
    HistoryStore,
    MAX_HISTORY_VALUES,
    flatten_history_page,
)
from .models import MAX_SIGNED_INT64
from .protocol import (
    MONITOR_PROTOCOL_VERSION,
    MONITOR_VERSION,
    TOOLKIT_VERSION,
    ProtocolResult,
    failure,
    success,
)
from .storage import MonitorDatabase, StorageFailure


MAX_EXPORT_VALUES = 1_000_000
MAX_EXPORT_BYTES = 160 * 1024 * 1024
MAX_WORKSPACE_EXPORTS = 100
MAX_WORKSPACE_EXPORT_BYTES = 512 * 1024 * 1024
MAX_MANIFEST_BYTES = 16 * 1024
_WRITE_BUFFER_BYTES = 4 * 1024 * 1024
_VERIFY_BUFFER_BYTES = 4 * 1024 * 1024
MAX_RECOVERY_RECORDS = 10
RECOVERY_TIME_BUDGET_NS = 100 * 1_000_000
_replace = os.replace
_MANIFEST_FIELDS = {
    "protocol", "toolkitVersion", "monitorVersion", "workspaceId", "sessionId",
    "exportId", "format", "sha256", "bytes", "valueCount", "createdAtUtc",
}


@dataclass(frozen=True)
class ExportRequest:
    session_id: str
    start_ns: int
    end_ns: int
    format: str

    def __post_init__(self) -> None:
        require_safe_session_id(self.session_id)
        if (
            not isinstance(self.start_ns, int)
            or isinstance(self.start_ns, bool)
            or not isinstance(self.end_ns, int)
            or isinstance(self.end_ns, bool)
            or self.start_ns < 0
            or self.end_ns <= self.start_ns
            or self.end_ns > MAX_SIGNED_INT64
        ):
            raise ValueError("export range is invalid")
        if self.format not in {"jsonl", "csv"}:
            raise ValueError("export format is invalid")


@dataclass(frozen=True)
class ExportArtifact:
    export_id: UUID
    directory: Path
    data_path: Path
    manifest_path: Path
    sha256: str
    byte_count: int
    value_count: int

    def to_dict(self) -> dict[str, object]:
        return {
            "exportId": str(self.export_id),
            "format": self.data_path.suffix.removeprefix("."),
            "sha256": self.sha256,
            "bytes": self.byte_count,
            "valueCount": self.value_count,
        }


class ExportDownload:
    def __init__(
        self,
        stream: BinaryIO,
        *,
        export_id: UUID,
        format_name: str,
        byte_count: int,
    ) -> None:
        self._stream = stream
        self.export_id = export_id
        self.byte_count = byte_count
        self.content_type = (
            "application/x-ndjson" if format_name == "jsonl" else "text/csv"
        )
        self.filename = f"history-{export_id}.{format_name}"

    def __repr__(self) -> str:
        return (
            f"ExportDownload(export_id={self.export_id!r}, "
            f"byte_count={self.byte_count!r}, content_type={self.content_type!r}, "
            f"filename={self.filename!r})"
        )

    def iter_chunks(self, size: int = 64 * 1024) -> Iterator[bytes]:
        if type(size) is not int or not 1 <= size <= 1024 * 1024:
            raise ValueError("download chunk size is invalid")
        while True:
            chunk = self._stream.read(size)
            if not chunk:
                return
            yield chunk

    def close(self) -> None:
        self._stream.close()


@dataclass(frozen=True)
class ExportDownloadResult:
    ok: bool
    code: str
    message: str
    data: ExportDownload | None


def _invalid_json_constant(_: str) -> object:
    raise ValueError("non-finite JSON number")


class _LimitedHashWriter:
    def __init__(self, stream: BinaryIO) -> None:
        self._stream = stream
        self._digest = hashlib.sha256()
        self._buffer = bytearray()
        self.byte_count = 0

    def write(self, data: bytes | bytearray) -> None:
        new_size = self.byte_count + len(data)
        if new_size > MAX_EXPORT_BYTES:
            raise StorageFailure("MONITOR_EXPORT_TOO_LARGE", "export byte limit was exceeded")
        self._digest.update(data)
        self.byte_count = new_size
        if len(self._buffer) + len(data) >= _WRITE_BUFFER_BYTES:
            if self._buffer:
                self._stream.write(self._buffer)
                self._buffer.clear()
            if len(data) >= _WRITE_BUFFER_BYTES:
                self._stream.write(data)
                return
        self._buffer.extend(data)

    def finish(self) -> None:
        if self._buffer:
            self._stream.write(self._buffer)
            self._buffer.clear()

    @property
    def sha256(self) -> str:
        return self._digest.hexdigest()


class _CsvTextSink:
    def __init__(self, target: _LimitedHashWriter) -> None:
        self._target = target

    def write(self, value: str) -> int:
        self._target.write(value.encode("utf-8"))
        return len(value)


def _fsync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    descriptor = os.open(path, os.O_RDONLY)  # pragma: no cover - POSIX durability gate
    try:  # pragma: no cover - POSIX durability gate
        os.fsync(descriptor)
    finally:  # pragma: no cover - POSIX durability gate
        os.close(descriptor)


def _redirect(metadata: os.stat_result) -> bool:
    attributes = getattr(metadata, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return stat.S_ISLNK(metadata.st_mode) or bool(attributes & reparse_flag)


def _directory_identity(path: Path) -> tuple[int, int]:
    metadata = os.lstat(path)
    if _redirect(metadata) or not stat.S_ISDIR(metadata.st_mode):
        raise OSError("export parent is unsafe")
    return metadata.st_dev, metadata.st_ino


def _validate_created_file(
    descriptor: int,
    path: Path,
    *,
    parent: Path,
    parent_identity: tuple[int, int],
) -> None:
    opened = os.fstat(descriptor)
    named = os.lstat(path)
    if (
        not stat.S_ISREG(opened.st_mode)
        or opened.st_nlink != 1
        or _redirect(named)
        or not stat.S_ISREG(named.st_mode)
        or named.st_nlink != 1
        or (opened.st_dev, opened.st_ino) != (named.st_dev, named.st_ino)
        or _directory_identity(parent) != parent_identity
    ):
        raise OSError("export artifact identity is unsafe")


@contextmanager
def _create_regular_exclusive(path: Path, *, parent: Path) -> Iterator[BinaryIO]:
    if path.parent != parent:
        raise OSError("export artifact parent is invalid")
    parent_identity = _directory_identity(parent)
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_BINARY", 0)
        | getattr(os, "O_NOINHERIT", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    parent_descriptor: int | None = None
    descriptor: int | None = None
    try:
        if os.name == "nt":
            descriptor = os.open(path, flags, 0o600)
        else:  # pragma: no cover - exercised by the Linux acceptance gate
            parent_descriptor = os.open(
                parent,
                os.O_RDONLY
                | getattr(os, "O_DIRECTORY", 0)
                | getattr(os, "O_NOFOLLOW", 0),
            )
            opened_parent = os.fstat(parent_descriptor)
            if (
                not stat.S_ISDIR(opened_parent.st_mode)
                or (opened_parent.st_dev, opened_parent.st_ino) != parent_identity
            ):
                raise OSError("export parent identity changed")
            descriptor = os.open(path.name, flags, 0o600, dir_fd=parent_descriptor)
        _validate_created_file(
            descriptor,
            path,
            parent=parent,
            parent_identity=parent_identity,
        )
        with os.fdopen(descriptor, "wb", buffering=0) as stream:
            descriptor = None
            yield stream
            stream.flush()
            os.fsync(stream.fileno())
            _validate_created_file(
                stream.fileno(),
                path,
                parent=parent,
                parent_identity=parent_identity,
            )
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if parent_descriptor is not None:
            os.close(parent_descriptor)


def _read_regular_limited(path: Path, *, limit: int, keep: bool) -> tuple[bytes | None, int, str]:
    before = os.lstat(path)
    if _redirect(before) or not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
        raise ValueError("export artifact is not an independent regular file")
    if before.st_size > limit:
        raise ValueError("export artifact exceeds its limit")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    chunks: list[bytes] | None = [] if keep else None
    digest = hashlib.sha256()
    total = 0
    try:
        opened = os.fstat(descriptor)
        if (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino):
            raise ValueError("export artifact identity changed")
        while True:
            chunk = os.read(descriptor, min(_VERIFY_BUFFER_BYTES, limit + 1 - total))
            if not chunk:
                break
            total += len(chunk)
            if total > limit:
                raise ValueError("export artifact exceeds its limit")
            digest.update(chunk)
            if chunks is not None:
                chunks.append(chunk)
        after = os.fstat(descriptor)
        if (
            (opened.st_dev, opened.st_ino) != (after.st_dev, after.st_ino)
            or after.st_size != total
            or after.st_nlink != 1
        ):
            raise ValueError("export artifact changed while reading")
        named_after = os.lstat(path)
        if (
            _redirect(named_after)
            or not stat.S_ISREG(named_after.st_mode)
            or named_after.st_nlink != 1
            or (named_after.st_dev, named_after.st_ino) != (opened.st_dev, opened.st_ino)
            or named_after.st_size != total
        ):
            raise ValueError("export artifact name changed while reading")
    finally:
        os.close(descriptor)
    return (b"".join(chunks) if chunks is not None else None), total, digest.hexdigest()


def _open_verified_regular(path: Path, *, limit: int) -> tuple[BinaryIO, int, str]:
    parent_identity = _directory_identity(path.parent)
    before = os.lstat(path)
    if _redirect(before) or not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
        raise ValueError("export artifact is not an independent regular file")
    if before.st_size > limit:
        raise ValueError("export artifact exceeds its limit")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    snapshot = tempfile.TemporaryFile(mode="w+b")
    try:
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_nlink != 1
            or (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino)
        ):
            raise ValueError("export artifact identity changed")
        digest = hashlib.sha256()
        total = 0
        while True:
            chunk = os.read(descriptor, min(_VERIFY_BUFFER_BYTES, limit + 1 - total))
            if not chunk:
                break
            total += len(chunk)
            if total > limit:
                raise ValueError("export artifact exceeds its limit")
            digest.update(chunk)
            snapshot.write(chunk)
        after = os.fstat(descriptor)
        named_after = os.lstat(path)
        if (
            (opened.st_dev, opened.st_ino) != (after.st_dev, after.st_ino)
            or after.st_size != total
            or after.st_nlink != 1
            or _redirect(named_after)
            or not stat.S_ISREG(named_after.st_mode)
            or named_after.st_nlink != 1
            or (named_after.st_dev, named_after.st_ino)
            != (opened.st_dev, opened.st_ino)
            or named_after.st_size != total
            or _directory_identity(path.parent) != parent_identity
        ):
            raise ValueError("export artifact changed while verifying")
        snapshot.flush()
        snapshot.seek(0)
        return snapshot, total, digest.hexdigest()
    except BaseException:
        snapshot.close()
        raise
    finally:
        os.close(descriptor)


def _exact_export_paths(
    monitor_root: Path,
    session_id: str,
    export_id: UUID,
    format_name: str,
) -> tuple[str, str, Path, Path]:
    extension = "jsonl" if format_name == "jsonl" else "csv"
    relative_root = Path("exports") / session_id / str(export_id)
    relative_data = (relative_root / f"history.{extension}").as_posix()
    relative_manifest = (relative_root / "manifest.json").as_posix()
    return relative_data, relative_manifest, monitor_root / relative_data, monitor_root / relative_manifest


class HistoryExporter:
    def __init__(self, paths: WorkspacePaths, history: HistoryStore) -> None:
        if not isinstance(paths, WorkspacePaths) or not isinstance(history, HistoryStore):
            raise TypeError("exporter requires workspace paths and history store")
        self._paths = paths
        self._history = history
        self._database = MonitorDatabase(paths)
        self._recover_pending()

    def _stream_history(self, request: ExportRequest, target: Path) -> tuple[str, int, int]:
        fieldnames = (
            "binding",
            "groupId",
            "groupRevision",
            "runId",
            "sequence",
            "scheduledUnixNs",
            "scheduledAtUtc",
            "capturedUnixNs",
            "capturedAtUtc",
            "latencyNs",
            "actualRateHz",
            "subscriberDrops",
            "historyDrops",
            "deadlineDrops",
            "batchValueCount",
            "watch",
            "status",
            "typedValue",
            "code",
            "definition",
            "valueOrdinal",
        )
        cursor: str | None = None
        value_count = 0
        jsonl_batch_started = False
        jsonl_static_prefix = b""
        jsonl_batch_buffer = bytearray()
        transient_history_cache: dict[str, object] = {}
        jsonl_dynamic_fields = (
            "watch",
            "status",
            "typedValue",
            "code",
            "definition",
            "valueOrdinal",
        )
        with _create_regular_exclusive(target, parent=target.parent) as stream:
            sink = _LimitedHashWriter(stream)
            encode_json = json.JSONEncoder(
                ensure_ascii=False,
                check_circular=False,
                separators=(",", ":"),
                allow_nan=False,
            ).encode

            csv_writer = None
            if request.format == "csv":
                csv_writer = csv.DictWriter(
                    _CsvTextSink(sink),
                    fieldnames=fieldnames,
                    extrasaction="ignore",
                    lineterminator="\n",
                )
                csv_writer.writeheader()
            def query_page(page_cursor: str | None):
                return self._history._query_history_uncached(
                    HistoryQuery(
                        request.session_id,
                        request.start_ns,
                        request.end_ns,
                        limit=MAX_EXPORT_HISTORY_VALUES,
                        cursor=page_cursor,
                    ),
                    transient_cache=transient_history_cache,
                    maximum_values=MAX_EXPORT_HISTORY_VALUES,
                )

            with ThreadPoolExecutor(
                max_workers=1,
                thread_name_prefix="stm32-monitor-export-read",
            ) as query_executor:
                page = query_page(cursor)
                while True:
                    if not page.ok or page.data is None:
                        raise StorageFailure(page.code, page.message)
                    next_cursor = page.data.next_cursor
                    if next_cursor is not None and (
                        next_cursor == cursor or not page.data.values
                    ):
                        raise StorageFailure(
                            "MONITOR_STORAGE_CORRUPT",
                            "monitor history is corrupt",
                        )
                    next_page = (
                        query_executor.submit(query_page, next_cursor)
                        if next_cursor is not None
                        else None
                    )
                    for value in flatten_history_page(page.data):
                        if value_count >= MAX_EXPORT_VALUES:
                            raise StorageFailure("MONITOR_EXPORT_TOO_LARGE", "export value limit was exceeded")
                        plain = value
                        if request.format == "jsonl":
                            if (
                                not jsonl_batch_started
                                or plain["valueOrdinal"] == 0
                            ):
                                if jsonl_batch_buffer:
                                    sink.write(jsonl_batch_buffer)
                                    jsonl_batch_buffer.clear()
                                jsonl_batch_started = True
                                static = {
                                    key: plain[key]
                                    for key in fieldnames
                                    if key not in jsonl_dynamic_fields
                                }
                                jsonl_static_prefix = (
                                    encode_json(static)[:-1].encode("utf-8") + b","
                                )
                            dynamic = {
                                key: plain[key]
                                for key in jsonl_dynamic_fields
                            }
                            jsonl_batch_buffer.extend(jsonl_static_prefix)
                            jsonl_batch_buffer.extend(
                                encode_json(dynamic)[1:].encode("utf-8")
                            )
                            jsonl_batch_buffer.append(0x0A)
                        else:
                            cast(csv.DictWriter, csv_writer).writerow(
                                {
                                    key: encode_json(plain.get(key))
                                    for key in fieldnames
                                }
                            )
                        value_count += 1
                    if next_page is None:
                        break
                    cursor = next_cursor
                    page = next_page.result()
            if jsonl_batch_buffer:
                sink.write(jsonl_batch_buffer)
            sink.finish()
            return sink.sha256, sink.byte_count, value_count

    def _reserve_pending(
        self,
        export_id: UUID,
        request: ExportRequest,
        relative_data: str,
        relative_manifest: str,
        created_at_utc: str,
    ) -> None:
        def reserve(connection) -> None:
            connection.execute("BEGIN IMMEDIATE")
            try:
                count, reserved_bytes = connection.execute(
                    "SELECT COUNT(*), COALESCE(SUM(CASE WHEN format LIKE 'PENDING:%' "
                    "THEN byte_count ELSE byte_count + ? END), 0) FROM export_records",
                    (MAX_MANIFEST_BYTES,),
                ).fetchone()
                reservation = MAX_EXPORT_BYTES + MAX_MANIFEST_BYTES
                if (
                    count >= MAX_WORKSPACE_EXPORTS
                    or reserved_bytes + reservation > MAX_WORKSPACE_EXPORT_BYTES
                ):
                    raise StorageFailure("MONITOR_EXPORT_QUOTA_EXCEEDED", "workspace export quota was exceeded")
                connection.execute(
                    "INSERT INTO export_records(export_id,session_id,format,relative_data_path,relative_manifest_path,sha256,byte_count,value_count,created_at_utc) VALUES (?,?,?,?,?,?,?,?,?)",
                    (
                        str(export_id), request.session_id, f"PENDING:{request.format}",
                        relative_data, relative_manifest, "0" * 64, reservation, 0, created_at_utc,
                    ),
                )
                connection.commit()
            except BaseException:
                connection.rollback()
                raise

        self._database.write(reserve)

    def _mark_ready(self, artifact: ExportArtifact, format_name: str, created_at_utc: str) -> None:
        def ready(connection) -> None:
            connection.execute("BEGIN IMMEDIATE")
            try:
                used_bytes = connection.execute(
                    "SELECT COALESCE(SUM(CASE WHEN format LIKE 'PENDING:%' THEN byte_count "
                    "ELSE byte_count + ? END), 0) FROM export_records WHERE export_id <> ?",
                    (MAX_MANIFEST_BYTES, str(artifact.export_id)),
                ).fetchone()[0]
                if used_bytes + artifact.byte_count + MAX_MANIFEST_BYTES > MAX_WORKSPACE_EXPORT_BYTES:
                    raise StorageFailure("MONITOR_EXPORT_QUOTA_EXCEEDED", "workspace export quota was exceeded")
                cursor = connection.execute(
                    "UPDATE export_records SET format = ?, sha256 = ?, byte_count = ?, value_count = ?, created_at_utc = ? WHERE export_id = ? AND format = ?",
                    (
                        format_name, artifact.sha256, artifact.byte_count, artifact.value_count,
                        created_at_utc, str(artifact.export_id), f"PENDING:{format_name}",
                    ),
                )
                if cursor.rowcount != 1:
                    raise StorageFailure("MONITOR_EXPORT_FAILED", "history export state changed")
                connection.commit()
            except BaseException:
                connection.rollback()
                raise

        self._database.write(ready)

    def _delete_record(self, export_id: UUID, pending_format: str) -> None:
        def remove(connection) -> None:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "DELETE FROM export_records WHERE export_id = ? AND format = ?",
                (str(export_id), pending_format),
            )
            connection.commit()

        self._database.write(remove)

    def _delete_pending_row(self, row_id: int) -> None:
        def remove(connection) -> None:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "DELETE FROM export_records WHERE rowid = ? AND format LIKE 'PENDING:%'",
                (row_id,),
            )
            connection.commit()

        self._database.write(remove)

    def _safe_remove_tree(self, path: Path, *, expected_parent: Path) -> None:
        try:
            self._database._require_path(path)
            if path.parent != expected_parent:
                return
            metadata = os.lstat(path)
            if _redirect(metadata):
                path.unlink()
            elif stat.S_ISDIR(metadata.st_mode):
                shutil.rmtree(path)
        except (FileNotFoundError, OSError, StorageFailure):
            pass

    def _validate_record(self, row: tuple[object, ...], *, pending: bool) -> tuple[ExportArtifact, str, str]:
        (
            raw_export_id, session_id, stored_format, relative_data, relative_manifest,
            digest, byte_count, value_count, created_at_utc,
        ) = row
        if (
            type(raw_export_id) is not str
            or type(session_id) is not str
            or type(stored_format) is not str
            or type(relative_data) is not str
            or type(relative_manifest) is not str
            or type(created_at_utc) is not str
        ):
            raise ValueError("invalid export record")
        export_id = UUID(raw_export_id)
        format_name = stored_format.removeprefix("PENDING:") if pending else stored_format
        require_safe_session_id(session_id)
        if format_name not in {"jsonl", "csv"}:
            raise ValueError("invalid export format")
        expected_data, expected_manifest, data_path, manifest_path = _exact_export_paths(
            self._paths.monitor_root, session_id, export_id, format_name
        )
        if relative_data != expected_data or relative_manifest != expected_manifest:
            raise ValueError("invalid export path")
        self._database._require_path(data_path)
        self._database._require_path(manifest_path)
        manifest_bytes, manifest_size, _ = _read_regular_limited(
            manifest_path, limit=MAX_MANIFEST_BYTES, keep=True
        )
        if manifest_size == 0:
            raise ValueError("invalid export manifest")
        manifest_bytes = cast(bytes, manifest_bytes)
        manifest = json.loads(
            manifest_bytes.decode("utf-8"),
            parse_constant=_invalid_json_constant,
        )
        if type(manifest) is not dict or set(manifest) != _MANIFEST_FIELDS:
            raise ValueError("invalid export manifest")
        manifest_digest = manifest["sha256"]
        manifest_bytes_count = manifest["bytes"]
        manifest_value_count = manifest["valueCount"]
        if (
            manifest["protocol"] != MONITOR_PROTOCOL_VERSION
            or manifest["toolkitVersion"] != TOOLKIT_VERSION
            or manifest["monitorVersion"] != MONITOR_VERSION
            or manifest["workspaceId"] != self._paths.workspace_id
            or manifest["sessionId"] != session_id
            or manifest["exportId"] != str(export_id)
            or manifest["format"] != format_name
            or manifest["createdAtUtc"] != created_at_utc
            or type(manifest_digest) is not str
            or len(manifest_digest) != 64
            or any(character not in "0123456789abcdef" for character in manifest_digest)
            or type(manifest_bytes_count) is not int
            or not 0 <= manifest_bytes_count <= MAX_EXPORT_BYTES
            or type(manifest_value_count) is not int
            or not 0 <= manifest_value_count <= MAX_EXPORT_VALUES
        ):
            raise ValueError("invalid export manifest")
        _, actual_size, actual_digest = _read_regular_limited(data_path, limit=MAX_EXPORT_BYTES, keep=False)
        if actual_size != manifest_bytes_count or actual_digest != manifest_digest:
            raise ValueError("export artifact changed")
        if not pending and (
            digest != manifest_digest
            or byte_count != manifest_bytes_count
            or value_count != manifest_value_count
        ):
            raise ValueError("export record changed")
        artifact = ExportArtifact(
            export_id, data_path.parent, data_path, manifest_path,
            manifest_digest, manifest_bytes_count, manifest_value_count,
        )
        return artifact, format_name, cast(str, created_at_utc)

    def _recover_pending(self) -> bool:
        started_ns = time.monotonic_ns()

        def read(connection):
            return connection.execute(
                "SELECT rowid,export_id,session_id,format,relative_data_path,relative_manifest_path,sha256,byte_count,value_count,created_at_utc FROM export_records WHERE format LIKE 'PENDING:%' ORDER BY created_at_utc, export_id LIMIT ?",
                (MAX_RECOVERY_RECORDS,),
            ).fetchall()

        try:
            rows = self._database.read(read, empty=())
        except StorageFailure:
            return False
        for row in rows:
            if time.monotonic_ns() - started_ns >= RECOVERY_TIME_BUDGET_NS:
                break
            try:
                if type(row[0]) is not int or row[0] < 1:
                    raise ValueError("invalid pending row identity")
                artifact, format_name, created_at_utc = self._validate_record(tuple(row[1:]), pending=True)
                self._mark_ready(artifact, format_name, created_at_utc)
            except (StorageFailure, OSError, ValueError, TypeError, json.JSONDecodeError, UnicodeError, RecursionError):
                try:
                    row_id = cast(int, row[0])
                    self._delete_pending_row(row_id)
                    export_id = UUID(cast(str, row[1]))
                    session_id = cast(str, row[2])
                    session_root = self._paths.monitor_root / "exports" / session_id
                    self._safe_remove_tree(session_root / str(export_id), expected_parent=session_root)
                    self._safe_remove_tree(session_root / f".{export_id}.tmp", expected_parent=session_root)
                except (StorageFailure, OSError, ValueError, TypeError):
                    continue
        try:
            return self._database.read(
                lambda connection: connection.execute(
                    "SELECT 1 FROM export_records WHERE format LIKE 'PENDING:%' LIMIT 1"
                ).fetchone() is not None,
                empty=False,
            )
        except StorageFailure:
            return False

    def _recover_all_pending(self) -> None:
        for _ in range(MAX_WORKSPACE_EXPORTS + 1):
            if not self._recover_pending():
                return

    def create_export(self, request: ExportRequest, *, authorized: object) -> ProtocolResult[ExportArtifact]:
        operation = "exports.create"
        if authorized is not True:
            return failure(operation, "MONITOR_AUTH_REQUIRED", "explicit authorization is required")
        if not isinstance(request, ExportRequest):
            return failure(operation, "MONITOR_REQUEST_INVALID", "export request is invalid")
        self._recover_all_pending()
        export_id = uuid4()
        session_root = self._paths.monitor_root / "exports" / request.session_id
        final_root = session_root / str(export_id)
        temporary_root = session_root / f".{export_id}.tmp"
        extension = "jsonl" if request.format == "jsonl" else "csv"
        data_path = temporary_root / f"history.{extension}"
        manifest_path = temporary_root / "manifest.json"
        relative_data, relative_manifest, _, _ = _exact_export_paths(
            self._paths.monitor_root, request.session_id, export_id, request.format
        )
        created_at_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        reserved = False
        published = False
        try:
            self._reserve_pending(
                export_id, request, relative_data, relative_manifest, created_at_utc
            )
            reserved = True
            self._database.ensure_directory(session_root)
            self._database._require_path(final_root)
            parent_identity = _directory_identity(session_root)
            temporary_root.mkdir(mode=0o700, parents=False, exist_ok=False)
            if _directory_identity(session_root) != parent_identity:
                raise StorageFailure("MONITOR_STORAGE_INVALID", "monitor storage directory changed")
            temporary_metadata = os.lstat(temporary_root)
            if _redirect(temporary_metadata) or not stat.S_ISDIR(temporary_metadata.st_mode):
                raise StorageFailure("MONITOR_STORAGE_INVALID", "monitor storage contains an unsafe directory")
            digest, byte_count, value_count = self._stream_history(request, data_path)
            manifest = {
                "protocol": MONITOR_PROTOCOL_VERSION,
                "toolkitVersion": TOOLKIT_VERSION,
                "monitorVersion": MONITOR_VERSION,
                "workspaceId": self._paths.workspace_id,
                "sessionId": request.session_id,
                "exportId": str(export_id),
                "format": request.format,
                "sha256": digest,
                "bytes": byte_count,
                "valueCount": value_count,
                "createdAtUtc": created_at_utc,
            }
            with _create_regular_exclusive(manifest_path, parent=temporary_root) as stream:
                encoded_manifest = json.dumps(
                    manifest, sort_keys=True, separators=(",", ":"), allow_nan=False
                ).encode("utf-8") + b"\n"
                if len(encoded_manifest) > MAX_MANIFEST_BYTES:
                    raise StorageFailure("MONITOR_EXPORT_FAILED", "history export manifest is invalid")
                stream.write(encoded_manifest)
            _fsync_directory(temporary_root)
            _replace(temporary_root, final_root)
            published = True
            _fsync_directory(session_root)
            published_data = final_root / data_path.name
            published_manifest = final_root / manifest_path.name
            artifact = ExportArtifact(
                export_id, final_root, published_data, published_manifest,
                digest, byte_count, value_count,
            )
            self._mark_ready(artifact, request.format, created_at_utc)
            return success(operation, artifact)
        except StorageFailure as error:
            if error.code in {"MONITOR_EXPORT_TOO_LARGE", "MONITOR_EXPORT_QUOTA_EXCEEDED"}:
                result = failure(operation, error.code, error.public_message)
            elif error.code.startswith("MONITOR_STORAGE"):
                result = failure(operation, error.code, error.public_message)
            else:
                result = failure(operation, "MONITOR_EXPORT_FAILED", "history export failed")
        except (OSError, ValueError, TypeError, UnicodeError, json.JSONDecodeError, RecursionError):
            result = failure(operation, "MONITOR_EXPORT_FAILED", "history export failed")
        recoverable = published and reserved and result.code not in {
            "MONITOR_EXPORT_TOO_LARGE", "MONITOR_EXPORT_QUOTA_EXCEEDED",
        }
        if not recoverable:
            if reserved:
                try:
                    self._delete_record(export_id, f"PENDING:{request.format}")
                except StorageFailure:
                    pass
            self._safe_remove_tree(temporary_root, expected_parent=session_root)
            self._safe_remove_tree(final_root, expected_parent=session_root)
        return result

    def get_export(self, export_id: UUID) -> ProtocolResult[ExportArtifact]:
        operation = "exports.get"
        if not isinstance(export_id, UUID):
            return failure(operation, "MONITOR_REQUEST_INVALID", "export ID is invalid")
        self._recover_all_pending()

        def read(connection):
            return connection.execute(
                "SELECT export_id,session_id,format,relative_data_path,relative_manifest_path,sha256,byte_count,value_count,created_at_utc FROM export_records WHERE export_id = ? AND session_id = ?",
                (str(export_id), self._paths.session_id),
            ).fetchone()

        try:
            row = self._database.read(read, empty=None)
            if row is None:
                return failure(operation, "MONITOR_EXPORT_FAILED", "history export was not found")
            if row[1] != self._paths.session_id:
                return failure(operation, "MONITOR_EXPORT_FAILED", "history export was not found")
            artifact, _, _ = self._validate_record(tuple(row), pending=False)
            return success(operation, artifact)
        except StorageFailure as error:
            return failure(operation, error.code, error.public_message)
        except (OSError, ValueError, TypeError, UnicodeError, json.JSONDecodeError, RecursionError):
            return failure(operation, "MONITOR_EXPORT_FAILED", "history export is unavailable")

    def open_download(self, export_id: UUID) -> ExportDownloadResult:
        if not isinstance(export_id, UUID):
            return ExportDownloadResult(
                False, "MONITOR_REQUEST_INVALID", "export ID is invalid", None
            )
        loaded = self.get_export(export_id)
        if not loaded.ok or loaded.data is None:
            return ExportDownloadResult(False, loaded.code, loaded.message, None)
        artifact = loaded.data
        stream: BinaryIO | None = None
        try:
            stream, byte_count, digest = _open_verified_regular(
                artifact.data_path, limit=MAX_EXPORT_BYTES
            )
            if byte_count != artifact.byte_count or digest != artifact.sha256:
                raise ValueError("export artifact changed")
            format_name = artifact.data_path.suffix.removeprefix(".")
            return ExportDownloadResult(
                True,
                "OK",
                "",
                ExportDownload(
                    stream,
                    export_id=artifact.export_id,
                    format_name=format_name,
                    byte_count=byte_count,
                ),
            )
        except (OSError, ValueError, TypeError):
            if stream is not None:
                stream.close()
            return ExportDownloadResult(
                False,
                "MONITOR_EXPORT_FAILED",
                "history export is unavailable",
                None,
            )

    def close(self) -> None:
        self._database.close()
