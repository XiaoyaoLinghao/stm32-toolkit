"""Contract tests for the derived, explicitly non-authoritative evidence catalog."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
import shutil
import sqlite3
import tempfile
from threading import Event

import pytest

from stm32_toolkit.evidence.catalog import EvidenceCatalog, EvidenceSummary, rebuild_catalog
from stm32_toolkit.evidence.model import EvidenceEnvelope, EvidenceIdentity
from stm32_toolkit.evidence.store import EvidenceStore


@pytest.fixture
def tmp_path():
    """Use a fresh C:\\tmp direct child; the host pytest temp root has an unreadable stale ACL."""
    path = Path(tempfile.mkdtemp(prefix="stm32tk-0601-t04-catalog-", dir=r"C:\tmp"))
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=False)


def _identity(*, workspace: str = "a", project: str = "123e4567-e89b-42d3-a456-426614174000", session: str = "session-01", build: str = "b", elf: str = "c") -> EvidenceIdentity:
    return EvidenceIdentity(
        workspace_id=workspace * 64,
        project_id=project,
        session_id=session,
        build_id=build * 64,
        elf_sha256=elf * 64,
        target_device="host:windows/amd64",
        input_snapshot_sha256="d" * 64,
        git_commit="e" * 40,
        git_dirty=False,
    )


def _put(store: EvidenceStore, source, *, marker: bytes, produced: str, operation: str, identity: EvidenceIdentity | None = None) -> EvidenceEnvelope:
    source.write_bytes(marker)
    artifact = store.ingest_file(source, kind="log", media_type="text/plain")
    envelope = EvidenceEnvelope(
        identity=identity or _identity(),
        operation=operation,
        produced_at_utc=produced,
        parents=(),
        artifacts=(artifact,),
        metadata={"marker": marker.decode("ascii")},
    )
    store.put_envelope(envelope)
    return envelope


def _fixture_catalog(tmp_path):
    store = EvidenceStore(tmp_path / "evidence")
    late = _put(store, tmp_path / "late.txt", marker=b"late", produced="2026-08-15T02:00:00.000000Z", operation="target.test")
    first = _put(store, tmp_path / "first.txt", marker=b"first", produced="2026-08-15T01:00:00.000000Z", operation="host.test")
    tied = _put(
        store,
        tmp_path / "tied.txt",
        marker=b"tied",
        produced="2026-08-15T02:00:00.000000Z",
        operation="host.test",
        identity=_identity(workspace="f", project="123e4567-e89b-42d3-a456-426614174001", session="session-02", build="1", elf="2"),
    )
    catalog = EvidenceCatalog(store)
    rebuild_catalog(store, catalog)
    return store, catalog, first, late, tied


def test_query_uses_exact_typed_filters_deterministic_order_and_limit(tmp_path):
    """Wildcard/loosely typed filters or unstable ordering could return the wrong run."""
    _store, catalog, first, late, tied = _fixture_catalog(tmp_path)

    assert catalog.query() == [
        EvidenceSummary.from_envelope(first),
        *sorted([EvidenceSummary.from_envelope(late), EvidenceSummary.from_envelope(tied)], key=lambda row: row.evidence_id),
    ]
    assert catalog.query(operation="host.test", limit=1) == [EvidenceSummary.from_envelope(first)]
    assert catalog.query(workspace_id="a" * 64) == [EvidenceSummary.from_envelope(first), EvidenceSummary.from_envelope(late)]
    assert catalog.query(project_id="123e4567-e89b-42d3-a456-426614174001") == [EvidenceSummary.from_envelope(tied)]
    assert catalog.query(session_id="session-02", build_id="1" * 64, elf_sha256="2" * 64) == [EvidenceSummary.from_envelope(tied)]
    assert catalog.query(
        produced_at_utc_from="2026-08-15T02:00:00.000000Z",
        produced_at_utc_to="2026-08-15T02:00:00.000000Z",
    ) == sorted([EvidenceSummary.from_envelope(late), EvidenceSummary.from_envelope(tied)], key=lambda row: row.evidence_id)
    assert catalog.query(operation="host%") == []
    for bad_limit in (True, 0, 1001):
        with pytest.raises(ValueError, match="limit"):
            catalog.query(limit=bad_limit)
    with pytest.raises(ValueError, match="UTC|range"):
        catalog.query(produced_at_utc_from="yesterday")
    with pytest.raises(ValueError, match="range"):
        catalog.query(
            produced_at_utc_from="2026-08-15T03:00:00.000000Z",
            produced_at_utc_to="2026-08-15T02:00:00.000000Z",
        )


@pytest.mark.parametrize(
    ("filters", "message"),
    [
        ({"workspace_id": "A" * 64}, "SHA-256"),
        ({"project_id": "not-a-uuid"}, "UUID"),
        ({"project_id": "123E4567-E89B-42D3-A456-426614174000"}, "lowercase"),
        ({"session_id": "Bad Session"}, "lowercase"),
        ({"operation": ""}, "non-empty"),
        ({"operation": "bad\noperation"}, "control"),
        ({"produced_at_utc_to": "2026-02-30T01:00:00.000000Z"}, "valid UTC"),
    ],
)
def test_query_rejects_invalid_typed_filter_values(tmp_path, filters, message):
    """Invalid exact filter types must fail closed before they reach SQLite."""
    _store, catalog, _first, _late, _tied = _fixture_catalog(tmp_path)
    with pytest.raises(ValueError, match=message):
        catalog.query(**filters)


def test_query_rejects_decomposed_nfc_operation_filter(tmp_path):
    """Canonically equivalent operation spellings must not cross the typed query boundary."""
    _store, catalog, _first, _late, _tied = _fixture_catalog(tmp_path)

    with pytest.raises(ValueError, match="NFC"):
        catalog.query(operation="cafe\u0301.test")


def test_query_rejects_decomposed_nfc_operation_in_catalog_row(tmp_path):
    """A forged derived row with decomposed operation text must not become an EvidenceSummary."""
    _store, catalog, _first, _late, _tied = _fixture_catalog(tmp_path)
    with closing(sqlite3.connect(catalog.path)) as database:
        database.execute(
            "INSERT INTO evidence VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "7" * 64,
                "a" * 64,
                "123e4567-e89b-42d3-a456-426614174000",
                "session-01",
                "b" * 64,
                "c" * 64,
                "cafe\u0301.test",
                "2026-08-15T03:00:00.000000Z",
            ),
        )
        database.commit()

    with pytest.raises(ValueError, match="NFC"):
        catalog.query()


def test_rebuild_is_complete_deterministic_and_uses_verified_manifest_reads(tmp_path):
    """Trusting directory names or catalog state could omit evidence or index corrupt objects."""
    store, catalog, first, late, tied = _fixture_catalog(tmp_path)
    first_bytes = catalog.path.read_bytes()

    catalog.path.unlink()
    rebuilt = rebuild_catalog(store, catalog)

    assert rebuilt == catalog.path
    assert catalog.query() == [
        EvidenceSummary.from_envelope(first),
        *sorted([EvidenceSummary.from_envelope(late), EvidenceSummary.from_envelope(tied)], key=lambda row: row.evidence_id),
    ]
    assert catalog.path.read_bytes() == first_bytes

    object_path = store.root.joinpath(*first.artifacts[0].relative_path.split("/"))
    object_path.write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="corrupt"):
        rebuild_catalog(store, catalog)


def test_old_rebuild_cannot_overwrite_catalog_built_after_manifest_publish(tmp_path):
    """Rebuild and authoritative publication must share one linearized store mutation order."""
    store, catalog, _first, _late, _tied = _fixture_catalog(tmp_path)
    source = tmp_path / "concurrent-catalog.txt"
    source.write_bytes(b"concurrent-catalog")
    artifact = store.ingest_file(source, kind="log", media_type="text/plain")
    new_envelope = EvidenceEnvelope(
        identity=_identity(workspace="7", build="8", elf="9"),
        operation="concurrent.catalog",
        produced_at_utc="2026-08-15T03:00:00.000000Z",
        parents=(),
        artifacts=(artifact,),
        metadata={"marker": "concurrent-catalog"},
    )
    old_ready = Event()
    release_old = Event()
    publisher_attempted = Event()
    publisher_finished = Event()

    def pause_old(point: str) -> None:
        if point == "catalog.before_publish":
            old_ready.set()
            assert release_old.wait(timeout=10)

    old_store = EvidenceStore(store.root, fault_injector=pause_old)

    def publish() -> Path:
        publisher_attempted.set()
        try:
            return store.put_envelope(new_envelope)
        finally:
            publisher_finished.set()

    try:
        with ThreadPoolExecutor(max_workers=3) as pool:
            old_rebuild = pool.submit(
                rebuild_catalog, old_store, EvidenceCatalog(old_store)
            )
            assert old_ready.wait(timeout=10)
            publisher = pool.submit(publish)
            assert publisher_attempted.wait(timeout=10)
            if publisher_finished.wait(timeout=1):
                newer_rebuild = pool.submit(rebuild_catalog, store, catalog)
                newer_rebuild.result(timeout=10)
                release_old.set()
            else:
                release_old.set()
                publisher.result(timeout=10)
                newer_rebuild = pool.submit(rebuild_catalog, store, catalog)
            old_rebuild.result(timeout=10)
            publisher.result(timeout=10)
            newer_rebuild.result(timeout=10)
    finally:
        release_old.set()

    assert catalog.query(operation="concurrent.catalog") == [
        EvidenceSummary.from_envelope(new_envelope)
    ]


def test_catalog_convenience_methods_preserve_authority_boundary(tmp_path):
    """Convenience APIs must rebuild derived state and resolve evidence only through the store."""
    store, catalog, first, _late, _tied = _fixture_catalog(tmp_path)
    assert EvidenceCatalog(store.root).path == catalog.path
    assert catalog.rebuild() == catalog.path
    assert catalog.get_envelope(str(first.evidence_id)) == first
    with pytest.raises(ValueError, match="EvidenceEnvelope"):
        EvidenceSummary.from_envelope(object())

    other = EvidenceCatalog(tmp_path / "other-root")
    with pytest.raises(ValueError, match="roots"):
        rebuild_catalog(store, other)


@pytest.mark.parametrize("invalid_catalog", [False, 0, "", object()])
def test_rebuild_rejects_every_non_none_non_catalog_value(tmp_path, invalid_catalog):
    """Falsey caller values must not silently request a newly constructed catalog."""
    store = EvidenceStore(tmp_path / "evidence")

    with pytest.raises(ValueError, match="EvidenceCatalog"):
        rebuild_catalog(store, invalid_catalog)


def test_public_path_mutation_cannot_redirect_query_outside_store_root(tmp_path):
    """Changing a public path must be rejected or leave query bound to root/catalog.sqlite3."""
    _store, catalog, first, late, tied = _fixture_catalog(tmp_path)
    sentinel = tmp_path / "outside-query.sqlite3"
    shutil.copyfile(catalog.path, sentinel)
    sentinel_bytes = sentinel.read_bytes()
    mutated = False
    try:
        catalog.path = sentinel
        mutated = True
    except (AttributeError, ValueError):
        pass

    if mutated:
        with pytest.raises(ValueError, match="bound"):
            catalog.query()
    else:
        assert catalog.query() == [
            EvidenceSummary.from_envelope(first),
            *sorted(
                [EvidenceSummary.from_envelope(late), EvidenceSummary.from_envelope(tied)],
                key=lambda row: row.evidence_id,
            ),
        ]
    assert sentinel.read_bytes() == sentinel_bytes


def test_public_path_mutation_cannot_redirect_rebuild_outside_store_root(tmp_path):
    """Atomic rebuild must never replace an external path supplied through mutable catalog state."""
    store, catalog, _first, _late, _tied = _fixture_catalog(tmp_path)
    sentinel = tmp_path / "outside-rebuild.sqlite3"
    sentinel.write_bytes(b"external sentinel bytes")
    sentinel_bytes = sentinel.read_bytes()
    mutated = False
    try:
        catalog.path = sentinel
        mutated = True
    except (AttributeError, ValueError):
        pass

    if mutated:
        with pytest.raises(ValueError, match="bound"):
            rebuild_catalog(store, catalog)
    else:
        assert rebuild_catalog(store, catalog) == store.root / "catalog.sqlite3"
    assert sentinel.read_bytes() == sentinel_bytes


def test_corrupt_manifest_fails_rebuild_and_preserves_old_catalog(tmp_path):
    """A partial rebuild must not replace a previously usable derived catalog."""
    store, catalog, first, _late, _tied = _fixture_catalog(tmp_path)
    before = catalog.path.read_bytes()
    manifest = store.root / "manifests" / f"{first.evidence_id}.json"
    manifest.write_bytes(manifest.read_bytes() + b"\n")

    with pytest.raises(ValueError):
        rebuild_catalog(store, catalog)

    assert catalog.path.read_bytes() == before
    assert not list(store.root.glob(".catalog-*.tmp"))


def test_manifest_directory_rejects_invalid_or_nonregular_entries(tmp_path):
    """A complete rebuild must fail on unknown manifest entries instead of silently omitting them."""
    store = EvidenceStore(tmp_path / "evidence")
    manifests = store.root / "manifests"
    manifests.mkdir(parents=True)
    (manifests / "unexpected.tmp").write_bytes(b"unknown")
    with pytest.raises(ValueError, match="invalid entry"):
        rebuild_catalog(store)

    (manifests / "unexpected.tmp").unlink()
    (manifests / ("0" * 64 + ".json")).mkdir()
    with pytest.raises(ValueError, match="regular"):
        rebuild_catalog(store)


@pytest.mark.parametrize("fault", ["catalog.after_flush", "catalog.after_fsync", "catalog.before_publish"])
def test_atomic_catalog_replacement_fault_preserves_old_database(tmp_path, fault):
    """A flush/fsync/pre-replace crash must retain the exact old database, never a partial one."""
    store, catalog, _first, _late, _tied = _fixture_catalog(tmp_path)
    before = catalog.path.read_bytes()

    def inject(point: str) -> None:
        if point == fault:
            raise OSError(point)

    fault_store = EvidenceStore(store.root, fault_injector=inject)
    with pytest.raises(OSError, match=fault):
        rebuild_catalog(fault_store, EvidenceCatalog(fault_store))

    assert catalog.path.read_bytes() == before
    assert catalog.query()
    assert not list(store.root.glob(".catalog-*.tmp"))


def test_forged_catalog_row_cannot_create_or_authorize_evidence(tmp_path):
    """A forged derived row must remain unusable without an authoritative store read."""
    store, catalog, _first, _late, _tied = _fixture_catalog(tmp_path)
    forged_id = "9" * 64
    with closing(sqlite3.connect(catalog.path)) as database:
        database.execute(
            "INSERT INTO evidence VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                forged_id,
                "a" * 64,
                "123e4567-e89b-42d3-a456-426614174000",
                "session-01",
                "b" * 64,
                "c" * 64,
                "forged.action",
                "2026-08-15T03:00:00.000000Z",
            ),
        )
        database.commit()

    rows = catalog.query(operation="forged.action")
    assert [row.evidence_id for row in rows] == [forged_id]
    assert all(row.authoritative is False for row in rows)
    with pytest.raises((FileNotFoundError, ValueError)):
        store.get_envelope(forged_id)


def test_invalid_forged_catalog_row_fails_query_closed(tmp_path):
    """Derived rows are still type-checked so corrupt catalog values cannot become summaries."""
    _store, catalog, _first, _late, _tied = _fixture_catalog(tmp_path)
    with closing(sqlite3.connect(catalog.path)) as database:
        database.execute(
            "INSERT INTO evidence VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "8" * 64,
                "not-a-hash",
                "123e4567-e89b-42d3-a456-426614174000",
                "session-01",
                "b" * 64,
                "c" * 64,
                "invalid.row",
                "2026-08-15T03:00:00.000000Z",
            ),
        )
        database.commit()

    with pytest.raises(ValueError, match="SHA-256"):
        catalog.query(operation="invalid.row")


def test_summary_query_does_not_hash_objects_but_action_read_must_get_envelope(tmp_path):
    """Catalog search is non-authoritative; consuming its row must detect later object corruption."""
    store, catalog, first, _late, _tied = _fixture_catalog(tmp_path)
    object_path = store.root.joinpath(*first.artifacts[0].relative_path.split("/"))
    object_path.write_bytes(b"tampered after catalog")

    summary = catalog.query(operation="host.test")[0]

    assert summary == EvidenceSummary.from_envelope(first)
    assert summary.authoritative is False
    with pytest.raises(ValueError, match="corrupt"):
        store.get_envelope(summary.evidence_id)


def test_query_fails_closed_for_corrupt_or_hard_linked_catalog(tmp_path):
    """Malformed or multiply named mutable metadata must not be trusted even as a summary."""
    store, catalog, _first, _late, _tied = _fixture_catalog(tmp_path)
    catalog.path.write_bytes(b"not sqlite")
    with pytest.raises(ValueError, match="catalog"):
        catalog.query()

    rebuild_catalog(store, catalog)
    alias = tmp_path / "catalog-alias.sqlite3"
    import os
    os.link(catalog.path, alias)
    with pytest.raises(ValueError, match="hard link"):
        catalog.query()


def test_t10_1a_catalog_typed_error_samples_preserve_existing_predicates(tmp_path):
    """Representative Catalog predicates must retain their behavior while gaining literal codes."""
    with pytest.raises(ValueError) as invalid:
        EvidenceSummary(
            evidence_id="not-a-hash",
            workspace_id="a" * 64,
            project_id="123e4567-e89b-42d3-a456-426614174000",
            session_id="session-01",
            build_id="b" * 64,
            elf_sha256="c" * 64,
            operation="test.host",
            produced_at_utc="2026-08-15T01:02:03.123456Z",
        )
    assert invalid.value.code == "EVIDENCE_INVALID"

    store = EvidenceStore(tmp_path / "evidence")
    store.root.mkdir()
    catalog = EvidenceCatalog(store)
    catalog.path.write_bytes(b"not sqlite")
    with pytest.raises(ValueError) as corrupt:
        catalog.query()
    assert corrupt.value.code == "EVIDENCE_CORRUPT"

    catalog._path = tmp_path / "other.sqlite3"
    with pytest.raises(ValueError) as unsafe:
        catalog.query()
    assert unsafe.value.code == "EVIDENCE_PATH_UNSAFE"
