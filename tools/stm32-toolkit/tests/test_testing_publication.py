"""Contract tests for durable Host TestRun publication and authoritative reload."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
import gc
from pathlib import Path
import shutil
import tempfile

import pytest

from stm32_toolkit.evidence import (
    EVIDENCE_CORRUPT,
    EVIDENCE_INVALID,
    EvidenceEnvelope,
    EvidenceIdentity,
    EvidenceValidationError,
    canonical_json_bytes,
)
from stm32_toolkit.evidence.gc import RootRecord
from stm32_toolkit.evidence.store import EvidenceStore
from stm32_toolkit.testing.model import (
    TestCaseResult as CaseResult,
    TestRunManifest as RunManifest,
    TestProtocolError as ProtocolError,
    create_inventory,
    host_target_device,
)
from stm32_toolkit.testing.publication import (
    TestRunPublisher as Publisher,
    TestRunRepository as Repository,
)


UTC_0 = "2026-08-20T00:00:00.000000Z"
UTC_1 = "2026-08-20T00:00:01.000000Z"


@pytest.fixture
def task_tmp() -> Path:
    path = Path(tempfile.mkdtemp(prefix="stm32tk-0601-t03-", dir="C:/tmp"))
    try:
        yield path
    finally:
        gc.collect()
        shutil.rmtree(path, ignore_errors=False)


def _identity() -> EvidenceIdentity:
    digest = lambda value: sha256(value.encode("ascii")).hexdigest()
    return EvidenceIdentity(
        workspace_id=digest("workspace"),
        project_id="123e4567-e89b-42d3-a456-426614174000",
        session_id="session-0601-t03",
        build_id=digest("host-build"),
        elf_sha256=digest("host-tests"),
        target_device=host_target_device(system="Windows", architecture="AMD64"),
        input_snapshot_sha256=digest("snapshot"),
        git_commit="a" * 40,
        git_dirty=False,
    )


def _fixture(task_tmp: Path, *, state: str = "failed") -> tuple[
    EvidenceStore, RunManifest, object
]:
    project = task_tmp / "project"
    project.mkdir()
    store = EvidenceStore(task_tmp / "evidence")
    identity = _identity()
    raw_path = project / "raw-events.xml"
    stdout_path = project / "stdout.txt"
    stderr_path = project / "stderr.txt"
    raw_path.write_bytes(b"<testsuite><testcase name='case-1'/></testsuite>")
    stdout_path.write_bytes(b"CTest output\n")
    stderr_path.write_bytes(b"CTest failure\n")
    raw = store.ingest_file(raw_path, kind="test-events", media_type="application/xml")
    stdout = store.ingest_file(stdout_path, kind="test-stdout", media_type="text/plain; charset=utf-8")
    stderr = store.ingest_file(stderr_path, kind="test-stderr", media_type="text/plain; charset=utf-8")
    case_state = state if state in {"failed", "error"} else "passed"
    case = CaseResult(
        "case-1", case_state, UTC_0, UTC_1, 1000,
        "failed" if state == "failed" else "error" if state == "error" else None,
        None, None,
    )
    manifest = RunManifest(
        "stm32-test/1", "run-0601-t03", "host", state, identity, None,
        (case,), UTC_0, UTC_1, 1000, stdout, stderr, raw,
    )
    inventory = create_inventory("host", identity, ("case-1",), UTC_0)
    return store, manifest, inventory


def _publisher(task_tmp: Path, store: EvidenceStore) -> Publisher:
    project = task_tmp / "project"
    return Publisher(store, project, task_tmp / "external-results")


def _summary(manifest: RunManifest) -> dict[str, object]:
    return {
        "run_id": manifest.run_id,
        "mode": manifest.mode,
        "state": manifest.state,
        "identity": manifest.identity.to_dict(),
        "transport": manifest.transport,
        "case_counts": {
            state: sum(case.state == state for case in manifest.cases)
            for state in ("passed", "failed", "skipped", "error", "timeout")
        },
        "started_at_utc": manifest.started_at_utc,
        "ended_at_utc": manifest.ended_at_utc,
        "duration_ms": manifest.duration_ms,
    }


def test_failed_host_run_publishes_four_artifacts_and_reloads_by_run_id(task_tmp: Path):
    """Failure is a durable product result, and reload uses only authoritative bindings."""
    store, manifest, inventory = _fixture(task_tmp)
    published = _publisher(task_tmp, store).publish_host(
        manifest, inventory_digest=inventory.inventory_digest
    )

    expected_public = {
        "run": _summary(manifest),
        "test_manifest": published.manifest_artifact.to_dict(),
        "evidence_id": published.envelope.evidence_id,
    }
    assert published.public_data() == expected_public
    assert published.envelope.operation == "host-test-run"
    assert published.envelope.identity == manifest.identity
    assert published.envelope.metadata == {
        "test_run_id": manifest.run_id,
        "test_manifest_sha256": published.manifest_artifact.sha256,
        "inventory_digest": inventory.inventory_digest,
    }
    assert published.envelope.artifacts == (
        published.manifest_artifact,
        manifest.raw_events,
        manifest.stdout,
        manifest.stderr,
    )
    assert published.root == RootRecord(
        "test-run", manifest.run_id, str(published.envelope.evidence_id),
        {"mode": "host", "state": manifest.state},
    )

    loaded = Repository(store).load(manifest.run_id)
    assert loaded.public_data(authoritative=True) == {**expected_public, "authoritative": True}
    assert loaded.manifest == manifest


def test_publication_rejects_non_host_or_incomplete_manifest(task_tmp: Path):
    """Only completed Host manifests may cross the Host publication boundary."""
    store, manifest, inventory = _fixture(task_tmp)
    publisher = _publisher(task_tmp, store)
    for candidate in (
        replace(manifest, state="running"),
        replace(manifest, mode="target"),
        replace(manifest, transport="serial"),
        replace(manifest, stdout=None),
        replace(manifest, stderr=None),
    ):
        with pytest.raises(ProtocolError):
            publisher.publish_host(candidate, inventory_digest=inventory.inventory_digest)


@pytest.mark.parametrize("state", ["passed", "failed", "error"])
def test_publication_accepts_each_terminal_host_state(task_tmp: Path, state: str):
    """Every terminal Host outcome, including failure, is a publishable product record."""
    store, manifest, inventory = _fixture(task_tmp, state=state)

    published = _publisher(task_tmp, store).publish_host(
        manifest, inventory_digest=inventory.inventory_digest
    )

    assert published.manifest.state == state


def test_publication_stops_on_root_conflict_without_replacing_existing_root(task_tmp: Path):
    """A same-run root conflict is fail-closed and never silently repaired."""
    store, manifest, inventory = _fixture(task_tmp)
    publisher = _publisher(task_tmp, store)
    first = publisher.publish_host(manifest, inventory_digest=inventory.inventory_digest)
    root_bytes = first.root and (store.root / "roots" / "test-run").glob("*.json")
    root_path = next(root_bytes)
    original = root_path.read_bytes()

    with pytest.raises(ProtocolError):
        publisher.publish_host(manifest, inventory_digest="1" * 64)

    assert root_path.read_bytes() == original


@pytest.mark.parametrize("contradiction", ["root", "envelope", "manifest", "digest"])
def test_repository_rejects_root_envelope_manifest_and_digest_contradictions(
    task_tmp: Path, contradiction: str,
):
    """Authoritative reload must bind run ID, envelope, manifest artifact, and digests together."""
    store, manifest, inventory = _fixture(task_tmp)
    published = _publisher(task_tmp, store).publish_host(
        manifest, inventory_digest=inventory.inventory_digest
    )
    root_path = next((store.root / "roots" / "test-run").glob("*.json"))
    envelope_path = store.root / "manifests" / f"{published.envelope.evidence_id}.json"
    if contradiction == "root":
        root_path.write_bytes(canonical_json_bytes(RootRecord(
            "test-run", manifest.run_id, "0" * 64, {"mode": "host", "state": manifest.state}
        ).to_dict()))
    elif contradiction == "envelope":
        envelope = EvidenceEnvelope(
            identity=published.envelope.identity,
            operation="other-operation",
            produced_at_utc=published.envelope.produced_at_utc,
            parents=published.envelope.parents,
            artifacts=published.envelope.artifacts,
            metadata=published.envelope.metadata,
        )
        envelope_path.write_bytes(envelope.to_json_bytes())
    elif contradiction == "manifest":
        manifest_path = store.root.joinpath(*published.manifest_artifact.relative_path.split("/"))
        changed = deepcopy(manifest.to_dict())
        changed["run_id"] = "other-run"
        manifest_path.write_bytes(canonical_json_bytes(changed))
    else:
        envelope = EvidenceEnvelope(
            identity=published.envelope.identity,
            operation=published.envelope.operation,
            produced_at_utc=published.envelope.produced_at_utc,
            parents=published.envelope.parents,
            artifacts=published.envelope.artifacts,
            metadata={**published.envelope.metadata, "test_manifest_sha256": "1" * 64},
        )
        envelope_path.write_bytes(envelope.to_json_bytes())

    with pytest.raises(EvidenceValidationError) as corrupt_failure:
        Repository(store).load(manifest.run_id)
    assert corrupt_failure.value.code == EVIDENCE_CORRUPT


def test_repository_preserves_malformed_run_id_as_caller_input_error(task_tmp: Path):
    """The repository does not reinterpret malformed lookup IDs as stored corruption."""
    store, _manifest, _inventory = _fixture(task_tmp)

    with pytest.raises(EvidenceValidationError) as invalid:
        Repository(store).load("invalid/run-id")

    assert invalid.value.code == EVIDENCE_INVALID
