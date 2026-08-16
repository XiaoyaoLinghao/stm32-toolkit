"""External result-file creation followed by authoritative evidence ingestion."""

from __future__ import annotations

import os
from pathlib import Path
import tempfile

from stm32_toolkit.evidence import ArtifactRef
from stm32_toolkit.evidence.store import EvidenceStore

from .model import MAX_RUN_STREAM_BYTES, protocol_error


class TestArtifactCollector:
    """Preserve native bytes outside the workspace and ingest verified copies."""

    def __init__(
        self,
        results_root: Path,
        evidence_store: EvidenceStore,
        *,
        project_root: Path,
    ) -> None:
        if not isinstance(results_root, Path) or not isinstance(project_root, Path):
            raise TypeError("results_root and project_root must be Paths")
        self.results_root = results_root.absolute()
        self.project_root = project_root.resolve(strict=True)
        self.results_root.mkdir(parents=True, exist_ok=True)
        resolved_results = self.results_root.resolve(strict=True)
        if resolved_results == self.project_root or self.project_root in resolved_results.parents:
            raise protocol_error("TEST_RESULTS_UNSAFE", "test results root must be outside the workspace")
        if not isinstance(evidence_store, EvidenceStore):
            raise TypeError("evidence_store must be an EvidenceStore")
        self.evidence_store = evidence_store

    def new_directory(self, prefix: str) -> Path:
        if not prefix or any(character not in "abcdefghijklmnopqrstuvwxyz0123456789-" for character in prefix):
            raise protocol_error("TEST_RESULTS_UNSAFE", "result directory prefix is invalid")
        return Path(tempfile.mkdtemp(prefix=f"{prefix}-", dir=self.results_root))

    def output_path(self, directory: Path, name: str) -> Path:
        if directory.parent != self.results_root or not directory.is_dir():
            raise protocol_error("TEST_RESULTS_UNSAFE", "result directory is not collector-owned")
        if not name or Path(name).name != name or "/" in name or "\\" in name:
            raise protocol_error("TEST_RESULTS_UNSAFE", "result filename is invalid")
        result = directory / name
        if result.exists():
            raise protocol_error("TEST_RESULTS_UNSAFE", "result path already exists")
        return result

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
        path = self.output_path(directory, name)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
        descriptor = os.open(path, flags, 0o600)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
        except BaseException:
            try:
                os.close(descriptor)
            except OSError:
                pass
            raise
        return self.evidence_store.ingest_file(path, kind=kind, media_type=media_type)
    def ingest_existing(
        self,
        path: Path,
        *,
        kind: str,
        media_type: str,
        stream_limit: bool = False,
    ) -> ArtifactRef:
        if not isinstance(path, Path) or path.parent.parent != self.results_root:
            raise protocol_error("TEST_RESULTS_UNSAFE", "native result is not collector-owned")
        try:
            size = path.stat().st_size
        except OSError as exc:
            raise protocol_error("TEST_NATIVE_RESULT_INVALID", "native result is missing") from exc
        if stream_limit and size > MAX_RUN_STREAM_BYTES:
            raise protocol_error("TEST_STREAM_TOO_LARGE", "raw event stream exceeds 64 MiB")
        return self.evidence_store.ingest_file(path, kind=kind, media_type=media_type)
