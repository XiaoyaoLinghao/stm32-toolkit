# STM32TK-0501 UI-Ready Monitor Contracts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Normalize Monitor history by batch, migrate schema v1 atomically, expose bounded UI-ready identity/catalog/state/download APIs, and meet all 0501 release gates before 0502 begins.

**Architecture:** SQLite schema v2 stores one canonical payload per `SampleBatch`; `HistoryPage` transmits immutable batch slices instead of repeated per-value evidence. The aiohttp service derives all firmware pins from canonical project evidence, proxies bounded catalog descriptors from the active observation, and publishes explicit state/sample/heartbeat events. The bundled Preact UI remains a separate 0502 deliverable based on the accepted 0501 merge SHA.

**Tech Stack:** Python 3.10+, SQLite WAL, aiohttp, pyelftools-backed Toolkit DWARF/SVD models, pytest, pytest-cov.

## Global Constraints

- Accepted base is `913600f471d8fb0fb5345bdf668ca39ec1faf4d8`; continue on `codex/STM32TK-0501-MONITOR-SERVICE` and Draft PR #13.
- No caller-supplied target, ELF path, SVD path, raw address, backend, operation level, workspace, session, or build path is accepted.
- A fresh workspace has zero groups and read/status/catalog operations do not modify the project.
- History pages contain at most 10,000 values and at most 4 MiB of exact compact `data` JSON.
- Ordinary request/response and WebSocket message limits remain 1 MiB.
- Catalog pages contain at most 256 descriptors and never expose raw addresses or absolute paths.
- Service startup never automatically connects a probe or starts sampling.
- No new runtime dependency is added in 0501.
- Every task follows strict RED -> GREEN and ends with a separate reviewable commit.
- All new or materially modified product modules require branch coverage >=90%.

---

### Task 1: Define normalized history models and exact serialization

**Files:**
- Modify: `tools/stm32-monitor/src/stm32_monitor/models.py`
- Modify: `tools/stm32-monitor/src/stm32_monitor/history.py`
- Modify: `tools/stm32-monitor/src/stm32_monitor/protocol.py`
- Modify: `tools/stm32-monitor/tests/test_models.py`
- Modify: `tools/stm32-monitor/tests/test_history.py`

**Interfaces:**
- Produces: `HistoryBatchSlice` and the replacement `HistoryPage` described in the approved design.
- Produces: `flatten_history_page(page: HistoryPage) -> Iterator[Mapping[str, object]]` for Task 3.
- Consumes: existing exact `ObservationBinding`, `SampleBatch`, `SampleValue`, and `WatchItem` models.

- [ ] **Step 1: Add RED immutable-model tests**

Add tests that construct two slices from one batch, mutate every original nested input after construction, and assert the page remains unchanged. Assert rejection of subclasses, non-contiguous ordinals, `value_count` mismatch, more than 10,000 values, non-finite data, invalid cursor, and exact compact JSON above 4 MiB.

- [ ] **Step 2: Add the 10,000-value RED protocol test**

Build 40 realistic 256-value batches, slice exactly 10,000 values, and assert:

```python
payload = success("history.query", page).to_dict()["data"]
assert payload["valueCount"] == 10_000
assert len(json.dumps(payload, separators=(",", ":")).encode()) <= 4 * 1024 * 1024
assert sum(len(item["values"]) for item in payload["batches"]) == 10_000
```

Also prove a generic 10,001-node result still fails with the existing generic JSON budget.

- [ ] **Step 3: Run the focused RED tests**

Run:

```powershell
python -m pytest tools/stm32-monitor/tests/test_models.py tools/stm32-monitor/tests/test_history.py -q
```

Expected: failures because `HistoryBatchSlice` and normalized page fields do not exist and the old flat page exceeds its node/byte limits.

- [ ] **Step 4: Implement the immutable models**

Implement exact-type validation, deep immutable snapshots, contiguous ordinal rules, value and byte budgets, deterministic `to_dict()`, and the single flatten iterator. Snapshot each batch/slice once; do not run the generic full-page `_freeze_json` pass over 10,000 values.

- [ ] **Step 5: Run focused GREEN and coverage**

Run the command from Step 3 with branch coverage for `models`, `history`, and `protocol`; require every module >=90%.

- [ ] **Step 6: Commit Task 1**

```powershell
git add tools/stm32-monitor/src/stm32_monitor/models.py tools/stm32-monitor/src/stm32_monitor/history.py tools/stm32-monitor/src/stm32_monitor/protocol.py tools/stm32-monitor/tests/test_models.py tools/stm32-monitor/tests/test_history.py
git commit -m "feat(monitor): normalize history page evidence"
```

### Task 2: Migrate SQLite history schema v1 to v2

**Files:**
- Modify: `tools/stm32-monitor/src/stm32_monitor/storage.py`
- Modify: `tools/stm32-monitor/src/stm32_monitor/history.py`
- Modify: `tools/stm32-monitor/tests/test_storage.py`
- Modify: `tools/stm32-monitor/tests/test_history.py`

**Interfaces:**
- Consumes: Task 1 `HistoryBatchSlice`, `HistoryPage`, and `flatten_history_page`.
- Produces: schema version 2 `history_batches(payload_json,payload_bytes,payload_sha256,value_count,...)` plus value-only indexed `history_values(batch_id,ordinal,selector_kind,selector,value_json,value_bytes,value_sha256)`.
- Produces: bounded `HistoryStore.query_history()` returning normalized pages.

- [ ] **Step 1: Add RED v2 schema and migration tests**

Create a real v1 database with multiple batches and flattened rows. Assert successful streaming migration preserves flattened semantics, exact accounting, cursor positions, selector indexes, and retention order. Prove v2 value rows contain only selector/value data and do not repeat batch evidence. Parameterize corruption of row ordinal, payload bytes, batch JSON, workspace, sequence, and timestamps; each must roll back with original database bytes/schema/inventory retained and return `MONITOR_STORAGE_CORRUPT`.

- [ ] **Step 2: Add RED query integrity tests**

Assert v2 rejects length, digest, value-count, SQLite identity-column, workspace, session, run, sequence, and timestamp mismatches. Include a recomputed digest over a semantically wrong payload. Assert a cursor in the middle of a 256-value batch resumes at the next ordinal with no duplicate or gap.

- [ ] **Step 3: Add RED hot-read integrity/performance structure tests**

Instrument `quick_check`, batch decode, and model normalization calls. One cold open must run exactly one integrity check; repeated reads with unchanged trusted file identities must not run a whole-database check. Each selected batch must be decoded exactly once, independent of its value count. An externally changed identity must require a new integrity check before returning data.

- [ ] **Step 4: Run Task 2 RED**

Run:

```powershell
python -m pytest tools/stm32-monitor/tests/test_storage.py tools/stm32-monitor/tests/test_history.py -q
```

Expected: schema/migration/query tests fail on the v1 duplicated-row implementation.

- [ ] **Step 5: Implement schema v2 and streaming migration**

Raise `SCHEMA_VERSION` to 2. Add an exclusive, one-batch-at-a-time migration that compares every v1 flattened row with canonical batch evidence, writes normalized rows, rebuilds indexes/accounting/triggers, and atomically swaps tables. Do not read the complete database into memory.

- [ ] **Step 6: Implement normalized query and trusted hot reads**

Select ordered batch payloads, validate length/SHA/identity/model once, slice values by cursor and exact encoded page budget, and return normalized pages. Use the lightweight value index for selector-filtered queries and prove indexed value payloads against canonical batch values. Replace timer-driven whole-database quick checks with cold-open/identity-change checks while preserving descriptor, directory, workspace, schema, and targeted payload validation.

- [ ] **Step 7: Run Task 2 GREEN and coverage**

Require all Task 2 tests pass and `storage.py`/`history.py` branch coverage >=90%.

- [ ] **Step 8: Commit Task 2**

```powershell
git add tools/stm32-monitor/src/stm32_monitor/storage.py tools/stm32-monitor/src/stm32_monitor/history.py tools/stm32-monitor/tests/test_storage.py tools/stm32-monitor/tests/test_history.py
git commit -m "feat(monitor): migrate history storage to schema v2"
```

### Task 3: Adapt exports and history REST contract

**Files:**
- Modify: `tools/stm32-monitor/src/stm32_monitor/exports.py`
- Modify: `tools/stm32-monitor/src/stm32_monitor/runtime.py`
- Modify: `tools/stm32-monitor/src/stm32_monitor/service.py`
- Modify: `tools/stm32-monitor/tests/test_exports.py`
- Modify: `tools/stm32-monitor/tests/test_runtime.py`
- Modify: `tools/stm32-monitor/tests/test_service.py`

**Interfaces:**
- Consumes: Task 1 `flatten_history_page()` and Task 2 normalized query.
- Produces: optional history filters `runId`, `groupId`, and symbolic selector.
- Produces: verified `GET /api/v1/exports/{exportId}/download`.

- [ ] **Step 1: Add RED lossless export tests**

Export normalized pages to JSONL and CSV and compare every flattened value/evidence/ordinal with the source batches. Assert 100,000 values produce no gaps or duplicates. Preserve CSV formula neutralization and manifest SHA/size/count evidence.

- [ ] **Step 2: Add RED history filter and download tests**

Assert exact run/group/selector filters, duplicate-query rejection, cursor/filter binding, cross-workspace rejection, Range/path/filename override rejection, verified download bytes, MIME type, `Content-Disposition`, and no absolute path/token leakage. Tampered data, manifest, DB record, hardlink, reparse point, or descriptor identity must fail before response bytes are sent.

- [ ] **Step 3: Run Task 3 RED**

Run:

```powershell
python -m pytest tools/stm32-monitor/tests/test_exports.py tools/stm32-monitor/tests/test_runtime.py tools/stm32-monitor/tests/test_service.py -q
```

- [ ] **Step 4: Implement single-source flattening and filters**

Use only Task 1's flatten iterator. Extend query models and indexed SQL without caller identity overrides. Stream export creation and verified download; never call `read_bytes()` for an artifact.

- [ ] **Step 5: Run Task 3 GREEN and coverage**

Require all focused tests pass and `exports.py`, `runtime.py`, and `service.py` branch coverage >=90%.

- [ ] **Step 6: Commit Task 3**

```powershell
git add tools/stm32-monitor/src/stm32_monitor/exports.py tools/stm32-monitor/src/stm32_monitor/runtime.py tools/stm32-monitor/src/stm32_monitor/service.py tools/stm32-monitor/tests/test_exports.py tools/stm32-monitor/tests/test_runtime.py tools/stm32-monitor/tests/test_service.py
git commit -m "feat(monitor): expose normalized history and downloads"
```

### Task 4: Add server-owned status, probe discovery, and catalog descriptors

**Files:**
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/debug/types.py`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/debug/dwarf.py`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/debug/svd.py`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/monitor_observation.py`
- Modify: `tools/stm32-toolkit/tests/test_dwarf.py`
- Modify: `tools/stm32-toolkit/tests/test_svd.py`
- Modify: `tools/stm32-toolkit/tests/test_monitor_observation.py`
- Modify: `tools/stm32-monitor/src/stm32_monitor/models.py`
- Modify: `tools/stm32-monitor/src/stm32_monitor/probe_session.py`
- Modify: `tools/stm32-monitor/src/stm32_monitor/runtime.py`
- Modify: `tools/stm32-monitor/tests/test_models.py`
- Modify: `tools/stm32-monitor/tests/test_probe_session.py`
- Modify: `tools/stm32-monitor/tests/test_runtime.py`

**Interfaces:**
- Produces: immutable `VariableDescriptor`, `RegisterDescriptor`, and `CatalogPage` without addresses/paths.
- Produces: observation methods `list_variables(query,cursor,limit)` and `list_registers(query,cursor,limit)`.
- Produces: `monitor.probes.list`, expanded `monitor.status`, and probe connect accepting only `probeId`.

- [ ] **Step 1: Add RED Toolkit catalog descriptor tests**

Use real DWARF/SVD fixtures. Assert deterministic paging/search, arrays/structures/enum/register metadata, cursor binding to catalog digest, limit 1..256, provenance revalidation, and absence of raw address/absolute path/backend/control data in objects, reprs, and JSON.

- [ ] **Step 2: Add RED runtime status/probe tests**

Assert disconnected status derives project/firmware pins without project writes, probe discovery is bounded, and connect accepts exactly `probeId`. Inject a firmware change between status and observation open; connect must fail closed. Unknown/manual build/ELF/target/SVD fields must never reach the observation factory.

- [ ] **Step 3: Run Task 4 RED**

Run focused Toolkit and Monitor files listed above; expect missing descriptor/list/status contracts.

- [ ] **Step 4: Implement bounded descriptor APIs**

Build descriptors from current immutable catalogs, use opaque digest-bound cursors, revalidate before each page, and expose no capability-bearing address or path.

- [ ] **Step 5: Implement server-owned probes/status/connect**

Use the existing Toolkit probe-list workflow through an injected bounded seam. Derive build/ELF pins from canonical current evidence immediately before connection. Status reports exact project, firmware, probe, sampler, active group/run, blocked code, binding epoch, and separate drop totals.

- [ ] **Step 6: Run Task 4 GREEN and coverage**

Require all focused suites pass; each modified Toolkit/Monitor module branch coverage >=90%.

- [ ] **Step 7: Commit Task 4**

```powershell
git add tools/stm32-toolkit/src/stm32_toolkit/debug tools/stm32-toolkit/src/stm32_toolkit/monitor_observation.py tools/stm32-toolkit/tests/test_dwarf.py tools/stm32-toolkit/tests/test_svd.py tools/stm32-toolkit/tests/test_monitor_observation.py tools/stm32-monitor/src/stm32_monitor tools/stm32-monitor/tests/test_models.py tools/stm32-monitor/tests/test_probe_session.py tools/stm32-monitor/tests/test_runtime.py
git commit -m "feat(monitor): expose identity-bound catalogs and status"
```

### Task 5: Publish explicit live state events and bounded replay

**Files:**
- Modify: `tools/stm32-monitor/src/stm32_monitor/models.py`
- Modify: `tools/stm32-monitor/src/stm32_monitor/sampler.py`
- Modify: `tools/stm32-monitor/src/stm32_monitor/runtime.py`
- Modify: `tools/stm32-monitor/src/stm32_monitor/service.py`
- Modify: `tools/stm32-monitor/tests/test_models.py`
- Modify: `tools/stm32-monitor/tests/test_sampler.py`
- Modify: `tools/stm32-monitor/tests/test_runtime.py`
- Modify: `tools/stm32-monitor/tests/test_service.py`

**Interfaces:**
- Produces: `hello`, `state`, `sample`, and `heartbeat` events with monotonic `eventId`.
- Produces: a 256-event replay ring and `afterEventId` reconnect grammar.

- [ ] **Step 1: Add RED state-machine and event tests**

Cover every sampling state, `PAUSED_BLOCKED`, active group/run/binding epoch, all four drop counters, event ordering, monotonic IDs, initial hello/state, heartbeat, replay, replay-gap state snapshot, slow-client eviction accounting, and repeated cancellation. Assert no auto connect/start/reacquire after restart or blocked state.

- [ ] **Step 2: Run Task 5 RED**

Run sampler/runtime/service focused tests; expect missing event union and state notification behavior.

- [ ] **Step 3: Implement state snapshots and event broker**

Keep one bounded event broker in the runtime. Publish a complete state snapshot after every transition and when blocked. Sample events carry service-subscriber drop evidence separately. Heartbeat uses monotonic scheduling and UTC capture without busy loops.

- [ ] **Step 4: Run Task 5 GREEN and coverage**

Require focused tests pass and all four modules branch coverage >=90%.

- [ ] **Step 5: Commit Task 5**

```powershell
git add tools/stm32-monitor/src/stm32_monitor/models.py tools/stm32-monitor/src/stm32_monitor/sampler.py tools/stm32-monitor/src/stm32_monitor/runtime.py tools/stm32-monitor/src/stm32_monitor/service.py tools/stm32-monitor/tests/test_models.py tools/stm32-monitor/tests/test_sampler.py tools/stm32-monitor/tests/test_runtime.py tools/stm32-monitor/tests/test_service.py
git commit -m "feat(monitor): publish observable live state"
```

### Task 6: Close performance, packaging, and acceptance gates

**Files:**
- Modify: `docs/superpowers/plans/2026-08-08-stm32tk-0501-monitor-service.md`
- Create: `docs/codex/returns/STM32TK-0501-MONITOR-SERVICE/implementation-report.md`
- Test-only modifications are allowed only when a gate proves a portability or isolation defect.

**Interfaces:**
- Consumes all Tasks 1-5 public contracts.
- Produces the code-head implementation report and merge-ready PR evidence.

- [ ] **Step 1: Run complete Monitor gates on CPython 3.10 and 3.12**

Run all `tools/stm32-monitor/tests` with branch coverage. Require every new product module >=90%, zero failures, and no new skip/xfail.

- [ ] **Step 2: Run complete Toolkit gates in mechanically complete shards**

List all Toolkit test files, prove assigned=unique=expected, run every shard with short external basetemp paths, and sum exact pass/skip/fail counts. No timeout or missing output counts as PASS.

- [ ] **Step 3: Run named performance gates**

On one realistic 100,000-value database, use 3 warmups and 20 measured runs:

- 256-value append p95 <50 ms;
- 10,000-value query p95 <100 ms, exact 10,000 values, <=4 MiB;
- 100,000-value export <5 s and traced peak memory <64 MiB;
- retention pass <2 s and no sampler stall >=100 ms;
- real aiohttp bootstrap/status p95 <10 ms.

Record min/median/p95/max, Python/OS, fixture digest, DB bytes, wheel digests, and commands.

- [ ] **Step 4: Build and install both wheels**

Build repository-external wheels, install them into fresh CPython 3.10 and 3.12 environments from a repository-external cwd, and verify zero-group CRUD, fake observation/sampling/history/export/REST/WebSocket/cancellation, package inventory, backend-lazy imports, and no legacy modules.

- [ ] **Step 5: Run static and filesystem gates**

Run compileall with external bytecode cache, accepted-base `git diff --check`, forbidden raw input/backend/token/default scans, status clean, and exact changed-path inventory. Verify project bytes/names/mtimes/modes and Git porcelain remain unchanged across read/start/status/catalog/history operations.

- [ ] **Step 6: Write the implementation report**

Record accepted base and the code head before the report commit. Include only verified evidence, named deferred physical-board/Linux owners, and no report self-SHA or moving commit totals.

- [ ] **Step 7: Commit report, push, and request independent review**

```powershell
git add docs/superpowers/plans/2026-08-08-stm32tk-0501-monitor-service.md docs/codex/returns/STM32TK-0501-MONITOR-SERVICE/implementation-report.md
git commit -m "docs(STM32TK-0501): record monitor service evidence"
git push origin codex/STM32TK-0501-MONITOR-SERVICE
```

Review the complete accepted-base-to-final-head diff in a fresh clean worktree.
Correct every P0/P1 on the same branch, rerun affected and full gates, mark PR #13
ready only after `ACCEPTED`, merge to `master`, and retain the remote branch.

## Self-Review Checklist

- [ ] Every approved design requirement maps to a task above.
- [ ] Task interfaces use the same `HistoryBatchSlice`, `HistoryPage`, catalog,
  status, event, and download names throughout.
- [ ] No step relaxes identity, workspace, size, corruption, or authorization
  boundaries to achieve performance.
- [ ] No step adds 0502 static assets, browser launch, Node dependencies, or UI.
- [ ] No placeholder work remains in this plan.
