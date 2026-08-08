from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from stm32_toolkit.paths import WorkspacePaths, require_safe_session_id

from .history import HistoryQuery, HistoryStore, MAX_HISTORY_VALUES
from .protocol import MONITOR_PROTOCOL_VERSION, ProtocolResult, failure, success
from .storage import MonitorDatabase, StorageFailure


MAX_EXPORT_VALUES = 1_000_000
MAX_EXPORT_BYTES = 64 * 1024 * 1024
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")
_replace = os.replace


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


def _neutralize(value: object) -> object:
    if isinstance(value, str):
        return "'" + value if value.startswith(_FORMULA_PREFIXES) else value
    if isinstance(value, list):
        return [_neutralize(item) for item in value]
    if isinstance(value, dict):
        return {key: _neutralize(item) for key, item in value.items()}
    return value


def _plain(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


class HistoryExporter:
    def __init__(self, paths: WorkspacePaths, history: HistoryStore) -> None:
        if not isinstance(paths, WorkspacePaths) or not isinstance(history, HistoryStore):
            raise TypeError("exporter requires workspace paths and history store")
        self._paths = paths
        self._history = history
        self._database = MonitorDatabase(paths)

    def _collect(self, request: ExportRequest) -> ProtocolResult[tuple[dict[str, object], ...]]:
        values: list[dict[str, object]] = []
        cursor: str | None = None
        while True:
            page = self._history.query_history(
                HistoryQuery(request.session_id, request.start_ns, request.end_ns, limit=MAX_HISTORY_VALUES, cursor=cursor)
            )
            if not page.ok:
                return failure("exports.create", page.code, page.message)
            for value in page.data.values:
                values.append(dict(value))
                if len(values) > MAX_EXPORT_VALUES:
                    return failure("exports.create", "MONITOR_EXPORT_TOO_LARGE", "export value limit was exceeded")
            cursor = page.data.next_cursor
            if cursor is None:
                break
        return success("exports.collect", tuple(values))

    @staticmethod
    def _encode(values: tuple[dict[str, object], ...], format_name: str, target: Path) -> tuple[str, int]:
        digest = hashlib.sha256()
        byte_count = 0
        mode = "wb" if format_name == "jsonl" else "w"
        kwargs = {} if format_name == "jsonl" else {"encoding": "utf-8", "newline": ""}
        with target.open(mode, **kwargs) as stream:
            if format_name == "jsonl":
                for value in values:
                    line = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"
                    byte_count += len(line)
                    if byte_count > MAX_EXPORT_BYTES:
                        raise StorageFailure("MONITOR_EXPORT_TOO_LARGE", "export byte limit was exceeded")
                    stream.write(line)
                    digest.update(line)
                stream.flush()
                os.fsync(stream.fileno())
            else:
                fieldnames = (
                    "capturedUnixNs", "sessionId", "runId", "sequence", "groupId", "groupRevision",
                    "watch", "status", "typedValue", "code", "definition",
                )
                writer = csv.DictWriter(stream, fieldnames=fieldnames, extrasaction="ignore", lineterminator="\n")
                writer.writeheader()
                for value in values:
                    safe = _neutralize(value)
                    writer.writerow(
                        {
                            key: json.dumps(safe.get(key), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                            if key in {"watch", "typedValue", "definition"}
                            else safe.get(key)
                            for key in fieldnames
                        }
                    )
                stream.flush()
                os.fsync(stream.fileno())
        if format_name == "csv":
            data = target.read_bytes()
            byte_count = len(data)
            if byte_count > MAX_EXPORT_BYTES:
                raise StorageFailure("MONITOR_EXPORT_TOO_LARGE", "export byte limit was exceeded")
            digest.update(data)
        return digest.hexdigest(), byte_count

    def create_export(self, request: ExportRequest, *, authorized: object) -> ProtocolResult[ExportArtifact]:
        operation = "exports.create"
        if authorized is not True:
            return failure(operation, "MONITOR_AUTH_REQUIRED", "explicit authorization is required")
        if not isinstance(request, ExportRequest):
            return failure(operation, "MONITOR_REQUEST_INVALID", "export request is invalid")
        collected = self._collect(request)
        if not collected.ok:
            return failure(operation, collected.code, collected.message)
        values = tuple(_plain(value) for value in collected.data)
        export_id = uuid4()
        session_root = self._paths.monitor_root / "exports" / request.session_id
        final_root = session_root / str(export_id)
        temporary_root = session_root / f".{export_id}.tmp"
        extension = "jsonl" if request.format == "jsonl" else "csv"
        data_path = temporary_root / f"history.{extension}"
        manifest_path = temporary_root / "manifest.json"
        try:
            self._database._require_path(final_root)
            session_root.mkdir(parents=True, exist_ok=True)
            self._database._require_path(final_root)
            temporary_root.mkdir()
            digest, byte_count = self._encode(values, request.format, data_path)
            manifest = {
                "protocol": MONITOR_PROTOCOL_VERSION,
                "workspaceId": self._paths.workspace_id,
                "sessionId": request.session_id,
                "exportId": str(export_id),
                "format": request.format,
                "sha256": digest,
                "bytes": byte_count,
                "valueCount": len(values),
                "createdAtUtc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            }
            with manifest_path.open("wb") as stream:
                stream.write(json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n")
                stream.flush()
                os.fsync(stream.fileno())
            _replace(temporary_root, final_root)
            published_data = final_root / data_path.name
            published_manifest = final_root / manifest_path.name
            artifact = ExportArtifact(export_id, final_root, published_data, published_manifest, digest, byte_count, len(values))

            def record(connection):
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    "INSERT INTO export_records(export_id,session_id,format,relative_data_path,relative_manifest_path,sha256,byte_count,value_count,created_at_utc) VALUES (?,?,?,?,?,?,?,?,?)",
                    (
                        str(export_id), request.session_id, request.format,
                        published_data.relative_to(self._paths.monitor_root).as_posix(),
                        published_manifest.relative_to(self._paths.monitor_root).as_posix(),
                        digest, byte_count, len(values), manifest["createdAtUtc"],
                    ),
                )
                connection.commit()

            self._database.write(record)
            return success(operation, artifact)
        except StorageFailure as error:
            if error.code == "MONITOR_EXPORT_TOO_LARGE":
                result = failure(operation, error.code, error.public_message)
            else:
                result = failure(operation, "MONITOR_EXPORT_FAILED", "history export failed")
        except (OSError, ValueError):
            result = failure(operation, "MONITOR_EXPORT_FAILED", "history export failed")
        for candidate in (temporary_root, final_root):
            try:
                if candidate.exists() and candidate.is_dir() and candidate.parent == session_root:
                    shutil.rmtree(candidate)
            except OSError:
                pass
        return result

    def get_export(self, export_id: UUID) -> ProtocolResult[ExportArtifact]:
        operation = "exports.get"
        if not isinstance(export_id, UUID):
            return failure(operation, "MONITOR_REQUEST_INVALID", "export ID is invalid")

        def read(connection):
            return connection.execute(
                "SELECT session_id,format,relative_data_path,relative_manifest_path,sha256,byte_count,value_count FROM export_records WHERE export_id = ?",
                (str(export_id),),
            ).fetchone()

        try:
            row = self._database.read(read, empty=None)
            if row is None:
                return failure(operation, "MONITOR_EXPORT_FAILED", "history export was not found")
            session_id, format_name, relative_data, relative_manifest, digest, byte_count, value_count = row
            if format_name not in {"jsonl", "csv"} or not isinstance(relative_data, str) or not isinstance(relative_manifest, str):
                raise ValueError("invalid export record")
            data_path = self._paths.monitor_root / relative_data
            manifest_path = self._paths.monitor_root / relative_manifest
            self._database._require_path(data_path)
            self._database._require_path(manifest_path)
            if not data_path.is_file() or not manifest_path.is_file():
                raise ValueError("export artifact missing")
            actual = data_path.read_bytes()
            if len(actual) != byte_count or hashlib.sha256(actual).hexdigest() != digest:
                raise ValueError("export artifact changed")
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if (
                not isinstance(manifest, dict)
                or manifest.get("exportId") != str(export_id)
                or manifest.get("workspaceId") != self._paths.workspace_id
                or manifest.get("sessionId") != session_id
                or manifest.get("format") != format_name
                or manifest.get("sha256") != digest
                or manifest.get("bytes") != byte_count
                or manifest.get("valueCount") != value_count
            ):
                raise ValueError("export manifest changed")
            directory = data_path.parent
            return success(
                operation,
                ExportArtifact(export_id, directory, data_path, manifest_path, digest, byte_count, value_count),
            )
        except StorageFailure as error:
            return failure(operation, error.code, error.public_message)
        except (OSError, ValueError, json.JSONDecodeError):
            return failure(operation, "MONITOR_EXPORT_FAILED", "history export is unavailable")

    def close(self) -> None:
        self._database.close()
