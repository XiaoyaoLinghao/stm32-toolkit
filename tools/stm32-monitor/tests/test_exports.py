from __future__ import annotations

import csv
import hashlib
import json
import os
import sqlite3
from collections.abc import Iterable
from dataclasses import replace
from io import BytesIO
from types import SimpleNamespace
from pathlib import Path
from uuid import UUID

import pytest

from stm32_monitor.exports import ExportRequest, HistoryExporter
from stm32_monitor.history import HistoryPage, HistoryQuery, HistoryStore
from stm32_monitor.models import (
    HistoryBatchSlice,
    ObservationBinding,
    SampleBatch,
    SampleValue,
    WatchItem,
)
from stm32_monitor.protocol import failure, success
from stm32_monitor.storage import StorageFailure
from stm32_toolkit.paths import WorkspacePaths


LOGICAL_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
GROUP_ID = UUID("11111111-1111-4111-8111-111111111111")
RUN_ID = UUID("22222222-2222-4222-8222-222222222222")


def _paths(tmp_path: Path) -> WorkspacePaths:
    project = tmp_path / "project"
    project.mkdir()
    return WorkspacePaths.from_roots(tmp_path / "state", project, LOGICAL_ID, "monitor-1")


def _binding(paths: WorkspacePaths) -> ObservationBinding:
    return ObservationBinding(
        workspace_id=paths.workspace_id,
        logical_project_id=str(LOGICAL_ID),
        session_id="monitor-1",
        probe_id="probe-1",
        target_device="STM32F407VGTx",
        physical_target="stm32f407vg",
        build_id="b" * 64,
        elf_sha256="e" * 64,
        input_snapshot_sha256="f" * 64,
        git_head="a" * 40,
        git_dirty=False,
        flash_session_id="flash-1",
        lease_id="lease-1",
        dwarf_sha256="d" * 64,
        svd_sha256=None,
    )


def _append(paths: WorkspacePaths, history: HistoryStore, value: object = 7) -> None:
    batch = SampleBatch(
        binding=_binding(paths),
        group_id=GROUP_ID,
        group_revision=1,
        run_id=RUN_ID,
        sequence=1,
        scheduled_unix_ns=100,
        captured_unix_ns=200,
        latency_ns=100,
        actual_rate_hz=4.0,
        subscriber_drops=0,
        history_drops=0,
        deadline_drops=0,
        values=(SampleValue(WatchItem.variable("counter"), "OK", typed_value={"type": "string", "value": value}),),
    )
    assert history.append_batch(batch).ok


def _source_rows(batches: tuple[SampleBatch, ...]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for batch in batches:
        payload = batch.to_dict()
        values = payload.pop("values")
        for ordinal, value in enumerate(values):
            row = dict(payload)
            row["batchValueCount"] = len(values)
            row.update(value)
            row["valueOrdinal"] = ordinal
            rows.append(row)
    return rows


def _batch_slice(batch: SampleBatch) -> HistoryBatchSlice:
    return HistoryBatchSlice(
        batch.binding,
        batch.group_id,
        batch.group_revision,
        batch.run_id,
        batch.sequence,
        batch.scheduled_unix_ns,
        batch.captured_unix_ns,
        batch.latency_ns,
        batch.actual_rate_hz,
        batch.subscriber_drops,
        batch.history_drops,
        batch.deadline_drops,
        0,
        len(batch.values),
        batch.values,
    )


def test_repeated_exports_reuse_verified_batches_and_append_invalidates_them(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import stm32_monitor.history as history_module

    paths = _paths(tmp_path)
    history = HistoryStore(paths)
    exporter = HistoryExporter(paths, history)
    _append(paths, history)
    decoded = 0
    real_decode = history_module._decode_history_batch

    def observed_decode(*args, **kwargs):
        nonlocal decoded
        decoded += 1
        return real_decode(*args, **kwargs)

    monkeypatch.setattr(history_module, "_decode_history_batch", observed_decode)
    try:
        first = exporter.create_export(
            ExportRequest("monitor-1", 0, 1_000, "jsonl"), authorized=True
        )
        assert first.ok and decoded == 1
        second = exporter.create_export(
            ExportRequest("monitor-1", 0, 1_000, "jsonl"), authorized=True
        )
        assert second.ok and decoded == 1

        appended = SampleBatch(
            binding=_binding(paths),
            group_id=GROUP_ID,
            group_revision=1,
            run_id=RUN_ID,
            sequence=2,
            scheduled_unix_ns=201,
            captured_unix_ns=202,
            latency_ns=1,
            actual_rate_hz=4.0,
            subscriber_drops=0,
            history_drops=0,
            deadline_drops=0,
            values=(
                SampleValue(
                    WatchItem.variable("counter"),
                    "OK",
                    typed_value={"type": "string", "value": 8},
                ),
            ),
        )
        assert history.append_batch(appended).ok
        third = exporter.create_export(
            ExportRequest("monitor-1", 0, 1_000, "jsonl"), authorized=True
        )
        assert third.ok and decoded == 3
    finally:
        exporter.close()
        history.close()


def test_export_internal_buffer_and_path_guards_cover_all_fail_closed_edges(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import stm32_monitor.exports as exports_module

    stream = BytesIO()
    writer = exports_module._LimitedHashWriter(stream)
    writer.write(b"prefix")
    writer.write(b"x" * exports_module._WRITE_BUFFER_BYTES)
    assert stream.getvalue().startswith(b"prefix")
    writer.finish()
    assert writer.byte_count == len(b"prefix") + exports_module._WRITE_BUFFER_BYTES
    direct = BytesIO()
    direct_writer = exports_module._LimitedHashWriter(direct)
    direct_writer.write(b"y" * exports_module._WRITE_BUFFER_BYTES)
    assert direct.getvalue() == b"y" * exports_module._WRITE_BUFFER_BYTES

    regular = tmp_path / "regular"
    regular.write_bytes(b"x")
    with pytest.raises(OSError, match="parent is unsafe"):
        exports_module._directory_identity(regular)
    with pytest.raises(OSError, match="parent is invalid"):
        with exports_module._create_regular_exclusive(
            tmp_path / "artifact", parent=tmp_path / "other"
        ):
            pass

    descriptor = os.open(regular, os.O_RDONLY)
    try:
        real_fstat = exports_module.os.fstat
        monkeypatch.setattr(
            exports_module.os,
            "fstat",
            lambda value: SimpleNamespace(st_mode=0, st_nlink=1, st_dev=0, st_ino=0)
            if value == descriptor
            else real_fstat(value),
        )
        with pytest.raises(OSError, match="identity is unsafe"):
            exports_module._validate_created_file(
                descriptor,
                regular,
                parent=tmp_path,
                parent_identity=exports_module._directory_identity(tmp_path),
            )
    finally:
        os.close(descriptor)

    oversized = tmp_path / "oversized"
    oversized.write_bytes(b"xx")
    with pytest.raises(ValueError, match="exceeds its limit"):
        exports_module._read_regular_limited(oversized, limit=1, keep=True)
    with pytest.raises(ValueError, match="exceeds its limit"):
        exports_module._open_verified_regular(oversized, limit=1)
    with pytest.raises(ValueError, match="independent regular file"):
        exports_module._open_verified_regular(tmp_path, limit=1)


def test_export_database_skips_callback_for_untrusted_or_missing_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import stm32_monitor.exports as exports_module
    from stm32_monitor.storage import MonitorDatabase

    paths = _paths(tmp_path)
    callbacks = []
    database = exports_module._ExportDatabase(paths, callbacks.append)
    monkeypatch.setattr(
        MonitorDatabase,
        "write",
        lambda _self, operation: operation(object()),
    )
    try:
        monkeypatch.setattr(database, "_inspect_storage_files", lambda: {})
        monkeypatch.setattr(database, "_integrity_fingerprint", lambda _files: ())
        database._integrity_identity = (("untrusted", 0, 0, 0, 0),)
        assert database.write(lambda _connection: "missing") == "missing"

        identity = (1, 2, 3)
        monkeypatch.setattr(
            database,
            "_inspect_storage_files",
            lambda: {database.path: identity},
        )
        monkeypatch.setattr(
            database,
            "_integrity_fingerprint",
            lambda _files: (("fingerprint", 1, 2, 3, 4),),
        )
        database._integrity_identity = (("different", 1, 2, 3, 4),)
        assert database.write(lambda _connection: "untrusted") == "untrusted"
        assert callbacks == []
    finally:
        database.close()


def test_export_cleanup_covers_mismatch_redirect_directory_and_missing_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import stm32_monitor.exports as exports_module

    paths = _paths(tmp_path)
    history = HistoryStore(paths)
    exporter = HistoryExporter(paths, history)
    root = paths.monitor_root / "cleanup"
    root.mkdir(parents=True)
    try:
        mismatched = root / "mismatch"
        mismatched.mkdir()
        exporter._safe_remove_tree(mismatched, expected_parent=paths.monitor_root)
        assert mismatched.is_dir()

        redirected = root / "redirected"
        redirected.write_bytes(b"cache")
        monkeypatch.setattr(exports_module, "_redirect", lambda _metadata: True)
        exporter._safe_remove_tree(redirected, expected_parent=root)
        assert not redirected.exists()

        monkeypatch.undo()
        directory = root / "directory"
        directory.mkdir()
        (directory / "value").write_bytes(b"x")
        exporter._safe_remove_tree(directory, expected_parent=root)
        assert not directory.exists()

        exporter._safe_remove_tree(root / "missing", expected_parent=root)
    finally:
        exporter.close()
        history.close()


def test_export_metadata_failure_branches_rollback_and_null_cache_rebind(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import stm32_monitor.exports as exports_module

    paths = _paths(tmp_path)
    history = HistoryStore(paths)
    exporter = HistoryExporter(paths, history)
    artifact = SimpleNamespace(
        export_id=UUID("33333333-3333-4333-8333-333333333333"),
        sha256="a" * 64,
        byte_count=1,
        value_count=1,
    )

    class Connection:
        def __init__(self, used_bytes: int, rowcount: int) -> None:
            self.used_bytes = used_bytes
            self.rowcount = rowcount
            self.rollbacks = 0

        def execute(self, sql: str, _parameters=None):
            if "SELECT COALESCE" in sql:
                return SimpleNamespace(fetchone=lambda: (self.used_bytes,))
            return SimpleNamespace(rowcount=self.rowcount)

        def commit(self) -> None:
            pass

        def rollback(self) -> None:
            self.rollbacks += 1

    try:
        quota = Connection(exports_module.MAX_WORKSPACE_EXPORT_BYTES, 1)
        monkeypatch.setattr(exporter._database, "write", lambda operation: operation(quota))
        with pytest.raises(StorageFailure, match="quota"):
            exporter._mark_ready(artifact, "jsonl", "2026-08-14T00:00:00Z")
        assert quota.rollbacks == 1

        changed = Connection(0, 0)
        monkeypatch.setattr(exporter._database, "write", lambda operation: operation(changed))
        with pytest.raises(StorageFailure, match="state changed"):
            exporter._mark_ready(artifact, "jsonl", "2026-08-14T00:00:00Z")
        assert changed.rollbacks == 1

        remembered = []
        monkeypatch.setattr(
            history._database,
            "_remember_validated_integrity",
            lambda identity, fingerprint: remembered.append((identity, fingerprint)),
        )
        exporter._history_cache.clear()
        exporter._rebind_history_cache(None, (1, 2, 3), ())  # type: ignore[arg-type]
        assert remembered == [((1, 2, 3), ())]
        assert exporter._history_cache == {}
    finally:
        exporter.close()
        history.close()


def test_jsonl_and_csv_exports_use_the_same_public_flattened_value_records(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import stm32_monitor.exports as exports_module

    paths = _paths(tmp_path)
    history = HistoryStore(paths)
    exporter = HistoryExporter(paths, history)
    first = SampleBatch(
        binding=_binding(paths),
        group_id=GROUP_ID,
        group_revision=2,
        run_id=RUN_ID,
        sequence=1,
        scheduled_unix_ns=100,
        captured_unix_ns=150,
        latency_ns=50,
        actual_rate_hz=10.0,
        subscriber_drops=1,
        history_drops=2,
        deadline_drops=3,
        values=(
            SampleValue(
                WatchItem.variable("counter"),
                "OK",
                typed_value={"type": "uint32", "value": 7},
            ),
            SampleValue(
                WatchItem.register("GPIOA.ODR"),
                "ERROR",
                code="READ_FAILED",
                definition={"source": "svd"},
            ),
        ),
    )
    second = SampleBatch(
        binding=_binding(paths),
        group_id=GROUP_ID,
        group_revision=2,
        run_id=RUN_ID,
        sequence=2,
        scheduled_unix_ns=200,
        captured_unix_ns=250,
        latency_ns=50,
        actual_rate_hz=10.0,
        subscriber_drops=4,
        history_drops=5,
        deadline_drops=6,
        values=(
            SampleValue(
                WatchItem.variable("temperature"),
                "OK",
                typed_value={"type": "float", "value": 21.5},
            ),
        ),
    )
    try:
        assert history.append_batch(first).ok and history.append_batch(second).ok
        expected = _source_rows((first, second))
        real_flatten = exports_module.flatten_history_page
        flattened_pages: list[int] = []

        def observed_flatten(page: HistoryPage):
            flattened_pages.append(page.value_count)
            yield from real_flatten(page)

        monkeypatch.setattr(exports_module, "flatten_history_page", observed_flatten)
        jsonl = exporter.create_export(
            ExportRequest("monitor-1", 0, 1_000, "jsonl"), authorized=True
        ).data
        csv_artifact = exporter.create_export(
            ExportRequest("monitor-1", 0, 1_000, "csv"), authorized=True
        ).data

        with jsonl.data_path.open("rb") as stream:
            actual_jsonl = [json.loads(line) for line in stream]
        with csv_artifact.data_path.open(encoding="utf-8", newline="") as stream:
            actual_csv = [
                {key: json.loads(value) for key, value in row.items()}
                for row in csv.DictReader(stream)
            ]
        assert actual_jsonl == expected
        assert actual_csv == expected
        assert flattened_pages == [3, 3]
        for artifact in (jsonl, csv_artifact):
            with artifact.data_path.open("rb") as stream:
                digest = hashlib.sha256()
                byte_count = 0
                for chunk in iter(lambda: stream.read(64 * 1024), b""):
                    digest.update(chunk)
                    byte_count += len(chunk)
            manifest = json.loads(artifact.manifest_path.read_text(encoding="utf-8"))
            assert manifest["sha256"] == digest.hexdigest()
            assert manifest["bytes"] == byte_count
            assert manifest["valueCount"] == len(expected)
    finally:
        exporter.close()
        history.close()


def test_jsonl_batch_static_prefix_is_byte_exact_for_adversarial_records(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import stm32_monitor.exports as exports_module

    paths = _paths(tmp_path)
    history = HistoryStore(paths)
    exporter = HistoryExporter(paths, history)
    batch = SampleBatch(
        binding=_binding(paths),
        group_id=GROUP_ID,
        group_revision=7,
        run_id=RUN_ID,
        sequence=1,
        scheduled_unix_ns=100,
        captured_unix_ns=200,
        latency_ns=100,
        actual_rate_hz=0.125,
        subscriber_drops=1,
        history_drops=2,
        deadline_drops=3,
        values=(
            SampleValue(
                WatchItem.variable('quoted["\\雪😀"]'),
                "OK",
                typed_value={
                    "type": "composite",
                    "value": {
                        "text": "nul:\u0000 newline:\n tab:\t quote:\" slash:\\ 雪😀",
                        "items": [None, True, False, -17, 1.25],
                    },
                },
                definition={"source": "DWARF 雪", "nested": {"enabled": True}},
            ),
            SampleValue(
                WatchItem.register("GPIOA.ODR"),
                "ERROR",
                code="READ_FAILED",
                definition={"source": "SVD", "description": "quoted \"value\""},
            ),
            SampleValue(
                WatchItem.variable("empty"),
                "OK",
                typed_value={"type": "array", "value": []},
                definition={},
            ),
        ),
    )
    encoder = json.JSONEncoder(
        ensure_ascii=False,
        check_circular=False,
        separators=(",", ":"),
        allow_nan=False,
    )
    flattened_rows: list[dict[str, object]] = []
    real_flatten = exports_module.flatten_history_page

    def observed_flatten(page: HistoryPage):
        for row in real_flatten(page):
            flattened_rows.append(dict(row))
            yield row

    monkeypatch.setattr(exports_module, "flatten_history_page", observed_flatten)
    batch_static_encodes = 0
    real_encode = json.JSONEncoder.encode

    def observed_encode(self, value):
        nonlocal batch_static_encodes
        if (
            isinstance(value, dict)
            and "binding" in value
            and "watch" not in value
            and "values" not in value
        ):
            batch_static_encodes += 1
        return real_encode(self, value)

    monkeypatch.setattr(json.JSONEncoder, "encode", observed_encode)
    try:
        assert history.append_batch(batch).ok
        artifact = exporter.create_export(
            ExportRequest("monitor-1", 0, 1_000, "jsonl"), authorized=True
        ).data
        actual_bytes = artifact.data_path.read_bytes()
        expected_bytes = b"".join(
            real_encode(encoder, row).encode("utf-8") + b"\n"
            for row in flattened_rows
        )
        assert actual_bytes == expected_bytes
        assert [json.loads(line) for line in actual_bytes.splitlines()] == list(
            flattened_rows
        )
        assert batch_static_encodes == 1
        assert artifact.byte_count == len(expected_bytes)
        assert artifact.sha256 == hashlib.sha256(expected_bytes).hexdigest()
    finally:
        exporter.close()
        history.close()


def _seed_numbered_history(
    paths: WorkspacePaths,
    history: HistoryStore,
    total_values: int,
) -> None:
    import stm32_monitor.history as history_module

    def seed(connection: sqlite3.Connection) -> None:
        connection.execute("BEGIN IMMEDIATE")
        remaining = total_values
        sequence = 1
        while remaining:
            count = min(256, remaining)
            batch = _numbered_batch(paths, sequence, count)
            raw = json.dumps(
                batch.to_dict(), ensure_ascii=False, sort_keys=True,
                separators=(",", ":"), allow_nan=False,
            ).encode("utf-8")
            cursor = connection.execute(
                "INSERT INTO history_batches(session_id,run_id,sequence,captured_ns,payload_json,"
                "payload_bytes,payload_sha256,value_count) VALUES (?,?,?,?,?,?,?,?)",
                ("monitor-1", str(batch.run_id), batch.sequence, batch.captured_unix_ns,
                 raw, len(raw), hashlib.sha256(raw).hexdigest(), len(batch.values)),
            )
            rows = []
            for ordinal, value in enumerate(batch.values):
                kind, selector, value_raw, digest = history_module._encode_history_value(value)
                rows.append(
                    (cursor.lastrowid, ordinal, kind, selector, value_raw, len(value_raw), digest)
                )
            connection.executemany(
                "INSERT INTO history_values(batch_id,ordinal,selector_kind,selector,value_json,"
                "value_bytes,value_sha256) VALUES (?,?,?,?,?,?,?)",
                rows,
            )
            remaining -= count
            sequence += 1
        connection.commit()

    history._database.write(seed)


def _numbered_batch(paths: WorkspacePaths, sequence: int, count: int) -> SampleBatch:
    start = (sequence - 1) * 256
    return SampleBatch(
        binding=_binding(paths), group_id=GROUP_ID, group_revision=1,
        run_id=RUN_ID, sequence=sequence, scheduled_unix_ns=sequence,
        captured_unix_ns=sequence, latency_ns=0, actual_rate_hz=1.0,
        subscriber_drops=0, history_drops=0, deadline_drops=0,
        values=tuple(
            SampleValue(
                WatchItem.variable(f"v{ordinal}"), "OK",
                typed_value={"type": "uint32", "value": ordinal},
            )
            for ordinal in range(start, start + count)
        ),
    )


def _numbered_source_rows(
    paths: WorkspacePaths,
    total_values: int,
) -> Iterable[dict[str, object]]:
    remaining = total_values
    sequence = 1
    while remaining:
        count = min(256, remaining)
        yield from _source_rows((_numbered_batch(paths, sequence, count),))
        remaining -= count
        sequence += 1


def _digest_numbered_rows(
    rows: Iterable[dict[str, object]],
    *,
    total_values: int,
) -> tuple[str, dict[str, object], dict[str, object], int]:
    digest = hashlib.sha256()
    first: dict[str, object] | None = None
    last: dict[str, object] | None = None
    count = 0
    for row in rows:
        expected_sequence = count // 256 + 1
        assert row["sequence"] == expected_sequence
        assert row["valueOrdinal"] == count % 256
        assert row["batchValueCount"] == min(
            256, total_values - (expected_sequence - 1) * 256
        )
        assert row["typedValue"] == {"type": "uint32", "value": count}
        encoded = json.dumps(
            row,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
        if first is None:
            first = row
        last = row
        count += 1
    assert first is not None and last is not None
    return digest.hexdigest(), first, last, count


def _read_numbered_export(
    path: Path,
    *,
    format_name: str,
    total_values: int,
) -> tuple[str, dict[str, object], dict[str, object], int]:
    if format_name == "jsonl":
        with path.open("rb") as stream:
            return _digest_numbered_rows(
                (json.loads(line) for line in stream),
                total_values=total_values,
            )
    with path.open(encoding="utf-8", newline="") as stream:
        return _digest_numbered_rows(
            (
                {key: json.loads(value) for key, value in row.items()}
                for row in csv.DictReader(stream)
            ),
            total_values=total_values,
        )


def test_jsonl_export_paginates_flattened_values_under_the_production_cap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import stm32_monitor.exports as exports_module
    import stm32_monitor.history as history_module

    total_values = 20_001
    paths = _paths(tmp_path)
    history = HistoryStore(paths)
    exporter = HistoryExporter(paths, history)
    _seed_numbered_history(paths, history, total_values)
    queries: list[tuple[int, str | None, int]] = []
    flattened_pages: list[int] = []
    constructed_pages: list[int] = []
    real_query = history._query_history_uncached
    real_flatten = exports_module.flatten_history_page
    real_page_post_init = HistoryPage.__post_init__

    def observed_query(query: HistoryQuery, **kwargs):
        result = real_query(query, **kwargs)
        if result.ok:
            queries.append((query.limit, query.cursor, result.data.value_count))
        return result

    def observed_flatten(page: HistoryPage):
        assert page.serialized_bytes <= 4 * 1024 * 1024
        assert all(batch._verified_marker is None for batch in page.batches)
        flattened_pages.append(page.value_count)
        yield from real_flatten(page)

    def observed_page_post_init(page: HistoryPage) -> None:
        real_page_post_init(page)
        constructed_pages.append(page.value_count)

    try:
        monkeypatch.setattr(
            history,
            "_query_history_uncached",
            observed_query,
        )
        monkeypatch.setattr(exports_module, "flatten_history_page", observed_flatten)
        monkeypatch.setattr(HistoryPage, "__post_init__", observed_page_post_init)
        monkeypatch.setattr(
            HistoryPage,
            "values",
            property(
                lambda _page: (_ for _ in ()).throw(
                    AssertionError("export materialized the compatibility values view")
                )
            ),
        )
        monkeypatch.setattr(
            history,
            "_stream_verified_batches",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                AssertionError("JSONL export retained the private batch stream")
            ),
        )
        result = exporter.create_export(
            ExportRequest("monitor-1", 0, 1_000_000, "jsonl"), authorized=True
        )
        assert result.ok
        artifact = result.data
        seen = 0
        records = 0
        with artifact.data_path.open("rb") as stream:
            for line in stream:
                value = json.loads(line)
                records += 1
                assert value["typedValue"]["value"] == seen
                assert value["batchValueCount"] == min(
                    256, total_values - (seen // 256) * 256
                )
                assert value["valueOrdinal"] == seen % 256
                seen += 1
        assert seen == total_values
        assert records == total_values
        assert artifact.value_count == total_values
        assert artifact.byte_count <= 64 * 1024 * 1024
        assert len(queries) > 1
        assert all(limit == history_module.MAX_HISTORY_VALUES for limit, _, _ in queries)
        assert queries[0][1] is None
        assert all(cursor is not None for _, cursor, _ in queries[1:])
        assert max(page_count for _, _, page_count in queries) <= history_module.MAX_HISTORY_VALUES
        assert flattened_pages == [page_count for _, _, page_count in queries]
        assert [count for count in constructed_pages if count] == flattened_pages
        assert max(constructed_pages) <= history_module.MAX_HISTORY_VALUES
        assert sum(flattened_pages) == total_values
    finally:
        exporter.close()
        history.close()


def test_realistic_jsonl_and_csv_exports_preserve_all_one_hundred_thousand_values(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import stm32_monitor.exports as exports_module
    import stm32_monitor.history as history_module

    total_values = 100_000
    paths = _paths(tmp_path)
    history = HistoryStore(paths)
    exporter = HistoryExporter(paths, history)
    _seed_numbered_history(paths, history, total_values)
    query_runs: list[list[int]] = []
    flatten_runs: list[list[int]] = []
    real_query = history._query_history_uncached
    real_flatten = exports_module.flatten_history_page

    def observed_query(query: HistoryQuery, **kwargs):
        result = real_query(query, **kwargs)
        if result.ok:
            if query.cursor is None:
                query_runs.append([])
            query_runs[-1].append(result.data.value_count)
        return result

    def observed_flatten(page: HistoryPage):
        if len(flatten_runs) < len(query_runs):
            flatten_runs.append([])
        flatten_runs[-1].append(page.value_count)
        yield from real_flatten(page)

    try:
        monkeypatch.setattr(history, "_query_history_uncached", observed_query)
        monkeypatch.setattr(exports_module, "flatten_history_page", observed_flatten)
        monkeypatch.setattr(
            history,
            "_stream_verified_batches",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                AssertionError("JSONL export retained the private batch stream")
            ),
        )
        expected = _digest_numbered_rows(
            _numbered_source_rows(paths, total_values),
            total_values=total_values,
        )
        artifacts = []
        for format_name in ("jsonl", "csv"):
            result = exporter.create_export(
                ExportRequest("monitor-1", 0, 1_000_000, format_name), authorized=True
            )
            assert result.ok
            artifact = result.data
            artifacts.append(artifact)
            actual = _read_numbered_export(
                artifact.data_path,
                format_name=format_name,
                total_values=total_values,
            )
            assert actual == expected
            assert artifact.value_count == total_values
            assert 64 * 1024 * 1024 < artifact.byte_count < 160 * 1024 * 1024
        assert len(query_runs) == len(flatten_runs) == 2
        assert query_runs == flatten_runs
        for page_counts in query_runs:
            assert len(page_counts) > 1
            assert sum(page_counts) == total_values
            assert max(page_counts) <= history_module.MAX_HISTORY_VALUES
        assert artifacts[0].sha256 != artifacts[1].sha256
    finally:
        exporter.close()
        history.close()


def test_open_download_returns_verified_stream_without_path_or_token_leakage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _paths(tmp_path)
    history = HistoryStore(paths)
    exporter = HistoryExporter(paths, history)
    download = None
    try:
        _append(paths, history)
        artifact = exporter.create_export(
            ExportRequest("monitor-1", 0, 1_000, "jsonl"), authorized=True
        ).data
        monkeypatch.setattr(
            Path,
            "read_bytes",
            lambda _path: (_ for _ in ()).throw(AssertionError("artifact read_bytes used")),
        )
        opened = exporter.open_download(artifact.export_id)
        assert opened.ok
        download = opened.data
        body = b"".join(download.iter_chunks())
        assert hashlib.sha256(body).hexdigest() == artifact.sha256
        assert len(body) == artifact.byte_count
        assert download.content_type == "application/x-ndjson"
        assert download.filename == f"history-{artifact.export_id}.jsonl"
        public = repr(download)
        assert str(paths.data_root) not in public
        assert "token" not in public.casefold()
    finally:
        if download is not None:
            download.close()
        exporter.close()
        history.close()


def test_get_export_rejects_another_session_in_the_same_workspace(
    tmp_path: Path,
) -> None:
    first_paths = _paths(tmp_path)
    second_paths = WorkspacePaths.from_roots(
        tmp_path / "state", tmp_path / "project", LOGICAL_ID, "monitor-2"
    )
    first_history = HistoryStore(first_paths)
    second_history = HistoryStore(second_paths)
    first_exporter = HistoryExporter(first_paths, first_history)
    second_exporter = HistoryExporter(second_paths, second_history)
    try:
        _append(first_paths, first_history)
        artifact = first_exporter.create_export(
            ExportRequest("monitor-1", 0, 1_000, "jsonl"), authorized=True
        ).data

        loaded = second_exporter.get_export(artifact.export_id)

        assert not loaded.ok
        assert loaded.code == "MONITOR_EXPORT_FAILED"
        assert loaded.data is None
    finally:
        second_exporter.close()
        first_exporter.close()
        second_history.close()
        first_history.close()


def test_open_download_rejects_another_session_in_the_same_workspace(
    tmp_path: Path,
) -> None:
    first_paths = _paths(tmp_path)
    second_paths = WorkspacePaths.from_roots(
        tmp_path / "state", tmp_path / "project", LOGICAL_ID, "monitor-2"
    )
    first_history = HistoryStore(first_paths)
    second_history = HistoryStore(second_paths)
    first_exporter = HistoryExporter(first_paths, first_history)
    second_exporter = HistoryExporter(second_paths, second_history)
    try:
        _append(first_paths, first_history)
        artifact = first_exporter.create_export(
            ExportRequest("monitor-1", 0, 1_000, "jsonl"), authorized=True
        ).data

        opened = second_exporter.open_download(artifact.export_id)

        assert not opened.ok
        assert opened.code == "MONITOR_EXPORT_FAILED"
        assert opened.data is None
    finally:
        second_exporter.close()
        first_exporter.close()
        second_history.close()
        first_history.close()


def test_open_download_stream_is_immutable_after_source_verification(
    tmp_path: Path,
) -> None:
    paths = _paths(tmp_path)
    history = HistoryStore(paths)
    exporter = HistoryExporter(paths, history)
    download = None
    try:
        _append(paths, history)
        artifact = exporter.create_export(
            ExportRequest("monitor-1", 0, 1_000, "jsonl"), authorized=True
        ).data
        with artifact.data_path.open("r+b", buffering=0) as concurrent_writer:
            opened = exporter.open_download(artifact.export_id)
            assert opened.ok
            download = opened.data
            concurrent_writer.seek(0)
            concurrent_writer.write(b"x" * artifact.byte_count)
            concurrent_writer.flush()
            os.fsync(concurrent_writer.fileno())
            body = b"".join(download.iter_chunks())
        assert hashlib.sha256(body).hexdigest() == artifact.sha256
    finally:
        if download is not None:
            download.close()
        exporter.close()
        history.close()


@pytest.mark.parametrize("tamper", ["data", "manifest", "record", "hardlink"])
def test_open_download_rejects_tampered_authority_before_yielding_bytes(
    tmp_path: Path,
    tamper: str,
) -> None:
    paths = _paths(tmp_path)
    history = HistoryStore(paths)
    exporter = HistoryExporter(paths, history)
    try:
        _append(paths, history)
        artifact = exporter.create_export(
            ExportRequest("monitor-1", 0, 1_000, "jsonl"), authorized=True
        ).data
        if tamper == "data":
            artifact.data_path.write_bytes(b"tampered\n")
        elif tamper == "manifest":
            artifact.manifest_path.write_text("{}\n", encoding="utf-8")
        elif tamper == "record":
            exporter._database.write(
                lambda connection: connection.execute(
                    "UPDATE export_records SET sha256 = ? WHERE export_id = ?",
                    ("0" * 64, str(artifact.export_id)),
                )
            )
        else:
            os.link(artifact.data_path, artifact.directory / "second-link.jsonl")

        rejected = exporter.open_download(artifact.export_id)
        assert not rejected.ok and rejected.data is None
    finally:
        exporter.close()
        history.close()


def test_open_download_rejects_reparse_and_descriptor_identity_changes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import stm32_monitor.exports as exports_module

    paths = _paths(tmp_path)
    history = HistoryStore(paths)
    exporter = HistoryExporter(paths, history)
    try:
        _append(paths, history)
        reparse = exporter.create_export(
            ExportRequest("monitor-1", 0, 1_000, "jsonl"), authorized=True
        ).data
        real_lstat = os.lstat

        def marked_reparse(path):
            metadata = real_lstat(path)
            if Path(path) == reparse.data_path:
                return SimpleNamespace(
                    **{
                        name: getattr(metadata, name)
                        for name in dir(metadata)
                        if name.startswith("st_")
                    },
                    st_file_attributes=getattr(metadata, "st_file_attributes", 0)
                    | 0x400,
                )
            return metadata

        monkeypatch.setattr(exports_module.os, "lstat", marked_reparse)
        assert not exporter.open_download(reparse.export_id).ok
        monkeypatch.setattr(exports_module.os, "lstat", real_lstat)

        changed = exporter.create_export(
            ExportRequest("monitor-1", 0, 1_000, "jsonl"), authorized=True
        ).data
        loaded = exporter.get_export(changed.export_id)
        assert loaded.ok
        monkeypatch.setattr(exporter, "get_export", lambda _export_id: loaded)
        real_fstat = os.fstat
        calls = 0

        def changed_fstat(descriptor: int):
            nonlocal calls
            metadata = real_fstat(descriptor)
            calls += 1
            if calls != 2:
                return metadata
            return SimpleNamespace(
                st_mode=metadata.st_mode,
                st_dev=metadata.st_dev,
                st_ino=metadata.st_ino + 1,
                st_size=metadata.st_size,
                st_nlink=metadata.st_nlink,
            )

        monkeypatch.setattr(exports_module.os, "fstat", changed_fstat)
        assert not exporter.open_download(changed.export_id).ok
    finally:
        exporter.close()
        history.close()


def test_open_download_cannot_cross_workspace_authority(tmp_path: Path) -> None:
    (tmp_path / "first").mkdir()
    (tmp_path / "second").mkdir()
    first_paths = _paths(tmp_path / "first")
    second_paths = _paths(tmp_path / "second")
    first_history = HistoryStore(first_paths)
    second_history = HistoryStore(second_paths)
    first_exporter = HistoryExporter(first_paths, first_history)
    second_exporter = HistoryExporter(second_paths, second_history)
    try:
        _append(first_paths, first_history)
        artifact = first_exporter.create_export(
            ExportRequest("monitor-1", 0, 1_000, "csv"), authorized=True
        ).data
        rejected = second_exporter.open_download(artifact.export_id)
        assert not rejected.ok and rejected.data is None
    finally:
        first_exporter.close()
        second_exporter.close()
        first_history.close()
        second_history.close()


def test_download_validates_chunks_csv_metadata_and_digest_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import stm32_monitor.exports as exports_module

    raw = BytesIO(b"csv")
    direct = exports_module.ExportDownload(
        raw,
        export_id=UUID("55555555-5555-4555-8555-555555555555"),
        format_name="csv",
        byte_count=3,
    )
    assert direct.content_type == "text/csv"
    for invalid in (0, 1024 * 1024 + 1, True):
        with pytest.raises(ValueError):
            tuple(direct.iter_chunks(invalid))
    direct.close()

    paths = _paths(tmp_path)
    history = HistoryStore(paths)
    exporter = HistoryExporter(paths, history)
    try:
        assert not exporter.open_download("not-a-uuid").ok
        _append(paths, history)
        artifact = exporter.create_export(
            ExportRequest("monitor-1", 0, 1_000, "jsonl"), authorized=True
        ).data
        loaded = exporter.get_export(artifact.export_id)
        fake_stream = BytesIO(b"verified")
        monkeypatch.setattr(exporter, "get_export", lambda _export_id: loaded)
        monkeypatch.setattr(
            exports_module,
            "_open_verified_regular",
            lambda *_args, **_kwargs: (fake_stream, artifact.byte_count, "0" * 64),
        )
        rejected = exporter.open_download(artifact.export_id)
        assert not rejected.ok and fake_stream.closed
    finally:
        exporter.close()
        history.close()


@pytest.mark.parametrize("corruption", ["gap", "selector"])
def test_verified_jsonl_stream_rejects_value_index_corruption_and_cleans_pending(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    corruption: str,
) -> None:
    paths = _paths(tmp_path)
    history = HistoryStore(paths)
    exporter = HistoryExporter(paths, history)

    try:
        source = SampleBatch(
            binding=_binding(paths), group_id=GROUP_ID, group_revision=1,
            run_id=RUN_ID, sequence=1, scheduled_unix_ns=1, captured_unix_ns=1,
            latency_ns=0, actual_rate_hz=1.0, subscriber_drops=0,
            history_drops=0, deadline_drops=0,
            values=tuple(
                SampleValue(
                    WatchItem.variable(f"v{ordinal}"), "OK",
                    typed_value={"type": "uint32", "value": ordinal},
                )
                for ordinal in range(3)
            ),
        )
        assert history.append_batch(source).ok

        def corrupt(connection: sqlite3.Connection) -> None:
            if corruption == "gap":
                connection.execute(
                    "UPDATE history_values SET ordinal = 3 WHERE batch_id = 1 AND ordinal = 2"
                )
            else:
                connection.execute(
                    "UPDATE history_values SET selector = 'forged' "
                    "WHERE batch_id = 1 AND ordinal = 1"
                )

        history._database.write(corrupt)
        result = exporter.create_export(
            ExportRequest("monitor-1", 0, 1_000, "jsonl"), authorized=True
        )
        assert not result.ok and result.code == "MONITOR_STORAGE_CORRUPT"
        pending = exporter._database.read(
            lambda connection: connection.execute(
                "SELECT COUNT(*) FROM export_records"
            ).fetchone()[0],
            empty=0,
        )
        assert pending == 0
    finally:
        exporter.close()
        history.close()


def test_export_requires_exact_authorization_and_uses_server_owned_path(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    history = HistoryStore(paths)
    exporter = HistoryExporter(paths, history)
    try:
        denied = exporter.create_export(ExportRequest("monitor-1", 0, 1_000, "jsonl"), authorized="true")
        assert not denied.ok and denied.code == "MONITOR_AUTH_REQUIRED"
        assert not paths.monitor_root.exists()

        _append(paths, history)
        result = exporter.create_export(ExportRequest("monitor-1", 0, 1_000, "jsonl"), authorized=True)
        assert result.ok
        artifact = result.data
        assert artifact.directory.parent == paths.monitor_root / "exports" / "monitor-1"
        assert artifact.data_path.is_file() and artifact.manifest_path.is_file()
        assert paths.project_root.joinpath("export.jsonl").exists() is False
    finally:
        exporter.close()
        history.close()


def test_jsonl_export_manifest_binds_sha_size_count_and_all_runtime_versions(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    history = HistoryStore(paths)
    exporter = HistoryExporter(paths, history)
    try:
        _append(paths, history)
        artifact = exporter.create_export(ExportRequest("monitor-1", 0, 1_000, "jsonl"), authorized=True).data
        data = artifact.data_path.read_bytes()
        manifest = json.loads(artifact.manifest_path.read_text(encoding="utf-8"))
        assert set(manifest) == {
            "protocol",
            "toolkitVersion",
            "monitorVersion",
            "workspaceId",
            "sessionId",
            "exportId",
            "format",
            "sha256",
            "bytes",
            "valueCount",
            "createdAtUtc",
        }
        assert manifest["protocol"] == "stm32-toolkit-monitor/1"
        assert manifest["toolkitVersion"] == "0.9.0"
        assert manifest["monitorVersion"] == "0.9.0"
        assert manifest["workspaceId"] == paths.workspace_id
        assert manifest["sha256"] == hashlib.sha256(data).hexdigest()
        assert manifest["bytes"] == len(data)
        assert manifest["valueCount"] == 1
        assert len(data.splitlines()) == 1
        assert artifact.to_dict() == {
            "exportId": str(artifact.export_id),
            "format": "jsonl",
            "sha256": artifact.sha256,
            "bytes": artifact.byte_count,
            "valueCount": 1,
        }
    finally:
        exporter.close()
        history.close()


@pytest.mark.parametrize("field", ["toolkitVersion", "monitorVersion"])
def test_get_export_rejects_tampered_runtime_versions(
    tmp_path: Path, field: str
) -> None:
    paths = _paths(tmp_path)
    history = HistoryStore(paths)
    exporter = HistoryExporter(paths, history)
    try:
        _append(paths, history)
        artifact = exporter.create_export(
            ExportRequest("monitor-1", 0, 1_000, "jsonl"), authorized=True
        ).data
        manifest = json.loads(artifact.manifest_path.read_text(encoding="utf-8"))
        manifest[field] = "9.9.9"
        artifact.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        rejected = exporter.get_export(artifact.export_id)
        assert not rejected.ok and rejected.code == "MONITOR_EXPORT_FAILED"
    finally:
        exporter.close()
        history.close()


def test_recovery_discards_pending_export_with_tampered_monitor_version(
    tmp_path: Path,
) -> None:
    paths = _paths(tmp_path)
    history = HistoryStore(paths)
    exporter = HistoryExporter(paths, history)
    recovered = None
    try:
        _append(paths, history)
        artifact = exporter.create_export(
            ExportRequest("monitor-1", 0, 1_000, "jsonl"), authorized=True
        ).data
        exporter._database.write(
            lambda connection: connection.execute(
                "UPDATE export_records SET format = 'PENDING:jsonl' WHERE export_id = ?",
                (str(artifact.export_id),),
            )
        )
        manifest = json.loads(artifact.manifest_path.read_text(encoding="utf-8"))
        manifest["monitorVersion"] = "9.9.9"
        artifact.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

        recovered = HistoryExporter(paths, history)
        assert recovered.get_export(artifact.export_id).code == "MONITOR_EXPORT_FAILED"
        assert not artifact.directory.exists()
    finally:
        if recovered is not None:
            recovered.close()
        exporter.close()
        history.close()


@pytest.mark.parametrize("dangerous", ["=1+1", "+cmd", "-2+3", "@SUM(A1)"])
def test_csv_export_preserves_formula_like_source_inside_formula_safe_json_cells(
    tmp_path: Path,
    dangerous: str,
) -> None:
    paths = _paths(tmp_path)
    history = HistoryStore(paths)
    exporter = HistoryExporter(paths, history)
    try:
        _append(paths, history, dangerous)
        artifact = exporter.create_export(ExportRequest("monitor-1", 0, 1_000, "csv"), authorized=True).data
        rows = list(csv.DictReader(artifact.data_path.open(encoding="utf-8", newline="")))
        raw_cell = rows[0]["typedValue"]
        assert raw_cell[0] not in "=+-@\t\r"
        assert json.loads(raw_cell)["value"] == dangerous
    finally:
        exporter.close()
        history.close()


def test_export_value_and_controlled_byte_caps_clean_pending_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import stm32_monitor.exports as exports_module

    paths = _paths(tmp_path)
    history = HistoryStore(paths)
    exporter = HistoryExporter(paths, history)
    try:
        _append(paths, history, "x" * 200)
        monkeypatch.setattr(exports_module, "MAX_EXPORT_VALUES", 0)
        too_many = exporter.create_export(ExportRequest("monitor-1", 0, 1_000, "jsonl"), authorized=True)
        assert not too_many.ok and too_many.code == "MONITOR_EXPORT_TOO_LARGE"

        monkeypatch.setattr(exports_module, "MAX_EXPORT_VALUES", 10)
        monkeypatch.setattr(exports_module, "MAX_EXPORT_BYTES", 32)
        too_large = exporter.create_export(ExportRequest("monitor-1", 0, 1_000, "jsonl"), authorized=True)
        assert not too_large.ok and too_large.code == "MONITOR_EXPORT_TOO_LARGE"
        export_root = paths.monitor_root / "exports" / "monitor-1"
        assert not export_root.exists() or list(export_root.iterdir()) == []
        remaining_records = exporter._database.read(
            lambda connection: connection.execute(
                "SELECT COUNT(*) FROM export_records"
            ).fetchone()[0],
            empty=-1,
        )
        assert remaining_records == 0
    finally:
        exporter.close()
        history.close()


@pytest.mark.parametrize("phase", ["data", "manifest"])
def test_export_exclusive_creation_never_truncates_a_raced_hardlink(
    tmp_path: Path,
    monkeypatch,
    phase: str,
) -> None:
    paths = _paths(tmp_path)
    history = HistoryStore(paths)
    exporter = HistoryExporter(paths, history)
    sentinel = tmp_path / f"external-{phase}.txt"
    sentinel.write_bytes(b"external-sentinel")
    before = sentinel.read_bytes()
    try:
        _append(paths, history)
        real_stream = exporter._stream_history

        def raced_stream(request: ExportRequest, target: Path):
            if phase == "data":
                os.link(sentinel, target)
                return real_stream(request, target)
            result = real_stream(request, target)
            os.link(sentinel, target.parent / "manifest.json")
            return result

        monkeypatch.setattr(exporter, "_stream_history", raced_stream)
        result = exporter.create_export(
            ExportRequest("monitor-1", 0, 1_000, "jsonl"),
            authorized=True,
        )
        assert not result.ok and result.code == "MONITOR_EXPORT_FAILED"
        assert sentinel.read_bytes() == before
    finally:
        exporter.close()
        history.close()


def test_export_replace_failure_is_atomic_and_returns_stable_failure(tmp_path: Path, monkeypatch) -> None:
    import stm32_monitor.exports as exports_module

    paths = _paths(tmp_path)
    history = HistoryStore(paths)
    exporter = HistoryExporter(paths, history)
    try:
        _append(paths, history)
        monkeypatch.setattr(exports_module, "_replace", lambda source, target: (_ for _ in ()).throw(OSError("secret path")))
        failed = exporter.create_export(ExportRequest("monitor-1", 0, 1_000, "jsonl"), authorized=True)
        assert not failed.ok and failed.code == "MONITOR_EXPORT_FAILED"
        assert "secret" not in failed.message and failed.details == {}
        export_root = paths.monitor_root / "exports" / "monitor-1"
        assert not export_root.exists() or list(export_root.iterdir()) == []
    finally:
        exporter.close()
        history.close()


def test_export_request_rejects_bad_format_range_and_session() -> None:
    with pytest.raises(ValueError):
        ExportRequest("../bad", 0, 1, "jsonl")
    with pytest.raises(ValueError):
        ExportRequest("monitor-1", 2, 1, "jsonl")
    with pytest.raises(ValueError):
        ExportRequest("monitor-1", 0, 1, "xlsx")
    with pytest.raises(ValueError):
        ExportRequest("monitor-1", 0, 2**63, "jsonl")


def test_exporter_constructor_and_create_reject_wrong_public_types(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    history = HistoryStore(paths)
    try:
        with pytest.raises(TypeError):
            HistoryExporter(paths, object())
        exporter = HistoryExporter(paths, history)
        try:
            assert exporter.create_export(object(), authorized=True).code == "MONITOR_REQUEST_INVALID"
        finally:
            exporter.close()
    finally:
        history.close()


def test_export_metadata_is_retrieved_only_by_id_and_detects_tampering(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    history = HistoryStore(paths)
    exporter = HistoryExporter(paths, history)
    try:
        _append(paths, history)
        created = exporter.create_export(ExportRequest("monitor-1", 0, 1_000, "jsonl"), authorized=True).data
        loaded = exporter.get_export(created.export_id)
        assert loaded.ok and loaded.data == created
        assert exporter.get_export("not-a-uuid").code == "MONITOR_REQUEST_INVALID"
        assert exporter.get_export(UUID("ffffffff-ffff-4fff-8fff-ffffffffffff")).code == "MONITOR_EXPORT_FAILED"

        created.data_path.write_bytes(b"tampered")
        assert exporter.get_export(created.export_id).code == "MONITOR_EXPORT_FAILED"
    finally:
        exporter.close()
        history.close()


def test_csv_export_and_get_stream_without_path_read_bytes(tmp_path: Path, monkeypatch) -> None:
    paths = _paths(tmp_path)
    history = HistoryStore(paths)
    exporter = HistoryExporter(paths, history)
    try:
        _append(paths, history, "safe")

        def forbidden_read_bytes(self: Path) -> bytes:
            raise AssertionError(f"unbounded read_bytes used for {self.name}")

        monkeypatch.setattr(Path, "read_bytes", forbidden_read_bytes)
        created = exporter.create_export(ExportRequest("monitor-1", 0, 1_000, "csv"), authorized=True)
        assert created.ok
        loaded = exporter.get_export(created.data.export_id)
        assert loaded.ok and loaded.data.byte_count == created.data.byte_count
    finally:
        exporter.close()
        history.close()


def test_workspace_export_count_and_byte_quotas_are_enforced(tmp_path: Path, monkeypatch) -> None:
    import stm32_monitor.exports as exports_module

    paths = _paths(tmp_path)
    history = HistoryStore(paths)
    exporter = HistoryExporter(paths, history)
    try:
        _append(paths, history, "quota")
        monkeypatch.setattr(exports_module, "MAX_WORKSPACE_EXPORTS", 1)
        first = exporter.create_export(ExportRequest("monitor-1", 0, 1_000, "jsonl"), authorized=True)
        assert first.ok
        count_limited = exporter.create_export(ExportRequest("monitor-1", 0, 1_000, "jsonl"), authorized=True)
        assert count_limited.code == "MONITOR_EXPORT_QUOTA_EXCEEDED"

        with sqlite3.connect(paths.monitor_root / "monitor.sqlite3") as connection:
            connection.execute("DELETE FROM export_records")
        monkeypatch.setattr(exports_module, "MAX_WORKSPACE_EXPORTS", 100)
        monkeypatch.setattr(exports_module, "MAX_WORKSPACE_EXPORT_BYTES", first.data.byte_count - 1)
        byte_limited = exporter.create_export(ExportRequest("monitor-1", 0, 1_000, "jsonl"), authorized=True)
        assert byte_limited.code == "MONITOR_EXPORT_QUOTA_EXCEEDED"
    finally:
        exporter.close()
        history.close()


def test_pending_exports_reserve_workspace_bytes_before_streaming(tmp_path: Path, monkeypatch) -> None:
    import stm32_monitor.exports as exports_module

    paths = _paths(tmp_path)
    history = HistoryStore(paths)
    exporter = HistoryExporter(paths, history)
    request = ExportRequest("monitor-1", 0, 1_000, "jsonl")
    monkeypatch.setattr(exports_module, "MAX_EXPORT_BYTES", 100)
    monkeypatch.setattr(exports_module, "MAX_MANIFEST_BYTES", 10)
    monkeypatch.setattr(exports_module, "MAX_WORKSPACE_EXPORT_BYTES", 110)
    try:
        first = UUID("11111111-1111-4111-8111-111111111111")
        second = UUID("22222222-2222-4222-8222-222222222222")
        exporter._reserve_pending(
            first,
            request,
            f"exports/monitor-1/{first}/history.jsonl",
            f"exports/monitor-1/{first}/manifest.json",
            "2026-08-08T00:00:00.000000Z",
        )
        with pytest.raises(StorageFailure) as full:
            exporter._reserve_pending(
                second,
                request,
                f"exports/monitor-1/{second}/history.jsonl",
                f"exports/monitor-1/{second}/manifest.json",
                "2026-08-08T00:00:01.000000Z",
            )
        assert full.value.code == "MONITOR_EXPORT_QUOTA_EXCEEDED"
    finally:
        exporter.close()
        history.close()


def test_production_pending_reservations_are_bounded_by_the_512_mib_quota(
    tmp_path: Path,
) -> None:
    paths = _paths(tmp_path)
    history = HistoryStore(paths)
    exporter = HistoryExporter(paths, history)
    request = ExportRequest("monitor-1", 0, 1_000, "jsonl")
    export_ids = tuple(
        UUID(f"00000000-0000-4000-8000-{ordinal:012d}")
        for ordinal in range(1, 5)
    )
    try:
        for ordinal, export_id in enumerate(export_ids[:3]):
            exporter._reserve_pending(
                export_id,
                request,
                f"exports/monitor-1/{export_id}/history.jsonl",
                f"exports/monitor-1/{export_id}/manifest.json",
                f"2026-08-08T00:00:0{ordinal}.000000Z",
            )
        reservations = exporter._database.read(
            lambda connection: connection.execute(
                "SELECT export_id,byte_count FROM export_records ORDER BY export_id"
            ).fetchall(),
            empty=(),
        )
        assert reservations == [
            (str(export_id), 160 * 1024 * 1024 + 16 * 1024)
            for export_id in export_ids[:3]
        ]
        assert sum(byte_count for _, byte_count in reservations) < 512 * 1024 * 1024

        rejected = export_ids[3]
        with pytest.raises(StorageFailure) as full:
            exporter._reserve_pending(
                rejected,
                request,
                f"exports/monitor-1/{rejected}/history.jsonl",
                f"exports/monitor-1/{rejected}/manifest.json",
                "2026-08-08T00:00:03.000000Z",
            )
        assert full.value.code == "MONITOR_EXPORT_QUOTA_EXCEEDED"
        assert exporter._database.read(
            lambda connection: connection.execute(
                "SELECT COUNT(*),SUM(byte_count) FROM export_records"
            ).fetchone(),
            empty=None,
        ) == (3, 3 * (160 * 1024 * 1024 + 16 * 1024))
    finally:
        exporter.close()
        history.close()


def test_startup_recovers_atomically_published_pending_export(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    history = HistoryStore(paths)
    exporter = HistoryExporter(paths, history)
    recovered = None
    try:
        _append(paths, history)
        created = exporter.create_export(ExportRequest("monitor-1", 0, 1_000, "jsonl"), authorized=True).data
        exporter._database.write(
            lambda connection: connection.execute(
                "UPDATE export_records SET format = ? WHERE export_id = ?",
                ("PENDING:jsonl", str(created.export_id)),
            )
        )
        recovered = HistoryExporter(paths, history)
        loaded = recovered.get_export(created.export_id)
        assert loaded.ok and loaded.data == created
        with sqlite3.connect(paths.monitor_root / "monitor.sqlite3") as connection:
            assert connection.execute(
                "SELECT format FROM export_records WHERE export_id = ?",
                (str(created.export_id),),
            ).fetchone() == ("jsonl",)
    finally:
        if recovered is not None:
            recovered.close()
        exporter.close()
        history.close()


def test_recovery_progresses_past_ten_records_and_removes_poison_head(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    history = HistoryStore(paths)
    exporter = HistoryExporter(paths, history)
    recovered = None
    try:
        _append(paths, history)
        artifacts = [
            exporter.create_export(
                ExportRequest("monitor-1", 0, 1_000, "jsonl"),
                authorized=True,
            ).data
            for _ in range(12)
        ]

        def make_pending(connection: sqlite3.Connection) -> None:
            connection.execute("UPDATE export_records SET format = 'PENDING:jsonl'")
            connection.execute(
                "INSERT INTO export_records(export_id,session_id,format,relative_data_path,"
                "relative_manifest_path,sha256,byte_count,value_count,created_at_utc) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    "not-a-uuid", "monitor-1", "PENDING:jsonl", "invalid", "invalid",
                    "0" * 64, 0, 0, "0001-01-01T00:00:00.000000Z",
                ),
            )

        exporter._database.write(make_pending)
        recovered = HistoryExporter(paths, history)
        assert recovered.get_export(artifacts[-1].export_id).ok
        pending = recovered._database.read(
            lambda connection: connection.execute(
                "SELECT COUNT(*) FROM export_records WHERE format LIKE 'PENDING:%'"
            ).fetchone()[0],
            empty=-1,
        )
        poison = recovered._database.read(
            lambda connection: connection.execute(
                "SELECT COUNT(*) FROM export_records WHERE export_id = 'not-a-uuid'"
            ).fetchone()[0],
            empty=-1,
        )
        assert pending == 0 and poison == 0
    finally:
        if recovered is not None:
            recovered.close()
        exporter.close()
        history.close()


def test_get_export_rejects_manifest_shape_recorded_path_and_multiple_links(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    history = HistoryStore(paths)
    exporter = HistoryExporter(paths, history)
    try:
        _append(paths, history)
        first = exporter.create_export(ExportRequest("monitor-1", 0, 1_000, "jsonl"), authorized=True).data
        manifest = json.loads(first.manifest_path.read_text(encoding="utf-8"))
        manifest["unexpected"] = True
        first.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        assert exporter.get_export(first.export_id).code == "MONITOR_EXPORT_FAILED"

        second = exporter.create_export(ExportRequest("monitor-1", 0, 1_000, "jsonl"), authorized=True).data
        exporter._database.write(
            lambda connection: connection.execute(
                "UPDATE export_records SET relative_data_path = relative_manifest_path WHERE export_id = ?",
                (str(second.export_id),),
            )
        )
        assert exporter.get_export(second.export_id).code == "MONITOR_EXPORT_FAILED"

        third = exporter.create_export(ExportRequest("monitor-1", 0, 1_000, "jsonl"), authorized=True).data
        extra_link = third.directory / "extra-link.jsonl"
        os.link(third.data_path, extra_link)
        assert exporter.get_export(third.export_id).code == "MONITOR_EXPORT_FAILED"
    finally:
        exporter.close()
        history.close()


@pytest.mark.parametrize("format_name", ["jsonl", "csv"])
def test_export_formats_propagate_history_failure_and_reject_stalled_cursor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    format_name: str,
) -> None:
    paths = _paths(tmp_path)
    history = HistoryStore(paths)
    exporter = HistoryExporter(paths, history)
    try:
        _append(paths, history)
        source_page = history.query_history(HistoryQuery("monitor-1", 0, 1_000)).data
        stalled_page = HistoryPage.create(source_page.batches, next_cursor="1:0")
        monkeypatch.setattr(
            history,
            "_query_history_uncached",
            lambda query, **_kwargs: failure(
                "history.query", "MONITOR_STORAGE_CORRUPT", "monitor history is corrupt"
            ),
        )
        corrupt = exporter.create_export(
            ExportRequest("monitor-1", 0, 1_000, format_name), authorized=True
        )
        assert corrupt.code == "MONITOR_STORAGE_CORRUPT"

        monkeypatch.setattr(
            history,
            "_query_history_uncached",
            lambda query, **_kwargs: SimpleNamespace(ok=True, data=stalled_page),
        )
        stalled = exporter.create_export(
            ExportRequest("monitor-1", 0, 1_000, format_name), authorized=True
        )
        assert stalled.code == "MONITOR_STORAGE_CORRUPT"
    finally:
        exporter.close()
        history.close()


def test_get_export_enforces_limit_nonfinite_manifest_and_record_digest(tmp_path: Path, monkeypatch) -> None:
    import stm32_monitor.exports as exports_module

    paths = _paths(tmp_path)
    history = HistoryStore(paths)
    exporter = HistoryExporter(paths, history)
    try:
        _append(paths, history)
        limited = exporter.create_export(ExportRequest("monitor-1", 0, 1_000, "jsonl"), authorized=True).data
        monkeypatch.setattr(exports_module, "MAX_EXPORT_BYTES", limited.byte_count - 1)
        assert exporter.get_export(limited.export_id).code == "MONITOR_EXPORT_FAILED"
        monkeypatch.setattr(exports_module, "MAX_EXPORT_BYTES", 160 * 1024 * 1024)

        nonfinite = exporter.create_export(ExportRequest("monitor-1", 0, 1_000, "jsonl"), authorized=True).data
        manifest_text = nonfinite.manifest_path.read_text(encoding="utf-8")
        manifest_text = manifest_text.replace(f'"bytes":{nonfinite.byte_count}', '"bytes":NaN')
        nonfinite.manifest_path.write_text(manifest_text, encoding="utf-8")
        assert exporter.get_export(nonfinite.export_id).code == "MONITOR_EXPORT_FAILED"

        record = exporter.create_export(ExportRequest("monitor-1", 0, 1_000, "jsonl"), authorized=True).data
        exporter._database.write(
            lambda connection: connection.execute(
                "UPDATE export_records SET sha256 = ? WHERE export_id = ?",
                ("0" * 64, str(record.export_id)),
            )
        )
        assert exporter.get_export(record.export_id).code == "MONITOR_EXPORT_FAILED"
    finally:
        exporter.close()
        history.close()


@pytest.mark.parametrize("phase", ["opened", "after"])
def test_get_export_rejects_file_identity_change_during_bounded_read(
    tmp_path: Path,
    monkeypatch,
    phase: str,
) -> None:
    import stm32_monitor.exports as exports_module

    paths = _paths(tmp_path)
    history = HistoryStore(paths)
    exporter = HistoryExporter(paths, history)
    try:
        _append(paths, history)
        artifact = exporter.create_export(ExportRequest("monitor-1", 0, 1_000, "jsonl"), authorized=True).data
        real_fstat = os.fstat
        calls = 0

        def changed_fstat(descriptor: int):
            nonlocal calls
            metadata = real_fstat(descriptor)
            calls += 1
            change_now = (phase == "opened" and calls == 1) or (phase == "after" and calls == 2)
            if not change_now:
                return metadata
            return SimpleNamespace(
                st_dev=metadata.st_dev,
                st_ino=metadata.st_ino + 1,
                st_size=metadata.st_size,
                st_nlink=metadata.st_nlink,
            )

        monkeypatch.setattr(exports_module.os, "fstat", changed_fstat)
        with pytest.raises(ValueError):
            exports_module._read_regular_limited(
                artifact.data_path,
                limit=exports_module.MAX_EXPORT_BYTES,
                keep=False,
            )
    finally:
        exporter.close()
        history.close()


def test_bounded_reader_revalidates_the_recorded_name_after_hashing(tmp_path: Path, monkeypatch) -> None:
    import stm32_monitor.exports as exports_module

    target = tmp_path / "artifact.jsonl"
    target.write_bytes(b"one line\n")
    real_lstat = os.lstat
    calls = 0

    def replaced_name(path: Path):
        nonlocal calls
        metadata = real_lstat(path)
        calls += 1
        if calls == 1:
            return metadata
        return SimpleNamespace(
            st_mode=metadata.st_mode,
            st_dev=metadata.st_dev,
            st_ino=metadata.st_ino + 1,
            st_size=metadata.st_size,
            st_nlink=metadata.st_nlink,
            st_file_attributes=getattr(metadata, "st_file_attributes", 0),
        )

    monkeypatch.setattr(exports_module.os, "lstat", replaced_name)
    with pytest.raises(ValueError):
        exports_module._read_regular_limited(target, limit=1024, keep=False)


def test_failed_ready_transition_remains_pending_and_recovers(tmp_path: Path, monkeypatch) -> None:
    paths = _paths(tmp_path)
    history = HistoryStore(paths)
    exporter = HistoryExporter(paths, history)
    recovered = None
    try:
        _append(paths, history)
        original_mark_ready = exporter._mark_ready
        monkeypatch.setattr(
            exporter,
            "_mark_ready",
            lambda artifact, format_name, created_at_utc: (_ for _ in ()).throw(
                StorageFailure("MONITOR_EXPORT_FAILED", "interrupted")
            ),
        )
        failed = exporter.create_export(ExportRequest("monitor-1", 0, 1_000, "jsonl"), authorized=True)
        assert failed.code == "MONITOR_EXPORT_FAILED"
        pending_id = UUID(
            exporter._database.read(
                lambda connection: connection.execute(
                    "SELECT export_id FROM export_records WHERE format = 'PENDING:jsonl'"
                ).fetchone()[0],
                empty=None,
            )
        )
        monkeypatch.setattr(exporter, "_mark_ready", original_mark_ready)
        recovered = HistoryExporter(paths, history)
        assert recovered.get_export(pending_id).ok
    finally:
        if recovered is not None:
            recovered.close()
        exporter.close()
        history.close()


def test_startup_discards_incomplete_pending_export_and_bounds_recovery(tmp_path: Path, monkeypatch) -> None:
    import stm32_monitor.exports as exports_module

    paths = _paths(tmp_path)
    history = HistoryStore(paths)
    exporter = HistoryExporter(paths, history)
    recovered = None
    bounded = None
    try:
        _append(paths, history)
        incomplete = exporter.create_export(ExportRequest("monitor-1", 0, 1_000, "jsonl"), authorized=True).data
        exporter._database.write(
            lambda connection: connection.execute(
                "UPDATE export_records SET format = 'PENDING:jsonl' WHERE export_id = ?",
                (str(incomplete.export_id),),
            )
        )
        incomplete.manifest_path.unlink()
        recovered = HistoryExporter(paths, history)
        assert recovered.get_export(incomplete.export_id).code == "MONITOR_EXPORT_FAILED"
        assert not incomplete.directory.exists()

        waiting = exporter.create_export(ExportRequest("monitor-1", 0, 1_000, "jsonl"), authorized=True).data
        exporter._database.write(
            lambda connection: connection.execute(
                "UPDATE export_records SET format = 'PENDING:jsonl' WHERE export_id = ?",
                (str(waiting.export_id),),
            )
        )
        ticks = iter((0, exports_module.RECOVERY_TIME_BUDGET_NS))
        monkeypatch.setattr(exports_module.time, "monotonic_ns", lambda: next(ticks))
        bounded = HistoryExporter(paths, history)
        pending_format = bounded._database.read(
            lambda connection: connection.execute(
                "SELECT format FROM export_records WHERE export_id = ?",
                (str(waiting.export_id),),
            ).fetchone()[0],
            empty=None,
        )
        assert pending_format == "PENDING:jsonl"
    finally:
        if bounded is not None:
            bounded.close()
        if recovered is not None:
            recovered.close()
        exporter.close()
        history.close()


def test_get_export_maps_storage_failure_without_raw_exception(tmp_path: Path, monkeypatch) -> None:
    paths = _paths(tmp_path)
    history = HistoryStore(paths)
    exporter = HistoryExporter(paths, history)
    try:
        _append(paths, history)
        artifact = exporter.create_export(ExportRequest("monitor-1", 0, 1_000, "jsonl"), authorized=True).data
        monkeypatch.setattr(
            exporter._database,
            "read",
            lambda operation, empty: (_ for _ in ()).throw(
                StorageFailure("MONITOR_STORAGE_INVALID", "monitor storage is unavailable")
            ),
        )
        assert exporter.get_export(artifact.export_id).code == "MONITOR_STORAGE_INVALID"
    finally:
        exporter.close()
        history.close()
