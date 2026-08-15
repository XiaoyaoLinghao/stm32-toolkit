"""Real-filesystem safety contract for reachability-based evidence GC."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from threading import Event
import time

import pytest

from stm32_toolkit.evidence.gc import (
    REGISTERED_ROOT_TYPES,
    GcPlan,
    apply_gc,
    plan_gc,
    put_root,
)
from stm32_toolkit.evidence.model import (
    ArtifactRef,
    EvidenceEnvelope,
    EvidenceIdentity,
    canonical_json_bytes,
)
from stm32_toolkit.evidence.store import EvidenceStore


@pytest.fixture
def tmp_path():
    """Use a fresh C:\\tmp direct child for the frozen Windows coverage contract."""
    path = Path(tempfile.mkdtemp(prefix="stm32tk-0601-t05-gc-", dir=r"C:\tmp"))
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=False)


def _identity() -> EvidenceIdentity:
    return EvidenceIdentity(
        workspace_id="a" * 64,
        project_id="123e4567-e89b-42d3-a456-426614174000",
        session_id="session-01",
        build_id="b" * 64,
        elf_sha256="c" * 64,
        target_device="host:windows/amd64",
        input_snapshot_sha256="d" * 64,
        git_commit="e" * 40,
        git_dirty=False,
    )


def _put(store: EvidenceStore, source: Path, marker: bytes, *artifacts: ArtifactRef):
    source.write_bytes(marker)
    own = store.ingest_file(source, kind="log", media_type="application/octet-stream")
    envelope = EvidenceEnvelope(
        identity=_identity(),
        operation="test.host",
        produced_at_utc="2026-08-15T01:02:03.123456Z",
        parents=(),
        artifacts=(own, *artifacts),
        metadata={"marker": marker.hex()},
    )
    store.put_envelope(envelope)
    return envelope, own


def _root(store: EvidenceStore, name: str, document: object) -> Path:
    directory = store.root / "roots"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_bytes(canonical_json_bytes(document))
    return path


def _typed_root(root_type: str, root_id: str, manifest_id: str, metadata=None):
    return {
        "root_type": root_type,
        "root_id": root_id,
        "manifest_id": manifest_id,
        "metadata": {} if metadata is None else metadata,
    }


def _object(store: EvidenceStore, artifact: ArtifactRef) -> Path:
    return store.root.joinpath(*artifact.relative_path.split("/"))


def test_registered_typed_roots_are_closed_and_shared_objects_follow_reachability(tmp_path):
    """Ignoring a root field/type or counting a shared object twice could delete live evidence."""
    store = EvidenceStore(tmp_path / "evidence")
    shared_source = tmp_path / "shared.bin"
    shared_source.write_bytes(b"shared")
    shared = store.ingest_file(shared_source, kind="trace", media_type="application/octet-stream")
    kept, kept_own = _put(store, tmp_path / "kept.bin", b"kept", shared)
    dropped, dropped_own = _put(store, tmp_path / "dropped.bin", b"dropped", shared)
    for index, root_type in enumerate(sorted(REGISTERED_ROOT_TYPES)):
        manifest = kept if index == 0 else dropped
        _root(
            store,
            f"{index}.json",
            _typed_root(root_type, f"root-{index}", str(manifest.evidence_id), {"index": index}),
        )

    plan = plan_gc(store)

    assert REGISTERED_ROOT_TYPES == frozenset(
        {"test-run", "diagnostic-session", "bundle", "annotation"}
    )
    assert [set(root.to_dict()) for root in plan.roots] == [
        {"root_type", "root_id", "manifest_id", "metadata"}
    ] * 4
    assert plan.reachable_objects == tuple(
        sorted(
            {shared.relative_path, kept_own.relative_path, dropped_own.relative_path},
            key=lambda value: value.encode("utf-8"),
        )
    )
    assert plan.unreachable_objects == ()


def test_typed_root_publication_is_idempotent_but_never_overwrites_identity(tmp_path):
    """One logical root identity must not be silently replaced with different metadata."""
    store = EvidenceStore(tmp_path / "evidence")
    envelope, _artifact = _put(store, tmp_path / "root-publish.bin", b"root-publish")
    document = _typed_root("test-run", "published", str(envelope.evidence_id))

    first = put_root(store, document)
    second = put_root(store, document)

    assert second == first
    conflict = _typed_root(
        "test-run", "published", str(envelope.evidence_id), {"changed": True}
    )
    with pytest.raises(ValueError, match="different canonical bytes"):
        put_root(store, conflict)


def test_apply_rejects_non_plan_values_before_authorization(tmp_path):
    """An arbitrary object must not cross the canonical plan authority boundary."""
    with pytest.raises(ValueError, match="GcPlan"):
        apply_gc(object(), "0" * 64, "0" * 64)  # type: ignore[arg-type]


def test_root_reachability_walks_parent_manifest_graph(tmp_path):
    """Collecting only direct artifacts would delete evidence inherited through a rooted parent."""
    store = EvidenceStore(tmp_path / "evidence")
    parent, parent_artifact = _put(store, tmp_path / "parent.bin", b"parent")
    child_source = tmp_path / "child.bin"
    child_source.write_bytes(b"child")
    child_artifact = store.ingest_file(
        child_source, kind="log", media_type="application/octet-stream"
    )
    child = EvidenceEnvelope(
        identity=_identity(),
        operation="test.child",
        produced_at_utc="2026-08-15T01:02:04.123456Z",
        parents=(str(parent.evidence_id),),
        artifacts=(child_artifact,),
        metadata={"result": "pass"},
    )
    store.put_envelope(child)
    _root(
        store,
        "child.json",
        _typed_root("test-run", "child", str(child.evidence_id)),
    )

    plan = plan_gc(store)

    assert parent_artifact.relative_path in plan.reachable_objects
    assert child_artifact.relative_path in plan.reachable_objects
    assert plan.unreachable_objects == ()


def test_missing_parent_manifest_makes_reachability_conservatively_closed(tmp_path):
    """A broken parent edge must retain all objects because the ancestor closure is unknowable."""
    store = EvidenceStore(tmp_path / "evidence")
    child, artifact = _put(store, tmp_path / "missing-parent.bin", b"missing-parent")
    broken = EvidenceEnvelope(
        identity=child.identity,
        operation=child.operation,
        produced_at_utc=child.produced_at_utc,
        parents=("0" * 64,),
        artifacts=child.artifacts,
        metadata=child.metadata,
    )
    store.put_envelope(broken)
    _root(
        store,
        "broken-parent.json",
        _typed_root("test-run", "broken-parent", str(broken.evidence_id)),
    )

    plan = plan_gc(store)

    assert "manifest:" + "0" * 64 in plan.corrupt_entries
    assert artifact.relative_path in plan.reachable_objects
    assert plan.unreachable_objects == ()


def test_canonical_dry_run_and_action_digest_bind_every_frozen_field(tmp_path):
    """A nondeterministic or incompletely bound plan could authorize a different deletion."""
    store = EvidenceStore(tmp_path / "evidence")
    envelope, artifact = _put(store, tmp_path / "orphan.bin", b"orphan")

    first = plan_gc(store)
    second = plan_gc(store)

    assert isinstance(first, GcPlan)
    assert first.to_json_bytes() == second.to_json_bytes()
    assert first.plan_digest == second.plan_digest
    assert first.unreachable_objects == (artifact.relative_path,)
    assert first.bytes_reclaimable == artifact.size_bytes
    bound = {
        "operation": "evidence.gc.apply",
        "store_id": first.store_id,
        "plan_digest": first.plan_digest,
        "manifest_snapshot_digest": first.manifest_snapshot_digest,
        "bytes_reclaimable": first.bytes_reclaimable,
    }
    assert first.action_digest == hashlib.sha256(canonical_json_bytes(bound)).hexdigest()
    document = json.loads(first.to_json_bytes())
    assert document["schema"] == "stm32-evidence-gc-plan/1"
    assert document["plan_digest"] == hashlib.sha256(
        canonical_json_bytes({key: value for key, value in document.items() if key != "plan_digest"})
    ).hexdigest()
    assert str(envelope.evidence_id) in first.manifest_ids


@pytest.mark.parametrize(
    "document",
    [
        _typed_root("future-root", "future-1", "0" * 64, {"object": "1" * 64}),
        _typed_root("test-run", "missing-manifest", "0" * 64),
        {"root_type": "test-run", "root_id": "missing-fields"},
        {**_typed_root("test-run", "extra", "0" * 64), "future": True},
        _typed_root("test-run", "", "0" * 64),
        _typed_root("test-run", "bad-manifest", "A" * 64),
        _typed_root("test-run", "bad-metadata", "0" * 64, []),
    ],
)
def test_unknown_or_malformed_future_root_conservatively_retains_every_object(tmp_path, document):
    """Guessing future root semantics could collect an object referenced only by new metadata."""
    store = EvidenceStore(tmp_path / "evidence")
    _envelope, artifact = _put(store, tmp_path / "future.bin", b"future")
    _root(store, "future.json", document)

    plan = plan_gc(store)

    assert plan.unreachable_objects == ()
    assert artifact.relative_path in plan.reachable_objects
    assert plan.unknown_entries or plan.corrupt_entries
    assert _object(store, artifact).exists()


def test_corrupt_hard_linked_and_unknown_entries_are_reported_and_never_reclaimable(tmp_path):
    """Trusting names without real file verification could unlink corrupt or aliased evidence."""
    store = EvidenceStore(tmp_path / "evidence")
    _one, corrupt = _put(store, tmp_path / "corrupt-source.bin", b"corrupt-me")
    _object(store, corrupt).write_bytes(b"wrong bytes")
    _two, linked = _put(store, tmp_path / "linked-source.bin", b"hard-linked")
    os.link(_object(store, linked), tmp_path / "outside-alias.bin")
    unknown = store.root / "objects" / "sha256" / "zz" / "not-an-object"
    unknown.parent.mkdir(parents=True)
    unknown.write_bytes(b"unknown")

    plan = plan_gc(store)

    assert plan.unreachable_objects == ()
    assert any(corrupt.sha256 in entry for entry in plan.corrupt_entries)
    assert any(linked.sha256 in entry for entry in plan.corrupt_entries)
    assert any("not-an-object" in entry for entry in plan.unknown_entries)
    assert plan.bytes_reclaimable == 0


def test_directory_at_canonical_object_path_is_corrupt_and_retained(tmp_path):
    """Treating a directory as an object could recurse into or delete an attacker-controlled tree."""
    store = EvidenceStore(tmp_path / "evidence")
    digest = "7" * 64
    special = store.root / "objects" / "sha256" / digest[:2] / digest
    special.mkdir(parents=True)

    plan = plan_gc(store)

    assert f"objects/sha256/{digest[:2]}/{digest}" in plan.corrupt_entries
    assert plan.unreachable_objects == ()
    assert special.is_dir()


def test_roots_junction_is_reported_without_following_external_records(tmp_path):
    """Following a reparse root directory could import reachability from outside the store."""
    store = EvidenceStore(tmp_path / "evidence")
    _envelope, artifact = _put(store, tmp_path / "junction.bin", b"junction")
    external = tmp_path / "external-roots"
    external.mkdir()
    (external / "forged.json").write_bytes(
        canonical_json_bytes(_typed_root("test-run", "outside", "0" * 64))
    )
    junction = store.root / "roots"
    result = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(junction), str(external)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout

    plan = plan_gc(store)

    assert "roots" in plan.corrupt_entries
    assert artifact.relative_path in plan.reachable_objects
    assert plan.unreachable_objects == ()


@pytest.mark.parametrize("authorized", [False, True, None, "0" * 64, 1])
def test_apply_requires_exact_action_digest_and_never_deletes_on_authorization_failure(
    tmp_path, authorized
):
    """Boolean/coerced/stale authorization must not authorize a MODIFY operation."""
    store = EvidenceStore(tmp_path / "evidence")
    _envelope, artifact = _put(store, tmp_path / "auth.bin", b"auth")
    plan = plan_gc(store)

    result = apply_gc(plan, authorized, plan.plan_digest)

    assert result.success is False
    assert result.code == "GC_AUTHORIZATION_INVALID"
    assert _object(store, artifact).exists()


def test_authorization_is_single_use_and_expected_digest_is_exact(tmp_path):
    """Reusing one action digest or changing the expected plan digest could repeat deletion."""
    store = EvidenceStore(tmp_path / "evidence")
    _envelope, artifact = _put(store, tmp_path / "once.bin", b"once")
    wrong_plan = plan_gc(store)
    mismatch = apply_gc(wrong_plan, wrong_plan.action_digest, "0" * 64)
    assert mismatch.code == "GC_PLAN_DIGEST_MISMATCH"
    assert _object(store, artifact).exists()

    _new_envelope, new_artifact = _put(store, tmp_path / "new-action.bin", b"new-action")
    plan = plan_gc(store)
    assert plan.action_digest != wrong_plan.action_digest
    first = apply_gc(plan, plan.action_digest, plan.plan_digest)
    second = apply_gc(plan, plan.action_digest, plan.plan_digest)

    assert first.success is True
    assert set(first.deleted_objects) == {
        artifact.relative_path,
        new_artifact.relative_path,
    }
    assert json.loads(first.to_json_bytes()) == first.to_dict()
    assert second.success is False
    assert second.code == "GC_AUTHORIZATION_CONSUMED"


def test_action_digest_cannot_be_reused_through_an_equivalent_plan_instance(tmp_path):
    """Token consumption must be store-scoped, not scoped to one mutable Python plan object."""
    store = EvidenceStore(tmp_path / "evidence")
    _envelope, artifact = _put(store, tmp_path / "duplicate-plan.bin", b"duplicate-plan")
    first_plan = plan_gc(store)
    second_plan = plan_gc(store)
    assert first_plan.action_digest == second_plan.action_digest

    first = apply_gc(first_plan, first_plan.action_digest, "0" * 64)
    second = apply_gc(second_plan, second_plan.action_digest, second_plan.plan_digest)

    assert first.code == "GC_PLAN_DIGEST_MISMATCH"
    assert second.code == "GC_AUTHORIZATION_CONSUMED"
    assert _object(store, artifact).exists()


def test_mutated_plan_or_action_binding_is_rejected_before_deletion(tmp_path):
    """Changing the prepared plan object must not turn its old digest into new authority."""
    store = EvidenceStore(tmp_path / "evidence")
    _envelope, artifact = _put(store, tmp_path / "mutated.bin", b"mutated")
    plan = plan_gc(store)
    original_plan_digest = plan.plan_digest
    plan.bytes_reclaimable += 1

    result = apply_gc(plan, plan.action_digest, original_plan_digest)

    assert result.success is False
    assert result.code == "GC_PLAN_INVALID"
    assert _object(store, artifact).exists()


def test_any_store_change_after_plan_fails_closed_without_deletion(tmp_path):
    """Applying a plan to a changed manifest/object snapshot could delete newly live evidence."""
    store = EvidenceStore(tmp_path / "evidence")
    _envelope, orphan = _put(store, tmp_path / "orphan.bin", b"orphan")
    plan = plan_gc(store)
    _put(store, tmp_path / "new.bin", b"new")

    result = apply_gc(plan, plan.action_digest, plan.plan_digest)

    assert result.success is False
    assert result.code == "GC_STORE_CHANGED"
    assert _object(store, orphan).exists()


def test_partial_delete_failure_reports_exact_progress_and_never_claims_success(tmp_path):
    """A later unlink failure must not hide already deleted objects behind a success result."""
    plain = EvidenceStore(tmp_path / "evidence")
    _first, artifact_one = _put(plain, tmp_path / "one.bin", b"one")
    _second, artifact_two = _put(plain, tmp_path / "two.bin", b"two")
    calls = 0

    def inject(point: str) -> None:
        nonlocal calls
        if point == "gc.before_delete":
            calls += 1
            if calls == 2:
                raise OSError("injected second delete failure")

    store = EvidenceStore(plain.root, fault_injector=inject)
    plan = plan_gc(store)
    result = apply_gc(plan, plan.action_digest, plan.plan_digest)

    assert result.success is False
    assert result.code == "GC_PARTIAL_DELETE"
    assert len(result.deleted_objects) == 1
    assert result.bytes_reclaimed in {artifact_one.size_bytes, artifact_two.size_bytes}
    assert len([path for path in (_object(store, artifact_one), _object(store, artifact_two)) if path.exists()]) == 1
    assert result.errors and "second delete failure" in result.errors[0]


def test_concurrent_new_root_at_delete_boundary_is_detected_and_object_is_retained(tmp_path):
    """A root created after planning but before unlink must win the reachability race."""
    plain = EvidenceStore(tmp_path / "evidence")
    envelope, artifact = _put(plain, tmp_path / "race.bin", b"race")
    injected = False

    def inject(point: str) -> None:
        nonlocal injected
        if point == "gc.before_delete" and not injected:
            injected = True
            _root(
                plain,
                "concurrent.json",
                _typed_root("test-run", "concurrent", str(envelope.evidence_id)),
            )

    store = EvidenceStore(plain.root, fault_injector=inject)
    plan = plan_gc(store)
    result = apply_gc(plan, plan.action_digest, plan.plan_digest)

    assert injected is True
    assert result.success is False
    assert result.code == "GC_STORE_CHANGED"
    assert result.deleted_objects == ()
    assert _object(store, artifact).exists()


def test_concurrent_root_after_snapshot_validation_still_prevents_unlink(tmp_path):
    """The final validation-to-unlink boundary must retain an object that becomes referenced."""
    plain = EvidenceStore(tmp_path / "evidence")
    envelope, artifact = _put(plain, tmp_path / "late-race.bin", b"late-race")
    injected = False

    def inject(point: str) -> None:
        nonlocal injected
        if point == "gc.before_unlink" and not injected:
            injected = True
            _root(
                plain,
                "late-concurrent.json",
                _typed_root("test-run", "late-concurrent", str(envelope.evidence_id)),
            )

    store = EvidenceStore(plain.root, fault_injector=inject)
    plan = plan_gc(store)
    result = apply_gc(plan, plan.action_digest, plan.plan_digest)

    assert injected is True
    assert result.success is False
    assert result.code == "GC_STORE_CHANGED"
    assert _object(store, artifact).exists()


def test_root_created_after_absent_roots_enumeration_is_not_missed(tmp_path):
    """An absent top directory must remain absent through the complete final enumeration."""
    plain = EvidenceStore(tmp_path / "evidence")
    envelope, artifact = _put(plain, tmp_path / "absent-roots.bin", b"absent-roots")
    injected = False

    def inject(point: str) -> None:
        nonlocal injected
        if point == "gc.final-snapshot.after-top.roots" and not injected:
            injected = True
            _root(
                plain,
                "created-during-scan.json",
                _typed_root("test-run", "created-during-scan", str(envelope.evidence_id)),
            )

    store = EvidenceStore(plain.root, fault_injector=inject)
    plan = plan_gc(store)
    result = apply_gc(plan, plan.action_digest, plan.plan_digest)

    assert injected is True
    assert result.success is False
    assert result.code == "GC_STORE_CHANGED"
    assert _object(store, artifact).exists()


def test_root_created_in_scanned_nested_registry_directory_is_not_missed(tmp_path):
    """Every traversed directory, not only roots itself, must remain stable through enumeration."""
    plain = EvidenceStore(tmp_path / "evidence")
    kept, _kept_artifact = _put(plain, tmp_path / "nested-kept.bin", b"nested-kept")
    orphan, orphan_artifact = _put(
        plain, tmp_path / "nested-orphan.bin", b"nested-orphan"
    )
    put_root(
        plain,
        _typed_root("test-run", "nested-kept", str(kept.evidence_id)),
    )
    injected = False

    def inject(point: str) -> None:
        nonlocal injected
        if point == "gc.final-snapshot.after-top.roots" and not injected:
            injected = True
            nested = plain.root / "roots" / "test-run" / "late.json"
            nested.write_bytes(
                canonical_json_bytes(
                    _typed_root("test-run", "nested-late", str(orphan.evidence_id))
                )
            )

    store = EvidenceStore(plain.root, fault_injector=inject)
    plan = plan_gc(store)
    assert plan.unreachable_objects == (orphan_artifact.relative_path,)
    result = apply_gc(plan, plan.action_digest, plan.plan_digest)

    assert injected is True
    assert result.success is False
    assert result.code == "GC_STORE_CHANGED"
    assert _object(store, orphan_artifact).exists()


def test_root_publisher_and_gc_share_cross_thread_mutation_coordination(tmp_path):
    """A publisher that wins the shared lock must make the waiting GC retain its new root."""
    plain = EvidenceStore(tmp_path / "evidence")
    envelope, artifact = _put(plain, tmp_path / "locked-race.bin", b"locked-race")
    plan = plan_gc(plain)
    publisher_holds_lock = Event()
    release_publisher = Event()

    def inject(point: str) -> None:
        if point == "gc-root.before_publish":
            publisher_holds_lock.set()
            assert release_publisher.wait(timeout=10)

    publishing_store = EvidenceStore(plain.root, fault_injector=inject)
    document = _typed_root("test-run", "locked-race", str(envelope.evidence_id))
    with ThreadPoolExecutor(max_workers=2) as pool:
        publication = pool.submit(put_root, publishing_store, document)
        assert publisher_holds_lock.wait(timeout=10)
        collection = pool.submit(apply_gc, plan, plan.action_digest, plan.plan_digest)
        release_publisher.set()
        root_path = publication.result(timeout=10)
        result = collection.result(timeout=10)

    assert root_path.exists()
    assert result.success is False
    assert result.code == "GC_STORE_CHANGED"
    assert _object(plain, artifact).exists()


@pytest.mark.parametrize("publisher_kind", ["object", "manifest"])
def test_task4_publisher_wins_shared_lock_and_gc_retains(tmp_path, publisher_kind):
    """Task4 object/manifest publication before GC validation must invalidate collection."""
    plain = EvidenceStore(tmp_path / "evidence")
    _orphan_envelope, orphan = _put(plain, tmp_path / "orphan-publish.bin", b"orphan-publish")
    source = tmp_path / "published.bin"
    source.write_bytes(b"published")
    published_artifact = plain.ingest_file(
        source, kind="log", media_type="application/octet-stream"
    )
    envelope = EvidenceEnvelope(
        identity=_identity(),
        operation="test.publisher",
        produced_at_utc="2026-08-15T01:02:05.123456Z",
        parents=(),
        artifacts=(published_artifact,),
        metadata={"publisher": publisher_kind},
    )
    plan = plan_gc(plain)
    publisher_holds_lock = Event()
    release_publisher = Event()
    fault = "artifact.before_publish" if publisher_kind == "object" else "manifest.before_publish"

    def inject(point: str) -> None:
        if point == fault:
            publisher_holds_lock.set()
            assert release_publisher.wait(timeout=10)

    publishing_store = EvidenceStore(plain.root, fault_injector=inject)

    def publish():
        if publisher_kind == "object":
            another = tmp_path / "published-late.bin"
            another.write_bytes(b"published-late")
            return publishing_store.ingest_file(
                another, kind="log", media_type="application/octet-stream"
            )
        return publishing_store.put_envelope(envelope)

    with ThreadPoolExecutor(max_workers=2) as pool:
        publication = pool.submit(publish)
        assert publisher_holds_lock.wait(timeout=10)
        collection = pool.submit(apply_gc, plan, plan.action_digest, plan.plan_digest)
        release_publisher.set()
        publication.result(timeout=10)
        result = collection.result(timeout=10)

    assert result.success is False
    assert result.code == "GC_STORE_CHANGED"
    assert _object(plain, orphan).exists()


@pytest.mark.parametrize("publisher_kind", ["object", "manifest", "root"])
def test_gc_wins_shared_lock_and_publishers_cannot_enter_delete_window(tmp_path, publisher_kind):
    """A waiting publisher may proceed only after GC completes its locked deletion decision."""
    base = EvidenceStore(tmp_path / "evidence")
    envelope, artifact = _put(base, tmp_path / "gc-first.bin", b"gc-first")
    gc_holds_lock = Event()
    release_gc = Event()
    publisher_attempted = Event()

    def inject(point: str) -> None:
        if point == "gc.locked.before_validate":
            gc_holds_lock.set()
            assert release_gc.wait(timeout=10)

    collecting_store = EvidenceStore(base.root, fault_injector=inject)
    plan = plan_gc(collecting_store)

    def publish():
        publisher_attempted.set()
        publishing_store = EvidenceStore(base.root)
        if publisher_kind == "object":
            source = tmp_path / "after-gc.bin"
            source.write_bytes(b"after-gc")
            return publishing_store.ingest_file(
                source, kind="log", media_type="application/octet-stream"
            )
        if publisher_kind == "manifest":
            return publishing_store.put_envelope(envelope)
        return put_root(
            publishing_store,
            _typed_root("test-run", "after-gc", str(envelope.evidence_id)),
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        collection = pool.submit(apply_gc, plan, plan.action_digest, plan.plan_digest)
        assert gc_holds_lock.wait(timeout=10)
        publication = pool.submit(publish)
        assert publisher_attempted.wait(timeout=10)
        assert not publication.done()
        release_gc.set()
        result = collection.result(timeout=10)
        if publisher_kind == "object":
            assert publication.result(timeout=10).size_bytes == len(b"after-gc")
        else:
            with pytest.raises((FileNotFoundError, ValueError)):
                publication.result(timeout=10)

    assert result.success is True
    assert artifact.relative_path in result.deleted_objects
    assert not _object(base, artifact).exists()


def test_root_publisher_and_gc_share_cross_process_mutation_coordination(tmp_path):
    """The same store lock must order an external publisher before destructive apply."""
    store = EvidenceStore(tmp_path / "evidence")
    envelope, artifact = _put(store, tmp_path / "process-race.bin", b"process-race")
    plan = plan_gc(store)
    child = r"""
import sys
from stm32_toolkit.evidence.gc import put_root
from stm32_toolkit.evidence.store import EvidenceStore

def inject(point):
    if point == "gc-root.before_publish":
        print("publisher-locked", flush=True)
        sys.stdin.readline()

root, manifest_id = sys.argv[1:]
store = EvidenceStore(root, fault_injector=inject)
put_root(store, {
    "root_type": "test-run",
    "root_id": "process-race",
    "manifest_id": manifest_id,
    "metadata": {},
})
print("publisher-done", flush=True)
"""
    process = subprocess.Popen(
        [sys.executable, "-c", child, str(store.root), str(envelope.evidence_id)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert process.stdout is not None
    assert process.stdin is not None
    assert process.stdout.readline().strip() == "publisher-locked"
    with ThreadPoolExecutor(max_workers=1) as pool:
        collection = pool.submit(apply_gc, plan, plan.action_digest, plan.plan_digest)
        process.stdin.write("release\n")
        process.stdin.flush()
        assert process.stdout.readline().strip() == "publisher-done"
        assert process.wait(timeout=10) == 0, process.stderr.read() if process.stderr else ""
        result = collection.result(timeout=10)

    assert result.success is False
    assert result.code == "GC_STORE_CHANGED"
    assert _object(store, artifact).exists()


@pytest.mark.parametrize("publisher_kind", ["object", "manifest", "root"])
def test_gc_first_lock_orders_each_independent_process_publisher(tmp_path, publisher_kind):
    """An external publisher cannot cross a GC-held deletion boundary for any store record type."""
    base = EvidenceStore(tmp_path / "evidence")
    envelope, artifact = _put(base, tmp_path / "process-gc-first.bin", b"process-gc-first")
    source = tmp_path / "process-new-object.bin"
    source.write_bytes(b"process-new-object")
    attempted = tmp_path / "process-attempted"
    status = tmp_path / "process-status"
    gc_holds_lock = Event()
    release_gc = Event()

    def inject(point: str) -> None:
        if point == "gc.locked.before_validate":
            gc_holds_lock.set()
            assert release_gc.wait(timeout=10)

    plan = plan_gc(EvidenceStore(base.root, fault_injector=inject))
    child = r"""
import sys
from pathlib import Path
from stm32_toolkit.evidence.gc import put_root
from stm32_toolkit.evidence.store import EvidenceStore

root, kind, evidence_id, source, attempted, status = sys.argv[1:]
store = EvidenceStore(root)
envelope = store.get_envelope(evidence_id)
Path(attempted).write_text("attempted", encoding="utf-8")
try:
    if kind == "object":
        store.ingest_file(Path(source), kind="log", media_type="application/octet-stream")
    elif kind == "manifest":
        store.put_envelope(envelope)
    else:
        put_root(store, {
            "root_type": "test-run",
            "root_id": "process-after-gc",
            "manifest_id": evidence_id,
            "metadata": {},
        })
except (FileNotFoundError, ValueError):
    Path(status).write_text("rejected", encoding="utf-8")
else:
    Path(status).write_text("published", encoding="utf-8")
"""
    with ThreadPoolExecutor(max_workers=1) as pool:
        collection = pool.submit(apply_gc, plan, plan.action_digest, plan.plan_digest)
        assert gc_holds_lock.wait(timeout=10)
        process = subprocess.Popen(
            [
                sys.executable,
                "-c",
                child,
                str(base.root),
                publisher_kind,
                str(envelope.evidence_id),
                str(source),
                str(attempted),
                str(status),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        deadline = time.monotonic() + 10
        while not attempted.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert attempted.exists()
        assert not status.exists()
        release_gc.set()
        result = collection.result(timeout=10)
        stdout, stderr = process.communicate(timeout=10)

    assert process.returncode == 0, stderr or stdout
    assert result.success is True
    assert not _object(base, artifact).exists()
    expected = "published" if publisher_kind == "object" else "rejected"
    assert status.read_text(encoding="utf-8") == expected


def test_concurrent_root_during_planning_invalidates_the_entire_dry_run(tmp_path):
    """A root arriving during the scan must not produce an apparently current deletion plan."""
    plain = EvidenceStore(tmp_path / "evidence")
    envelope, artifact = _put(plain, tmp_path / "plan-race.bin", b"plan-race")
    injected = False

    def inject(point: str) -> None:
        nonlocal injected
        if point == "gc.plan.after_scan" and not injected:
            injected = True
            _root(
                plain,
                "during-plan.json",
                _typed_root("test-run", "during-plan", str(envelope.evidence_id)),
            )

    store = EvidenceStore(plain.root, fault_injector=inject)
    with pytest.raises(ValueError, match="changed.*planning"):
        plan_gc(store)

    assert injected is True
    assert _object(store, artifact).exists()


def test_root_bytes_are_bound_to_the_snapshot_used_for_planning(tmp_path):
    """A transient root-byte swap must not select reachability absent from the captured snapshot."""
    plain = EvidenceStore(tmp_path / "evidence")
    live, live_artifact = _put(plain, tmp_path / "live.bin", b"live")
    forged, forged_artifact = _put(plain, tmp_path / "forged.bin", b"forged")
    root = _root(
        plain,
        "stable.json",
        _typed_root("test-run", "stable", str(live.evidence_id)),
    )
    original = root.read_bytes()
    original_info = root.stat()
    swapped = False

    def inject(point: str) -> None:
        nonlocal swapped
        if point == "gc.plan.after_snapshot":
            root.write_bytes(
                canonical_json_bytes(
                    _typed_root("test-run", "stable", str(forged.evidence_id))
                )
            )
            swapped = True
        elif point == "gc.plan.after_scan" and swapped:
            root.write_bytes(original)
            os.utime(
                root,
                ns=(original_info.st_atime_ns, original_info.st_mtime_ns),
            )

    store = EvidenceStore(plain.root, fault_injector=inject)
    plan = plan_gc(store)

    assert swapped is True
    assert live_artifact.relative_path in plan.reachable_objects
    assert forged_artifact.relative_path in plan.reachable_objects
    assert plan.unreachable_objects == ()
    assert "roots/stable.json" in plan.corrupt_entries
