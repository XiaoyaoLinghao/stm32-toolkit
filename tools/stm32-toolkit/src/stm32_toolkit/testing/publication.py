"""Authoritative publication and reload of completed Host and replay TestRuns."""

from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
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
    MAX_RUN_STREAM_BYTES,
    TestCaseResult,
    TestProtocolError,
    TestRunManifest,
    protocol_error,
    validate_host_identity,
)
from .replay import (
    MAX_REPLAY_DESCRIPTOR_BYTES,
    TargetReplayDescriptor,
    canonical_replay_json_bytes,
)


_HASH = re.compile(r"^[0-9a-f]{64}$")
_HOST_OPERATION = "host-test-run"
_TARGET_INPUT_OPERATION = "target-replay-input"
_TARGET_OPERATION = "target-test-replay"
_TERMINAL_STATES = frozenset({"passed", "failed", "error"})
_CASE_COUNT_STATES = ("passed", "failed", "skipped", "error", "timeout")
_ENVELOPE_METADATA = {"test_run_id", "test_manifest_sha256", "inventory_digest"}
_TARGET_PARENT_METADATA = {
    "replay_id",
    "scenario_role",
    "stream_sha256",
    "stream_size_bytes",
    "execution_source",
    "physical_transport_evidence",
    "origin_workspace_id",
    "import_workspace_id",
}
_TARGET_METADATA = {
    "descriptor_evidence_id",
    "execution_source",
    "import_workspace_id",
    "origin_workspace_id",
    "operation_id",
    "operation_intent_sha256",
    "physical_transport_evidence",
    "test_manifest_sha256",
    "test_run_id",
}
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


def _target_artifact(value: object, field: str, *, kind: str, media_type: str) -> ArtifactRef:
    if not isinstance(value, ArtifactRef):
        _publication_invalid(f"{field} must be an ArtifactRef")
    if value.kind != kind or value.media_type != media_type:
        _publication_invalid(f"{field} has an invalid Target replay artifact type")
    return value


def _target_manifest(manifest: object) -> TestRunManifest:
    if not isinstance(manifest, TestRunManifest):
        _publication_invalid("manifest must be a TestRunManifest")
    try:
        verified = TestRunManifest.from_dict(manifest.to_dict())
    except TestProtocolError:
        raise
    except (TypeError, ValueError) as exc:
        _publication_invalid("manifest is not canonical", exc)
    if verified.mode != "target" or verified.transport != "replay":
        _publication_invalid("publication requires a Target replay manifest")
    if verified.state not in _TERMINAL_STATES:
        _publication_invalid("publication requires a completed Target replay manifest")
    if verified.stdout is not None or verified.stderr is not None:
        _publication_invalid("Target replay manifests must not contain Host output artifacts")
    _target_artifact(
        verified.raw_events,
        "raw_events",
        kind="test-events",
        media_type="application/vnd.stm32.target-events",
    )
    return verified


def _target_descriptor_bytes(payload: bytes) -> TargetReplayDescriptor:
    if not isinstance(payload, bytes) or len(payload) > MAX_REPLAY_DESCRIPTOR_BYTES:
        _corrupt("stored Target replay descriptor is invalid")
    try:
        document = json.loads(payload.decode("utf-8"))
        descriptor = TargetReplayDescriptor.from_value(document)
        canonical = canonical_replay_json_bytes(descriptor.to_dict())
    except Exception as exc:
        if isinstance(exc, EvidenceValidationError) and exc.code == EVIDENCE_LIMIT_EXCEEDED:
            raise
        _corrupt("stored Target replay descriptor is invalid", exc)
    if payload not in {canonical, canonical + b"\n"}:
        _corrupt("stored Target replay descriptor is not canonical JSON")
    return descriptor


def _target_stream_validation(
    stream_bytes: bytes,
    descriptor: TargetReplayDescriptor,
) -> tuple[object, ...]:
    try:
        from .target import TargetFrameDecoder, TargetRunBinding, TargetRunValidator

        decoder = TargetFrameDecoder(max_stream_bytes=MAX_RUN_STREAM_BYTES)
        frames = decoder.feed(stream_bytes)
        decoder.finish()
        validator = TargetRunValidator(
            TargetRunBinding(
                descriptor.inventory_digest,
                descriptor.identity.build_id,
                descriptor.identity.elf_sha256,
                descriptor.identity.target_device,
            )
        )
        for frame in frames:
            validator.accept(frame)
        validator.finish()
    except TestProtocolError as exc:
        _corrupt("stored Target replay stream is invalid", exc)
    except (TypeError, ValueError, OSError) as exc:
        _corrupt("stored Target replay stream is invalid", exc)
    if not frames:
        _corrupt("stored Target replay stream is empty")
    inventory = frames[0]
    if inventory.kind != 1 or inventory.payload.get("identity") != descriptor.identity.to_dict():
        _corrupt("stored Target replay stream identity contradicts its descriptor")
    if inventory.payload.get("inventory_digest") != descriptor.inventory_digest:
        _corrupt("stored Target replay stream inventory contradicts its descriptor")
    terminal = frames[-1]
    if terminal.kind != 5 or terminal.payload.get("state") != descriptor.expected_terminal_state:
        _corrupt("stored Target replay stream terminal state contradicts its descriptor")
    return frames


def _target_manifest_matches_stream(
    manifest: TestRunManifest,
    frames: tuple[object, ...],
) -> None:
    """Bind the durable manifest projection back to the decoded Target frames."""
    try:
        run_start = next(frame for frame in frames if frame.kind == 2)
        terminal = frames[-1]
        case_starts = {
            str(frame.payload["case_id"]): frame.payload
            for frame in frames
            if frame.kind == 3
        }
        expected_cases = tuple(
            TestCaseResult(
                str(frame.payload["case_id"]),
                str(frame.payload["state"]),
                str(case_starts[str(frame.payload["case_id"])].get("started_at_utc")),
                str(frame.payload["ended_at_utc"]),
                int(frame.payload["duration_ms"]),
                frame.payload["message"],
                None,
                None,
            )
            for frame in frames
            if frame.kind == 4
        )
    except (KeyError, StopIteration, TypeError, ValueError, TestProtocolError) as exc:
        _corrupt("Target replay stream cannot produce a manifest projection", exc)
    if (
        manifest.cases != expected_cases
        or manifest.state != terminal.payload.get("state")
        or manifest.started_at_utc != run_start.payload.get("started_at_utc")
        or manifest.ended_at_utc != terminal.payload.get("ended_at_utc")
        or manifest.duration_ms != terminal.payload.get("duration_ms")
    ):
        _corrupt("Target replay manifest contradicts its decoded stream")


def _target_parent(
    evidence_store: EvidenceStore,
    descriptor_envelope: object,
    *,
    import_workspace_id: str,
) -> tuple[EvidenceEnvelope, TargetReplayDescriptor, ArtifactRef, bytes, tuple[object, ...]]:
    if not isinstance(descriptor_envelope, EvidenceEnvelope):
        _corrupt("Target replay descriptor parent is invalid")
    if descriptor_envelope.operation != _TARGET_INPUT_OPERATION or descriptor_envelope.parents != ():
        _corrupt("Target replay descriptor parent operation or ancestry is invalid")
    metadata = dict(descriptor_envelope.metadata)
    if set(metadata) != _TARGET_PARENT_METADATA:
        _corrupt("Target replay descriptor parent metadata is not closed")
    origin_workspace_id = _hash(metadata["origin_workspace_id"], "origin_workspace_id")
    parent_import_workspace_id = _hash(metadata["import_workspace_id"], "import_workspace_id")
    if parent_import_workspace_id != import_workspace_id:
        _corrupt("Target replay descriptor parent import workspace contradicts the import")
    if descriptor_envelope.identity.workspace_id != origin_workspace_id:
        _corrupt("Target replay descriptor parent origin workspace contradicts its identity")
    if metadata["execution_source"] != "replay" or metadata["physical_transport_evidence"] is not False:
        _corrupt("Target replay descriptor parent physical/source labels are invalid")
    descriptor_refs = tuple(
        artifact
        for artifact in descriptor_envelope.artifacts
        if artifact.kind == "target-replay-descriptor" and artifact.media_type == "application/json"
    )
    stream_refs = tuple(
        artifact
        for artifact in descriptor_envelope.artifacts
        if artifact.kind == "target-replay-stream" and artifact.media_type == "application/octet-stream"
    )
    if len(descriptor_refs) != 1 or len(stream_refs) != 1 or len(descriptor_envelope.artifacts) != 2:
        _corrupt("Target replay descriptor parent artifacts are invalid")
    descriptor_ref = descriptor_refs[0]
    stream_ref = stream_refs[0]
    try:
        descriptor = _target_descriptor_bytes(
            evidence_store.read_artifact(descriptor_ref, maximum_bytes=MAX_REPLAY_DESCRIPTOR_BYTES)
        )
        stream_bytes = evidence_store.read_artifact(stream_ref, maximum_bytes=MAX_EVIDENCE_READ_BYTES)
    except EvidenceValidationError as exc:
        if exc.code in {EVIDENCE_CORRUPT, EVIDENCE_LIMIT_EXCEEDED}:
            raise
        _corrupt("Target replay descriptor parent artifact is invalid", exc)
    if descriptor.identity != descriptor_envelope.identity:
        _corrupt("Target replay descriptor identity contradicts its parent envelope")
    if descriptor.replay_id != metadata["replay_id"]:
        _corrupt("Target replay descriptor ID contradicts its parent metadata")
    if descriptor.scenario_role != metadata["scenario_role"]:
        _corrupt("Target replay descriptor role contradicts its parent metadata")
    if type(metadata["stream_size_bytes"]) is not int or metadata["stream_size_bytes"] < 0:
        _corrupt("Target replay parent stream size metadata is invalid")
    if descriptor.stream.sha256 != metadata["stream_sha256"] or descriptor.stream.size_bytes != metadata["stream_size_bytes"]:
        _corrupt("Target replay descriptor stream contradicts its parent metadata")
    if stream_ref.sha256 != descriptor.stream.sha256 or stream_ref.size_bytes != descriptor.stream.size_bytes:
        _corrupt("Target replay binary stream artifact contradicts its descriptor")
    frames = _target_stream_validation(stream_bytes, descriptor)
    return descriptor_envelope, descriptor, stream_ref, stream_bytes, frames


def _target_intent_digest(
    manifest: TestRunManifest,
    descriptor_evidence_id: str,
    import_workspace_id: str,
) -> str:
    payload = {
        "operation_id": manifest.run_id,
        "descriptor_evidence_id": descriptor_evidence_id,
        "manifest": manifest.to_dict(),
        "import_workspace_id": import_workspace_id,
    }
    return sha256(canonical_json_bytes(payload)).hexdigest()


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
        if self.envelope.operation == _TARGET_OPERATION:
            data.update(
                {
                    "execution_source": self.root.metadata["execution_source"],
                    "physical_transport_evidence": self.root.metadata[
                        "physical_transport_evidence"
                    ],
                    "origin_workspace_id": self.root.metadata["origin_workspace_id"],
                    "import_workspace_id": self.root.metadata["import_workspace_id"],
                }
            )
        if authoritative:
            data["authoritative"] = True
        return data


class TestRunPublisher:
    """Publish completed Host or non-physical Target replay manifests."""

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

    def publish_target_replay(
        self,
        manifest: TestRunManifest,
        descriptor_envelope: EvidenceEnvelope,
        import_workspace_id: str,
    ) -> PublishedTestRun:
        """Publish one immutable, non-physical Target replay TestRun."""
        verified = _target_manifest(manifest)
        import_workspace_id = _hash(import_workspace_id, "import_workspace_id")
        parent, descriptor, _stream_ref, _stream_bytes, _frames = _target_parent(
            self.evidence_store,
            descriptor_envelope,
            import_workspace_id=import_workspace_id,
        )
        if verified.identity != descriptor.identity:
            _corrupt("Target replay manifest identity contradicts its descriptor")
        if verified.state != descriptor.expected_terminal_state:
            _corrupt("Target replay manifest state contradicts its descriptor")
        _target_manifest_matches_stream(verified, _frames)
        descriptor_evidence_id = str(parent.evidence_id)
        intent_digest = _target_intent_digest(
            verified, descriptor_evidence_id, import_workspace_id
        )

        # A completed identical operation is reusable across publisher instances.  A
        # different intent is left for put_root to reject without replacing the root.
        try:
            existing_root = get_root(self.evidence_store, "test-run", verified.run_id)
        except EvidenceValidationError as exc:
            if exc.code != EVIDENCE_CORRUPT:
                raise
        else:
            try:
                existing_envelope = self.evidence_store.get_envelope(existing_root.manifest_id)
            except EvidenceValidationError:
                raise
            existing_intent = dict(existing_envelope.metadata).get("operation_intent_sha256")
            if (
                existing_envelope.operation == _TARGET_OPERATION
                and existing_intent == intent_digest
            ):
                return TestRunRepository(self.evidence_store).load(verified.run_id)
            _corrupt("Target replay operation ID is already bound to another intent")

        try:
            self.evidence_store.put_envelope(parent)
        except EvidenceValidationError:
            raise
        except OSError as exc:
            _evidence_commit_failure("Target replay descriptor publication failed", exc)

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
            _evidence_commit_failure("Target replay manifest artifact publication failed", exc)

        envelope = EvidenceEnvelope(
            identity=verified.identity,
            operation=_TARGET_OPERATION,
            produced_at_utc=verified.ended_at_utc,
            parents=(descriptor_evidence_id,),
            artifacts=(manifest_artifact, verified.raw_events),
            metadata={
                "descriptor_evidence_id": descriptor_evidence_id,
                "execution_source": "replay",
                "import_workspace_id": import_workspace_id,
                "origin_workspace_id": verified.identity.workspace_id,
                "operation_id": verified.run_id,
                "operation_intent_sha256": intent_digest,
                "physical_transport_evidence": False,
                "test_manifest_sha256": manifest_artifact.sha256,
                "test_run_id": verified.run_id,
            },
        )
        try:
            self.evidence_store.put_envelope(envelope)
        except EvidenceValidationError:
            raise
        except OSError as exc:
            _evidence_commit_failure("Target replay envelope publication failed", exc)
        root = RootRecord(
            "test-run",
            verified.run_id,
            str(envelope.evidence_id),
            {
                "mode": "target",
                "state": verified.state,
                "execution_source": "replay",
                "physical_transport_evidence": False,
                "origin_workspace_id": verified.identity.workspace_id,
                "import_workspace_id": import_workspace_id,
            },
        )
        try:
            put_root(self.evidence_store, root)
        except EvidenceValidationError:
            raise
        except OSError as exc:
            _evidence_commit_failure("Target replay root publication failed", exc)
        return PublishedTestRun(verified, manifest_artifact, envelope, root)


class TestRunRepository:
    """Reload one TestRun through its exact Evidence root and object bindings."""

    def __init__(self, evidence_store: EvidenceStore) -> None:
        if not isinstance(evidence_store, EvidenceStore):
            raise TypeError("evidence_store must be an EvidenceStore")
        self.evidence_store = evidence_store

    def _load_target_replay(
        self,
        root: RootRecord,
        envelope: EvidenceEnvelope,
        run_id: str,
    ) -> PublishedTestRun:
        if envelope.operation != _TARGET_OPERATION:
            _corrupt("stored envelope operation contradicts Target replay TestRun")
        if envelope.parents and len(envelope.parents) != 1:
            _corrupt("stored Target replay envelope must have one descriptor parent")
        metadata = dict(envelope.metadata)
        if set(metadata) != _TARGET_METADATA:
            _corrupt("stored Target replay envelope metadata is not closed")
        if metadata["test_run_id"] != run_id or metadata["operation_id"] != run_id:
            _corrupt("stored Target replay operation ID contradicts the root")
        descriptor_evidence_id = metadata["descriptor_evidence_id"]
        if not isinstance(descriptor_evidence_id, str) or _HASH.fullmatch(descriptor_evidence_id) is None:
            _corrupt("stored Target replay descriptor evidence ID is invalid")
        if envelope.parents != (descriptor_evidence_id,):
            _corrupt("stored Target replay parent does not match metadata")
        import_workspace_id = _hash(metadata["import_workspace_id"], "import_workspace_id")
        origin_workspace_id = _hash(metadata["origin_workspace_id"], "origin_workspace_id")
        if metadata["execution_source"] != "replay" or metadata["physical_transport_evidence"] is not False:
            _corrupt("stored Target replay source labels are invalid")
        if envelope.identity.workspace_id != origin_workspace_id:
            _corrupt("stored Target replay origin workspace contradicts its identity")

        try:
            parent = self.evidence_store.get_envelope(descriptor_evidence_id)
        except EvidenceValidationError as exc:
            _corrupt("stored Target replay descriptor parent is absent", exc)
        _parent, descriptor, stream_ref, stream_bytes, _frames = _target_parent(
            self.evidence_store,
            parent,
            import_workspace_id=import_workspace_id,
        )
        if descriptor.identity != envelope.identity:
            _corrupt("stored Target replay descriptor identity contradicts the envelope")
        if descriptor.identity.workspace_id != origin_workspace_id:
            _corrupt("stored Target replay descriptor origin workspace contradicts metadata")

        manifest_refs = tuple(
            artifact
            for artifact in envelope.artifacts
            if artifact.kind == "test-manifest" and artifact.media_type == "application/json"
        )
        if len(manifest_refs) != 1:
            _corrupt("stored Target replay envelope has an invalid test manifest artifact")
        manifest_artifact = manifest_refs[0]
        if manifest_artifact.sha256 != metadata["test_manifest_sha256"]:
            _corrupt("stored Target replay manifest digest contradicts metadata")
        try:
            payload = self.evidence_store.read_artifact(
                manifest_artifact, maximum_bytes=MAX_EVIDENCE_READ_BYTES
            )
            manifest = _decode_manifest_bytes(payload)
        except EvidenceValidationError:
            raise
        if manifest.run_id != run_id:
            _corrupt("stored Target replay manifest run ID contradicts the root")
        if manifest.mode != "target" or manifest.transport != "replay":
            _corrupt("stored Target replay manifest has the wrong execution mode")
        if manifest.state not in _TERMINAL_STATES:
            _corrupt("stored Target replay manifest is not terminal")
        if manifest.stdout is not None or manifest.stderr is not None:
            _corrupt("stored Target replay manifest contains Host output artifacts")
        _target_artifact(
            manifest.raw_events,
            "raw_events",
            kind="test-events",
            media_type="application/vnd.stm32.target-events",
        )
        if manifest.identity != envelope.identity or manifest.identity != descriptor.identity:
            _corrupt("stored Target replay manifest identity contradicts its inputs")
        if manifest.state != descriptor.expected_terminal_state:
            _corrupt("stored Target replay manifest state contradicts its descriptor")
        _target_manifest_matches_stream(manifest, _frames)
        if manifest.raw_events.sha256 != descriptor.stream.sha256 or manifest.raw_events.size_bytes != descriptor.stream.size_bytes:
            _corrupt("stored Target replay event stream contradicts its descriptor")
        if len(envelope.artifacts) != 2 or envelope.artifacts != (manifest_artifact, manifest.raw_events):
            _corrupt("stored Target replay envelope artifact membership is invalid")
        try:
            raw_bytes = self.evidence_store.read_artifact(
                manifest.raw_events, maximum_bytes=MAX_EVIDENCE_READ_BYTES
            )
        except EvidenceValidationError:
            raise
        if raw_bytes != stream_bytes or stream_ref.sha256 != manifest.raw_events.sha256:
            _corrupt("stored Target replay event bytes contradict the descriptor stream")
        if envelope.identity != manifest.identity:
            _corrupt("stored Target replay envelope identity contradicts the manifest")
        if envelope.produced_at_utc != manifest.ended_at_utc:
            _corrupt("stored Target replay envelope time contradicts the manifest")
        expected_intent = _target_intent_digest(
            manifest, descriptor_evidence_id, import_workspace_id
        )
        if metadata["operation_intent_sha256"] != expected_intent:
            _corrupt("stored Target replay operation intent digest is invalid")
        expected_root_metadata = {
            "mode": "target",
            "state": manifest.state,
            "execution_source": "replay",
            "physical_transport_evidence": False,
            "origin_workspace_id": origin_workspace_id,
            "import_workspace_id": import_workspace_id,
        }
        if root.manifest_id != envelope.evidence_id:
            _corrupt("stored root manifest ID contradicts the Target replay envelope")
        if root.metadata != expected_root_metadata:
            _corrupt("stored root metadata contradicts the Target replay record")
        return PublishedTestRun(manifest, manifest_artifact, envelope, root)

    def load(self, run_id: str) -> PublishedTestRun:
        root = get_root(self.evidence_store, "test-run", run_id)
        try:
            envelope = self.evidence_store.get_envelope(root.manifest_id)
            if envelope.operation == _TARGET_OPERATION:
                return self._load_target_replay(root, envelope, run_id)
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
