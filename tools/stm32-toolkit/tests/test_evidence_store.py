"""Real-filesystem contract tests for the immutable evidence store."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import hashlib
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
from types import SimpleNamespace

import pytest

from stm32_toolkit.evidence.model import ArtifactRef, EvidenceEnvelope, EvidenceIdentity
import stm32_toolkit.evidence.store as store_module
from stm32_toolkit.evidence.store import EvidenceStore


@pytest.fixture
def tmp_path():
    """Use a fresh C:\\tmp direct child; the host pytest temp root has an unreadable stale ACL."""
    path = Path(tempfile.mkdtemp(prefix="stm32tk-0601-t04-store-", dir=r"C:\tmp"))
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


def _envelope(artifact: ArtifactRef, *, operation: str = "test.host") -> EvidenceEnvelope:
    return EvidenceEnvelope(
        identity=_identity(),
        operation=operation,
        produced_at_utc="2026-08-15T01:02:03.123456Z",
        parents=(),
        artifacts=(artifact,),
        metadata={"result": "pass"},
    )


def _object_path(root: Path, artifact: ArtifactRef) -> Path:
    return root.joinpath(*artifact.relative_path.split("/"))


def test_ingest_copies_flushes_publishes_and_returns_verified_reference(tmp_path):
    """Skipping copy/publication verification could admit bytes that differ from the returned digest."""
    source = tmp_path / "source.bin"
    source.write_bytes(b"firmware evidence\x00\xff")
    root = tmp_path / "evidence"

    artifact = EvidenceStore(root).ingest_file(source, kind="log", media_type="application/octet-stream")

    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    assert artifact == ArtifactRef(
        sha256=digest,
        size_bytes=19,
        relative_path=f"objects/sha256/{digest[:2]}/{digest}",
        kind="log",
        media_type="application/octet-stream",
    )
    assert _object_path(root, artifact).read_bytes() == source.read_bytes()
    assert not list(root.rglob(".tmp-*"))


def test_existing_object_is_rehashed_and_corruption_is_never_overwritten(tmp_path):
    """Blind deduplication could bless corrupt old evidence or overwrite it with new bytes."""
    source = tmp_path / "source.bin"
    source.write_bytes(b"same object")
    store = EvidenceStore(tmp_path / "evidence")
    artifact = store.ingest_file(source, kind="log", media_type="text/plain")
    target = _object_path(store.root, artifact)
    target.write_bytes(b"corrupt old")

    with pytest.raises(ValueError, match="corrupt"):
        store.ingest_file(source, kind="log", media_type="text/plain")

    assert target.read_bytes() == b"corrupt old"


def test_relative_source_and_oversized_sparse_source_obey_public_boundaries(tmp_path, monkeypatch):
    """Relative inputs must be normalized, while even sparse files beyond 2 GiB are rejected early."""
    monkeypatch.chdir(tmp_path)
    source = Path("relative.bin")
    source.write_bytes(b"relative")
    artifact = EvidenceStore(Path("evidence")).ingest_file(
        source, kind="log", media_type="text/plain"
    )
    assert artifact.size_bytes == 8

    oversized = tmp_path / "oversized.bin"
    with oversized.open("wb") as stream:
        stream.seek(2 * 1024 * 1024 * 1024)
        stream.write(b"x")
    with pytest.raises(ValueError, match="2 GiB"):
        EvidenceStore(tmp_path / "large-root").ingest_file(
            oversized, kind="log", media_type="text/plain"
        )


def test_store_root_and_managed_directories_must_have_safe_types(tmp_path):
    """A file occupying a store directory must fail closed rather than be treated as a directory."""
    source = tmp_path / "source.bin"
    source.write_bytes(b"directory types")
    root_file = tmp_path / "root-file"
    root_file.write_bytes(b"not a directory")
    with pytest.raises(ValueError, match="root|directory"):
        EvidenceStore(root_file).ingest_file(source, kind="log", media_type="text/plain")

    root = tmp_path / "evidence"
    root.mkdir()
    (root / "objects").write_bytes(b"not a directory")
    with pytest.raises(ValueError, match="directory"):
        EvidenceStore(root).ingest_file(source, kind="log", media_type="text/plain")


@pytest.mark.parametrize("mutation", ["identity", "type", "links", "changed"])
def test_verified_hash_read_detects_open_and_read_races(tmp_path, monkeypatch, mutation):
    """A kernel metadata change between lstat/open/read snapshots must invalidate the object."""
    path = tmp_path / "object.bin"
    path.write_bytes(b"race checked bytes")
    real_fstat = store_module.os.fstat
    calls = 0

    def changed_fstat(descriptor):
        nonlocal calls
        calls += 1
        info = real_fstat(descriptor)
        values = {
            "st_dev": info.st_dev,
            "st_ino": info.st_ino,
            "st_mode": info.st_mode,
            "st_nlink": info.st_nlink,
            "st_size": info.st_size,
            "st_mtime_ns": info.st_mtime_ns,
        }
        if calls == 1 and mutation == "identity":
            values["st_ino"] += 1
        if calls == 1 and mutation == "type":
            values["st_mode"] = stat.S_IFDIR
        if calls == 1 and mutation == "links":
            values["st_nlink"] = 2
        if calls == 2 and mutation == "changed":
            values["st_mtime_ns"] += 1
        return SimpleNamespace(**values)

    monkeypatch.setattr(store_module.os, "fstat", changed_fstat)
    with pytest.raises(ValueError, match="identity|regular|hard link|changed"):
        EvidenceStore._hash_file(path)


@pytest.mark.parametrize("mutation", ["identity", "changed"])
def test_ingest_detects_source_open_and_read_races_without_publication(tmp_path, monkeypatch, mutation):
    """A source swap or mutation during the real copy must leave no authoritative object."""
    source = tmp_path / "source.bin"
    source.write_bytes(b"source race")
    root = tmp_path / "evidence"
    real_fstat = store_module.os.fstat
    calls = 0

    def changed_fstat(descriptor):
        nonlocal calls
        calls += 1
        info = real_fstat(descriptor)
        values = {
            "st_dev": info.st_dev,
            "st_ino": info.st_ino,
            "st_mode": info.st_mode,
            "st_nlink": info.st_nlink,
            "st_size": info.st_size,
            "st_mtime_ns": info.st_mtime_ns,
        }
        if calls == 1 and mutation == "identity":
            values["st_ino"] += 1
        if calls == 2 and mutation == "changed":
            values["st_mtime_ns"] += 1
        return SimpleNamespace(**values)

    monkeypatch.setattr(store_module.os, "fstat", changed_fstat)
    with pytest.raises(ValueError, match="identity|changed"):
        EvidenceStore(root).ingest_file(source, kind="log", media_type="text/plain")
    assert not list(root.rglob(".tmp-*"))


def test_ingest_detects_real_source_change_between_hash_and_same_directory_copy(tmp_path, monkeypatch):
    """Changing bytes between the two real passes must fail before the final object is published."""
    source = tmp_path / "source.bin"
    source.write_bytes(b"first version")
    root = tmp_path / "evidence"
    real_hash_file = EvidenceStore._hash_file.__func__

    def hash_then_change(cls, path, **arguments):
        result = real_hash_file(cls, path, **arguments)
        Path(path).write_bytes(b"second version")
        return result

    monkeypatch.setattr(EvidenceStore, "_hash_file", classmethod(hash_then_change))
    with pytest.raises(ValueError, match="between"):
        EvidenceStore(root).ingest_file(source, kind="log", media_type="text/plain")

    assert not list((root / "objects").rglob("[0-9a-f]" * 64))
    assert not list(root.rglob(".tmp-*"))


@pytest.mark.parametrize("fault", ["artifact.after_flush", "artifact.after_fsync", "artifact.before_publish"])
def test_prepublication_flush_and_fsync_faults_leave_no_authoritative_object(tmp_path, fault):
    """A write/flush/fsync crash must not expose a partial content-addressed object."""
    source = tmp_path / "source.bin"
    source.write_bytes(b"atomic object")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()

    def inject(point: str) -> None:
        if point == fault:
            raise OSError(fault)

    root = tmp_path / "evidence"
    with pytest.raises(OSError, match=fault):
        EvidenceStore(root, fault_injector=inject).ingest_file(source, kind="log", media_type="text/plain")

    assert not (root / "objects" / "sha256" / digest[:2] / digest).exists()
    assert not list(root.rglob(".tmp-*"))


def test_artifact_temporary_file_is_in_the_final_object_directory(tmp_path):
    """A staging file in another directory would violate the atomic same-directory publication contract."""
    source = tmp_path / "source.bin"
    source.write_bytes(b"same directory temp")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    observed_parents = []
    root = tmp_path / "evidence"

    def inject(point: str) -> None:
        if point == "artifact.before_publish":
            temporary = list(root.rglob(".tmp-*"))
            assert len(temporary) == 1
            observed_parents.append(temporary[0].parent)
            raise OSError(point)

    with pytest.raises(OSError, match="before_publish"):
        EvidenceStore(root, fault_injector=inject).ingest_file(
            source, kind="log", media_type="text/plain"
        )

    assert observed_parents == [root / "objects" / "sha256" / digest[:2]]


def test_postpublication_fault_exposes_only_the_complete_verified_object(tmp_path):
    """A crash after the atomic create-new point may leave a complete object, never partial bytes."""
    source = tmp_path / "source.bin"
    source.write_bytes(b"complete before publish")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()

    def inject(point: str) -> None:
        if point == "artifact.after_publish":
            raise OSError(point)

    root = tmp_path / "evidence"
    with pytest.raises(OSError, match="after_publish"):
        EvidenceStore(root, fault_injector=inject).ingest_file(source, kind="log", media_type="text/plain")

    target = root / "objects" / "sha256" / digest[:2] / digest
    assert target.read_bytes() == b"complete before publish"
    assert hashlib.sha256(target.read_bytes()).hexdigest() == digest
    assert not list(root.rglob(".tmp-*"))


def test_concurrent_same_object_writers_publish_one_complete_object(tmp_path):
    """A check-then-rename race could overwrite an object or expose partial concurrent output."""
    source = tmp_path / "source.bin"
    source.write_bytes(os.urandom(256 * 1024))
    store = EvidenceStore(tmp_path / "evidence")

    with ThreadPoolExecutor(max_workers=8) as pool:
        artifacts = list(pool.map(lambda _: store.ingest_file(source, kind="trace", media_type="application/octet-stream"), range(16)))

    assert len(set(artifacts)) == 1
    artifact = artifacts[0]
    target = _object_path(store.root, artifact)
    assert target.read_bytes() == source.read_bytes()
    assert target.stat().st_nlink == 1
    assert not list(store.root.rglob(".tmp-*"))


def test_concurrent_same_manifest_writers_create_once_and_all_verify(tmp_path):
    """Concurrent manifest publication must use create-new semantics and return one canonical file."""
    source = tmp_path / "source.bin"
    source.write_bytes(b"same manifest")
    store = EvidenceStore(tmp_path / "evidence")
    envelope = _envelope(store.ingest_file(source, kind="log", media_type="text/plain"))

    with ThreadPoolExecutor(max_workers=8) as pool:
        paths = list(pool.map(lambda _: store.put_envelope(envelope), range(16)))

    assert len(set(paths)) == 1
    assert paths[0].read_bytes() == envelope.to_json_bytes()
    assert paths[0].stat().st_nlink == 1


def test_source_symlink_is_rejected_without_following_it(tmp_path):
    """Following a file symlink could ingest bytes outside the caller-selected source."""
    # This host does not grant SeCreateSymbolicLinkPrivilege. Windows supplies this real,
    # stable directory symbolic link, distinct from the junction exercised below.
    link = Path(r"C:\Users\All Users")
    assert stat.S_ISLNK(link.lstat().st_mode)

    with pytest.raises(ValueError, match="link|reparse"):
        EvidenceStore(tmp_path / "evidence").ingest_file(link, kind="log", media_type="text/plain")


def test_source_under_real_junction_reparse_ancestor_is_rejected(tmp_path):
    """Checking only the leaf would let a junction/reparse ancestor escape the selected tree."""
    target = tmp_path / "junction-target"
    target.mkdir()
    (target / "source.bin").write_bytes(b"junction bytes")
    junction = tmp_path / "junction"
    result = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(junction), str(target)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    assert junction.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT

    with pytest.raises(ValueError, match="link|reparse"):
        EvidenceStore(tmp_path / "evidence").ingest_file(
            junction / "source.bin", kind="log", media_type="text/plain"
        )


def test_hard_link_and_special_file_sources_are_rejected(tmp_path):
    """Multiple names or a non-regular source could change identity during a trusted copy."""
    original = tmp_path / "original.bin"
    original.write_bytes(b"linked")
    hard_link = tmp_path / "hard-link.bin"
    os.link(original, hard_link)
    store = EvidenceStore(tmp_path / "evidence")

    with pytest.raises(ValueError, match="hard link"):
        store.ingest_file(hard_link, kind="log", media_type="text/plain")
    with pytest.raises(ValueError, match="regular"):
        store.ingest_file(tmp_path, kind="log", media_type="text/plain")


def test_case_fold_collision_in_managed_object_path_is_rejected(tmp_path):
    """Treating differently-cased path segments as distinct is unsafe on Windows filesystems."""
    source = tmp_path / "source.bin"
    source.write_bytes(b"case collision-a")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    root = tmp_path / "evidence"
    collision = root / "objects" / "sha256" / digest[:2].upper()
    collision.mkdir(parents=True)
    assert collision.name != digest[:2]

    with pytest.raises(ValueError, match="case-fold"):
        EvidenceStore(root).ingest_file(source, kind="log", media_type="text/plain")


def test_put_and_get_envelope_verify_canonical_manifest_id_path_size_and_hash(tmp_path):
    """An authoritative read that trusts a manifest alone could consume substituted object bytes."""
    source = tmp_path / "source.bin"
    source.write_bytes(b"verified envelope")
    store = EvidenceStore(tmp_path / "evidence")
    artifact = store.ingest_file(source, kind="log", media_type="text/plain")
    envelope = _envelope(artifact)

    manifest = store.put_envelope(envelope)

    assert manifest == store.root / "manifests" / f"{envelope.evidence_id}.json"
    assert manifest.read_bytes() == envelope.to_json_bytes()
    assert store.get_envelope(str(envelope.evidence_id)) == envelope
    assert store.verify_envelope(envelope) == envelope

    _object_path(store.root, artifact).write_bytes(b"substituted bytes")
    with pytest.raises(ValueError, match="corrupt"):
        store.get_envelope(str(envelope.evidence_id))


def test_verify_rejects_non_envelope_and_non_content_addressed_artifact_path(tmp_path):
    """Only typed envelopes whose artifact path is derived from its digest may become authoritative."""
    store = EvidenceStore(tmp_path / "evidence")
    with pytest.raises(ValueError, match="EvidenceEnvelope"):
        store.verify_envelope(object())

    source = tmp_path / "source.bin"
    source.write_bytes(b"wrong path")
    artifact = store.ingest_file(source, kind="log", media_type="text/plain")
    wrong = ArtifactRef(
        sha256=artifact.sha256,
        size_bytes=artifact.size_bytes,
        relative_path="objects/sha256/00/" + artifact.sha256,
        kind=artifact.kind,
        media_type=artifact.media_type,
    )
    with pytest.raises(ValueError, match="content-addressed"):
        store.verify_envelope(_envelope(wrong))


def test_put_existing_manifest_verifies_and_never_overwrites_corruption(tmp_path):
    """Idempotent publication must reject rather than repair a corrupt authoritative manifest."""
    source = tmp_path / "source.bin"
    source.write_bytes(b"manifest object")
    store = EvidenceStore(tmp_path / "evidence")
    envelope = _envelope(store.ingest_file(source, kind="log", media_type="text/plain"))
    manifest = store.put_envelope(envelope)
    manifest.write_bytes(b"corrupt old manifest")

    with pytest.raises(ValueError):
        store.put_envelope(envelope)

    assert manifest.read_bytes() == b"corrupt old manifest"


def test_put_existing_valid_manifest_is_idempotent(tmp_path):
    """Publishing the same envelope again must verify and reuse its unchanged manifest."""
    source = tmp_path / "source.bin"
    source.write_bytes(b"idempotent manifest")
    store = EvidenceStore(tmp_path / "evidence")
    envelope = _envelope(store.ingest_file(source, kind="log", media_type="text/plain"))
    first = store.put_envelope(envelope)
    before = first.read_bytes()

    second = store.put_envelope(envelope)

    assert second == first
    assert second.read_bytes() == before


@pytest.mark.parametrize("fault", ["manifest.after_flush", "manifest.after_fsync", "manifest.before_publish"])
def test_manifest_prepublication_faults_leave_no_authoritative_manifest(tmp_path, fault):
    """A manifest write crash must not expose bytes before flush, fsync, and atomic create-new."""
    source = tmp_path / "source.bin"
    source.write_bytes(b"manifest fault")
    plain_store = EvidenceStore(tmp_path / "evidence")
    envelope = _envelope(plain_store.ingest_file(source, kind="log", media_type="text/plain"))

    def inject(point: str) -> None:
        if point == fault:
            raise OSError(fault)

    store = EvidenceStore(plain_store.root, fault_injector=inject)
    with pytest.raises(OSError, match=fault):
        store.put_envelope(envelope)

    assert not (store.root / "manifests" / f"{envelope.evidence_id}.json").exists()
    assert not list(store.root.rglob(".tmp-*"))


def test_manifest_postpublication_fault_leaves_complete_authoritative_bytes(tmp_path):
    """A post-publish crash may retain a complete canonical manifest but never partial JSON."""
    source = tmp_path / "source.bin"
    source.write_bytes(b"manifest complete")
    plain_store = EvidenceStore(tmp_path / "evidence")
    envelope = _envelope(plain_store.ingest_file(source, kind="log", media_type="text/plain"))

    def inject(point: str) -> None:
        if point == "manifest.after_publish":
            raise OSError(point)

    store = EvidenceStore(plain_store.root, fault_injector=inject)
    with pytest.raises(OSError, match="after_publish"):
        store.put_envelope(envelope)

    manifest = store.root / "manifests" / f"{envelope.evidence_id}.json"
    assert manifest.read_bytes() == envelope.to_json_bytes()
    assert EvidenceStore(store.root).get_envelope(str(envelope.evidence_id)) == envelope


def test_get_rejects_path_escape_noncanonical_manifest_and_managed_links(tmp_path):
    """Unchecked IDs or managed metadata links could escape the store or alias mutable evidence."""
    store = EvidenceStore(tmp_path / "evidence")
    with pytest.raises(ValueError, match="evidence_id"):
        store.get_envelope("../outside")

    source = tmp_path / "source.bin"
    source.write_bytes(b"manifest safety")
    envelope = _envelope(store.ingest_file(source, kind="log", media_type="text/plain"))
    manifest = store.put_envelope(envelope)
    canonical = manifest.read_bytes()
    manifest.write_bytes(canonical + b"\n")
    with pytest.raises(ValueError):
        store.get_envelope(str(envelope.evidence_id))

    manifest.write_bytes(canonical)
    alias = tmp_path / "manifest-alias.json"
    os.link(manifest, alias)
    with pytest.raises(ValueError, match="hard link"):
        store.get_envelope(str(envelope.evidence_id))


def test_manifest_filename_must_match_canonical_payload_id(tmp_path):
    """A valid envelope copied under another digest name must not inherit that filename's authority."""
    source = tmp_path / "source.bin"
    source.write_bytes(b"wrong manifest name")
    store = EvidenceStore(tmp_path / "evidence")
    envelope = _envelope(store.ingest_file(source, kind="log", media_type="text/plain"))
    manifest = store.put_envelope(envelope)
    wrong_id = "0" * 64
    wrong_manifest = manifest.with_name(f"{wrong_id}.json")
    wrong_manifest.write_bytes(manifest.read_bytes())

    with pytest.raises(ValueError, match="name"):
        store.get_envelope(wrong_id)
