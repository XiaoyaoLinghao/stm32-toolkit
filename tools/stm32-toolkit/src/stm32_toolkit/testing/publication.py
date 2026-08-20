"""Authoritative publication and reload of completed Host TestRuns."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
import re

from stm32_toolkit.evidence import (
    EVIDENCE_CORRUPT,
    EVIDENCE_LIMIT_EXCEEDED,
    ArtifactRef,
    EvidenceEnvelope,
    EvidenceValidationError,
    canonical_json_bytes,
)
from stm32_toolkit.evidence.gc import RootRecord, get_root, put_root
from stm32_toolkit.evidence.store import MAX_EVIDENCE_READ_BYTES, EvidenceStore

from .artifacts import TestArtifactCollector
from .model import (
    TestProtocolError,
    TestRunManifest,
    protocol_error,
    validate_host_identity,
)


_HASH = re.compile(r"^[0-9a-f]{64}$")
_HOST_OPERATION = "host-test-run"
_TERMINAL_STATES = frozenset({"passed", "failed", "error"})
_CASE_COUNT_STATES = ("passed", "failed", "skipped", "error", "timeout")
_ENVELOPE_METADATA = {"test_run_id", "test_manifest_sha256", "inventory_digest"}


def _publication_invalid(message: str, error: BaseException | None = None) -> None:
    failure = protocol_error("TEST_PROTOCOL_INVALID", message)
    if error is None:
        raise failure
    raise failure from error


def _evidence_commit_failure(message: str, error: BaseException) -> None:
    failure = EvidenceValidationError(EVIDENCE_CORRUPT, message)
    raise failure from error


def _corrupt(message: str, error: BaseException | None = None) -> None:
    failure = EvidenceValidationError(EVIDENCE_CORRUPT, message)
    if error is None:
        raise failure
    raise failure from error


def _hash(value: object, field: str) -> str:
    if not isinstance(value, str) or _HASH.fullmatch(value) is None:
        _publication_invalid(f"{field} must be a lowercase SHA-256")
    return value


def _host_artifact(value: object, field: str, *, kind: str, media_type: str) -> ArtifactRef:
    if not isinstance(value, ArtifactRef):
        _publication_invalid(f"{field} must be an ArtifactRef")
    if value.kind != kind or value.media_type != media_type:
        _publication_invalid(f"{field} has an invalid Host artifact type")
    return value


def _host_manifest(manifest: object) -> TestRunManifest:
    if not isinstance(manifest, TestRunManifest):
        _publication_invalid("manifest must be a TestRunManifest")
    try:
        verified = TestRunManifest.from_dict(manifest.to_dict())
    except TestProtocolError:
        raise
    except (TypeError, ValueError) as exc:
        _publication_invalid("manifest is not canonical", exc)
    if verified.mode != "host" or verified.transport is not None:
        _publication_invalid("publication requires a Host manifest without transport")
    if verified.state not in _TERMINAL_STATES:
        _publication_invalid("publication requires a completed Host manifest")
    if verified.stdout is None or verified.stderr is None:
        _publication_invalid("Host publication requires stdout and stderr artifacts")
    validate_host_identity(verified.identity)
    _host_artifact(
        verified.raw_events, "raw_events", kind="test-events", media_type="application/xml"
    )
    _host_artifact(
        verified.stdout, "stdout", kind="test-stdout", media_type="text/plain; charset=utf-8"
    )
    _host_artifact(
        verified.stderr, "stderr", kind="test-stderr", media_type="text/plain; charset=utf-8"
    )
    return verified


def _case_counts(manifest: TestRunManifest) -> dict[str, int]:
    return {
        state: sum(case.state == state for case in manifest.cases)
        for state in _CASE_COUNT_STATES
    }


def _run_summary(manifest: TestRunManifest) -> dict[str, object]:
    return {
        "run_id": manifest.run_id,
        "mode": manifest.mode,
        "state": manifest.state,
        "identity": manifest.identity.to_dict(),
        "transport": manifest.transport,
        "case_counts": _case_counts(manifest),
        "started_at_utc": manifest.started_at_utc,
        "ended_at_utc": manifest.ended_at_utc,
        "duration_ms": manifest.duration_ms,
    }


def _decode_manifest_bytes(payload: bytes) -> TestRunManifest:
    if not isinstance(payload, bytes):
        _corrupt("stored test manifest bytes are invalid")

    def pairs(items: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in items:
            if key in result:
                _corrupt("stored test manifest has duplicate JSON keys")
            result[key] = value
        return result

    def reject_number(value: str) -> object:
        _corrupt("stored test manifest has a non-integer JSON number")

    try:
        document = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=pairs,
            parse_float=reject_number,
            parse_constant=reject_number,
        )
        manifest = TestRunManifest.from_dict(document)
        if canonical_json_bytes(manifest.to_dict()) != payload:
            _corrupt("stored test manifest is not canonical JSON")
        return manifest
    except EvidenceValidationError as exc:
        if exc.code == EVIDENCE_LIMIT_EXCEEDED:
            raise
        _corrupt("stored test manifest is corrupt", exc)
    except TestProtocolError as exc:
        _corrupt("stored test manifest is invalid", exc)
    except (UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        _corrupt("stored test manifest is invalid", exc)


@dataclass(frozen=True)
class PublishedTestRun:
    manifest: TestRunManifest
    manifest_artifact: ArtifactRef
    envelope: EvidenceEnvelope
    root: RootRecord

    def public_data(self, *, authoritative: bool = False) -> dict[str, object]:
        if type(authoritative) is not bool:
            raise protocol_error("TEST_PROTOCOL_INVALID", "authoritative must be a boolean")
        data: dict[str, object] = {
            "run": _run_summary(self.manifest),
            "test_manifest": self.manifest_artifact.to_dict(),
            "evidence_id": self.envelope.evidence_id,
        }
        if authoritative:
            data["authoritative"] = True
        return data


class TestRunPublisher:
    """Publish one completed Host manifest and its exact Evidence bindings."""

    def __init__(
        self,
        evidence_store: EvidenceStore,
        project_root: Path,
        results_root: Path,
    ) -> None:
        if not isinstance(evidence_store, EvidenceStore):
            raise TypeError("evidence_store must be an EvidenceStore")
        if not isinstance(project_root, Path) or not isinstance(results_root, Path):
            raise TypeError("project_root and results_root must be Paths")
        self.evidence_store = evidence_store
        self.project_root = project_root.resolve(strict=True)
        self._collector = TestArtifactCollector(
            results_root, evidence_store, project_root=self.project_root
        )

    def publish_host(
        self, manifest: TestRunManifest, *, inventory_digest: str
    ) -> PublishedTestRun:
        verified = _host_manifest(manifest)
        inventory_digest = _hash(inventory_digest, "inventory_digest")
        payload = canonical_json_bytes(verified.to_dict())
        if len(payload) > MAX_EVIDENCE_READ_BYTES:
            raise EvidenceValidationError(
                EVIDENCE_LIMIT_EXCEEDED,
                "canonical test manifest exceeds the authoritative read limit",
            )
        try:
            directory = self._collector.new_directory("test-manifest")
            manifest_artifact = self._collector.write_and_ingest(
                directory,
                "test-run-manifest.json",
                payload,
                kind="test-manifest",
                media_type="application/json",
            )
        except EvidenceValidationError:
            raise
        except OSError as exc:
            _evidence_commit_failure("Host manifest artifact publication failed", exc)
        artifacts = (
            manifest_artifact,
            verified.raw_events,
            verified.stdout,
            verified.stderr,
        )
        assert verified.stdout is not None and verified.stderr is not None
        envelope = EvidenceEnvelope(
            identity=verified.identity,
            operation=_HOST_OPERATION,
            produced_at_utc=verified.ended_at_utc,
            parents=(),
            artifacts=artifacts,
            metadata={
                "test_run_id": verified.run_id,
                "test_manifest_sha256": manifest_artifact.sha256,
                "inventory_digest": inventory_digest,
            },
        )
        try:
            self.evidence_store.put_envelope(envelope)
        except EvidenceValidationError:
            raise
        except OSError as exc:
            _evidence_commit_failure("Host envelope publication failed", exc)
        root = RootRecord(
            "test-run",
            verified.run_id,
            str(envelope.evidence_id),
            {"mode": "host", "state": verified.state},
        )
        try:
            put_root(self.evidence_store, root)
        except EvidenceValidationError:
            raise
        except OSError as exc:
            _evidence_commit_failure("Host root publication failed", exc)
        return PublishedTestRun(verified, manifest_artifact, envelope, root)


class TestRunRepository:
    """Reload one Host TestRun through exact Evidence root and object bindings."""

    def __init__(self, evidence_store: EvidenceStore) -> None:
        if not isinstance(evidence_store, EvidenceStore):
            raise TypeError("evidence_store must be an EvidenceStore")
        self.evidence_store = evidence_store

    def load(self, run_id: str) -> PublishedTestRun:
        root = get_root(self.evidence_store, "test-run", run_id)
        try:
            envelope = self.evidence_store.get_envelope(root.manifest_id)
            if envelope.operation != _HOST_OPERATION:
                _corrupt("stored envelope operation contradicts Host TestRun")
            if envelope.parents != ():
                _corrupt("stored Host envelope has parents")
            metadata = dict(envelope.metadata)
            if set(metadata) != _ENVELOPE_METADATA:
                _corrupt("stored Host envelope metadata is not closed")
            if metadata["test_run_id"] != run_id:
                _corrupt("stored envelope run ID contradicts the root")
            manifest_digest = _hash(metadata["test_manifest_sha256"], "test_manifest_sha256")
            inventory_digest = _hash(metadata["inventory_digest"], "inventory_digest")
            manifest_refs = tuple(
                artifact for artifact in envelope.artifacts
                if artifact.kind == "test-manifest" and artifact.media_type == "application/json"
            )
            if len(manifest_refs) != 1 or manifest_refs[0].sha256 != manifest_digest:
                _corrupt("stored Host envelope has an invalid test manifest artifact")
            manifest_artifact = manifest_refs[0]
            payload = self.evidence_store.read_artifact(
                manifest_artifact, maximum_bytes=MAX_EVIDENCE_READ_BYTES
            )
            manifest = _decode_manifest_bytes(payload)
            if manifest.run_id != run_id:
                _corrupt("stored test manifest run ID contradicts the root")
            if manifest.mode != "host" or manifest.transport is not None:
                _corrupt("stored test manifest is not a Host record")
            if manifest.state not in _TERMINAL_STATES:
                _corrupt("stored test manifest is not terminal")
            if manifest.stdout is None or manifest.stderr is None:
                _corrupt("stored Host manifest lacks stdout or stderr")
            _host_artifact(
                manifest.raw_events, "raw_events", kind="test-events", media_type="application/xml"
            )
            _host_artifact(
                manifest.stdout, "stdout", kind="test-stdout", media_type="text/plain; charset=utf-8"
            )
            _host_artifact(
                manifest.stderr, "stderr", kind="test-stderr", media_type="text/plain; charset=utf-8"
            )
            if envelope.identity != manifest.identity:
                _corrupt("stored envelope identity contradicts the test manifest")
            if envelope.produced_at_utc != manifest.ended_at_utc:
                _corrupt("stored envelope time contradicts the test manifest")
            expected_artifacts = (
                manifest_artifact, manifest.raw_events, manifest.stdout, manifest.stderr
            )
            if envelope.artifacts != expected_artifacts:
                _corrupt("stored Host envelope artifact membership is invalid")
            if root.manifest_id != envelope.evidence_id:
                _corrupt("stored root manifest ID contradicts the envelope")
            if root.metadata != {"mode": "host", "state": manifest.state}:
                _corrupt("stored root metadata contradicts the Host manifest")
            return PublishedTestRun(manifest, manifest_artifact, envelope, root)
        except EvidenceValidationError as exc:
            if exc.code in {EVIDENCE_CORRUPT, EVIDENCE_LIMIT_EXCEEDED}:
                raise
            _corrupt("stored Host TestRun is corrupt", exc)
        except (OSError, TypeError, ValueError) as exc:
            _corrupt("stored Host TestRun is corrupt", exc)


__all__ = ["PublishedTestRun", "TestRunPublisher", "TestRunRepository"]
