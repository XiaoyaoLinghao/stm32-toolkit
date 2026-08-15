"""Derived SQLite search catalog for immutable evidence manifests."""

from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass, field
from datetime import datetime
import os
from pathlib import Path
import re
import sqlite3
import stat
import tempfile
from uuid import UUID

from .model import EvidenceEnvelope, EvidenceValidationError
from .store import EvidenceStore


_HASH = re.compile(r"^[0-9a-f]{64}$")
_SESSION = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
_UTC = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z$")
_CATALOG_NAME = "catalog.sqlite3"
_SCHEMA = """
CREATE TABLE evidence (
    evidence_id TEXT PRIMARY KEY NOT NULL,
    workspace_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    build_id TEXT NOT NULL,
    elf_sha256 TEXT NOT NULL,
    operation TEXT NOT NULL,
    produced_at_utc TEXT NOT NULL
) WITHOUT ROWID;
CREATE INDEX evidence_search_order ON evidence (produced_at_utc, evidence_id);
"""


def _string(field_name: str, value: object) -> str:
    if not isinstance(value, str) or not value or len(value.encode("utf-8")) > 64 * 1024:
        raise EvidenceValidationError(f"{field_name} must be a bounded non-empty string")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise EvidenceValidationError(f"{field_name} contains a control character")
    return value


def _hash(field_name: str, value: object) -> str:
    string = _string(field_name, value)
    if _HASH.fullmatch(string) is None:
        raise EvidenceValidationError(f"{field_name} must be a lowercase SHA-256")
    return string


def _project(value: object) -> str:
    string = _string("project_id", value)
    try:
        parsed = UUID(string)
    except ValueError as exc:
        raise EvidenceValidationError("project_id must be a canonical UUID") from exc
    if str(parsed) != string:
        raise EvidenceValidationError("project_id must be a lowercase canonical UUID")
    return string


def _session(value: object) -> str:
    string = _string("session_id", value)
    if _SESSION.fullmatch(string) is None:
        raise EvidenceValidationError("session_id must be lowercase ASCII")
    return string


def _utc(field_name: str, value: object) -> str:
    string = _string(field_name, value)
    if _UTC.fullmatch(string) is None:
        raise EvidenceValidationError(f"{field_name} must use canonical UTC microseconds")
    try:
        datetime.strptime(string, "%Y-%m-%dT%H:%M:%S.%fZ")
    except ValueError as exc:
        raise EvidenceValidationError(f"{field_name} is not a valid UTC timestamp") from exc
    return string


@dataclass(frozen=True)
class EvidenceSummary:
    """A non-authoritative search projection; actions must use store.get_envelope()."""

    evidence_id: str
    workspace_id: str
    project_id: str
    session_id: str
    build_id: str
    elf_sha256: str
    operation: str
    produced_at_utc: str
    authoritative: bool = field(default=False, init=False, compare=False)

    def __post_init__(self) -> None:
        _hash("evidence_id", self.evidence_id)
        _hash("workspace_id", self.workspace_id)
        _project(self.project_id)
        _session(self.session_id)
        _hash("build_id", self.build_id)
        _hash("elf_sha256", self.elf_sha256)
        _string("operation", self.operation)
        _utc("produced_at_utc", self.produced_at_utc)

    @classmethod
    def from_envelope(cls, envelope: EvidenceEnvelope) -> "EvidenceSummary":
        if not isinstance(envelope, EvidenceEnvelope):
            raise EvidenceValidationError("catalog summary source is not an EvidenceEnvelope")
        identity = envelope.identity
        return cls(
            evidence_id=str(envelope.evidence_id),
            workspace_id=identity.workspace_id,
            project_id=identity.project_id,
            session_id=identity.session_id,
            build_id=identity.build_id,
            elf_sha256=identity.elf_sha256,
            operation=envelope.operation,
            produced_at_utc=envelope.produced_at_utc,
        )


class EvidenceCatalog:
    """Read-only query facade over catalog.sqlite3 derived from one EvidenceStore."""

    def __init__(self, store: EvidenceStore | Path | str) -> None:
        self.store = store if isinstance(store, EvidenceStore) else EvidenceStore(store)
        self.path = self.store.root / _CATALOG_NAME

    def query(
        self,
        *,
        workspace_id: str | None = None,
        project_id: str | None = None,
        session_id: str | None = None,
        build_id: str | None = None,
        elf_sha256: str | None = None,
        operation: str | None = None,
        produced_at_utc_from: str | None = None,
        produced_at_utc_to: str | None = None,
        limit: int = 100,
    ) -> list[EvidenceSummary]:
        if type(limit) is not int or not 1 <= limit <= 1_000:
            raise EvidenceValidationError("limit must be an integer from 1 through 1000")
        filters: list[str] = []
        values: list[object] = []
        validators = (
            ("workspace_id", workspace_id, _hash),
            ("project_id", project_id, lambda _field, value: _project(value)),
            ("session_id", session_id, lambda _field, value: _session(value)),
            ("build_id", build_id, _hash),
            ("elf_sha256", elf_sha256, _hash),
            ("operation", operation, lambda field_name, value: _string(field_name, value)),
        )
        for column, raw_value, validator in validators:
            if raw_value is not None:
                filters.append(f"{column} = ?")
                values.append(validator(column, raw_value))
        start = _utc("produced_at_utc_from", produced_at_utc_from) if produced_at_utc_from is not None else None
        end = _utc("produced_at_utc_to", produced_at_utc_to) if produced_at_utc_to is not None else None
        if start is not None and end is not None and start > end:
            raise EvidenceValidationError("UTC range start must not be after its end")
        if start is not None:
            filters.append("produced_at_utc >= ?")
            values.append(start)
        if end is not None:
            filters.append("produced_at_utc <= ?")
            values.append(end)
        values.append(limit)
        where = f" WHERE {' AND '.join(filters)}" if filters else ""
        statement = (
            "SELECT evidence_id, workspace_id, project_id, session_id, build_id, "
            "elf_sha256, operation, produced_at_utc FROM evidence"
            f"{where} ORDER BY produced_at_utc, evidence_id LIMIT ?"
        )

        self.store._reject_casefold_collision(self.store.root, _CATALOG_NAME)
        self.store._validate_existing_path(self.path, regular=True, single_link=True)
        uri = self.path.as_uri() + "?mode=ro"
        try:
            with closing(sqlite3.connect(uri, uri=True)) as database:
                database.execute("PRAGMA query_only = ON")
                rows = database.execute(statement, values).fetchall()
            return [EvidenceSummary(*row) for row in rows]
        except (sqlite3.DatabaseError, TypeError, ValueError) as exc:
            if isinstance(exc, EvidenceValidationError):
                raise
            raise EvidenceValidationError("catalog contains corrupt schema or row data") from exc

    def get_envelope(self, evidence_id: str) -> EvidenceEnvelope:
        """Cross the authority boundary explicitly through the store's verified read."""
        return self.store.get_envelope(evidence_id)

    def rebuild(self) -> Path:
        return rebuild_catalog(self.store, self)


def _manifest_names(store: EvidenceStore) -> list[str]:
    directory = store._managed_directory("manifests")
    names: list[str] = []
    folded: dict[str, str] = {}
    for entry in directory.iterdir():
        prior = folded.setdefault(entry.name.casefold(), entry.name)
        if prior != entry.name:
            raise EvidenceValidationError(
                f"manifest directory has a case-fold collision: {prior!r} and {entry.name!r}"
            )
        info = store._validate_existing_path(entry, regular=True, single_link=True)
        if not stat.S_ISREG(info.st_mode):
            raise EvidenceValidationError(f"manifest entry is not a regular file: {entry}")
        if not entry.name.endswith(".json") or _HASH.fullmatch(entry.name[:-5]) is None:
            raise EvidenceValidationError(f"manifest directory contains an invalid entry: {entry.name}")
        names.append(entry.name)
    return sorted(names, key=lambda name: name.encode("utf-8"))


def rebuild_catalog(
    store: EvidenceStore | Path | str,
    catalog: EvidenceCatalog | None = None,
) -> Path:
    """Verify all manifests and atomically replace the complete derived catalog."""
    evidence_store = store if isinstance(store, EvidenceStore) else EvidenceStore(store)
    evidence_catalog = catalog or EvidenceCatalog(evidence_store)
    if evidence_catalog.store.root != evidence_store.root:
        raise EvidenceValidationError("catalog and evidence store roots must match")
    evidence_store._ensure_root()

    summaries = [
        EvidenceSummary.from_envelope(evidence_store.get_envelope(name[:-5]))
        for name in _manifest_names(evidence_store)
    ]
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".catalog-", suffix=".tmp", dir=evidence_store.root
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        with closing(sqlite3.connect(temporary)) as database:
            database.execute("PRAGMA journal_mode = DELETE")
            database.execute("PRAGMA synchronous = FULL")
            database.executescript(_SCHEMA)
            database.executemany(
                "INSERT INTO evidence VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        row.evidence_id,
                        row.workspace_id,
                        row.project_id,
                        row.session_id,
                        row.build_id,
                        row.elf_sha256,
                        row.operation,
                        row.produced_at_utc,
                    )
                    for row in summaries
                ],
            )
            database.commit()
        evidence_store._fault("catalog.after_flush")
        file_descriptor = os.open(temporary, os.O_RDWR | getattr(os, "O_BINARY", 0))
        try:
            os.fsync(file_descriptor)
        finally:
            os.close(file_descriptor)
        evidence_store._fault("catalog.after_fsync")

        evidence_store._reject_casefold_collision(evidence_store.root, _CATALOG_NAME)
        try:
            evidence_store._validate_existing_path(
                evidence_catalog.path, regular=True, single_link=True
            )
        except FileNotFoundError:
            pass
        evidence_store._fault("catalog.before_publish")
        os.replace(temporary, evidence_catalog.path)
        evidence_store._fault("catalog.after_publish")
        evidence_store._flush_directory(evidence_store.root)
        evidence_store._fault("catalog.after_directory_fsync")
    except (sqlite3.DatabaseError, OSError):
        raise
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
    evidence_store._validate_existing_path(
        evidence_catalog.path, regular=True, single_link=True
    )
    return evidence_catalog.path


__all__ = ["EvidenceCatalog", "EvidenceSummary", "rebuild_catalog"]
