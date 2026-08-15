"""Crash-safe content-addressed persistence for canonical evidence envelopes."""

from __future__ import annotations

from collections.abc import Callable
import hashlib
import os
from pathlib import Path
import re
import stat
import tempfile

from .model import (
    MAX_ARTIFACT_BYTES,
    ArtifactRef,
    EvidenceEnvelope,
    EvidenceValidationError,
)


_HASH = re.compile(r"^[0-9a-f]{64}$")
_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
_COPY_CHUNK = 1024 * 1024


class EvidenceStore:
    """An immutable object/manifest store rooted at a local directory."""

    def __init__(
        self,
        root: Path | str,
        *,
        fault_injector: Callable[[str], None] | None = None,
    ) -> None:
        root_path = Path(root)
        self.root = root_path if root_path.is_absolute() else root_path.absolute()
        self._fault_injector = fault_injector

    def _fault(self, point: str) -> None:
        if self._fault_injector is not None:
            self._fault_injector(point)

    @staticmethod
    def _is_reparse(info: os.stat_result) -> bool:
        return bool(getattr(info, "st_file_attributes", 0) & _REPARSE_POINT)

    @classmethod
    def _validate_existing_path(
        cls,
        path: Path,
        *,
        regular: bool = False,
        single_link: bool = False,
    ) -> os.stat_result:
        """Validate every existing component without resolving through a reparse point."""
        absolute = path if path.is_absolute() else path.absolute()
        parts = absolute.parts
        current = Path(parts[0])
        for part in parts[1:]:
            current = current / part
            try:
                info = current.lstat()
            except FileNotFoundError:
                raise
            if stat.S_ISLNK(info.st_mode) or cls._is_reparse(info):
                raise EvidenceValidationError(f"path contains a link or reparse point: {current}")
        info = absolute.lstat()
        if regular and not stat.S_ISREG(info.st_mode):
            raise EvidenceValidationError(f"path is not a regular file: {absolute}")
        if single_link and info.st_nlink != 1:
            raise EvidenceValidationError(f"managed file has a hard link: {absolute}")
        return info

    @staticmethod
    def _reject_casefold_collision(parent: Path, name: str) -> None:
        folded = name.casefold()
        for child in parent.iterdir():
            if child.name.casefold() == folded and child.name != name:
                raise EvidenceValidationError(
                    f"managed path has a case-fold collision: {child.name!r} and {name!r}"
                )

    def _ensure_root(self) -> None:
        try:
            self.root.mkdir(parents=True, exist_ok=True)
        except FileExistsError:
            # Validation below produces the stable evidence-domain failure for a file root.
            pass
        info = self._validate_existing_path(self.root)
        if not stat.S_ISDIR(info.st_mode):
            raise EvidenceValidationError("evidence root is not a directory")

    def _managed_directory(self, *parts: str) -> Path:
        self._ensure_root()
        current = self.root
        for part in parts:
            self._reject_casefold_collision(current, part)
            candidate = current / part
            try:
                candidate.mkdir()
            except FileExistsError:
                pass
            info = self._validate_existing_path(candidate)
            if not stat.S_ISDIR(info.st_mode):
                raise EvidenceValidationError(f"managed path is not a directory: {candidate}")
            current = candidate
        return current

    @staticmethod
    def _open_readonly(path: Path) -> int:
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        return os.open(path, flags)

    @classmethod
    def _hash_file(
        cls,
        path: Path,
        *,
        expected_size: int | None = None,
        expected_digest: str | None = None,
        single_link: bool = True,
    ) -> tuple[int, str]:
        before = cls._validate_existing_path(path, regular=True, single_link=single_link)
        if before.st_size > MAX_ARTIFACT_BYTES:
            raise EvidenceValidationError("artifact exceeds the 2 GiB limit")
        digest = hashlib.sha256()
        size = 0
        descriptor = cls._open_readonly(path)
        try:
            opened = os.fstat(descriptor)
            if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
                raise EvidenceValidationError("file identity changed while it was opened")
            if not stat.S_ISREG(opened.st_mode):
                raise EvidenceValidationError("opened path is not a regular file")
            if single_link and opened.st_nlink != 1:
                raise EvidenceValidationError(f"managed file has a hard link: {path}")
            while True:
                block = os.read(descriptor, _COPY_CHUNK)
                if not block:
                    break
                size += len(block)
                if size > MAX_ARTIFACT_BYTES:
                    raise EvidenceValidationError("artifact exceeds the 2 GiB limit")
                digest.update(block)
            after = os.fstat(descriptor)
            if (
                (after.st_dev, after.st_ino) != (opened.st_dev, opened.st_ino)
                or after.st_size != opened.st_size
                or after.st_mtime_ns != opened.st_mtime_ns
            ):
                raise EvidenceValidationError("file changed while it was read")
        finally:
            os.close(descriptor)
        actual_digest = digest.hexdigest()
        if expected_size is not None and size != expected_size:
            raise EvidenceValidationError(f"evidence object is corrupt: size mismatch for {path}")
        if expected_digest is not None and actual_digest != expected_digest:
            raise EvidenceValidationError(f"evidence object is corrupt: digest mismatch for {path}")
        return size, actual_digest

    @staticmethod
    def _flush_directory(path: Path) -> None:
        """Best-effort directory durability; Windows has no portable directory fsync."""
        if os.name == "nt":
            return
        descriptor = os.open(path, os.O_RDONLY)  # pragma: no cover - POSIX-only durability
        try:  # pragma: no cover - POSIX-only durability
            os.fsync(descriptor)  # pragma: no cover - POSIX-only durability
        finally:  # pragma: no cover - POSIX-only durability
            os.close(descriptor)  # pragma: no cover - POSIX-only durability

    def _atomic_create_new(self, target: Path, payload: bytes, *, phase: str) -> bool:
        """Publish complete bytes without ever replacing an existing authoritative file."""
        descriptor, temporary_name = tempfile.mkstemp(prefix=".tmp-", dir=target.parent)
        temporary = Path(temporary_name)
        published = False
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(payload)
                stream.flush()
                self._fault(f"{phase}.after_flush")
                os.fsync(stream.fileno())
                self._fault(f"{phase}.after_fsync")
            self._fault(f"{phase}.before_publish")
            try:
                # Windows rename is an atomic create-new operation and never replaces target.
                os.rename(temporary, target)
                published = True
            except FileExistsError:
                return False
            self._fault(f"{phase}.after_publish")
            self._flush_directory(target.parent)
            self._fault(f"{phase}.after_directory_fsync")
            return True
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass
            if published and target.exists():
                # Atomic rename consumed the temporary; the published file must be singular.
                self._validate_existing_path(target, regular=True, single_link=True)

    def _expected_object(self, digest: str) -> tuple[str, Path]:
        directory = self._managed_directory("objects", "sha256", digest[:2])
        self._reject_casefold_collision(directory, digest)
        relative = f"objects/sha256/{digest[:2]}/{digest}"
        return relative, directory / digest

    def _verify_artifact(self, artifact: ArtifactRef) -> None:
        expected_relative, target = self._expected_object(artifact.sha256)
        if artifact.relative_path != expected_relative:
            raise EvidenceValidationError("artifact relative_path is not its content-addressed object path")
        self._hash_file(
            target,
            expected_size=artifact.size_bytes,
            expected_digest=artifact.sha256,
            single_link=True,
        )

    def ingest_file(self, source: Path, *, kind: str, media_type: str) -> ArtifactRef:
        source_path = Path(source)
        if not source_path.is_absolute():
            source_path = source_path.absolute()
        size, actual_digest = self._hash_file(source_path, single_link=True)
        relative, target = self._expected_object(actual_digest)

        # The first verified pass makes the digest directory knowable. The second pass copies
        # into that final directory and must match the first before atomic publication.
        descriptor, temporary_name = tempfile.mkstemp(prefix=".tmp-", dir=target.parent)
        temporary = Path(temporary_name)
        copied_digest = hashlib.sha256()
        copied_size = 0
        try:
            source_info = self._validate_existing_path(
                source_path, regular=True, single_link=True
            )
            source_descriptor = self._open_readonly(source_path)
            try:
                opened = os.fstat(source_descriptor)
                if not stat.S_ISREG(opened.st_mode):
                    raise EvidenceValidationError("opened second-pass source is not a regular file")
                if (opened.st_dev, opened.st_ino) != (source_info.st_dev, source_info.st_ino):
                    raise EvidenceValidationError("source identity changed while it was opened")
                if opened.st_nlink != 1:
                    raise EvidenceValidationError("second-pass source has a hard link")
                if opened.st_size != source_info.st_size:
                    raise EvidenceValidationError("source size changed between second-pass lstat and open")
                if opened.st_mtime_ns != source_info.st_mtime_ns:
                    raise EvidenceValidationError("source mtime changed between second-pass lstat and open")
                with os.fdopen(descriptor, "wb") as output:
                    while True:
                        block = os.read(source_descriptor, _COPY_CHUNK)
                        if not block:
                            break
                        copied_size += len(block)
                        if copied_size > MAX_ARTIFACT_BYTES:
                            raise EvidenceValidationError("artifact exceeds the 2 GiB limit")
                        copied_digest.update(block)
                        output.write(block)
                    output.flush()
                    self._fault("artifact.after_flush")
                    os.fsync(output.fileno())
                    self._fault("artifact.after_fsync")
                after = os.fstat(source_descriptor)
                if not stat.S_ISREG(after.st_mode):
                    raise EvidenceValidationError("read second-pass source is not a regular file")
                if (after.st_dev, after.st_ino) != (opened.st_dev, opened.st_ino):
                    raise EvidenceValidationError("source identity changed while it was ingested")
                if after.st_nlink != 1:
                    raise EvidenceValidationError("second-pass source acquired a hard link")
                if after.st_size != opened.st_size:
                    raise EvidenceValidationError("source size changed while it was ingested")
                if after.st_mtime_ns != opened.st_mtime_ns:
                    raise EvidenceValidationError("source mtime changed while it was ingested")
                if copied_size != size or copied_digest.hexdigest() != actual_digest:
                    raise EvidenceValidationError("source changed between the verified hash and copy")
            finally:
                os.close(source_descriptor)
        except BaseException:
            try:
                os.close(descriptor)
            except OSError:
                pass
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass
            raise

        published = False
        try:
            self._fault("artifact.before_publish")
            try:
                # Windows rename is an atomic create-new operation and never replaces target.
                os.rename(temporary, target)
                published = True
            except FileExistsError:
                pass
            if published:
                self._fault("artifact.after_publish")
                self._flush_directory(target.parent)
                self._fault("artifact.after_directory_fsync")
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass

        self._hash_file(target, expected_size=size, expected_digest=actual_digest, single_link=True)
        return ArtifactRef(
            sha256=actual_digest,
            size_bytes=size,
            relative_path=relative,
            kind=kind,
            media_type=media_type,
        )

    def verify_envelope(self, envelope: EvidenceEnvelope) -> EvidenceEnvelope:
        if not isinstance(envelope, EvidenceEnvelope):
            raise EvidenceValidationError("value is not an EvidenceEnvelope")
        # Reparse the exact canonical bytes so direct objects share the authoritative decoder gate.
        verified = EvidenceEnvelope.from_json_bytes(envelope.to_json_bytes())
        for artifact in verified.artifacts:
            self._verify_artifact(artifact)
        return verified

    def put_envelope(self, envelope: EvidenceEnvelope) -> Path:
        verified = self.verify_envelope(envelope)
        directory = self._managed_directory("manifests")
        evidence_id = str(verified.evidence_id)
        self._reject_casefold_collision(directory, f"{evidence_id}.json")
        target = directory / f"{evidence_id}.json"
        payload = verified.to_json_bytes()
        try:
            self._validate_existing_path(target, regular=True, single_link=True)
        except FileNotFoundError:
            created = self._atomic_create_new(target, payload, phase="manifest")
            if created:
                return target
        # A concurrent or pre-existing manifest is reusable only through the full authoritative read.
        self.get_envelope(evidence_id)
        return target

    def get_envelope(self, evidence_id: str) -> EvidenceEnvelope:
        if not isinstance(evidence_id, str) or _HASH.fullmatch(evidence_id) is None:
            raise EvidenceValidationError("evidence_id must be a lowercase SHA-256")
        directory = self._managed_directory("manifests")
        name = f"{evidence_id}.json"
        self._reject_casefold_collision(directory, name)
        path = directory / name
        self._validate_existing_path(path, regular=True, single_link=True)
        descriptor = self._open_readonly(path)
        try:
            info = os.fstat(descriptor)
            if info.st_nlink != 1:
                raise EvidenceValidationError(f"managed file has a hard link: {path}")
            with os.fdopen(descriptor, "rb") as stream:
                payload = stream.read()
            descriptor = -1
        finally:
            if descriptor >= 0:
                os.close(descriptor)
        envelope = EvidenceEnvelope.from_json_bytes(payload)
        if envelope.evidence_id != evidence_id:
            raise EvidenceValidationError("manifest name does not match its evidence_id")
        return self.verify_envelope(envelope)


__all__ = ["EvidenceStore"]
