"""Crash-safe append-only persistence for the closed VS-02 diagnostic domain."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import stat
from typing import NoReturn, cast

from stm32_toolkit.evidence import (
    EVIDENCE_LIMIT_EXCEEDED,
    EvidenceEnvelope,
    EvidenceIdentity,
    EvidenceValidationError,
)
from stm32_toolkit.evidence.gc import RootRecord, get_root, put_root
from stm32_toolkit.evidence.store import EvidenceStore

from .events import reduce_event
from .model import (
    DIAGNOSTIC_CHAIN_CORRUPT,
    DIAGNOSTIC_EVIDENCE_MISSING,
    DIAGNOSTIC_IDENTITY_MISMATCH,
    DIAGNOSTIC_INVALID_EVENT,
    DIAGNOSTIC_LIMIT_EXCEEDED,
    DIAGNOSTIC_NOT_FOUND,
    DIAGNOSTIC_OPERATION_CONFLICT,
    DIAGNOSTIC_REVISION_CONFLICT,
    MAX_EVENT_BYTES,
    MAX_EVENTS,
    DiagnosticMarkerRef,
    DiagnosticEvent,
    DiagnosticSession,
    DiagnosticValidationError,
    FixVerification,
    SourceChangeDeclaration,
    VerificationPlan,
    canonical_diagnostic_json_bytes,
)


_SESSION_ID = re.compile(r"^[0-9a-f]{32}$")
_EVENT_NAME = re.compile(r"^[0-9]{8}\.json$")
_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
_LOCK_NAME = ".diagnostic.lock"
_SESSIONS_NAME = "sessions"
_EVENTS_NAME = "events"
_EVENT_KIND = "diagnostic-event"
_EVENT_MEDIA_TYPE = "application/json"
_ROOT_TYPE = "diagnostic-session"
_MAX_SESSIONS = 64


def _raise(code: str) -> NoReturn:
    raise DiagnosticValidationError(code)


def _same_identity(left: EvidenceIdentity, right: EvidenceIdentity) -> bool:
    return left.to_dict() == right.to_dict()


def _same_scope(left: EvidenceIdentity, right: EvidenceIdentity) -> bool:
    return (
        left.workspace_id == right.workspace_id
        and left.project_id == right.project_id
        and left.target_device == right.target_device
    )


def _same_after_identity(identity: EvidenceIdentity, declaration: SourceChangeDeclaration) -> bool:
    return (
        identity.input_snapshot_sha256 == declaration.after_source_sha256
        and identity.build_id == declaration.after_build_id
        and identity.elf_sha256 == declaration.after_elf_sha256
    )


def _is_reparse(info: os.stat_result) -> bool:
    return bool(getattr(info, "st_file_attributes", 0) & _REPARSE_POINT)


def _is_link_or_reparse(info: os.stat_result) -> bool:
    return stat.S_ISLNK(info.st_mode) or _is_reparse(info)


def _intent(event: DiagnosticEvent) -> tuple[str, str, bytes]:
    payload = event.to_dict()["payload"]
    assert isinstance(payload, dict)
    request = payload["request"]
    assert isinstance(request, dict)
    return event.event_type, event.actor, canonical_diagnostic_json_bytes(request)


def _event_references(event: DiagnosticEvent) -> tuple[str, ...]:
    payload = event.to_dict()["payload"]
    assert isinstance(payload, dict)
    result = payload["result"]
    assert isinstance(result, dict)
    references: list[str] = []
    if event.event_type == "session.created":
        references.append(cast(str, result["failed_evidence_id"]))
    elif event.event_type == "observation.plan_executed":
        values = result["observation_results"]
        assert isinstance(values, list)
        references.extend(cast(str, item["evidence_id"]) for item in values if isinstance(item, dict))
    elif event.event_type == "hypothesis.assessed":
        assessment = result["assessment"]
        assert isinstance(assessment, dict)
        references.append(cast(str, assessment["evidence_id"]))
    elif event.event_type == "source_change.declared":
        request = payload["request"]
        assert isinstance(request, dict)
        declaration = SourceChangeDeclaration.from_value(request["source_change_declaration"])
        references.append(declaration.diff_evidence_id)
    elif event.event_type == "verification.plan_added":
        request = payload["request"]
        assert isinstance(request, dict)
        plan = VerificationPlan.from_value(request["verification_plan"])
        references.extend(
            (
                plan.failed_before_evidence_id,
                plan.fixed_after_evidence_id,
                *plan.required_analysis_evidence_ids,
            )
        )
    elif event.event_type == "analysis.marker_attached":
        request = payload["request"]
        assert isinstance(request, dict)
        marker = DiagnosticMarkerRef.from_value(request["diagnostic_marker_ref"])
        references.extend((marker.marker_evidence_id, marker.analysis_evidence_id))
    elif event.event_type == "verification.completed":
        request = payload["request"]
        assert isinstance(request, dict)
        verification = FixVerification.from_value(request["fix_verification"])
        references.extend(
            (
                verification.failed_before_evidence_id,
                verification.fixed_after_evidence_id,
                *verification.analysis_evidence_ids,
            )
        )
    if event.event_type in {
        "source_change.declared",
        "verification.plan_added",
        "verification.started",
        "analysis.marker_attached",
        "verification.completed",
    }:
        return tuple(dict.fromkeys(references))
    return tuple(sorted(set(references)))


@dataclass(frozen=True)
class DiagnosticMutationRecord:
    """The exact accepted event and the current authoritative session."""

    session: DiagnosticSession
    event: DiagnosticEvent
    appended: bool

    def __post_init__(self) -> None:
        if not isinstance(self.session, DiagnosticSession):
            _raise(DIAGNOSTIC_INVALID_EVENT)
        if not isinstance(self.event, DiagnosticEvent):
            _raise(DIAGNOSTIC_INVALID_EVENT)
        if type(self.appended) is not bool:
            _raise(DIAGNOSTIC_INVALID_EVENT)

    def to_dict(self) -> dict[str, object]:
        return {
            "session": self.session.to_dict(),
            "event": self.event.to_dict(),
            "appended": self.appended,
        }


class DiagnosticStore:
    """An append-only diagnostic event store with immutable Evidence checkpoints."""

    def __init__(
        self,
        diagnostics_root: Path | str,
        evidence_store: EvidenceStore,
        *,
        fault_injector: Callable[[str], None] | None = None,
    ) -> None:
        if not isinstance(evidence_store, EvidenceStore):
            _raise(DIAGNOSTIC_INVALID_EVENT)
        try:
            root = Path(diagnostics_root)
        except (TypeError, ValueError):
            _raise(DIAGNOSTIC_INVALID_EVENT)
        self.diagnostics_root = root if root.is_absolute() else root.absolute()
        self.evidence_store = evidence_store
        self._fault_injector = fault_injector

    def _fault(self, point: str) -> None:
        if self._fault_injector is not None:
            self._fault_injector(point)

    @classmethod
    def _existing(cls, path: Path) -> os.stat_result:
        """lstat every component and reject links/reparse points before use."""

        absolute = path if path.is_absolute() else path.absolute()
        parts = absolute.parts
        if not parts:
            _raise(DIAGNOSTIC_CHAIN_CORRUPT)
        current = Path(parts[0])
        for part in parts[1:]:
            current = current / part
            info = current.lstat()
            if _is_link_or_reparse(info):
                _raise(DIAGNOSTIC_CHAIN_CORRUPT)
        info = absolute.lstat()
        if _is_link_or_reparse(info):
            _raise(DIAGNOSTIC_CHAIN_CORRUPT)
        return info

    @classmethod
    def _regular_single(cls, path: Path) -> os.stat_result:
        info = cls._existing(path)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            _raise(DIAGNOSTIC_CHAIN_CORRUPT)
        return info

    @staticmethod
    def _children(parent: Path) -> list[Path]:
        try:
            children = list(parent.iterdir())
        except (OSError, ValueError):
            _raise(DIAGNOSTIC_CHAIN_CORRUPT)
        folded: dict[str, str] = {}
        for child in children:
            key = child.name.casefold()
            previous = folded.get(key)
            if previous is not None and previous != child.name:
                _raise(DIAGNOSTIC_CHAIN_CORRUPT)
            folded[key] = child.name
        return children

    @classmethod
    def _require_directory(cls, path: Path) -> None:
        info = cls._existing(path)
        if not stat.S_ISDIR(info.st_mode):
            _raise(DIAGNOSTIC_CHAIN_CORRUPT)

    @classmethod
    def _mkdir_checked(cls, path: Path) -> None:
        parent = path.parent
        try:
            cls._require_directory(parent)
        except FileNotFoundError:
            _raise(DIAGNOSTIC_CHAIN_CORRUPT)
        try:
            path.mkdir()
        except FileExistsError:
            pass
        except OSError:
            _raise(DIAGNOSTIC_CHAIN_CORRUPT)
        cls._require_directory(path)

    def _ensure_root(self) -> None:
        root = self.diagnostics_root
        try:
            info = self._existing(root)
        except FileNotFoundError:
            try:
                self._require_directory(root.parent)
                root.mkdir()
            except FileExistsError:
                pass
            except (OSError, DiagnosticValidationError):
                _raise(DIAGNOSTIC_CHAIN_CORRUPT)
            info = self._existing(root)
        if not stat.S_ISDIR(info.st_mode):
            _raise(DIAGNOSTIC_CHAIN_CORRUPT)

    def _ensure_lock_file(self) -> Path:
        lock = self.diagnostics_root / _LOCK_NAME
        try:
            info = self._regular_single(lock)
        except FileNotFoundError:
            descriptor = -1
            try:
                descriptor = os.open(
                    lock,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0),
                    0o600,
                )
                os.write(descriptor, b"\0")
                os.fsync(descriptor)
            except FileExistsError:
                pass
            except OSError:
                _raise(DIAGNOSTIC_CHAIN_CORRUPT)
            finally:
                if descriptor >= 0:
                    os.close(descriptor)
            info = self._regular_single(lock)
        if info.st_size != 1:
            _raise(DIAGNOSTIC_CHAIN_CORRUPT)
        return lock

    def _validate_root_primitives(self, *, create: bool) -> None:
        if create:
            self._ensure_root()
        else:
            try:
                self._require_directory(self.diagnostics_root)
            except FileNotFoundError:
                _raise(DIAGNOSTIC_NOT_FOUND)
        root_children = self._children(self.diagnostics_root)
        names = {child.name for child in root_children}
        allowed = {_LOCK_NAME, _SESSIONS_NAME}
        if not names <= allowed:
            _raise(DIAGNOSTIC_CHAIN_CORRUPT)
        if create:
            self._ensure_lock_file()
            sessions = self.diagnostics_root / _SESSIONS_NAME
            try:
                self._require_directory(sessions)
            except FileNotFoundError:
                self._mkdir_checked(sessions)
        else:
            lock = self.diagnostics_root / _LOCK_NAME
            sessions = self.diagnostics_root / _SESSIONS_NAME
            try:
                self._regular_single(lock)
                self._require_directory(sessions)
            except FileNotFoundError:
                _raise(DIAGNOSTIC_CHAIN_CORRUPT)

    def _validate_root_layout(self, *, create: bool) -> None:
        self._validate_root_primitives(create=create)
        self._validate_sessions_layout()

    def _validate_sessions_layout(self) -> tuple[str, ...]:
        sessions = self.diagnostics_root / _SESSIONS_NAME
        children = self._children(sessions)
        result: list[str] = []
        for child in children:
            if not _SESSION_ID.fullmatch(child.name):
                _raise(DIAGNOSTIC_CHAIN_CORRUPT)
            self._require_directory(child)
            session_children = self._children(child)
            if {entry.name for entry in session_children} != {_EVENTS_NAME}:
                _raise(DIAGNOSTIC_CHAIN_CORRUPT)
            events = child / _EVENTS_NAME
            self._require_directory(events)
            self._event_paths(events)
            result.append(child.name)
        if len(result) > _MAX_SESSIONS:
            _raise(DIAGNOSTIC_LIMIT_EXCEEDED)
        return tuple(sorted(result))

    def _prepare_session_directories(self, session_id: str) -> Path:
        sessions = self.diagnostics_root / _SESSIONS_NAME
        session_dir = sessions / session_id
        if session_dir.exists():
            self._require_directory(session_dir)
        else:
            self._mkdir_checked(session_dir)
        children = self._children(session_dir)
        if {child.name for child in children} - {_EVENTS_NAME}:
            _raise(DIAGNOSTIC_CHAIN_CORRUPT)
        events = session_dir / _EVENTS_NAME
        if events.exists():
            self._require_directory(events)
        else:
            self._mkdir_checked(events)
        return events

    def _session_events_directory(self, session_id: str) -> Path:
        session_dir = self.diagnostics_root / _SESSIONS_NAME / session_id
        try:
            self._require_directory(session_dir)
            children = self._children(session_dir)
            if {child.name for child in children} != {_EVENTS_NAME}:
                _raise(DIAGNOSTIC_CHAIN_CORRUPT)
            events = session_dir / _EVENTS_NAME
            self._require_directory(events)
            return events
        except FileNotFoundError:
            _raise(DIAGNOSTIC_NOT_FOUND)

    @staticmethod
    def _flush_directory(path: Path) -> None:
        if os.name == "nt":
            return
        try:  # pragma: no cover - CPython Windows is the primary acceptance host
            descriptor = os.open(path, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        except OSError:
            _raise(DIAGNOSTIC_CHAIN_CORRUPT)

    @contextmanager
    def _store_lock(self, *, create: bool):
        # Only the immutable root/lock/sessions container shape may be
        # inspected before acquiring the lock. Session and event children can
        # be temporarily incomplete while another writer is publishing one.
        self._validate_root_primitives(create=create)
        lock_path = self.diagnostics_root / _LOCK_NAME
        before = self._regular_single(lock_path)
        flags = os.O_RDWR | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = -1
        locked = False
        try:
            descriptor = os.open(lock_path, flags)
        except OSError:
            _raise(DIAGNOSTIC_CHAIN_CORRUPT)
        try:
            opened = os.fstat(descriptor)
            if not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1 or opened.st_size != 1:
                _raise(DIAGNOSTIC_CHAIN_CORRUPT)
            current = self._regular_single(lock_path)
            if (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino) or (
                current.st_dev,
                current.st_ino,
            ) != (opened.st_dev, opened.st_ino):
                _raise(DIAGNOSTIC_CHAIN_CORRUPT)
            os.lseek(descriptor, 0, os.SEEK_SET)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(descriptor, msvcrt.LK_LOCK, 1)
            else:  # pragma: no cover - the acceptance owner exercises this on Windows
                import fcntl

                fcntl.flock(descriptor, fcntl.LOCK_EX)
            locked = True
            held = self._regular_single(lock_path)
            if (held.st_dev, held.st_ino) != (opened.st_dev, opened.st_ino):
                _raise(DIAGNOSTIC_CHAIN_CORRUPT)
            self._validate_root_layout(create=False)
            yield
        except OSError:
            _raise(DIAGNOSTIC_CHAIN_CORRUPT)
        finally:
            if locked:
                os.lseek(descriptor, 0, os.SEEK_SET)
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
                else:  # pragma: no cover - the acceptance owner exercises this on Windows
                    import fcntl

                    fcntl.flock(descriptor, fcntl.LOCK_UN)
            if descriptor >= 0:
                os.close(descriptor)

    @classmethod
    def _read_event_file(cls, path: Path) -> DiagnosticEvent:
        try:
            info = cls._regular_single(path)
            if info.st_size > MAX_EVENT_BYTES:
                _raise(DIAGNOSTIC_CHAIN_CORRUPT)
            descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0))
            try:
                opened = os.fstat(descriptor)
                if (opened.st_dev, opened.st_ino, opened.st_nlink) != (info.st_dev, info.st_ino, 1):
                    _raise(DIAGNOSTIC_CHAIN_CORRUPT)
                payload = b""
                while True:
                    chunk = os.read(descriptor, MAX_EVENT_BYTES + 1 - len(payload))
                    if not chunk:
                        break
                    payload += chunk
                    if len(payload) > MAX_EVENT_BYTES:
                        _raise(DIAGNOSTIC_CHAIN_CORRUPT)
                after = os.fstat(descriptor)
                if (after.st_dev, after.st_ino, after.st_nlink, after.st_size) != (
                    opened.st_dev,
                    opened.st_ino,
                    1,
                    len(payload),
                ):
                    _raise(DIAGNOSTIC_CHAIN_CORRUPT)
            finally:
                os.close(descriptor)
        except FileNotFoundError:
            _raise(DIAGNOSTIC_CHAIN_CORRUPT)
        except OSError:
            _raise(DIAGNOSTIC_CHAIN_CORRUPT)
        try:
            decoded = cls._decode_json(payload)
            if canonical_diagnostic_json_bytes(decoded) != payload:
                _raise(DIAGNOSTIC_CHAIN_CORRUPT)
            return DiagnosticEvent.from_value(decoded)
        except DiagnosticValidationError:
            _raise(DIAGNOSTIC_CHAIN_CORRUPT)
        except (TypeError, ValueError, UnicodeError, json.JSONDecodeError):
            _raise(DIAGNOSTIC_CHAIN_CORRUPT)

    @staticmethod
    def _decode_json(payload: bytes) -> object:
        if payload.startswith(b"\xef\xbb\xbf"):
            _raise(DIAGNOSTIC_CHAIN_CORRUPT)

        def pairs(items: list[tuple[str, object]]) -> dict[str, object]:
            result: dict[str, object] = {}
            for key, value in items:
                if key in result:
                    _raise(DIAGNOSTIC_CHAIN_CORRUPT)
                result[key] = value
            return result

        try:
            return json.loads(payload.decode("utf-8"), object_pairs_hook=pairs, parse_constant=lambda value: _raise(DIAGNOSTIC_CHAIN_CORRUPT))
        except DiagnosticValidationError:
            raise
        except (UnicodeError, json.JSONDecodeError, TypeError, ValueError):
            _raise(DIAGNOSTIC_CHAIN_CORRUPT)

    @classmethod
    def _event_paths(cls, events: Path) -> tuple[Path, ...]:
        children = cls._children(events)
        names = [child.name for child in children]
        if not names:
            _raise(DIAGNOSTIC_CHAIN_CORRUPT)
        if any(_EVENT_NAME.fullmatch(name) is None for name in names):
            _raise(DIAGNOSTIC_CHAIN_CORRUPT)
        numeric = sorted(int(name[:8]) for name in names)
        if numeric != list(range(len(numeric))):
            _raise(DIAGNOSTIC_CHAIN_CORRUPT)
        paths = tuple(events / f"{sequence:08d}.json" for sequence in numeric)
        for path in paths:
            cls._regular_single(path)
        return paths

    def _load_chain_locked(
        self, session_id: str
    ) -> tuple[DiagnosticSession, tuple[DiagnosticEvent, ...]]:
        events_dir = self._session_events_directory(session_id)
        paths = self._event_paths(events_dir)
        if len(paths) > MAX_EVENTS:
            _raise(DIAGNOSTIC_LIMIT_EXCEEDED)
        session: DiagnosticSession | None = None
        events: list[DiagnosticEvent] = []
        operation_ids: set[str] = set()
        for sequence, path in enumerate(paths):
            event = self._read_event_file(path)
            if event.diagnostic_session_id != session_id or event.sequence != sequence:
                _raise(DIAGNOSTIC_CHAIN_CORRUPT)
            if event.operation_id in operation_ids:
                _raise(DIAGNOSTIC_CHAIN_CORRUPT)
            operation_ids.add(event.operation_id)
            before = session
            try:
                session = reduce_event(session, event)
            except DiagnosticValidationError:
                _raise(DIAGNOSTIC_CHAIN_CORRUPT)
            assert session is not None
            self._validate_referenced_evidence(event, session)
            self._ensure_checkpoint_locked(event, before, session, path)
            events.append(event)
        if session is None:
            _raise(DIAGNOSTIC_CHAIN_CORRUPT)
        return session, tuple(events)

    def _validate_referenced_evidence(self, event: DiagnosticEvent, session: DiagnosticSession) -> None:
        references = _event_references(event)
        new_event = event.event_type in {
            "source_change.declared",
            "verification.plan_added",
            "verification.started",
            "analysis.marker_attached",
            "verification.completed",
        }
        if not new_event:
            for evidence_id in references:
                try:
                    envelope = self.evidence_store.get_envelope(evidence_id)
                except (EvidenceValidationError, OSError, ValueError):
                    _raise(DIAGNOSTIC_EVIDENCE_MISSING)
                if not _same_identity(envelope.identity, session.identity):
                    _raise(DIAGNOSTIC_IDENTITY_MISMATCH)
            return

        envelopes: dict[str, EvidenceEnvelope] = {}
        for evidence_id in references:
            try:
                envelope = self.evidence_store.get_envelope(evidence_id)
            except (EvidenceValidationError, OSError, ValueError):
                _raise(DIAGNOSTIC_EVIDENCE_MISSING)
            envelopes[evidence_id] = envelope

        payload = event.to_dict()["payload"]
        assert isinstance(payload, dict)
        request = payload["request"]
        assert isinstance(request, dict)

        def require_scope(envelope: EvidenceEnvelope) -> None:
            if not _same_scope(envelope.identity, session.identity):
                _raise(DIAGNOSTIC_IDENTITY_MISMATCH)

        def require_after(envelope: EvidenceEnvelope, declaration: SourceChangeDeclaration) -> None:
            require_scope(envelope)
            if not _same_after_identity(envelope.identity, declaration):
                _raise(DIAGNOSTIC_IDENTITY_MISMATCH)

        def require_failed(envelope: EvidenceEnvelope) -> None:
            if not _same_identity(envelope.identity, session.identity):
                _raise(DIAGNOSTIC_IDENTITY_MISMATCH)

        if event.event_type == "source_change.declared":
            declaration = SourceChangeDeclaration.from_value(request["source_change_declaration"])
            envelope = envelopes[declaration.diff_evidence_id]
            require_scope(envelope)
            if declaration.diff_artifact not in envelope.artifacts:
                _raise(DIAGNOSTIC_EVIDENCE_MISSING)
            return

        if event.event_type == "verification.plan_added":
            plan = VerificationPlan.from_value(request["verification_plan"])
            declaration = next(
                (
                    item
                    for item in session.source_change_declarations
                    if item.declaration_id == plan.source_change_declaration_id
                ),
                None,
            )
            if declaration is None:
                _raise(DIAGNOSTIC_CHAIN_CORRUPT)
            require_failed(envelopes[plan.failed_before_evidence_id])
            require_after(envelopes[plan.fixed_after_evidence_id], declaration)
            for evidence_id in plan.required_analysis_evidence_ids:
                require_after(envelopes[evidence_id], declaration)
            return

        if event.event_type == "verification.started":
            return

        if event.event_type == "analysis.marker_attached":
            marker = DiagnosticMarkerRef.from_value(request["diagnostic_marker_ref"])
            plan = next(
                (
                    item
                    for item in session.verification_plans
                    if item.verification_plan_id == session.active_verification_plan_id
                ),
                None,
            )
            if plan is None or (marker.analysis_id, marker.analysis_evidence_id) not in zip(
                plan.required_analysis_ids,
                plan.required_analysis_evidence_ids,
            ):
                _raise(DIAGNOSTIC_PLAN_INVALID)
            declaration = next(
                (
                    item
                    for item in session.source_change_declarations
                    if item.validation_plan_id == plan.verification_plan_id
                ),
                None,
            )
            if declaration is None:
                _raise(DIAGNOSTIC_CHAIN_CORRUPT)
            require_after(envelopes[marker.marker_evidence_id], declaration)
            require_after(envelopes[marker.analysis_evidence_id], declaration)
            return

        verification = FixVerification.from_value(request["fix_verification"])
        plan = next(
            (
                item
                for item in session.verification_plans
                if item.verification_plan_id == verification.verification_plan_id
            ),
            None,
        )
        if plan is None:
            _raise(DIAGNOSTIC_PLAN_INVALID)
        declaration = next(
            (
                item
                for item in session.source_change_declarations
                if item.declaration_id == plan.source_change_declaration_id
            ),
            None,
        )
        if declaration is None:
            _raise(DIAGNOSTIC_CHAIN_CORRUPT)
        if tuple(zip(verification.analysis_ids, verification.analysis_evidence_ids)) != tuple(
            zip(plan.required_analysis_ids, plan.required_analysis_evidence_ids)
        ):
            _raise(DIAGNOSTIC_PLAN_INVALID)
        require_failed(envelopes[verification.failed_before_evidence_id])
        require_after(envelopes[verification.fixed_after_evidence_id], declaration)
        for evidence_id in verification.analysis_evidence_ids:
            require_after(envelopes[evidence_id], declaration)

    def _checkpoint_expected(
        self,
        event: DiagnosticEvent,
        before: DiagnosticSession | None,
        after: DiagnosticSession,
        path: Path,
    ) -> tuple[EvidenceEnvelope, RootRecord, bytes]:
        try:
            artifact = self.evidence_store.ingest_file(path, kind=_EVENT_KIND, media_type=_EVENT_MEDIA_TYPE)
        except (EvidenceValidationError, OSError, ValueError):
            _raise(DIAGNOSTIC_CHAIN_CORRUPT)
        self._fault("artifact.after_ingest")
        try:
            event_bytes = path.read_bytes()
        except OSError:
            _raise(DIAGNOSTIC_CHAIN_CORRUPT)
        if len(event_bytes) > MAX_EVENT_BYTES or event_bytes != canonical_diagnostic_json_bytes(event.to_dict()):
            _raise(DIAGNOSTIC_CHAIN_CORRUPT)

        previous_manifest: str | None = None
        if before is not None:
            try:
                previous_root = get_root(
                    self.evidence_store,
                    _ROOT_TYPE,
                    f"{before.diagnostic_session_id}.{before.revision:08d}",
                )
            except (EvidenceValidationError, OSError, ValueError):
                _raise(DIAGNOSTIC_CHAIN_CORRUPT)
            previous_manifest = previous_root.manifest_id
        parents = [previous_manifest] if previous_manifest is not None else []
        parents.extend(reference for reference in _event_references(event) if reference not in parents)
        try:
            envelope = EvidenceEnvelope(
                identity=after.identity,
                operation="diagnostic-event",
                produced_at_utc=event.occurred_at_utc,
                parents=tuple(cast(str, item) for item in parents),
                artifacts=(artifact,),
                metadata={
                    "diagnostic_session_id": after.diagnostic_session_id,
                    "sequence": event.sequence,
                    "revision": after.revision,
                    "event_digest": event.digest,
                },
            )
            root = RootRecord(
                root_type=_ROOT_TYPE,
                root_id=f"{after.diagnostic_session_id}.{after.revision:08d}",
                manifest_id=str(envelope.evidence_id),
                metadata={
                    "diagnostic_session_id": after.diagnostic_session_id,
                    "revision": after.revision,
                    "state": after.state,
                    "event_digest": event.digest,
                },
            )
        except EvidenceValidationError as error:
            if error.code == EVIDENCE_LIMIT_EXCEEDED:
                _raise(DIAGNOSTIC_LIMIT_EXCEEDED)
            _raise(DIAGNOSTIC_CHAIN_CORRUPT)
        return envelope, root, event_bytes

    def _ensure_checkpoint_locked(
        self,
        event: DiagnosticEvent,
        before: DiagnosticSession | None,
        after: DiagnosticSession,
        path: Path,
    ) -> None:
        envelope, root, event_bytes = self._checkpoint_expected(event, before, after, path)
        try:
            existing_envelope = self.evidence_store.get_envelope(str(envelope.evidence_id))
        except (EvidenceValidationError, OSError, ValueError):
            try:
                self.evidence_store.put_envelope(envelope)
            except (EvidenceValidationError, OSError, ValueError):
                _raise(DIAGNOSTIC_CHAIN_CORRUPT)
            self._fault("envelope.after_publish")
            try:
                existing_envelope = self.evidence_store.get_envelope(str(envelope.evidence_id))
            except (EvidenceValidationError, OSError, ValueError):
                _raise(DIAGNOSTIC_CHAIN_CORRUPT)
        if existing_envelope.to_dict() != envelope.to_dict():
            _raise(DIAGNOSTIC_CHAIN_CORRUPT)
        if len(existing_envelope.artifacts) != 1:
            _raise(DIAGNOSTIC_CHAIN_CORRUPT)
        artifact = existing_envelope.artifacts[0]
        try:
            if self.evidence_store.read_artifact(artifact, maximum_bytes=MAX_EVENT_BYTES) != event_bytes:
                _raise(DIAGNOSTIC_CHAIN_CORRUPT)
        except (EvidenceValidationError, OSError, ValueError):
            _raise(DIAGNOSTIC_CHAIN_CORRUPT)
        try:
            existing_root = get_root(self.evidence_store, root.root_type, root.root_id)
        except (EvidenceValidationError, OSError, ValueError):
            try:
                put_root(self.evidence_store, root)
            except (EvidenceValidationError, OSError, ValueError):
                _raise(DIAGNOSTIC_CHAIN_CORRUPT)
            self._fault("root.after_publish")
            try:
                existing_root = get_root(self.evidence_store, root.root_type, root.root_id)
            except (EvidenceValidationError, OSError, ValueError):
                _raise(DIAGNOSTIC_CHAIN_CORRUPT)
        if existing_root.to_dict() != root.to_dict():
            _raise(DIAGNOSTIC_CHAIN_CORRUPT)

    def _write_event_new(self, path: Path, event: DiagnosticEvent) -> None:
        payload = canonical_diagnostic_json_bytes(event.to_dict())
        if len(payload) > MAX_EVENT_BYTES:
            _raise(DIAGNOSTIC_LIMIT_EXCEEDED)
        descriptor = -1
        try:
            descriptor = os.open(
                path,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0),
                0o600,
            )
            with os.fdopen(descriptor, "wb") as stream:
                descriptor = -1
                stream.write(payload)
                stream.flush()
                self._fault("event.after_flush")
                os.fsync(stream.fileno())
                self._fault("event.after_fsync")
            self._fault("event.after_publish")
            self._flush_directory(path.parent)
            self._fault("event.after_directory_fsync")
        except FileExistsError:
            _raise(DIAGNOSTIC_CHAIN_CORRUPT)
        except DiagnosticValidationError:
            raise
        except OSError:
            _raise(DIAGNOSTIC_CHAIN_CORRUPT)
        finally:
            if descriptor >= 0:
                os.close(descriptor)

    def _find_operation_locked(
        self,
        operation_id: str,
        *,
        session_id: str | None = None,
    ) -> tuple[DiagnosticSession, DiagnosticEvent] | None:
        session_ids = (
            (session_id,)
            if session_id is not None
            else self._validate_sessions_layout()
        )
        workspace_create_operations: set[str] = set()
        found: tuple[DiagnosticSession, DiagnosticEvent] | None = None
        for current_session_id in session_ids:
            assert current_session_id is not None
            session, events = self._load_chain_locked(current_session_id)
            for event in events:
                if event.event_type == "session.created":
                    if event.operation_id in workspace_create_operations:
                        _raise(DIAGNOSTIC_CHAIN_CORRUPT)
                    workspace_create_operations.add(event.operation_id)
                if (
                    event.operation_id == operation_id
                    and (session_id is not None or event.event_type == "session.created")
                    and found is None
                ):
                    found = session, event
        return found

    def _validate_session_id(self, value: object) -> str:
        if not isinstance(value, str) or _SESSION_ID.fullmatch(value) is None:
            _raise(DIAGNOSTIC_INVALID_EVENT)
        return value

    def create(self, event: DiagnosticEvent) -> DiagnosticMutationRecord:
        if not isinstance(event, DiagnosticEvent):
            _raise(DIAGNOSTIC_INVALID_EVENT)
        if event.event_type != "session.created" or event.sequence != 0 or event.revision_before != 0 or event.previous_digest is not None:
            _raise(DIAGNOSTIC_INVALID_EVENT)
        with self._store_lock(create=True):
            found = self._find_operation_locked(event.operation_id)
            if found is not None:
                session, accepted = found
                if _intent(accepted) != _intent(event):
                    _raise(DIAGNOSTIC_OPERATION_CONFLICT)
                return DiagnosticMutationRecord(session, accepted, False)
            session_id = self._validate_session_id(event.diagnostic_session_id)
            sessions = self._validate_sessions_layout()
            if session_id in sessions:
                _raise(DIAGNOSTIC_INVALID_EVENT)
            if len(sessions) >= _MAX_SESSIONS:
                _raise(DIAGNOSTIC_LIMIT_EXCEEDED)
            provisional = reduce_event(None, event)
            self._validate_referenced_evidence(event, provisional)
            events_dir = self._prepare_session_directories(session_id)
            self._fault("session.after_prepare")
            path = events_dir / "00000000.json"
            self._write_event_new(path, event)
            self._fault("event.after_create")
            self._ensure_checkpoint_locked(event, None, provisional, path)
            return DiagnosticMutationRecord(provisional, event, True)

    def append(
        self,
        diagnostic_session_id: str,
        event: DiagnosticEvent,
        expected_revision: int,
    ) -> DiagnosticMutationRecord:
        session_id = self._validate_session_id(diagnostic_session_id)
        if not isinstance(event, DiagnosticEvent) or event.diagnostic_session_id != session_id:
            _raise(DIAGNOSTIC_INVALID_EVENT)
        if event.event_type == "session.created":
            _raise(DIAGNOSTIC_INVALID_EVENT)
        if type(expected_revision) is not int or expected_revision < 0:
            _raise(DIAGNOSTIC_REVISION_CONFLICT)
        try:
            self._existing(self.diagnostics_root)
        except FileNotFoundError:
            _raise(DIAGNOSTIC_NOT_FOUND)
        with self._store_lock(create=False):
            found = self._find_operation_locked(event.operation_id, session_id=session_id)
            if found is not None:
                session, accepted = found
                if _intent(accepted) != _intent(event):
                    _raise(DIAGNOSTIC_OPERATION_CONFLICT)
                return DiagnosticMutationRecord(session, accepted, False)
            session, _events = self._load_chain_locked(session_id)
            if expected_revision != session.revision:
                _raise(DIAGNOSTIC_REVISION_CONFLICT)
            if event.sequence != expected_revision or event.revision_before != expected_revision or event.previous_digest != session.event_head:
                _raise(DIAGNOSTIC_INVALID_EVENT)
            if session.revision >= MAX_EVENTS:
                _raise(DIAGNOSTIC_LIMIT_EXCEEDED)
            after = reduce_event(session, event)
            self._validate_referenced_evidence(event, after)
            events_dir = self._session_events_directory(session_id)
            path = events_dir / f"{event.sequence:08d}.json"
            self._write_event_new(path, event)
            self._fault("event.after_create")
            self._ensure_checkpoint_locked(event, session, after, path)
            return DiagnosticMutationRecord(after, event, True)

    def load(self, diagnostic_session_id: str) -> DiagnosticSession:
        session_id = self._validate_session_id(diagnostic_session_id)
        try:
            info = self._existing(self.diagnostics_root)
        except FileNotFoundError:
            _raise(DIAGNOSTIC_NOT_FOUND)
        if not stat.S_ISDIR(info.st_mode):
            _raise(DIAGNOSTIC_CHAIN_CORRUPT)
        with self._store_lock(create=False):
            return self._load_chain_locked(session_id)[0]


__all__ = ["DiagnosticMutationRecord", "DiagnosticStore"]
