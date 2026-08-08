# STM32TK-0501 UI-Ready Monitor Contracts Design

**Status:** Approved by the user on 2026-08-08

**Module:** `STM32TK-0501-MONITOR-SERVICE`

**Accepted base:** `913600f471d8fb0fb5345bdf668ca39ec1faf4d8`

**Active branch:** `codex/STM32TK-0501-MONITOR-SERVICE`

**Draft PR:** `#13`

## Purpose

Finish the Monitor service as a stable backend for the 0.5 bundled UI. The
service must page 10,000 realistic sample values within a bounded response,
expose only identity-derived probe and catalog choices, publish observable
state transitions, and provide verified export downloads. `STM32TK-0502`
will consume these contracts and add the same-process Preact UI; 0502 will not
redesign the service protocol.

## Decisions

### 1. Batch-normalized history is the sole history authority

The current v1 schema duplicates complete binding, group, run, timing, and drop
evidence in every `history_values.row_json`. A realistic row is about 1.26 KiB,
so a 4 MiB page can contain only about 3,300 values. Warm queries are about
752 ms p95. Increasing a generic JSON node limit or the response size would
retain the duplication and cannot meet the 10,000-value / 100 ms gate.

Schema v2 stores each canonical `SampleBatch` once in `history_batches`:

- `payload_json`: compact, sorted, UTF-8 canonical batch JSON;
- `payload_bytes`: exact byte count;
- `payload_sha256`: lowercase SHA-256 of `payload_json`;
- `value_count`: exact number of values in the batch;
- existing workspace/session/run/sequence/captured identity columns.

The v2 authority has no duplicated full-evidence row JSON. It retains a
lightweight `history_values` table containing only `batch_id`, `ordinal`,
`selector_kind`, `selector`, canonical value-only JSON, its byte count, and its
SHA-256. That table supports indexed selector filters and targeted corruption
checks; it never repeats binding, group, run, timing, drop, workspace, session,
or firmware evidence. The cursor is the pair `batch_id:value_ordinal`.

### 2. History wire model uses batch slices

`HistoryBatchSlice` carries batch evidence once and a contiguous value slice:

```python
@dataclass(frozen=True)
class HistoryBatchSlice:
    binding: ObservationBinding
    group_id: UUID
    group_revision: int
    run_id: UUID
    sequence: int
    scheduled_unix_ns: int
    captured_unix_ns: int
    latency_ns: int
    actual_rate_hz: float
    subscriber_drops: int
    history_drops: int
    deadline_drops: int
    start_ordinal: int
    batch_value_count: int
    values: tuple[SampleValue, ...]
```

`HistoryPage` is:

```python
@dataclass(frozen=True)
class HistoryPage:
    batches: tuple[HistoryBatchSlice, ...]
    value_count: int
    next_cursor: str | None
    serialized_bytes: int
```

The public JSON uses `batches`, `valueCount`, `nextCursor`, and
`serializedBytes`. Values in one slice are ordinals
`startOrdinal .. startOrdinal + len(values) - 1`. `batchValueCount` proves the
complete source batch size. A cursor always identifies the last value actually
returned; a page may end in the middle of a batch without gaps or duplicates.

The exact compact JSON encoding of `HistoryPage.to_dict()` is limited to
4 MiB. The page is also limited to 10,000 values. The history response is the
only REST response with this dedicated 4 MiB output limit; ordinary request and
response envelopes remain limited to 1 MiB.

### 3. Schema v1 to v2 migration is atomic and streaming

An existing v1 database is opened read-only and validated before mutation.
Migration runs under `BEGIN EXCLUSIVE` and processes one batch at a time:

1. Parse and fully validate the canonical v1 `history_batches.payload_json`.
2. Stream the matching v1 `history_values` in ordinal order.
3. Prove every flattened v1 row equals the corresponding canonical batch value
   plus its batch evidence.
4. Compute `payload_sha256` and `value_count`.
5. Insert the normalized v2 batch row and its value-only ordinal/index rows
   into new tables.
6. Rebuild indexes, retention accounting, and triggers.
7. Atomically replace the v1 tables and set `user_version = 2`.

Any length, digest, ordinal, workspace, session, run, sequence, timestamp,
model, or accounting mismatch rolls back the entire migration and returns
`MONITOR_STORAGE_CORRUPT`. Migration never materializes the full database in
memory.

### 4. Hot reads retain integrity without whole-database scans

A newly opened existing database receives one read-only `quick_check(1)` before
use. The MonitorDatabase instance records the main/sidecar file identities and
content metadata after every successful owned write. A hot read performs
component, descriptor, identity, schema, workspace, accounting, and targeted
payload checks; it does not rescan the whole database on a timer. Any external
identity/content change invalidates the trusted snapshot and requires a fresh
read-only integrity check before data is returned.

History query validates each selected batch exactly once: stored byte length,
SHA-256, SQLite identity columns, exact JSON shape, binding, all values, and
canonical `SampleBatch.to_dict()` equality. Unfiltered queries read batch rows
directly. Selector-filtered queries use the lightweight value index to locate
batch ordinals, then prove every selected value-only row equals the canonical
batch value. The immutable normalized batch is sliced without per-value
reconstruction of the common evidence.

### 5. The UI never supplies target, ELF, SVD, address, or build paths

`GET /api/v1/status` derives current project/build evidence from the canonical
project root. `POST /api/v1/probe/connect` accepts only:

```json
{"probeId":"<exact discovered probe ID>"}
```

The runtime obtains `expectedBuildId` and `expectedElfSha256` from its current
server-owned status snapshot immediately before opening the observation. The
operation fails if the evidence changes. Callers cannot override target, ELF,
SVD, backend, operation level, address, workspace, session, or identity pins.

### 6. UI-ready REST contracts

The existing authenticated routes remain. The following contracts are added
or replaced:

- `GET /api/v1/status` returns project, firmware, probe, and sampling state.
- `GET /api/v1/probes` returns a bounded list of exact public probe descriptors.
- `GET /api/v1/catalog/variables?query=&cursor=&limit=` returns bounded DWARF
  descriptors only after an observation is connected.
- `GET /api/v1/catalog/registers?query=&cursor=&limit=` returns bounded SVD
  register descriptors only after an observation is connected.
- `POST /api/v1/probe/connect` accepts only `probeId`.
- `GET /api/v1/history` returns normalized batch pages and accepts optional
  `runId`, `groupId`, and symbolic selector filters.
- `GET /api/v1/exports/{exportId}` returns verified metadata.
- `GET /api/v1/exports/{exportId}/download` streams the verified artifact by ID;
  no filesystem path is accepted or exposed.

All query and body grammars reject duplicate keys, unknown fields, non-finite
numbers, invalid Unicode, oversized values, and caller-supplied identity data.

### 7. Catalogs are bounded descriptors, not capabilities

Toolkit adds immutable paged descriptors backed by the already-proven current
`DwarfCatalog` and `SvdSelection`. A descriptor contains a symbolic selector,
display/type metadata, and child/array information required by the UI. It never
contains a raw address, absolute file path, backend object, or mutable catalog
reference. Pagination cursors are opaque, bounded, and tied to the current
firmware/catalog digest. Every page request revalidates the observation binding.

Default page size is 100; maximum is 256. Search text is optional, NFC
normalized, case-insensitive, and at most 128 characters. Results are sorted
deterministically by public selector.

### 8. Status and WebSocket state are explicit

Sampling states are exactly:

`IDLE`, `STARTING`, `RUNNING`, `PAUSED`, `PAUSED_BLOCKED`, `STOPPING`.

Status includes `blockedCode`, active `groupId`, `groupRevision`, `runId`, last
sequence, current binding epoch, and separate subscriber/history/deadline/service
drop totals. A connected sampler object is not reported as active unless its
state is `RUNNING` or `PAUSED`.

`GET /api/v1/live` publishes a discriminated event union:

- `hello`: protocol/toolkit/monitor versions and current state revision;
- `state`: complete public status after every state transition;
- `sample`: one `SampleBatch` plus service-subscriber drop evidence;
- `heartbeat`: current state revision and UTC timestamp.

Each event has a monotonically increasing `eventId`. The service retains a
bounded ring of 256 events. Reconnect may send `afterEventId`; if the event is
still retained, later events are replayed. Otherwise the server sends a fresh
state event with an explicit gap indicator. Clients never send WebSocket
messages.

`PAUSED_BLOCKED` never auto-resumes or auto-reacquires a probe. Reconnect and
start are explicit user actions and create a new run/binding epoch. The service
may persist UI selection preferences, but service startup never automatically
connects a probe or starts sampling.

### 9. Export flattening is single-source and lossless

One internal iterator flattens `HistoryBatchSlice` into value records for CSV,
JSONL, and tests. It preserves every batch evidence field and ordinal. Export
remains streamed, quota-bound, crash-recoverable, formula-neutralized for CSV,
and tied to its manifest SHA-256. Download revalidates database record, manifest,
path, descriptor identity, size, and digest before sending bytes.

### 10. 0501 / 0502 boundary

0501 owns the Python service, schema migration, catalog descriptor APIs,
history/export contracts, state events, release gates, and implementation
report. It does not add static routes, browser launching, Node dependencies, or
frontend assets.

After 0501 is accepted and merged, 0502 starts from that exact merge SHA and
adds:

- a bundled Preact + strict TypeScript SPA;
- Vite and a committed lockfile;
- modular ECharts;
- Vitest, Testing Library, Playwright, and axe gates;
- same-process aiohttp static routes and CSP;
- launcher/plugin/Skill integration and the 0.5.0 version promotion.

## Acceptance Evidence

- Realistic 10,000-value history page fits within 4 MiB and has no gaps,
  duplicates, or missing evidence.
- Three warmups plus 20 runs: history query p95 <100 ms on the named fixture.
- 256-value append p95 <50 ms.
- 100,000-value export <5 s and peak traced memory <64 MiB.
- 100,000-value retention pass <2 s and no sampler stall >=100 ms.
- Real aiohttp bootstrap/status p95 <10 ms.
- CPython 3.10 and 3.12 full Monitor suites, every new product module branch
  coverage >=90%.
- Full Toolkit tests are proven by complete, non-overlapping, successful shards.
- Two wheels build and install in fresh repository-external environments.
- Independent accepted-base-to-final-head review has no P0/P1 findings.
