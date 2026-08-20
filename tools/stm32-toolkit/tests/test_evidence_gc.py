"""Real-filesystem safety contract for reachability-based evidence GC."""

from __future__ import annotations

import ast
from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError, replace
import gc as python_gc
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
import weakref

import pytest

import stm32_toolkit.evidence as evidence_package
import stm32_toolkit.evidence.gc as gc_module
from stm32_toolkit.evidence.catalog import EvidenceCatalog, rebuild_catalog
from stm32_toolkit.evidence.gc import (
    REGISTERED_ROOT_TYPES,
    GcPlan,
    RootRecord,
    apply_gc,
    plan_gc,
    put_root,
)
from stm32_toolkit.evidence.model import (
    ArtifactRef,
    EVIDENCE_CORRUPT,
    EVIDENCE_LIMIT_EXCEEDED,
    EvidenceEnvelope,
    EvidenceIdentity,
    EvidenceValidationError,
    MAX_ENVELOPE_BYTES,
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


def _authorization_ledger_entry(store: EvidenceStore, plan: GcPlan) -> Path:
    return (
        store.root.parent
        / ".stm32-evidence-gc-ledger"
        / "actions"
        / plan.store_id
        / f"{plan.action_digest}.json"
    )


def test_gc_collects_unreachable_manifest_before_object_and_remains_rebuildable(tmp_path):
    """Collection must never leave an authoritative manifest pointing at a deleted object."""
    store = EvidenceStore(tmp_path / "evidence")
    envelope, artifact = _put(store, tmp_path / "orphan.bin", b"orphan")
    manifest_relative = f"manifests/{envelope.evidence_id}.json"
    manifest_path = store.root.joinpath(*manifest_relative.split("/"))

    plan = plan_gc(store)
    expected_bytes = plan.bytes_reclaimable
    assert plan.unreachable_manifests == (manifest_relative,)
    result = apply_gc(plan, plan.action_digest, plan.plan_digest)

    assert result.success is True
    assert result.deleted_manifests == (manifest_relative,)
    assert result.deleted_objects == (artifact.relative_path,)
    assert not manifest_path.exists()
    assert not _object(store, artifact).exists()
    assert result.bytes_reclaimed == expected_bytes
    catalog_path = rebuild_catalog(store)
    assert catalog_path.exists()
    assert EvidenceCatalog(store).query(operation=envelope.operation) == []

    second = plan_gc(store)
    assert second.unreachable_manifests == ()
    assert second.unreachable_objects == ()
    second_result = apply_gc(second, second.action_digest, second.plan_digest)
    assert second_result.success is True


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


def test_get_root_loads_one_exact_authoritative_root_without_catalog_inference(tmp_path):
    """An exact root key returns its canonical record through either store input form."""
    store = EvidenceStore(tmp_path / "evidence")
    envelope, _artifact = _put(store, tmp_path / "root-read.bin", b"root-read")
    root = RootRecord("test-run", "run-1", str(envelope.evidence_id), {"source": "test"})
    put_root(store, root)

    assert hasattr(gc_module, "get_root")
    assert evidence_package.get_root is gc_module.get_root
    assert gc_module.get_root(store, "test-run", "run-1") == root
    assert gc_module.get_root(store.root, "test-run", "run-1") == root


def test_get_root_missing_does_not_create_store_state(tmp_path):
    """A root miss is a read-only failure and cannot initialize the requested store path."""
    root = tmp_path / "missing-evidence"
    assert not root.exists()

    with pytest.raises(EvidenceValidationError) as missing_failure:
        gc_module.get_root(root, "test-run", "missing")

    assert missing_failure.value.code == EVIDENCE_CORRUPT
    assert not root.exists()


def test_get_root_rejects_oversize_root_before_json_validation(tmp_path):
    """Root reads use the bounded authoritative JSON limit before parsing bytes."""
    store = EvidenceStore(tmp_path / "evidence")
    envelope, _artifact = _put(store, tmp_path / "root-oversize.bin", b"root-oversize")
    root = RootRecord("test-run", "oversize", str(envelope.evidence_id), {})
    path = put_root(store, root)
    path.write_bytes(b"x" * (MAX_ENVELOPE_BYTES + 1))

    with pytest.raises(EvidenceValidationError) as limit_failure:
        gc_module.get_root(store, "test-run", "oversize")

    assert limit_failure.value.code == EVIDENCE_LIMIT_EXCEEDED


@pytest.mark.parametrize(
    ("root_type", "root_id"),
    [
        ("future-root", "run-1"),
        ("test-run", "../escape"),
        ("test-run", "e\u0301"),
    ],
)
def test_get_root_rejects_unsafe_key_without_creating_store_state(tmp_path, root_type, root_id):
    """Root key normalization is closed before any filesystem path can be selected."""
    root = tmp_path / "unsafe-evidence"

    with pytest.raises(EvidenceValidationError):
        gc_module.get_root(root, root_type, root_id)

    assert not root.exists()


def test_get_root_rejects_noncanonical_payload_key_and_casefold_collision(tmp_path):
    """Canonical bytes, exact key binding, and case-fold uniqueness are all authoritative gates."""
    store = EvidenceStore(tmp_path / "evidence")
    envelope, _artifact = _put(store, tmp_path / "root-integrity.bin", b"root-integrity")
    root = RootRecord("test-run", "run-integrity", str(envelope.evidence_id), {})
    path = put_root(store, root)
    canonical = path.read_bytes()

    path.write_bytes(canonical + b"\n")
    with pytest.raises(EvidenceValidationError):
        gc_module.get_root(store, "test-run", "run-integrity")

    mismatch = RootRecord("test-run", "other-root", str(envelope.evidence_id), {})
    path.write_bytes(canonical_json_bytes(mismatch.to_dict()))
    with pytest.raises(EvidenceValidationError, match="root"):
        gc_module.get_root(store, "test-run", "run-integrity")

    path.write_bytes(canonical)
    temporary = path.with_name(".casefold-temporary.json")
    path.rename(temporary)
    collision = path.with_name(path.name.upper())
    temporary.rename(collision)
    with pytest.raises(EvidenceValidationError, match="case-fold"):
        gc_module.get_root(store, "test-run", "run-integrity")


def test_direct_root_construction_cannot_escape_registry_or_store_root(tmp_path):
    """Direct dataclass construction must not bypass the same closed path-safe root gate."""
    store = EvidenceStore(tmp_path / "evidence")
    envelope, _artifact = _put(store, tmp_path / "root-direct.bin", b"root-direct")
    outside = tmp_path / "outside-root-registry"

    with pytest.raises(ValueError, match="root_type|registered"):
        put_root(
            store,
            RootRecord(str(outside), "direct", str(envelope.evidence_id), {}),
        )

    assert not outside.exists()


def test_put_root_revalidates_a_mutated_root_record_before_any_store_write(tmp_path):
    """The publication boundary must not trust a previously validated dataclass instance."""
    store = EvidenceStore(tmp_path / "evidence")
    envelope, _artifact = _put(store, tmp_path / "root-mutated.bin", b"root-mutated")
    outside = tmp_path / "outside-mutated-root"
    record = RootRecord("test-run", "direct", str(envelope.evidence_id), {})
    object.__setattr__(record, "root_type", str(outside))

    with pytest.raises(ValueError, match="root_type|registered"):
        put_root(store, record)

    assert not outside.exists()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("root_type", "future-root"),
        ("root_id", "../escape"),
        ("root_id", "nested/root"),
        ("root_id", r"nested\root"),
        ("root_id", "C:/absolute"),
        ("manifest_id", "A" * 64),
        ("metadata", []),
    ],
)
def test_direct_and_mapping_roots_share_one_closed_validation(field, value):
    """Both construction paths must reject the same invalid closed root fields."""
    values = {
        "root_type": "test-run",
        "root_id": "root-01",
        "manifest_id": "1" * 64,
        "metadata": {},
    }
    values[field] = value

    with pytest.raises(ValueError):
        RootRecord(**values)
    with pytest.raises(ValueError):
        RootRecord.from_value(values)


def test_direct_root_freezes_a_canonical_metadata_copy():
    """Caller mutation cannot rewrite an already constructed root record."""
    metadata = {"nested": {"value": 1}, "items": [1, {"ok": True}]}
    direct = RootRecord("test-run", "root-01", "1" * 64, metadata)
    mapped = RootRecord.from_value(
        {
            "root_type": "test-run",
            "root_id": "root-01",
            "manifest_id": "1" * 64,
            "metadata": {"nested": {"value": 1}, "items": [1, {"ok": True}]},
        }
    )
    metadata["nested"]["value"] = 2

    assert direct.to_dict() == mapped.to_dict()
    with pytest.raises(TypeError):
        direct.metadata["new"] = True
    with pytest.raises(TypeError):
        direct.metadata["items"][0] = 2


def test_apply_rejects_non_plan_values_before_authorization(tmp_path):
    """An arbitrary object must not cross the canonical plan authority boundary."""
    with pytest.raises(ValueError, match="GcPlan"):
        apply_gc(object(), "0" * 64, "0" * 64)  # type: ignore[arg-type]


def test_exact_authorized_empty_plan_initializes_coordination_and_applies(tmp_path):
    """A store with no prior publisher still needs a usable globally consumed action."""
    store = EvidenceStore(tmp_path / "empty-evidence")
    plan = plan_gc(store)

    result = apply_gc(plan, plan.action_digest, plan.plan_digest)

    assert result.success is True
    assert result.code == "GC_APPLIED"
    assert result.deleted_objects == ()
    assert result.bytes_reclaimed == 0


def test_public_gc_plan_is_immutable_and_cannot_rewrite_prepared_results(tmp_path):
    """A caller must not be able to mutate any public field after prepare."""
    store = EvidenceStore(tmp_path / "evidence")
    _envelope, artifact = _put(store, tmp_path / "immutable-plan.bin", b"immutable-plan")
    plan = plan_gc(store)
    expected_bytes = plan.bytes_reclaimable

    with pytest.raises(FrozenInstanceError):
        plan.bytes_reclaimable = 0
    with pytest.raises(FrozenInstanceError):
        plan.unreachable_objects = ()

    result = apply_gc(plan, plan.action_digest, plan.plan_digest)
    assert result.deleted_objects == (artifact.relative_path,)
    assert result.bytes_reclaimed == expected_bytes


def test_reconstructed_gc_plan_consumes_but_cannot_execute_prepared_action(tmp_path):
    """Copying every dataclass field must not copy the opaque prepare provenance."""
    store = EvidenceStore(tmp_path / "evidence")
    _envelope, artifact = _put(store, tmp_path / "reconstructed-plan.bin", b"reconstructed")
    original = plan_gc(store)
    reconstructed = replace(original)

    forged = apply_gc(
        reconstructed,
        reconstructed.action_digest,
        reconstructed.plan_digest,
    )
    retry = apply_gc(original, original.action_digest, original.plan_digest)

    assert forged.code == "GC_PLAN_INVALID"
    assert forged.deleted_objects == ()
    assert forged.retained_objects == (artifact.relative_path,)
    assert retry.code == "GC_AUTHORIZATION_CONSUMED"
    assert _object(store, artifact).exists()


def test_reconstructed_plan_consumes_action_after_original_plan_is_collected(tmp_path):
    """Prepared action identity must outlive its original public plan and persist consumption."""
    store = EvidenceStore(tmp_path / "evidence")
    _envelope, artifact = _put(store, tmp_path / "collected-plan.bin", b"collected")
    original = plan_gc(store)
    reconstructed = replace(original)
    action_digest = original.action_digest
    plan_digest = original.plan_digest
    retained = original.unreachable_objects
    del original
    python_gc.collect()

    rejected = apply_gc(reconstructed, action_digest, plan_digest)

    assert rejected.code == "GC_PLAN_INVALID"
    assert rejected.action_digest == action_digest
    assert rejected.plan_digest == plan_digest
    assert rejected.retained_objects == retained == (artifact.relative_path,)
    assert _object(store, artifact).exists()

    second_copy = replace(reconstructed)
    consumed = apply_gc(second_copy, action_digest, plan_digest)
    assert consumed.code == "GC_AUTHORIZATION_CONSUMED"

    child = """
import json
import sys
from stm32_toolkit.evidence.gc import apply_gc, plan_gc
from stm32_toolkit.evidence.store import EvidenceStore

plan = plan_gc(EvidenceStore(sys.argv[1]))
print(json.dumps(apply_gc(plan, plan.action_digest, plan.plan_digest).to_dict()))
"""
    completed = subprocess.run(
        [sys.executable, "-c", child, str(store.root)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
    assert json.loads(completed.stdout)["code"] == "GC_AUTHORIZATION_CONSUMED"

    equivalent = plan_gc(store)
    retry = apply_gc(equivalent, equivalent.action_digest, equivalent.plan_digest)
    assert retry.code == "GC_AUTHORIZATION_CONSUMED"
    assert _object(store, artifact).exists()


def test_changed_public_bytes_never_consume_regenerated_prepared_action(tmp_path):
    """Digest reuse cannot identify a reconstructed plan whose canonical bytes changed."""
    store = EvidenceStore(tmp_path / "evidence")
    _envelope, artifact = _put(store, tmp_path / "changed-public.bin", b"changed")
    original = plan_gc(store)
    reconstructed = replace(original)
    action_digest = original.action_digest
    plan_digest = original.plan_digest
    object.__setattr__(
        reconstructed,
        "bytes_reclaimable",
        reconstructed.bytes_reclaimable + 1,
    )
    del original
    python_gc.collect()

    rejected = apply_gc(reconstructed, action_digest, plan_digest)

    assert rejected.code == "GC_PLAN_INVALID"
    assert not (store.root / "gc-authorizations" / f"{action_digest}.json").exists()
    equivalent = plan_gc(store)
    applied = apply_gc(equivalent, equivalent.action_digest, equivalent.plan_digest)
    assert applied.code == "GC_APPLIED"
    assert applied.deleted_objects == (artifact.relative_path,)


def test_rederive_and_rejection_consumption_are_one_publisher_lock_order(
    tmp_path, monkeypatch
):
    """A queued publisher cannot enter between trusted regeneration and its tombstone."""
    store = EvidenceStore(tmp_path / "evidence")
    _envelope, _artifact = _put(store, tmp_path / "one-lock.bin", b"planned")
    original = plan_gc(store)
    reconstructed = replace(original)
    action_digest = original.action_digest
    plan_digest = original.plan_digest
    del original
    python_gc.collect()
    source = tmp_path / "publisher-after-rederive.bin"
    source.write_bytes(b"publisher")
    rederived = Event()
    release_rederive = Event()
    publisher_attempted = Event()
    real_plan_locked = gc_module._plan_gc_locked

    def pause_after_rederive(evidence_store):
        regenerated = real_plan_locked(evidence_store)
        rederived.set()
        assert release_rederive.wait(timeout=10)
        return regenerated

    def publish():
        publisher_attempted.set()
        return store.ingest_file(
            source,
            kind="log",
            media_type="application/octet-stream",
        )

    monkeypatch.setattr(gc_module, "_plan_gc_locked", pause_after_rederive)
    with ThreadPoolExecutor(max_workers=2) as pool:
        applying = pool.submit(apply_gc, reconstructed, action_digest, plan_digest)
        assert rederived.wait(timeout=10)
        publishing = pool.submit(publish)
        assert publisher_attempted.wait(timeout=10)
        assert not publishing.done()
        release_rederive.set()
        rejected = applying.result(timeout=10)
        published = publishing.result(timeout=10)

    tombstone = _authorization_ledger_entry(store, reconstructed)
    published_object = store.root.joinpath(*published.relative_path.split("/"))
    assert rejected.code == "GC_PLAN_INVALID"
    assert tombstone.stat().st_mtime_ns <= published_object.stat().st_mtime_ns


def test_terminal_action_releases_regenerated_prepared_snapshot(
    tmp_path, monkeypatch
):
    """Terminal consumption must not retain Store and full snapshot state for process life."""
    store = EvidenceStore(tmp_path / "evidence")
    _envelope, _artifact = _put(store, tmp_path / "released-plan.bin", b"released")
    original = plan_gc(store)
    reconstructed = replace(original)
    action_digest = original.action_digest
    plan_digest = original.plan_digest
    del original
    python_gc.collect()
    captured_prepared = []
    real_plan_locked = gc_module._plan_gc_locked

    def capture_regenerated(evidence_store):
        regenerated = real_plan_locked(evidence_store)
        captured_prepared.append(gc_module._PREPARED_BY_PLAN[regenerated])
        return regenerated

    monkeypatch.setattr(gc_module, "_plan_gc_locked", capture_regenerated)

    result = apply_gc(reconstructed, action_digest, plan_digest)
    assert result.code == "GC_PLAN_INVALID"
    assert len(captured_prepared) == 1
    regenerated_reference = weakref.ref(captured_prepared.pop())
    del reconstructed
    python_gc.collect()

    assert regenerated_reference() is None


def test_collected_plan_never_writes_tombstone_into_replacement_store_identity(tmp_path):
    """A reused path is not the frozen store and must remain entirely unmodified."""
    store = EvidenceStore(tmp_path / "evidence")
    _envelope, _artifact = _put(store, tmp_path / "replaced-store.bin", b"replaced")
    original = plan_gc(store)
    reconstructed = replace(original)
    action_digest = original.action_digest
    plan_digest = original.plan_digest
    del original
    python_gc.collect()
    shutil.rmtree(store.root)
    store.root.mkdir()
    marker = store.root / "replacement-marker.txt"
    marker.write_text("replacement", encoding="utf-8")

    result = apply_gc(reconstructed, action_digest, plan_digest)

    assert result.success is False
    assert result.code == "GC_PLAN_INVALID"
    assert marker.read_text(encoding="utf-8") == "replacement"
    assert sorted(path.name for path in store.root.iterdir()) == [marker.name]


def test_collected_plan_with_wrong_typed_store_identity_never_accesses_store(tmp_path):
    """Malformed public identity cannot enter read-only regeneration after provenance is gone."""
    store = EvidenceStore(tmp_path / "evidence")
    _envelope, artifact = _put(store, tmp_path / "wrong-store-id.bin", b"wrong-id")
    original = plan_gc(store)
    reconstructed = replace(original)
    object.__setattr__(reconstructed, "store_id", object())
    del original
    python_gc.collect()

    rejected = apply_gc(
        reconstructed,
        reconstructed.action_digest,
        reconstructed.plan_digest,
    )

    assert rejected.code == "GC_PLAN_INVALID"
    assert not (store.root / "gc-authorizations").exists()
    assert _object(store, artifact).exists()


def test_registered_plan_never_writes_into_replacement_store_identity(tmp_path):
    """Exact plan provenance still binds the original directory identity, not its pathname."""
    store = EvidenceStore(tmp_path / "evidence")
    _envelope, _artifact = _put(store, tmp_path / "registered-replaced.bin", b"replaced")
    plan = plan_gc(store)
    shutil.rmtree(store.root)
    store.root.mkdir()
    marker = store.root / "replacement-marker.txt"
    marker.write_text("replacement", encoding="utf-8")

    result = apply_gc(plan, plan.action_digest, plan.plan_digest)

    assert result.code == "GC_AUTHORIZATION_INVALID"
    assert marker.read_text(encoding="utf-8") == "replacement"
    assert sorted(path.name for path in store.root.iterdir()) == [marker.name]


def test_unregistered_public_store_path_is_never_created_during_recognition(tmp_path):
    """Recognition must be read-only until an existing matching store identity is proven."""
    store = EvidenceStore(tmp_path / "evidence")
    _envelope, artifact = _put(store, tmp_path / "forged-store-path.bin", b"forged")
    original = plan_gc(store)
    outside = tmp_path / "outside" / "nested"
    forged = replace(original, store_root=str(outside))

    rejected = apply_gc(forged, forged.action_digest, forged.plan_digest)

    assert rejected.code == "GC_PLAN_INVALID"
    assert not (tmp_path / "outside").exists()
    applied = apply_gc(original, original.action_digest, original.plan_digest)
    assert applied.code == "GC_APPLIED"
    assert applied.deleted_objects == (artifact.relative_path,)


def test_unregistered_public_store_file_is_rejected_without_mutation(tmp_path):
    """A regular file can never be reinterpreted as an evidence store root."""
    store = EvidenceStore(tmp_path / "evidence")
    _envelope, _artifact = _put(store, tmp_path / "store-file-plan.bin", b"file")
    original = plan_gc(store)
    outside_file = tmp_path / "outside-store-file"
    outside_file.write_bytes(b"unchanged")
    forged = replace(original, store_root=str(outside_file))

    rejected = apply_gc(forged, forged.action_digest, forged.plan_digest)

    assert rejected.code == "GC_PLAN_INVALID"
    assert outside_file.read_bytes() == b"unchanged"


def test_root_swap_before_authorization_lock_never_initializes_lock_in_replacement(
    tmp_path, monkeypatch
):
    """A pathname swap between identity read and lock acquisition must perform zero writes."""
    store = EvidenceStore(tmp_path / "evidence")
    _envelope, _artifact = _put(store, tmp_path / "lock-swap.bin", b"lock-swap")
    plan = plan_gc(store)
    displaced = tmp_path / "displaced-evidence"
    marker = store.root / "replacement-marker.txt"
    real_store_identity = gc_module._existing_store_identity
    calls = 0

    def swap_after_identity(evidence_store):
        nonlocal calls
        identity = real_store_identity(evidence_store)
        calls += 1
        if calls == 1:
            evidence_store.root.rename(displaced)
            evidence_store.root.mkdir()
            marker.write_text("replacement", encoding="utf-8")
        return identity

    monkeypatch.setattr(gc_module, "_existing_store_identity", swap_after_identity)

    result = apply_gc(plan, plan.action_digest, plan.plan_digest)

    assert result.success is False
    assert marker.read_text(encoding="utf-8") == "replacement"
    assert sorted(path.name for path in store.root.iterdir()) == [marker.name]


def test_store_identity_mismatch_while_lock_held_never_writes_tombstone(
    tmp_path, monkeypatch
):
    """The held-lock identity recheck must reject before authorization publication."""
    store = EvidenceStore(tmp_path / "evidence")
    _envelope, artifact = _put(store, tmp_path / "held-identity.bin", b"held")
    plan = plan_gc(store)
    real_store_identity = gc_module._existing_store_identity
    calls = 0

    def change_second_identity(evidence_store):
        nonlocal calls
        store_root, store_id = real_store_identity(evidence_store)
        calls += 1
        return (store_root, store_id) if calls == 1 else (store_root, "0" * 64)

    monkeypatch.setattr(gc_module, "_existing_store_identity", change_second_identity)

    result = apply_gc(plan, plan.action_digest, plan.plan_digest)

    assert result.code == "GC_AUTHORIZATION_INVALID"
    assert not (store.root / "gc-authorizations").exists()
    assert _object(store, artifact).exists()


def test_root_move_before_public_rederive_never_recreates_original_store_path(
    tmp_path, monkeypatch
):
    """Re-deriving trusted state must stay read-only if the verified root is moved."""
    store = EvidenceStore(tmp_path / "evidence")
    _envelope, _artifact = _put(store, tmp_path / "rederive-move.bin", b"move")
    original = plan_gc(store)
    reconstructed = replace(original)
    action_digest = original.action_digest
    plan_digest = original.plan_digest
    del original
    python_gc.collect()
    moved = tmp_path / "moved-evidence"
    real_store_identity = gc_module._existing_store_identity
    calls = 0

    def move_after_identity(evidence_store):
        nonlocal calls
        identity = real_store_identity(evidence_store)
        calls += 1
        if calls == 1:
            evidence_store.root.rename(moved)
        return identity

    monkeypatch.setattr(gc_module, "_existing_store_identity", move_after_identity)

    result = apply_gc(reconstructed, action_digest, plan_digest)

    assert result.code == "GC_PLAN_INVALID"
    assert moved.exists()
    assert not store.root.exists()


def test_unregistered_plan_with_unidentifiable_action_never_accesses_store(tmp_path):
    """A reconstructed document without registered action provenance is only a dry-run value."""
    store = EvidenceStore(tmp_path / "evidence")
    _envelope, artifact = _put(store, tmp_path / "unregistered-plan.bin", b"unregistered")
    original = plan_gc(store)
    forged_action = "0" * 64 if original.action_digest != "0" * 64 else "1" * 64
    unregistered = replace(original, action_digest=forged_action)

    rejected = apply_gc(unregistered, forged_action, unregistered.plan_digest)
    applied = apply_gc(original, original.action_digest, original.plan_digest)

    assert rejected.code == "GC_PLAN_INVALID"
    assert rejected.deleted_objects == ()
    assert applied.code == "GC_APPLIED"
    assert applied.deleted_objects == (artifact.relative_path,)


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
    assert first.bytes_reclaimable == (
        artifact.size_bytes
        + (store.root / "manifests" / f"{envelope.evidence_id}.json").stat().st_size
    )
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


@pytest.mark.parametrize(
    "root_type",
    [[], {}, True, 7, None],
)
def test_every_json_type_for_malformed_root_type_fails_closed(tmp_path, root_type):
    """Unhashable or scalar JSON root types must be reported, never escape as TypeError."""
    store = EvidenceStore(tmp_path / "evidence")
    _envelope, artifact = _put(store, tmp_path / "typed-malformed.bin", b"typed-malformed")
    _root(
        store,
        "typed-malformed.json",
        _typed_root(root_type, "typed-malformed", "0" * 64),
    )

    plan = plan_gc(store)

    assert plan.unreachable_objects == ()
    assert artifact.relative_path in plan.reachable_objects
    assert plan.unknown_entries or plan.corrupt_entries


@pytest.mark.parametrize(
    ("field", "value"),
    [
        *((field, value) for field in ("root_type", "root_id", "manifest_id") for value in ([], {}, True, 7, None)),
        *(("metadata", value) for value in ([], True, 7, None, "bad")),
    ],
)
def test_every_root_field_rejects_all_wrong_json_types_without_crashing(
    tmp_path, field, value
):
    """Every closed typed-root field must reject wrong JSON types conservatively."""
    store = EvidenceStore(tmp_path / "evidence")
    _envelope, artifact = _put(store, tmp_path / f"wrong-{field}.bin", b"wrong-field")
    document = _typed_root("test-run", "wrong-field", "0" * 64)
    document[field] = value
    _root(store, f"wrong-{field}.json", document)

    plan = plan_gc(store)

    assert plan.unreachable_objects == ()
    assert artifact.relative_path in plan.reachable_objects
    assert plan.unknown_entries or plan.corrupt_entries


def test_noncanonical_root_json_is_corrupt_and_retains_objects(tmp_path):
    """Semantically valid but noncanonical root bytes cannot authorize reachability."""
    store = EvidenceStore(tmp_path / "evidence")
    _envelope, artifact = _put(store, tmp_path / "noncanonical-root.bin", b"retain")
    roots = store.root / "roots"
    roots.mkdir()
    (roots / "noncanonical.json").write_text(
        '{"root_type": "test-run", "root_id": "x", '
        '"manifest_id": "' + "0" * 64 + '", "metadata": {}}',
        encoding="utf-8",
    )

    plan = plan_gc(store)

    assert "roots/noncanonical.json" in plan.corrupt_entries
    assert artifact.relative_path in plan.reachable_objects
    assert plan.unreachable_objects == ()


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


def test_every_malformed_manifest_shape_is_classified_without_trust(tmp_path):
    """Manifest names, type, links, bytes, and embedded identity are all closed."""
    store = EvidenceStore(tmp_path / "evidence")
    envelope, _artifact = _put(store, tmp_path / "manifest-shapes.bin", b"manifest-shapes")
    manifests = store.root / "manifests"
    linked_name = "1" * 64 + ".json"
    external = tmp_path / "linked-manifest-source"
    external.write_bytes(envelope.to_json_bytes())
    os.link(external, manifests / linked_name)
    (manifests / "future-name.txt").write_bytes(b"future")
    directory_name = "2" * 64 + ".json"
    (manifests / directory_name).mkdir()
    corrupt_name = "3" * 64 + ".json"
    (manifests / corrupt_name).write_bytes(b"not-an-envelope")
    mismatch_name = "4" * 64 + ".json"
    assert mismatch_name[:-5] != str(envelope.evidence_id)
    (manifests / mismatch_name).write_bytes(envelope.to_json_bytes())

    plan = plan_gc(store)

    assert f"manifests/{linked_name}" in plan.corrupt_entries
    assert "manifests/future-name.txt" in plan.unknown_entries
    assert f"manifests/{directory_name}" in plan.corrupt_entries
    assert f"manifests/{corrupt_name}" in plan.corrupt_entries
    assert f"manifests/{mismatch_name}" in plan.corrupt_entries


@pytest.mark.parametrize("corruption", ["relative-path", "size"])
def test_manifest_artifacts_use_store_authoritative_snapshot_validation(
    tmp_path, corruption
):
    """A malformed artifact binding makes even an unrooted scanned manifest conservative."""
    store = EvidenceStore(tmp_path / "evidence")
    source = tmp_path / "authoritative-object.bin"
    source.write_bytes(b"authoritative-object")
    artifact = store.ingest_file(
        source, kind="log", media_type="application/octet-stream"
    )
    other_source = tmp_path / "other-object.bin"
    other_source.write_bytes(b"other-object")
    other = store.ingest_file(
        other_source, kind="log", media_type="application/octet-stream"
    )
    malformed = ArtifactRef(
        sha256=artifact.sha256,
        size_bytes=artifact.size_bytes + (1 if corruption == "size" else 0),
        relative_path=(
            other.relative_path if corruption == "relative-path" else artifact.relative_path
        ),
        kind=artifact.kind,
        media_type=artifact.media_type,
    )
    envelope = EvidenceEnvelope(
        identity=_identity(),
        operation="test.malformed-artifact",
        produced_at_utc="2026-08-15T01:02:03.123456Z",
        parents=(),
        artifacts=(malformed,),
        metadata={"corruption": corruption},
    )
    manifests = store.root / "manifests"
    manifests.mkdir(exist_ok=True)
    manifest_path = manifests / f"{envelope.evidence_id}.json"
    manifest_path.write_bytes(envelope.to_json_bytes())
    if corruption == "relative-path":
        _root(
            store,
            "malformed-artifact.json",
            _typed_root("test-run", "malformed-artifact", str(envelope.evidence_id)),
        )

    plan = plan_gc(store)

    assert f"manifests/{envelope.evidence_id}.json" in plan.corrupt_entries
    assert plan.unreachable_objects == ()
    assert set(plan.reachable_objects) == {artifact.relative_path, other.relative_path}


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


@pytest.mark.parametrize(
    ("denial", "expected_code"),
    [
        ("false", "GC_AUTHORIZATION_INVALID"),
        ("wrong-type", "GC_AUTHORIZATION_INVALID"),
        ("wrong-digest", "GC_AUTHORIZATION_INVALID"),
        ("expected-mismatch", "GC_PLAN_DIGEST_MISMATCH"),
        ("plan-invalid", "GC_PLAN_INVALID"),
    ],
)
def test_every_recognizable_execute_denial_consumes_prepared_action(
    tmp_path, denial, expected_code
):
    """A denied execute attempt must close its prepared action across equivalent plans."""
    store = EvidenceStore(tmp_path / "evidence")
    _envelope, artifact = _put(store, tmp_path / f"denial-{denial}.bin", denial.encode())
    plan = plan_gc(store)
    equivalent = plan_gc(store)
    authorized: object = plan.action_digest
    expected = plan.plan_digest
    if denial == "false":
        authorized = False
    elif denial == "wrong-type":
        authorized = 1
    elif denial == "wrong-digest":
        authorized = "0" * 64
    elif denial == "expected-mismatch":
        expected = "0" * 64
    else:
        object.__setattr__(plan, "bytes_reclaimable", plan.bytes_reclaimable + 1)

    first = apply_gc(plan, authorized, expected)
    second = apply_gc(equivalent, equivalent.action_digest, equivalent.plan_digest)

    assert first.code == expected_code
    assert second.code == "GC_AUTHORIZATION_CONSUMED"
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


def test_store_identity_denial_consumes_stable_ledger_without_touching_replacement(
    tmp_path,
):
    """Same-path replacement cannot receive the token or make the old action reusable."""
    store = EvidenceStore(tmp_path / "evidence")
    source = tmp_path / "stable-ledger.bin"
    source.write_bytes(b"stable-ledger")
    artifact = store.ingest_file(
        source, kind="log", media_type="application/octet-stream"
    )
    plan = plan_gc(store)
    original_root = tmp_path / "original-evidence"
    replacement_root = tmp_path / "replacement-evidence"
    store.root.rename(original_root)
    store.root.mkdir()
    marker = store.root / "replacement-marker.txt"
    marker.write_text("replacement", encoding="utf-8")

    denied = apply_gc(plan, plan.action_digest, plan.plan_digest)

    assert denied.code == "GC_AUTHORIZATION_INVALID"
    assert sorted(path.name for path in store.root.iterdir()) == [marker.name]
    store.root.rename(replacement_root)
    original_root.rename(store.root)
    child = r"""
import sys
from pathlib import Path
from stm32_toolkit.evidence.gc import apply_gc, plan_gc
from stm32_toolkit.evidence.store import EvidenceStore

plan = plan_gc(EvidenceStore(Path(sys.argv[1])))
print(apply_gc(plan, plan.action_digest, plan.plan_digest).code, flush=True)
"""
    completed = subprocess.run(
        [sys.executable, "-c", child, str(store.root)],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
    assert completed.stdout.strip() == "GC_AUTHORIZATION_CONSUMED"
    assert _object(store, artifact).exists()


@pytest.mark.parametrize(
    ("root_name", "ledger_name"),
    [
        (".stm32-evidence-gc-ledger", ".stm32-evidence-gc-ledger-alt"),
        (".STM32-EVIDENCE-GC-LEDGER", ".stm32-evidence-gc-ledger-alt"),
        (".stm32-evidence-gc-ledger-alt", ".stm32-evidence-gc-ledger"),
        (".STM32-EVIDENCE-GC-LEDGER-ALT", ".stm32-evidence-gc-ledger"),
    ],
)
def test_ledger_sibling_never_aliases_store_root_and_consumes_after_restore(
    tmp_path, root_name, ledger_name
):
    """A reserved-name store must not receive its own denial tombstone as ledger data."""
    store = EvidenceStore(tmp_path / root_name)
    source = tmp_path / "ledger-alias.bin"
    source.write_bytes(b"ledger-alias")
    artifact = store.ingest_file(
        source, kind="log", media_type="application/octet-stream"
    )
    plan = plan_gc(store)
    original_root = tmp_path / "original-store"
    replacement_root = tmp_path / "replacement-store"
    store.root.rename(original_root)
    store.root.mkdir()
    marker = store.root / "replacement-marker.txt"
    marker.write_text("replacement", encoding="utf-8")

    denied = apply_gc(plan, plan.action_digest, plan.plan_digest)

    assert denied.code == "GC_AUTHORIZATION_INVALID"
    assert sorted(path.name for path in store.root.iterdir()) == [marker.name]
    expected_tombstone = (
        tmp_path
        / ledger_name
        / "actions"
        / plan.store_id
        / f"{plan.action_digest}.json"
    )
    assert expected_tombstone.is_file()
    store.root.rename(replacement_root)
    original_root.rename(store.root)
    child = r"""
import sys
from pathlib import Path
from stm32_toolkit.evidence.gc import apply_gc, plan_gc
from stm32_toolkit.evidence.store import EvidenceStore

plan = plan_gc(EvidenceStore(Path(sys.argv[1])))
print(apply_gc(plan, plan.action_digest, plan.plan_digest).code, flush=True)
"""
    completed = subprocess.run(
        [sys.executable, "-c", child, str(store.root)],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
    assert completed.stdout.strip() == "GC_AUTHORIZATION_CONSUMED"
    assert _object(store, artifact).exists()


def test_authorization_ledger_parent_is_identity_pinned_during_first_create(
    tmp_path, monkeypatch
):
    """The parent containing the stable sibling cannot be swapped during consumption."""
    store = EvidenceStore(tmp_path / "evidence")
    _envelope, _artifact = _put(
        store, tmp_path / "parent-guard.bin", b"parent-guard"
    )
    plan = plan_gc(store)
    moved_parent = tmp_path.parent / f"{tmp_path.name}-moved"
    real_information = gc_module._windows_file_information
    attempted = False

    def try_parent_swap(handle):
        nonlocal attempted
        information = real_information(handle)
        if not attempted:
            attempted = True
            with pytest.raises(PermissionError):
                tmp_path.rename(moved_parent)
        return information

    monkeypatch.setattr(gc_module, "_windows_file_information", try_parent_swap)
    result = apply_gc(plan, plan.action_digest, plan.plan_digest)

    assert attempted is True
    assert result.code == "GC_APPLIED"
    assert tmp_path.exists()
    assert not moved_parent.exists()


def test_win32_identity_helpers_fail_closed_on_invalid_handles_and_shapes(
    tmp_path, monkeypatch
):
    """Low-level Win32 failures and shape drift must stay evidence-domain denials."""
    with pytest.raises(OSError):
        gc_module._windows_file_information(-1)
    with pytest.raises(OSError):
        gc_module._open_windows_file(tmp_path / "absent")
    with pytest.raises(OSError):
        gc_module._close_windows_handle(0)

    regular = tmp_path / "identity.bin"
    regular.write_bytes(b"identity")
    info = regular.lstat()
    real_information = gc_module._windows_file_information

    def wrong_shape(handle):
        result = real_information(handle)
        return {**result, "links": result["links"] + 1}

    monkeypatch.setattr(gc_module, "_windows_file_information", wrong_shape)
    with pytest.raises(gc_module.EvidenceValidationError):
        gc_module._file_identity_fields(regular, info)


def test_authorization_parent_guard_rejects_wrong_opened_identity(tmp_path, monkeypatch):
    """A mismatched opened directory identity cannot authorize ledger writes."""
    info = tmp_path.lstat()
    real_information = gc_module._windows_file_information

    def wrong_identity(handle):
        result = real_information(handle)
        return {**result, "file_index": result["file_index"] + 1}

    monkeypatch.setattr(gc_module, "_windows_file_information", wrong_identity)
    with pytest.raises(gc_module.EvidenceValidationError):
        with gc_module._stable_parent_guard(tmp_path, info):
            pytest.fail("mismatched parent guard yielded")

    vanished = tmp_path / "vanished-parent"
    vanished.mkdir()
    vanished_info = vanished.lstat()
    vanished.rmdir()
    with pytest.raises(OSError):
        with gc_module._stable_parent_guard(vanished, vanished_info):
            pytest.fail("vanished parent guard yielded")


def test_identity_bound_delete_rejects_missing_and_mismatched_snapshot_targets(tmp_path):
    """Deletion cannot proceed without the exact planned snapshot entry and shape."""
    store = EvidenceStore(tmp_path / "evidence")
    source = tmp_path / "snapshot-target.bin"
    source.write_bytes(b"snapshot-target")
    artifact = store.ingest_file(
        source, kind="log", media_type="application/octet-stream"
    )
    plan = plan_gc(store)
    prepared = gc_module._registered_prepared(plan)
    assert prepared is not None
    with pytest.raises(gc_module.GcStoreChangedError):
        gc_module._delete_identity_bound(prepared, artifact.relative_path, (), set())

    snapshot = list(prepared.snapshot_entries)
    index = next(
        i for i, entry in enumerate(snapshot) if entry.get("path") == artifact.relative_path
    )
    snapshot[index] = {**snapshot[index], "links": 2}
    with pytest.raises(gc_module.GcStoreChangedError):
        gc_module._delete_identity_bound(
            prepared, artifact.relative_path, tuple(snapshot), set()
        )


def test_reconstructed_plan_fails_closed_for_missing_or_consumed_regeneration(
    tmp_path, monkeypatch
):
    """Opaque regenerated provenance has explicit missing and already-consumed denials."""
    store = EvidenceStore(tmp_path / "evidence")
    original = plan_gc(store)
    reconstructed = replace(original)
    monkeypatch.setattr(gc_module, "_registered_prepared", lambda _plan: None)
    assert (
        apply_gc(reconstructed, reconstructed.action_digest, reconstructed.plan_digest).code
        == "GC_PLAN_INVALID"
    )

    monkeypatch.undo()
    second_original = plan_gc(store)
    second_reconstructed = replace(second_original)
    real_registered = gc_module._registered_prepared

    def mark_regenerated_consumed(candidate):
        prepared = real_registered(candidate)
        if prepared is not None:
            prepared.consumed = True
        return prepared

    monkeypatch.setattr(gc_module, "_registered_prepared", mark_regenerated_consumed)
    assert (
        apply_gc(
            second_reconstructed,
            second_reconstructed.action_digest,
            second_reconstructed.plan_digest,
        ).code
        == "GC_AUTHORIZATION_CONSUMED"
    )


def test_mutating_public_action_digest_still_consumes_original_prepared_action(tmp_path):
    """Plan mutation cannot redirect the tombstone away from its prepared action."""
    store = EvidenceStore(tmp_path / "evidence")
    _envelope, artifact = _put(store, tmp_path / "mutated-action.bin", b"mutated-action")
    invalid = plan_gc(store)
    equivalent = plan_gc(store)
    prepared_action = invalid.action_digest
    object.__setattr__(
        invalid,
        "action_digest",
        "f" * 64 if prepared_action != "f" * 64 else "e" * 64,
    )

    first = apply_gc(invalid, invalid.action_digest, invalid.plan_digest)
    second = apply_gc(equivalent, equivalent.action_digest, equivalent.plan_digest)

    assert first.code == "GC_PLAN_INVALID"
    assert first.action_digest == prepared_action
    assert second.code == "GC_AUTHORIZATION_CONSUMED"
    assert _object(store, artifact).exists()


def test_non_json_store_id_cannot_prevent_original_action_consumption(tmp_path):
    """The authorization tombstone must use frozen fields before public-plan validation."""
    store = EvidenceStore(tmp_path / "evidence")
    _envelope, artifact = _put(store, tmp_path / "mutated-store-id.bin", b"mutated-store-id")
    invalid = plan_gc(store)
    equivalent = plan_gc(store)
    object.__setattr__(invalid, "store_id", object())

    first = apply_gc(invalid, invalid.action_digest, invalid.plan_digest)
    second = apply_gc(equivalent, equivalent.action_digest, equivalent.plan_digest)

    assert first.code == "GC_PLAN_INVALID"
    assert second.code == "GC_AUTHORIZATION_CONSUMED"
    assert _object(store, artifact).exists()


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [("roots", (object(),)), ("unreachable_objects", object())],
)
def test_invalid_public_plan_collections_return_canonical_denial(
    tmp_path, field_name, invalid_value
):
    """Result construction must never revisit public fields already found invalid."""
    store = EvidenceStore(tmp_path / "evidence")
    _envelope, artifact = _put(store, tmp_path / f"invalid-{field_name}.bin", b"invalid-plan")
    invalid = plan_gc(store)
    equivalent = plan_gc(store)
    object.__setattr__(invalid, field_name, invalid_value)

    first = apply_gc(invalid, invalid.action_digest, invalid.plan_digest)
    second = apply_gc(equivalent, equivalent.action_digest, equivalent.plan_digest)

    assert first.code == "GC_PLAN_INVALID"
    assert first.retained_objects == (artifact.relative_path,)
    assert second.code == "GC_AUTHORIZATION_CONSUMED"
    assert _object(store, artifact).exists()


def test_rebound_store_handle_cannot_redirect_prepared_execution(tmp_path):
    """A plan must execute only through the exact store instance that prepared its action."""
    store = EvidenceStore(tmp_path / "evidence")
    _envelope, artifact = _put(store, tmp_path / "rebound-store.bin", b"rebound-store")
    invalid = plan_gc(store)
    equivalent = plan_gc(store)
    outside = EvidenceStore(tmp_path / "outside-store")
    object.__setattr__(invalid, "_store", outside)

    first = apply_gc(invalid, invalid.action_digest, invalid.plan_digest)
    second = apply_gc(equivalent, equivalent.action_digest, equivalent.plan_digest)

    assert first.code == "GC_APPLIED"
    assert first.deleted_objects == (artifact.relative_path,)
    assert second.code == "GC_AUTHORIZATION_CONSUMED"
    assert not _object(store, artifact).exists()
    assert not outside.root.exists()


def test_authorization_is_consumed_once_across_competing_processes(tmp_path):
    """Exactly one process may redeem and execute one prepared action digest."""
    store = EvidenceStore(tmp_path / "evidence")
    _envelope, artifact = _put(
        store, tmp_path / "process-authorization.bin", b"process-authorization"
    )
    release = tmp_path / "authorization-release"
    expected_bytes = plan_gc(store).bytes_reclaimable
    child = r"""
import json
import sys
import time
from pathlib import Path
from stm32_toolkit.evidence.gc import apply_gc, plan_gc
from stm32_toolkit.evidence.store import EvidenceStore

root, ready, release = map(Path, sys.argv[1:])
plan = plan_gc(EvidenceStore(root))
ready.write_text("ready", encoding="utf-8")
deadline = time.monotonic() + 10
while not release.exists() and time.monotonic() < deadline:
    time.sleep(0.005)
if not release.exists():
    raise RuntimeError("authorization race was never released")
result = apply_gc(plan, plan.action_digest, plan.plan_digest)
print(json.dumps(result.to_dict()), flush=True)
"""
    processes = []
    ready_paths = []
    for index in range(2):
        ready = tmp_path / f"authorization-ready-{index}"
        ready_paths.append(ready)
        processes.append(
            subprocess.Popen(
                [sys.executable, "-c", child, str(store.root), str(ready), str(release)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        )
    deadline = time.monotonic() + 10
    while not all(path.exists() for path in ready_paths) and time.monotonic() < deadline:
        time.sleep(0.005)
    assert all(path.exists() for path in ready_paths)
    release.write_text("release", encoding="utf-8")
    results = []
    for process in processes:
        stdout, stderr = process.communicate(timeout=10)
        assert process.returncode == 0, stderr or stdout
        results.append(json.loads(stdout))

    assert sorted(result["code"] for result in results) == [
        "GC_APPLIED",
        "GC_AUTHORIZATION_CONSUMED",
    ]
    applied = next(result for result in results if result["code"] == "GC_APPLIED")
    assert applied["deleted_objects"] == [artifact.relative_path]
    assert applied["bytes_reclaimed"] == expected_bytes
    assert not _object(store, artifact).exists()


def test_mutated_plan_or_action_binding_is_rejected_before_deletion(tmp_path):
    """Changing the prepared plan object must not turn its old digest into new authority."""
    store = EvidenceStore(tmp_path / "evidence")
    _envelope, artifact = _put(store, tmp_path / "mutated.bin", b"mutated")
    plan = plan_gc(store)
    original_plan_digest = plan.plan_digest
    object.__setattr__(plan, "bytes_reclaimable", plan.bytes_reclaimable + 1)

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
            if calls == 4:
                raise OSError("injected second object delete failure")

    store = EvidenceStore(plain.root, fault_injector=inject)
    plan = plan_gc(store)
    manifest_bytes = plan.bytes_reclaimable - artifact_one.size_bytes - artifact_two.size_bytes
    result = apply_gc(plan, plan.action_digest, plan.plan_digest)

    assert result.success is False
    assert result.code == "GC_PARTIAL_DELETE"
    assert len(result.deleted_manifests) == 2
    assert len(result.deleted_objects) == 1
    assert result.bytes_reclaimed in {
        manifest_bytes + artifact_one.size_bytes,
        manifest_bytes + artifact_two.size_bytes,
    }
    assert len([path for path in (_object(store, artifact_one), _object(store, artifact_two)) if path.exists()]) == 1
    assert result.errors and "second object delete failure" in result.errors[0]


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


def test_identity_swap_after_final_snapshot_never_deletes_replacement_object(
    tmp_path, monkeypatch
):
    """Deletion must target the verified handle identity, never a later occupant of its path."""
    store = EvidenceStore(tmp_path / "evidence")
    envelope, artifact = _put(store, tmp_path / "identity-race.bin", b"identity-race")
    plan = plan_gc(store)
    object_path = _object(store, artifact)
    original_path = tmp_path / "original-object-outside-store"
    real_snapshot = gc_module._snapshot_entries
    swapped = False

    def snapshot_then_swap(evidence_store, *, phase=None, excluded=frozenset()):
        nonlocal swapped
        snapshot = real_snapshot(evidence_store, phase=phase, excluded=excluded)
        if phase == "gc.final-snapshot" and not swapped:
            object_path.replace(original_path)
            object_path.write_bytes(b"identity-race")
            _root(
                store,
                "identity-race.json",
                _typed_root("test-run", "identity-race", str(envelope.evidence_id)),
            )
            swapped = True
        return snapshot

    monkeypatch.setattr(gc_module, "_snapshot_entries", snapshot_then_swap)
    result = apply_gc(plan, plan.action_digest, plan.plan_digest)

    assert swapped is True
    assert result.success is False
    assert result.code == "GC_STORE_CHANGED"
    assert result.deleted_objects == ()
    assert result.bytes_reclaimed == 0
    assert object_path.read_bytes() == b"identity-race"


def test_root_only_publish_after_final_snapshot_is_revalidated_with_handle_held(
    tmp_path, monkeypatch
):
    """A late reference must be seen again after the exact delete handle is acquired."""
    store = EvidenceStore(tmp_path / "evidence")
    envelope, artifact = _put(store, tmp_path / "root-only-race.bin", b"root-only-race")
    plan = plan_gc(store)
    real_snapshot = gc_module._snapshot_entries
    published = False

    def snapshot_then_publish(evidence_store, *, phase=None, excluded=frozenset()):
        nonlocal published
        snapshot = real_snapshot(evidence_store, phase=phase, excluded=excluded)
        if phase == "gc.final-snapshot" and not published:
            _root(
                store,
                "root-only-race.json",
                _typed_root("test-run", "root-only-race", str(envelope.evidence_id)),
            )
            published = True
        return snapshot

    monkeypatch.setattr(gc_module, "_snapshot_entries", snapshot_then_publish)
    result = apply_gc(plan, plan.action_digest, plan.plan_digest)

    assert published is True
    assert result.code == "GC_STORE_CHANGED"
    assert result.deleted_objects == ()
    assert result.bytes_reclaimed == 0
    assert _object(store, artifact).read_bytes() == b"root-only-race"


def test_object_disappearing_after_final_snapshot_fails_closed(tmp_path, monkeypatch):
    """A stale snapshot cannot authorize deletion when its object no longer opens."""
    store = EvidenceStore(tmp_path / "evidence")
    _envelope, artifact = _put(store, tmp_path / "vanish-race.bin", b"vanish-race")
    plan = plan_gc(store)
    object_path = _object(store, artifact)
    moved = tmp_path / "vanished-object-outside-store"
    real_snapshot = gc_module._snapshot_entries

    def snapshot_then_remove(evidence_store, *, phase=None, excluded=frozenset()):
        snapshot = real_snapshot(evidence_store, phase=phase, excluded=excluded)
        if phase == "gc.final-snapshot" and not moved.exists():
            object_path.replace(moved)
        return snapshot

    monkeypatch.setattr(gc_module, "_snapshot_entries", snapshot_then_remove)
    result = apply_gc(plan, plan.action_digest, plan.plan_digest)

    assert result.code == "GC_STORE_CHANGED"
    assert result.deleted_objects == ()
    assert result.bytes_reclaimed == 0
    assert moved.read_bytes() == b"vanish-race"


def test_object_bytes_changing_after_final_snapshot_fail_closed(tmp_path, monkeypatch):
    """The delete handle must hash its own identity again before disposition."""
    store = EvidenceStore(tmp_path / "evidence")
    _envelope, artifact = _put(store, tmp_path / "rewrite-race.bin", b"before-bytes")
    plan = plan_gc(store)
    object_path = _object(store, artifact)
    real_snapshot = gc_module._snapshot_entries
    rewritten = False

    def snapshot_then_rewrite(evidence_store, *, phase=None, excluded=frozenset()):
        nonlocal rewritten
        snapshot = real_snapshot(evidence_store, phase=phase, excluded=excluded)
        if phase == "gc.final-snapshot" and not rewritten:
            object_path.write_bytes(b"after--bytes")
            rewritten = True
        return snapshot

    monkeypatch.setattr(gc_module, "_snapshot_entries", snapshot_then_rewrite)
    result = apply_gc(plan, plan.action_digest, plan.plan_digest)

    assert rewritten is True
    assert result.code == "GC_STORE_CHANGED"
    assert result.deleted_objects == ()
    assert result.bytes_reclaimed == 0
    assert object_path.read_bytes() == b"after--bytes"


def test_write_after_handle_snapshot_is_blocked_or_revalidated_before_disposition(
    tmp_path, monkeypatch
):
    """No byte change after the handle snapshot may cross the disposition boundary."""
    store = EvidenceStore(tmp_path / "evidence")
    source = tmp_path / "late-write.bin"
    source.write_bytes(b"before-late")
    artifact = store.ingest_file(
        source, kind="log", media_type="application/octet-stream"
    )
    plan = plan_gc(store)
    object_path = _object(store, artifact)
    real_snapshot = gc_module._snapshot_entries
    write_attempted = False
    write_blocked = False

    def write_after_handle_snapshot(evidence_store, *, phase=None, excluded=frozenset()):
        nonlocal write_attempted, write_blocked
        snapshot = real_snapshot(evidence_store, phase=phase, excluded=excluded)
        if phase == "gc.handle-snapshot" and not write_attempted:
            write_attempted = True
            try:
                object_path.write_bytes(b"after--late")
            except PermissionError:
                write_blocked = True
        return snapshot

    monkeypatch.setattr(gc_module, "_snapshot_entries", write_after_handle_snapshot)
    result = apply_gc(plan, plan.action_digest, plan.plan_digest)

    assert write_attempted is True
    assert write_blocked is True
    assert result.code == "GC_APPLIED"
    assert result.deleted_objects == (artifact.relative_path,)
    assert not object_path.exists()


def test_committed_disposition_remains_truthful_when_close_reports_error(
    tmp_path, monkeypatch
):
    """A close failure after disposition cannot erase already committed progress."""
    store = EvidenceStore(tmp_path / "evidence")
    source = tmp_path / "close-error.bin"
    source.write_bytes(b"close-error")
    artifact = store.ingest_file(
        source, kind="log", media_type="application/octet-stream"
    )
    plan = plan_gc(store)
    expected_bytes = plan.bytes_reclaimable
    real_close = gc_module._close_windows_handle
    real_snapshot = gc_module._snapshot_entries
    armed = False

    def arm_after_handle_snapshot(evidence_store, *, phase=None, excluded=frozenset()):
        nonlocal armed
        snapshot = real_snapshot(evidence_store, phase=phase, excluded=excluded)
        if phase == "gc.handle-snapshot":
            armed = True
        return snapshot

    def close_then_error(handle):
        real_close(handle)
        if armed:
            raise OSError("injected close error after committed disposition")

    monkeypatch.setattr(gc_module, "_snapshot_entries", arm_after_handle_snapshot)
    monkeypatch.setattr(gc_module, "_close_windows_handle", close_then_error)
    result = apply_gc(plan, plan.action_digest, plan.plan_digest)

    assert result.success is False
    assert result.code == "GC_PARTIAL_DELETE"
    assert result.deleted_objects == (artifact.relative_path,)
    assert result.retained_objects == ()
    assert result.bytes_reclaimed == expected_bytes
    assert not _object(store, artifact).exists()


def test_successful_disposition_is_reported_while_an_external_reader_delays_removal(
    tmp_path,
):
    """A committed delete remains progress even while another handle keeps its name pending."""
    store = EvidenceStore(tmp_path / "evidence")
    _envelope, artifact = _put(store, tmp_path / "held-reader.bin", b"held-reader")
    plan = plan_gc(store)
    expected_bytes = plan.bytes_reclaimable
    object_path = _object(store, artifact)
    held = gc_module._open_windows_file(object_path)
    try:
        result = apply_gc(plan, plan.action_digest, plan.plan_digest)
        pending_info = object_path.lstat()
    finally:
        gc_module._close_windows_handle(held)

    assert pending_info.st_size == artifact.size_bytes
    assert result.success is True
    assert result.code == "GC_APPLIED"
    assert result.deleted_objects == (artifact.relative_path,)
    assert result.bytes_reclaimed == expected_bytes
    assert not object_path.exists()


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


def test_t10_1a_gc_store_change_type_is_public_separate_and_no_argument():
    """The GC store-change boundary must be public, separate, fixed-message, and no-argument."""
    assert hasattr(gc_module, "GcStoreChangedError")
    error_type = gc_module.GcStoreChangedError
    assert issubclass(error_type, Exception)
    assert not issubclass(error_type, gc_module.EvidenceValidationError)
    assert error_type.code == "GC_STORE_CHANGED"
    error = error_type()
    assert error.args == ("evidence store changed during GC",)
    assert str(error) == "evidence store changed during GC"
    with pytest.raises(TypeError):
        error_type("message")
    assert "GcStoreChangedError" in gc_module.__all__

    tree = ast.parse(Path(gc_module.__file__).read_text(encoding="utf-8"))
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "GcStoreChangedError"
    ]
    assert len(calls) == 7
    assert all(not node.args and not node.keywords for node in calls)
    assert not any(
        isinstance(node, (ast.Name, ast.ClassDef))
        and getattr(node, "id", getattr(node, "name", None))
        == "".join(("_Gc", "StoreChanged"))
        for node in ast.walk(tree)
    )
