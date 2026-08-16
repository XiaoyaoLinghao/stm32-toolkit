# STM32TK-0603 Monitor Analytics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a non-destructive Monitor history extension, bounded cross-run analytics, quality/stage/halt analysis, safe annotations and markers, accessible UI, and explicit deterministic AI bundles without regressing 0.5 live monitoring.

**Architecture:** Python owns canonical history reads, compatibility, alignment, statistics, decimation, annotations, and bundle creation. One `monitor.sqlite3` receives a non-destructive transactional structure extension while accepted 0.5 original-column counts, keys, values, inventory hashes, and meaning remain unchanged; the Preact UI renders bounded typed responses and never opens storage. 0603 freezes a Windows-only candidate as the final product CodeHead, then hands that unchanged CodeHead to 0600 for the later unified 0.4+0.6 hardware activity and final release acceptance.

**Tech Stack:** Windows, Python 3.10/3.12, SQLite, aiohttp, dataclasses, pytest/pytest-cov, TypeScript 5.9, Preact, ECharts, Vitest/V8 coverage, Playwright, axe-core, Vite, Chromium.

## Global Constraints

- Begin at the accepted report commit of `STM32TK-0602-DIAGNOSTIC-LOOP`; record its full SHA.
- Follow `docs/superpowers/specs/2026-08-14-stm32tk-0603-monitor-analytics-design.md`.
- Codex and Codex-created subagents permanently own 0603 implementation, review, and acceptance;
  no other implementation owner is introduced by this plan.
- Keep one `monitor.sqlite3`; extend its structure transactionally while preserving every accepted
  0.5 original-column row count, key, value, canonical inventory hash, identity, and meaning. Do not
  assert physical database/page/row bytes. Use descriptive semantic names for new tables/columns/
  events and numeric versions only for internal storage metadata.
- Keep loopback/random-port/auth/origin/CSP/static protections and every 0.5 threshold unchanged.
- Expand groups, canonicalize, and deduplicate before enforcing the 16-selector limit. Maximum
  request is 8 runs, 8 groups, 16 selectors, 640,000 post-expansion scalar observations, and a
  hard 64,000 returned-point cap. If mandatory points exceed the cap, fail with
  `ANALYSIS_LIMIT_EXCEEDED` and the exact required minimum; never drop them or exceed the cap.
- Every changed Python and TypeScript product file must reach at least 90% branch coverage in its
  owning shard; correctness runs on Windows Python 3.10/3.12 and Chromium.
- No browser/model/cloud/API-key/automatic-annotation or automatic group creation is permitted.
- Any impact-selected real reset/flash/modify gate requires a current-task exact user authorization;
  this plan and prior-module evidence do not transfer authorization.
- Preserve frozen gate families and 0601/0602 entries; fill only reserved 0603 families and freeze
  the complete catalog/node/performance digests before candidate.
- The reconciled Windows candidate is the final product CodeHead. It may finish as
  `SOFTWARE_COMPLETE_HARDWARE_PENDING`; real-board link/diagnostic evidence belongs to the later
  unified 0.4+0.6 hardware activity, while final `v0.6.0` still requires hardware PASS.
- Linux ownership/shards, Firefox/WebKit, and Linux ZIP transfer are deferred beyond 0603.
- 0603 creates no report-only commit; 0600 alone owns the final tracked report.
- No remote Git action is authorized by this plan.

### Layer and reuse boundary for unimplemented 0603 work

- L0 is the accepted SQLite/aiohttp/Preact/ECharts/Vitest/Playwright/Vite stack. 0603 pins and
  invokes it; it does not reproduce storage, HTTP/WebSocket, rendering, unit-test, browser-test,
  or bundling engines.
- L1 is the existing Toolkit identity/Evidence/Test/authorization contract and the one shared
  0600 controller, verifier, catalog, performance catalog, and native-output adapter.
- L2 is the accepted 0.5 `monitor.sqlite3`, HistoryStore, sampling/storage/service/WebSocket and
  typed Monitor protocol. Task 1 transactionally extends that same database and service; no task
  creates a second Monitor, database, service, or Serial Studio path.
- L3 additions are limited to compatibility, alignment, statistics, deterministic decimation,
  quality/stage/halt analysis, annotations/markers, explicit AI bundles, and incremental UI over
  the existing Preact/ECharts components.
- L4 work in Tasks 11--13 reuses the shared 0600 gates. It may fill reserved 0603 catalog entries
  and exact nodes, but it may not copy or fork a module-specific controller or verifier.

Before a new numeric or UI dependency is added, the owning task must first produce a bounded
proof-of-fit with exact version/license/offline source, real Windows argv/exit, a real sanitized
native fixture, closed parser/error mapping, path/credential/network/concurrency/timeout/partial-
output safety, deterministic rounding, package/performance cost, and full affected 0.5 Monitor
regression. The default is no new dependency: bounded deterministic algorithms remain local unless
the proof demonstrates a material reduction in not-yet-written code and maintenance. Failure
rejects the component without changing any 0603 product requirement.

Existing package locks freeze Preact `10.29.8`, ECharts `6.1.0`, Vitest `4.1.10`, and Playwright
`1.56.1`; Python support freezes SQLite through the managed interpreter and the accepted aiohttp
lock. Any version change is a dependency task and new CodeHead, never an ambient update.

---

## Task 1: Extend history storage with identity and quality metadata

**Files:**

- Modify: `tools/stm32-monitor/src/stm32_monitor/models.py`
- Modify: `tools/stm32-monitor/src/stm32_monitor/history.py`
- Modify: `tools/stm32-monitor/src/stm32_monitor/storage.py`
- Create: `tools/stm32-monitor/tests/test_history_extension.py`
- Modify: `tools/stm32-monitor/tests/test_history.py`
- Modify: `tools/stm32-monitor/tests/test_storage.py`

- [ ] Write failing tests for a single `monitor.sqlite3`; non-destructive transactional structure
  upgrade and failure injection after every upgrade statement; accepted-0.5 original-column row
  count, primary-key, key/value, and canonical inventory SHA-256 preservation using the spec's
  length-prefixed tagged-cell encoding; exact logical schema/data rollback after reopen; and
  `PRAGMA integrity_check` returning exactly `ok` after success and rollback. Explicitly prove the
  gate does not compare database-file, page, or physical-row bytes. Also cover descriptive semantic
  names independent of internal numeric storage versions; unknown future internal version failure;
  firmware/source identity; monotonic sequence/time; UTC display time; all quality codes and their
  frozen precedence; stage/pause/halt/gap/dropped/backpressure events; evidence/test/diagnostic
  links; `legacy_missing`; append-only normal writes; permitted bounded retention GC; and forged/
  corrupt index/cache rejection.

- [ ] Run RED:

```powershell
py -3.12 -m pytest tools/stm32-monitor/tests/test_history_extension.py tools/stm32-monitor/tests/test_history.py tools/stm32-monitor/tests/test_storage.py -q -p no:cacheprovider
```

Expected: the non-destructive history extension and its preservation checks are absent.

- [ ] Implement the frozen row/event models and one atomic structural upgrade for existing and new
  `monitor.sqlite3` databases. Add only the structures needed for new writes; project accepted 0.5
  rows as `legacy_missing` without changing their original columns, keys, values, or meaning. Keep numeric versions
  internal, use descriptive public semantic names, preserve controlled retention GC, and add
  explicit quality/identity/link writes in the append path. Do not toggle process-global GC or
  weaken append locking.

- [ ] Run GREEN on 3.10/3.12, concurrent history regressions, and branch coverage:

```powershell
py -3.10 -m pytest tools/stm32-monitor/tests/test_history_extension.py tools/stm32-monitor/tests/test_history.py tools/stm32-monitor/tests/test_storage.py -q -p no:cacheprovider
py -3.12 tools/release/run_0600_gates.py dev-coverage --task-id STM32TK-0603-T01 --evidence-root C:\tmp\stm32tk-0603-t01-coverage -- tools/stm32-monitor/tests/test_history_extension.py tools/stm32-monitor/tests/test_history.py tools/stm32-monitor/tests/test_storage.py --cov=stm32_monitor.models --cov=stm32_monitor.history --cov=stm32_monitor.storage -q -p no:cacheprovider
```

- [ ] Commit:

```powershell
git add tools/stm32-monitor/src/stm32_monitor/models.py tools/stm32-monitor/src/stm32_monitor/history.py tools/stm32-monitor/src/stm32_monitor/storage.py tools/stm32-monitor/tests/test_history_extension.py tools/stm32-monitor/tests/test_history.py tools/stm32-monitor/tests/test_storage.py
git commit -m "feat(STM32TK-0603): extend monitor history metadata"
```

## Task 2: Define bounded analysis requests and compatibility

**Files:**

- Create: `schemas/monitor-analysis.schema.json`
- Create: `tools/stm32-monitor/src/stm32_monitor/schemas/monitor-analysis.schema.json`
- Create: `tools/stm32-monitor/src/stm32_monitor/analysis/__init__.py`
- Create: `tools/stm32-monitor/src/stm32_monitor/analysis/model.py`
- Create: `tools/stm32-monitor/src/stm32_monitor/analysis/query.py`
- Modify: `tools/stm32-monitor/pyproject.toml`
- Create: `tools/stm32-monitor/tests/test_analysis_model.py`
- Create: `tools/stm32-monitor/tests/test_analysis_query.py`

- [ ] Write failing tests for canonical `AnalysisRequest`, exact unknown/duplicate/type rejection,
  and byte-identical closed root/packaged JSON Schema definitions for `AnalysisRequest`,
  `RunSelector`, `GroupSelector`, `SelectorRef`, `DifferencePair`, every `AlignmentSpec` variant,
  `TimeWindow`, `LogicalSelectorIdentity`, and `SelectorResolutionIdentity`. Cover every required/
  optional field, exact string format, integer range, conditional field set, unknown field,
  duplicate canonical object, malformed UUID/SHA-256/HexU64, invalid Unicode, and non-finite/
  boolean-as-integer rejection. Cover the 64 KiB body, zero direct selectors only when group
  expansion/deduplication yields 1..16, missing/stale/empty/ambiguous/cross-workspace groups,
  immutable stored `selectorId` resolution, no raw expression/path on the wire, group expansion
  then selector-ID deduplication before the 16-selector check,
  the 640,000 post-expansion scalar-observation bound, the hard 64,000-point cap, all other
  cardinality/deadline bounds, and stable logical versus resolution identities. Cover default
  `strict`; explicit `allow-firmware-difference`; logical target/expression/path/type/width/
  signedness/encoding mismatch; visible build/ELF/source/address/DWARF differences; deterministic
  order; zero-to-eight directed difference pairs; interpolation-gap bounds; workspace isolation;
  corrupt history; byte-identical root/packaged schema; and no raw SQL/expression surface.

```python
def test_name_only_match_does_not_override_type_identity(history):
    result = compare(history, request_for_same_name_different_type())
    assert result.error.code == "ANALYSIS_INCOMPATIBLE"
```

- [ ] Run RED:

```powershell
py -3.12 -m pytest tools/stm32-monitor/tests/test_analysis_model.py tools/stm32-monitor/tests/test_analysis_query.py -q -p no:cacheprovider
```

- [ ] Implement the spec's closed immutable request/result/identity models and byte-identical JSON
  Schemas. Analysis wire accepts only immutable stored `selectorId` values; history ingestion uses
  the accepted Monitor canonicalizer, stores the closed logical identity, and derives `selectorId`
  from the domain-prefixed RFC 8785 canonical JSON bytes. Implement revision-bound group expansion,
  pre-read selector-ID deduplication, exact empty/ambiguous errors, bounded public HistoryStore query
  methods, and the exact compatibility matrix. Logical identity is target plus normalized
  expression/path and resolved type/width/signedness/encoding; resolution identity is build/ELF/
  source snapshot/address/source location/DWARF. Default strict requires both; the explicit
  firmware-difference mode requires logical equality and returns every resolution difference.

- [ ] Run GREEN dual Python and branch coverage:

```powershell
py -3.10 -m pytest tools/stm32-monitor/tests/test_analysis_model.py tools/stm32-monitor/tests/test_analysis_query.py -q -p no:cacheprovider
py -3.12 tools/release/run_0600_gates.py dev-coverage --task-id STM32TK-0603-T02 --evidence-root C:\tmp\stm32tk-0603-t02-coverage -- tools/stm32-monitor/tests/test_analysis_model.py tools/stm32-monitor/tests/test_analysis_query.py --cov=stm32_monitor.analysis.model --cov=stm32_monitor.analysis.query -q -p no:cacheprovider
```

- [ ] Commit:

```powershell
git add -- schemas/monitor-analysis.schema.json tools/stm32-monitor/src/stm32_monitor/schemas/monitor-analysis.schema.json tools/stm32-monitor/src/stm32_monitor/analysis/__init__.py tools/stm32-monitor/src/stm32_monitor/analysis/model.py tools/stm32-monitor/src/stm32_monitor/analysis/query.py tools/stm32-monitor/pyproject.toml tools/stm32-monitor/tests/test_analysis_model.py tools/stm32-monitor/tests/test_analysis_query.py
git commit -m "feat(STM32TK-0603): query compatible monitor runs"
```

## Task 3: Implement alignment, statistics, and deterministic decimation

**Files:**

- Create: `tools/stm32-monitor/src/stm32_monitor/analysis/alignment.py`
- Create: `tools/stm32-monitor/src/stm32_monitor/analysis/decimation.py`
- Modify: `tools/stm32-monitor/src/stm32_monitor/analysis/query.py`
- Create: `tools/stm32-monitor/tests/test_analysis_alignment.py`
- Create: `tools/stm32-monitor/tests/test_analysis_decimation.py`
- Create: `tools/stm32-monitor/tests/test_analysis_statistics.py`

- [ ] Write failing alignment tests for absolute clock uncertainty, run-relative first valid point,
  exact marker/annotation anchors, explicit `start` or `end` for interval marker-relative anchors,
  rejection when that boundary is omitted, missing/ambiguous markers, multiple runs, empty/no-valid
  input, no fallback, and proof raw timestamps remain unchanged.

- [ ] Write failing numeric/state statistic tests for finite filtering, population deviation,
  nearest-rank p50/p95 over valid finite scalar observations, delta, dwell/transition counts,
  excluded-quality counts, series-level `ANALYSIS_NO_VALID_SAMPLES`, overall failure only when all
  requested series are empty, deterministic float serialization, and raw-versus-eligible counts.

- [ ] Write failing decimation tests for first/min/max/last order, transition/endpoints, quality
  boundaries, marker adjacency, duplicate elimination by sequence, exact total budget allocation,
  repeatability, adversarial spikes, statistics remaining raw-data based, and mandatory-point
  overflow returning `ANALYSIS_LIMIT_EXCEEDED` with the exact required minimum without dropping
  points or returning more than 64,000. Add golden allocations spanning ordinary and directed-
  difference streams for mandatory-only, proportional, equal-remainder, zero-optional, and
  under-filled budgets. For every golden case, permute run/selector/group/difference input order and
  assert identical per-stream budgets, returned sample/difference keys, and serialized response.

- [ ] Write failing directed-difference tests using baseline timestamps: `candidate - baseline`,
  bounded linear interpolation, no extrapolation, no interpolation across invalid quality/stage/
  discontinuity or excessive gaps, excluded counts/reasons, numeric-only compatibility, and
  statistics computed before difference decimation.

- [ ] Run RED:

```powershell
py -3.12 -m pytest tools/stm32-monitor/tests/test_analysis_alignment.py tools/stm32-monitor/tests/test_analysis_decimation.py tools/stm32-monitor/tests/test_analysis_statistics.py -q -p no:cacheprovider
```

- [ ] Implement pure alignment/statistic/decimation functions and the spec's one global point-budget
  allocator: canonical stream keys, mandatory-first rejection, proportional integer floor, exact
  fractional-remainder ordering, and stable stream-key tie-break. Assemble `RunComparison` with
  mandatory/optional counts and algorithm version `stm32-monitor-decimation/1`.

- [ ] Run GREEN on both Pythons and per-file branch coverage:

```powershell
py -3.10 -m pytest tools/stm32-monitor/tests/test_analysis_alignment.py tools/stm32-monitor/tests/test_analysis_decimation.py tools/stm32-monitor/tests/test_analysis_statistics.py -q -p no:cacheprovider
py -3.12 tools/release/run_0600_gates.py dev-coverage --task-id STM32TK-0603-T03 --evidence-root C:\tmp\stm32tk-0603-t03-coverage -- tools/stm32-monitor/tests/test_analysis_alignment.py tools/stm32-monitor/tests/test_analysis_decimation.py tools/stm32-monitor/tests/test_analysis_statistics.py --cov=stm32_monitor.analysis.alignment --cov=stm32_monitor.analysis.decimation --cov=stm32_monitor.analysis.query -q -p no:cacheprovider
```

- [ ] Commit:

```powershell
git add -- tools/stm32-monitor/src/stm32_monitor/analysis/alignment.py tools/stm32-monitor/src/stm32_monitor/analysis/decimation.py tools/stm32-monitor/src/stm32_monitor/analysis/query.py tools/stm32-monitor/tests/test_analysis_alignment.py tools/stm32-monitor/tests/test_analysis_decimation.py tools/stm32-monitor/tests/test_analysis_statistics.py
git commit -m "feat(STM32TK-0603): align and reduce monitor comparisons"
```

## Task 4: Add quality, stage, gap, and halt-impact analysis

**Files:**

- Create: `tools/stm32-monitor/src/stm32_monitor/analysis/quality.py`
- Create: `tools/stm32-monitor/tests/test_analysis_quality.py`

- [ ] Write failing tests for valid ratio, counts/duration by every status, longest gap, p95
  interval over consecutive valid scalar observations without crossing a stage/pause/halt/quality/
  discontinuity boundary, dropped/backpressure totals, pause/halt overlaps, discontinuities,
  128-stage bound,
  recorded-only stage boundaries, legacy missing-metadata warning, mixed-quality samples, exact
  primary precedence `discontinuity > decode_error > probe_error > unavailable > halted > paused >
  dropped > backpressured > stale > legacy_missing > valid`, preservation of all reason codes,
  request-window duration clipping, overflow/zero-duration intervals, and deterministic ordering.

- [ ] Run RED:

```powershell
py -3.12 -m pytest tools/stm32-monitor/tests/test_analysis_quality.py -q -p no:cacheprovider
```

- [ ] Implement `analyze_quality(samples, events, stages, window)` without heuristic stage names or
  silently accepting invalid-quality numeric values.

- [ ] Run GREEN on both Python versions with branch coverage:

```powershell
py -3.10 -m pytest tools/stm32-monitor/tests/test_analysis_quality.py -q -p no:cacheprovider
py -3.12 tools/release/run_0600_gates.py dev-coverage --task-id STM32TK-0603-T04 --evidence-root C:\tmp\stm32tk-0603-t04-coverage -- tools/stm32-monitor/tests/test_analysis_quality.py --cov=stm32_monitor.analysis.quality -q -p no:cacheprovider
```

- [ ] Commit:

```powershell
git add tools/stm32-monitor/src/stm32_monitor/analysis/quality.py tools/stm32-monitor/tests/test_analysis_quality.py
git commit -m "feat(STM32TK-0603): explain monitor data quality"
```

## Task 5: Add append-only annotations and diagnostic markers

**Files:**

- Create: `tools/stm32-monitor/src/stm32_monitor/annotations.py`
- Create: `tools/stm32-monitor/tests/test_annotations.py`
- Create: `tools/stm32-monitor/tests/test_annotation_concurrency.py`

- [ ] Write failing tests for note/bookmark/diagnostic-marker revisions, canonical digest chain,
  exact sample/interval/event anchors, title/body/tag/evidence limits, optimistic revision conflict,
  create without a prior revision, edit/tombstone with an explicit integer `expectedRevision`,
  stale concurrent writers, crash recovery, text-only content, workspace/run link isolation,
  Toolkit diagnostic/evidence validation, unavailable bridge, and no raw-history update.

- [ ] Run RED:

```powershell
py -3.12 -m pytest tools/stm32-monitor/tests/test_annotations.py tools/stm32-monitor/tests/test_annotation_concurrency.py -q -p no:cacheprovider
```

- [ ] Implement authoritative append-only revisions through the 0601 public evidence-store API
  plus a rebuildable Monitor query index; a forged/corrupt index must never override a revision.
  Validate external diagnostic/evidence IDs through a narrow injected Toolkit bridge before
  publication.

- [ ] Run GREEN dual Python and branch coverage:

```powershell
py -3.10 -m pytest tools/stm32-monitor/tests/test_annotations.py tools/stm32-monitor/tests/test_annotation_concurrency.py -q -p no:cacheprovider
py -3.12 tools/release/run_0600_gates.py dev-coverage --task-id STM32TK-0603-T05 --evidence-root C:\tmp\stm32tk-0603-t05-coverage -- tools/stm32-monitor/tests/test_annotations.py tools/stm32-monitor/tests/test_annotation_concurrency.py --cov=stm32_monitor.annotations -q -p no:cacheprovider
```

- [ ] Commit:

```powershell
git add tools/stm32-monitor/src/stm32_monitor/annotations.py tools/stm32-monitor/tests/test_annotations.py tools/stm32-monitor/tests/test_annotation_concurrency.py
git commit -m "feat(STM32TK-0603): add revisioned monitor annotations"
```

## Task 6: Expose authenticated analysis and annotation APIs

**Files:**

- Modify: `tools/stm32-monitor/src/stm32_monitor/protocol.py`
- Modify: `tools/stm32-monitor/src/stm32_monitor/service.py`
- Create: `tools/stm32-monitor/tests/test_analysis_service.py`
- Create: `tools/stm32-monitor/tests/test_annotation_service.py`
- Modify: `tools/stm32-monitor/tests/test_service.py`
- Modify: `tools/stm32-monitor/tests/test_auth.py`

- [ ] Write failing real-HTTP tests for exact routes/schemas, auth/origin/content type, no-store,
  request IDs, body/result limits, one 30-second monotonic absolute deadline covering validation,
  reads, computation, optional bundle preparation, and serialization, unknown field/Unicode/
  non-finite input, explicit annotation `expectedRevision`, all errors,
  WebSocket invalidation coalescing/backpressure/reconnect, cross-workspace ID forgery, and proof
  rejected requests do not query/mutate.

- [ ] Run RED:

```powershell
py -3.12 -m pytest tools/stm32-monitor/tests/test_analysis_service.py tools/stm32-monitor/tests/test_annotation_service.py tools/stm32-monitor/tests/test_service.py tools/stm32-monitor/tests/test_auth.py -q -p no:cacheprovider
```

- [ ] Implement typed request/response codecs and handlers over public analysis/annotation APIs;
  keep bulk results on HTTP and bounded notifications on WebSocket.

- [ ] Run GREEN on 3.10/3.12 with branch coverage and all existing service/auth regressions:

```powershell
py -3.10 -m pytest tools/stm32-monitor/tests/test_analysis_service.py tools/stm32-monitor/tests/test_annotation_service.py tools/stm32-monitor/tests/test_service.py tools/stm32-monitor/tests/test_auth.py -q -p no:cacheprovider
py -3.12 tools/release/run_0600_gates.py dev-coverage --task-id STM32TK-0603-T06 --evidence-root C:\tmp\stm32tk-0603-t06-coverage -- tools/stm32-monitor/tests/test_analysis_service.py tools/stm32-monitor/tests/test_annotation_service.py tools/stm32-monitor/tests/test_service.py tools/stm32-monitor/tests/test_auth.py --cov=stm32_monitor.protocol --cov=stm32_monitor.service -q -p no:cacheprovider
```

- [ ] Commit:

```powershell
git add tools/stm32-monitor/src/stm32_monitor/protocol.py tools/stm32-monitor/src/stm32_monitor/service.py tools/stm32-monitor/tests/test_analysis_service.py tools/stm32-monitor/tests/test_annotation_service.py tools/stm32-monitor/tests/test_service.py tools/stm32-monitor/tests/test_auth.py
git commit -m "feat(STM32TK-0603): serve bounded monitor analytics"
```

## Task 7: Build deterministic AI analysis bundles and Toolkit bridge

**Files:**

- Create: `tools/stm32-monitor/src/stm32_monitor/analysis/bundle.py`
- Modify: `tools/stm32-monitor/src/stm32_monitor/exports.py`
- Create: `tools/stm32-toolkit/src/stm32_toolkit/monitor_analysis.py`
- Create: `tools/stm32-monitor/tests/test_analysis_bundle.py`
- Create: `tools/stm32-toolkit/tests/test_monitor_analysis.py`

- [ ] Write failing bundle tests for explicit selection/minimal scope, deterministic bytes,
  an explicit canonical UTC creation time as the only serialization clock, identical bytes for
  identical canonical input plus creation time, identities/request/compatibility/counts/stats/
  quality/markers/revisions/evidence/schema versions, fixed CSV/ZIP, formula injection, inventory
  hashes, corrupt links, case-fold collisions, unsafe entry names, excessive output, secret/path/
  source/raw-memory/unselected-data exclusion, and no upload/share action.

- [ ] Write failing bridge tests for the exact OBSERVE operations `monitor_analysis_list_runs`,
  `monitor_analysis_compare`, `monitor_analysis_quality`, `monitor_analysis_read_annotations`,
  `monitor_analysis_read_markers`, and `monitor_analysis_create_bundle`, using a real local fake
  Monitor server. Cover exact loopback origin, token header not URL, closed response schemas,
  timeout/size/error, typed workspace-scoped artifact reference plus bytes/SHA-256, unavailable
  service, workspace isolation, and proof no Monitor database/evidence file is opened.

- [ ] Run RED:

```powershell
py -3.12 -m pytest tools/stm32-monitor/tests/test_analysis_bundle.py tools/stm32-toolkit/tests/test_monitor_analysis.py -q -p no:cacheprovider
```

- [ ] Implement server-side deterministic bundle creation plus Toolkit OBSERVE bridge methods.
  Reuse safe export primitives but do not change existing 0.5 export semantics/thresholds.

- [ ] Run GREEN on 3.10/3.12 with coverage and existing export regressions:

```powershell
py -3.10 -m pytest tools/stm32-monitor/tests/test_analysis_bundle.py tools/stm32-monitor/tests/test_exports.py tools/stm32-toolkit/tests/test_monitor_analysis.py -q -p no:cacheprovider
py -3.12 tools/release/run_0600_gates.py dev-coverage --task-id STM32TK-0603-T07 --evidence-root C:\tmp\stm32tk-0603-t07-coverage -- tools/stm32-monitor/tests/test_analysis_bundle.py tools/stm32-monitor/tests/test_exports.py tools/stm32-toolkit/tests/test_monitor_analysis.py --cov=stm32_monitor.analysis.bundle --cov=stm32_monitor.exports --cov=stm32_toolkit.monitor_analysis -q -p no:cacheprovider
```

- [ ] Commit:

```powershell
git add tools/stm32-monitor/src/stm32_monitor/analysis/bundle.py tools/stm32-monitor/src/stm32_monitor/exports.py tools/stm32-toolkit/src/stm32_toolkit/monitor_analysis.py tools/stm32-monitor/tests/test_analysis_bundle.py tools/stm32-toolkit/tests/test_monitor_analysis.py
git commit -m "feat(STM32TK-0603): create explicit monitor analysis bundles"
```

## Task 8: Add typed frontend analysis state and API client

**Files:**

- Create: `tools/stm32-monitor/ui/src/analysis/model.ts`
- Create: `tools/stm32-monitor/ui/src/analysis/selectors.ts`
- Create: `tools/stm32-monitor/ui/src/analysis/alignment.ts`
- Create: `tools/stm32-monitor/ui/src/analysis/quality.ts`
- Create: `tools/stm32-monitor/ui/src/analysis/bundle.ts`
- Modify: `tools/stm32-monitor/ui/src/api/contract.ts`
- Modify: `tools/stm32-monitor/ui/src/api/client.ts`
- Modify: `tools/stm32-monitor/ui/src/api/wire.ts`
- Modify: `tools/stm32-monitor/ui/src/state/model.ts`
- Modify: `tools/stm32-monitor/ui/src/state/reducer.ts`
- Modify: `tools/stm32-monitor/ui/src/state/selectors.ts`
- Create: `tools/stm32-monitor/ui/tests/analysis-contract.test.ts`
- Create: `tools/stm32-monitor/ui/tests/analysis-state.test.ts`

- [ ] Write failing decoder tests for exact schemas, limits, unknown/missing/wrong/non-finite
  fields, required-minimum limit errors, series-level no-valid results, resolution-identity
  differences, fresh results, and all error responses. Write reducer tests for selection bounds,
  compatibility visibility, request revision, stale response rejection, invalidation coalescing,
  reconnect, closing-state release, and no duplicated raw sample arrays.

- [ ] Run RED:

```powershell
Push-Location tools/stm32-monitor/ui
npm.cmd run test -- tests/analysis-contract.test.ts tests/analysis-state.test.ts
Pop-Location
```

- [ ] Implement closed TypeScript types/decoders, API calls, and bounded reducer/selectors.

- [ ] Run GREEN with typecheck/lint and changed-file branch coverage:

```powershell
Push-Location tools/stm32-monitor/ui
npm.cmd run typecheck
npm.cmd run lint
npm.cmd run test:coverage -- tests/analysis-contract.test.ts tests/analysis-state.test.ts
npm.cmd run coverage:check
Pop-Location
```

Expected: tests pass and each changed product TypeScript file reaches at least 90% branch coverage.

- [ ] Commit:

```powershell
git add -- tools/stm32-monitor/ui/src/analysis/model.ts tools/stm32-monitor/ui/src/analysis/selectors.ts tools/stm32-monitor/ui/src/analysis/alignment.ts tools/stm32-monitor/ui/src/analysis/quality.ts tools/stm32-monitor/ui/src/analysis/bundle.ts tools/stm32-monitor/ui/src/api/contract.ts tools/stm32-monitor/ui/src/api/client.ts tools/stm32-monitor/ui/src/api/wire.ts tools/stm32-monitor/ui/src/state/model.ts tools/stm32-monitor/ui/src/state/reducer.ts tools/stm32-monitor/ui/src/state/selectors.ts tools/stm32-monitor/ui/tests/analysis-contract.test.ts tools/stm32-monitor/ui/tests/analysis-state.test.ts
git commit -m "feat(STM32TK-0603): model bounded analytics in the UI"
```

## Task 9: Implement comparison and quality UI

**Files:**

- Create: `tools/stm32-monitor/ui/src/components/RunComparison.tsx`
- Create: `tools/stm32-monitor/ui/src/components/QualityPanel.tsx`
- Modify: `tools/stm32-monitor/ui/src/components/HistoryPanel.tsx`
- Modify: `tools/stm32-monitor/ui/src/app.tsx`
- Modify: `tools/stm32-monitor/ui/src/styles.css`
- Create: `tools/stm32-monitor/ui/tests/run-comparison.test.tsx`
- Create: `tools/stm32-monitor/ui/tests/quality-panel.test.tsx`

- [ ] Write failing component tests for 2--8 runs/1--16 selectors/0--8 groups, compatibility before
  submit, all three alignments, directed baseline/candidate differences, pointer brush producing a
  bounded canonical time window, keyboard start/end equivalent, explicit interval-anchor start/end,
  visible logical/resolution identity differences,
  redundant color/dash/label/table, raw/eligible/returned counts, quality distributions/gaps/
  stages/halt impact, no-valid/error/loading states, bounded rerender, keyboard control, focus,
  live notices, and text-only values.

- [ ] Run RED:

```powershell
Push-Location tools/stm32-monitor/ui
npm.cmd run test -- tests/run-comparison.test.tsx tests/quality-panel.test.tsx
Pop-Location
```

- [ ] Implement the components using existing chart adapters and bounded API results. Ensure the
  accessible table contains the same run/selector/point/quality identity as the chart.

- [ ] Run GREEN with typecheck/lint/coverage/a11y unit gates:

```powershell
Push-Location tools/stm32-monitor/ui
npm.cmd run typecheck
npm.cmd run lint
npm.cmd run test:coverage -- tests/run-comparison.test.tsx tests/quality-panel.test.tsx
npm.cmd run coverage:check
npm.cmd run test:a11y
Pop-Location
```

- [ ] Commit:

```powershell
git add -- tools/stm32-monitor/ui/src/components/RunComparison.tsx tools/stm32-monitor/ui/src/components/QualityPanel.tsx tools/stm32-monitor/ui/src/components/HistoryPanel.tsx tools/stm32-monitor/ui/src/app.tsx tools/stm32-monitor/ui/src/styles.css tools/stm32-monitor/ui/tests/run-comparison.test.tsx tools/stm32-monitor/ui/tests/quality-panel.test.tsx
git commit -m "feat(STM32TK-0603): render cross-run quality analytics"
```

## Task 10: Implement annotation and explicit bundle UI

**Files:**

- Create: `tools/stm32-monitor/ui/src/components/AnnotationPanel.tsx`
- Create: `tools/stm32-monitor/ui/src/components/AnalysisExport.tsx`
- Modify: `tools/stm32-monitor/ui/src/app.tsx`
- Modify: `tools/stm32-monitor/ui/src/styles.css`
- Create: `tools/stm32-monitor/ui/tests/annotation-panel.test.tsx`
- Create: `tools/stm32-monitor/ui/tests/analysis-export.test.tsx`

- [ ] Write failing tests for note/bookmark/diagnostic marker create/edit/tombstone, exact anchors,
  validation/limits, explicit `expectedRevision` for edit/tombstone, revision conflicts, text-only
  malicious content, evidence link states, dialog focus trap/restoration, explicit export selection/
  summary/confirmation, frozen canonical creation UTC, minimal typed result reference, cancellation,
  and absence of send/share/upload/automatic creation.

- [ ] Run RED, implement the two components, then run type/lint/unit/coverage/a11y GREEN:

```powershell
Push-Location tools/stm32-monitor/ui
npm.cmd run test -- tests/annotation-panel.test.tsx tests/analysis-export.test.tsx
npm.cmd run typecheck
npm.cmd run lint
npm.cmd run test:coverage -- tests/annotation-panel.test.tsx tests/analysis-export.test.tsx
npm.cmd run coverage:check
npm.cmd run test:a11y
Pop-Location
```

- [ ] Commit:

```powershell
git add tools/stm32-monitor/ui/src/components/AnnotationPanel.tsx tools/stm32-monitor/ui/src/components/AnalysisExport.tsx tools/stm32-monitor/ui/src/app.tsx tools/stm32-monitor/ui/src/styles.css tools/stm32-monitor/ui/tests/annotation-panel.test.tsx tools/stm32-monitor/ui/tests/analysis-export.test.tsx
git commit -m "feat(STM32TK-0603): annotate and export monitor analysis"
```

## Task 11: Calibrate analytics and close browser acceptance

**Files:**

- Create: `tools/stm32-monitor/ui/e2e/analysis.spec.ts`
- Create: `tools/stm32-monitor/ui/e2e/analysis-security.spec.ts`
- Create: `tools/stm32-monitor/ui/e2e/analysis-accessibility.spec.ts`
- Create: `tools/stm32-monitor/ui/e2e/analysis-isolation.spec.ts`
- Modify: `tools/stm32-monitor/ui/e2e/performance.spec.ts`
- Modify: `tools/stm32-monitor/ui/e2e/fake_runtime.py`
- Modify: `tools/stm32-monitor/ui/playwright.config.ts`
- Create: `tools/stm32-monitor/tests/test_analysis_performance.py`
- Modify: `tools/release/performance_0600.json`
- Modify: `tools/stm32-monitor/src/stm32_monitor/analysis/query.py`
- Modify: `tools/stm32-monitor/src/stm32_monitor/analysis/quality.py`
- Modify: `tools/stm32-monitor/src/stm32_monitor/analysis/decimation.py`
- Modify: `tools/stm32-monitor/tests/test_analysis_query.py`
- Modify: `tools/stm32-monitor/tests/test_analysis_quality.py`
- Modify: `tools/stm32-monitor/tests/test_analysis_decimation.py`
- Create: `tools/stm32-monitor/ui/tests/analysis-performance.test.ts`
- Modify: `tools/stm32-monitor/ui/src/analysis/selectors.ts`
- Modify: `tools/stm32-monitor/ui/src/state/reducer.ts`
- Modify: `tools/stm32-monitor/ui/src/components/RunComparison.tsx`
- Modify: `tools/stm32-monitor/src/stm32_monitor/ui_dist`

- [ ] Add real HTTP/WebSocket functional flows: connect, select compatible/incompatible runs,
  compare in all alignment modes, select a directed diff, brush then keyboard-edit its bounded
  window, inspect table/stats/quality/stages/markers, add/edit/tombstone annotation, create explicit
  bundle, reconnect/invalidate, and verify persisted results.

- [ ] Add exact security assertions for DOM text/outerHTML/all attributes/form values, URL,
  console, cookie, local/session storage, IndexedDB names, exact headers/CSP, CSV/ZIP-safe export,
  and a real random-port second-origin sentinel whose request count remains zero.

- [ ] Add keyboard-only 1280×720 and 1024×768 at 200% flows through connect→compare→quality→
  note→export, reduced motion, focus behavior, chart table, no two-axis page scroll, and axe zero
  critical/serious violations.

- [ ] Add two simultaneous workspace services and prove no run/group/selector/annotation/
  diagnostic/evidence/bundle ID crosses either HTTP, WebSocket, UI, cache, or export boundary.

- [ ] Set Playwright `retries: 0`; list Python, Vitest, and Playwright nodes to validate that every
  new test is discoverable. Complete final node collection and catalog/impact-map freeze occurs in
  Task 13, after Task 12 has made the last packaging/version test changes.

- [ ] Capture Vitest `4.1.10` and Playwright `1.56.1` native JSON from the real frozen commands,
  sanitize only verified repository/evidence-root fields, and run the one shared native-output
  adapter contract. Cross-check exit code, declared summary, and every required node outcome;
  reject hand-written simplified fixtures, unknown depended-on fields, absolute/private paths,
  credentials, retries, partial JSON, and contradictory status/counts.

- [ ] Add a correctness-first Python workload for exactly 640,000 post-expansion scalar
  observations, no more than 64,000 plotted points, and eight directed difference pairs. Use the
  0600 performance helper's frozen three-batch calculation and record every batch sample/MAD.
  Extend the accepted 0.5 continuous five-minute browser fixture without changing its warmup or
  measurement windows; freeze an interaction every five seconds in the order compare→quality→
  marker→table, repeating for the complete measurement window.

```powershell
py -3.10 tools/release/run_0600_gates.py performance --module STM32TK-0603 --test-file tools/stm32-monitor/tests/test_analysis_performance.py --mode calibrate --output C:\tmp\stm32tk-0603-perf-310.json
py -3.12 tools/release/run_0600_gates.py performance --module STM32TK-0603 --test-file tools/stm32-monitor/tests/test_analysis_performance.py --mode calibrate --output C:\tmp\stm32tk-0603-perf-312.json
Push-Location tools/stm32-monitor/ui
try {
  npm.cmd run typecheck:e2e
  if ($LASTEXITCODE -ne 0) { throw 'typecheck:e2e failed' }
  .\node_modules\.bin\playwright.cmd test --list
  if ($LASTEXITCODE -ne 0) { throw 'Playwright node listing failed' }
  $env:STM32TK_PERFORMANCE_MODE='calibrate'
  $env:STM32TK_PERFORMANCE_OUTPUT='C:\tmp\stm32tk-0603-browser-perf.json'
  npm.cmd run test:e2e:performance
  if ($LASTEXITCODE -ne 0) { throw 'browser performance calibration failed' }
} finally {
  Remove-Item Env:STM32TK_PERFORMANCE_MODE -ErrorAction SilentlyContinue
  Remove-Item Env:STM32TK_PERFORMANCE_OUTPUT -ErrorAction SilentlyContinue
  Pop-Location
}
py -3.12 tools/release/verify_0600_release.py performance-calibration --profile STM32TK-0603 --input C:\tmp\stm32tk-0603-perf-310.json --input C:\tmp\stm32tk-0603-perf-312.json --input C:\tmp\stm32tk-0603-browser-perf.json --output tools/release/performance_0600.json
```

Expected: comparison, quality, and browser-design maxima are not exceeded; batch p95/MAD,
environment, workload, continuous-window, cadence, and <=15% limits verify.

- [ ] Require the calibration verifier to update `performance_0600.json` atomically only when all
  calculated thresholds are within their predeclared maxima; a failure leaves the tracked file
  byte-identical and requires implementation improvement without workload/maximum changes plus a
  repeated characterization.

- [ ] Commit accepted calibrated performance entries, exact performance/browser tests, and
  zero-retry configuration before any optional post-baseline analytics optimization:

```powershell
git add -- tools/release/performance_0600.json tools/stm32-monitor/tests/test_analysis_performance.py tools/stm32-monitor/ui/playwright.config.ts tools/stm32-monitor/ui/tests/analysis-performance.test.ts tools/stm32-monitor/ui/e2e/analysis.spec.ts tools/stm32-monitor/ui/e2e/analysis-security.spec.ts tools/stm32-monitor/ui/e2e/analysis-accessibility.spec.ts tools/stm32-monitor/ui/e2e/analysis-isolation.spec.ts tools/stm32-monitor/ui/e2e/performance.spec.ts tools/stm32-monitor/ui/e2e/fake_runtime.py
git commit -m "test(STM32TK-0603): freeze analytics performance and browser tests"
```

- [ ] Profile the correct reference and add only necessary bounded Python/TypeScript optimizations
  with statistics/quality/decimation/state/concurrency regressions. Record CPU, memory, NVMe, OS,
  power, antivirus, Python/Node/browser, GC, serialized bytes, database size, heap, queue, and long
  tasks. Do not change maxima, baselines, workloads, or thresholds after a failure.

- [ ] Re-run the frozen workload in verify mode on both supported Pythons before browser gates:

```powershell
py -3.10 tools/release/run_0600_gates.py performance --module STM32TK-0603 --test-file tools/stm32-monitor/tests/test_analysis_performance.py --mode verify --performance-config tools/release/performance_0600.json --output C:\tmp\stm32tk-0603-perf-verify-310.json
py -3.12 tools/release/run_0600_gates.py performance --module STM32TK-0603 --test-file tools/stm32-monitor/tests/test_analysis_performance.py --mode verify --performance-config tools/release/performance_0600.json --output C:\tmp\stm32tk-0603-perf-verify-312.json
```

Expected: every design maximum, accepted absolute threshold, and <=15% per-Python regression limit
passes without changing workload, calibration, or threshold data.

- [ ] If and only if profiling produced Python product/test edits, run per-file branch coverage;
  otherwise record “no Python optimization required” externally:

```powershell
py -3.12 tools/release/run_0600_gates.py dev-coverage --task-id STM32TK-0603-T11 --evidence-root C:\tmp\stm32tk-0603-t11-coverage -- tools/stm32-monitor/tests/test_analysis_query.py tools/stm32-monitor/tests/test_analysis_quality.py tools/stm32-monitor/tests/test_analysis_decimation.py --cov=stm32_monitor.analysis.query --cov=stm32_monitor.analysis.quality --cov=stm32_monitor.analysis.decimation -q -p no:cacheprovider
```

- [ ] Run all Node/browser gates and retain screenshots, traces, axe JSON, performance JSON, and
  sentinel counts outside the worktree:

```powershell
Push-Location tools/stm32-monitor/ui
try {
  $scripts=@('typecheck','typecheck:e2e','lint','test:coverage','coverage:check','build','verify:dist','test:e2e:windows','test:e2e:performance')
  foreach($script in $scripts) {
    npm.cmd run $script
    if ($LASTEXITCODE -ne 0) { throw "npm script failed: $script" }
  }
} finally {
  Pop-Location
}
```

Expected: all local Chromium flows pass at both viewports; calibrated thresholds and security/
accessibility/isolation pass; product frameworks report zero hidden retries. No Linux,
Firefox, or WebKit evidence belongs to 0603.

- [ ] Commit:

```powershell
git add -- tools/stm32-monitor/src/stm32_monitor/analysis/query.py tools/stm32-monitor/src/stm32_monitor/analysis/quality.py tools/stm32-monitor/src/stm32_monitor/analysis/decimation.py tools/stm32-monitor/tests/test_analysis_query.py tools/stm32-monitor/tests/test_analysis_quality.py tools/stm32-monitor/tests/test_analysis_decimation.py tools/stm32-monitor/ui/src/analysis/selectors.ts tools/stm32-monitor/ui/src/state/reducer.ts tools/stm32-monitor/ui/src/components/RunComparison.tsx tools/stm32-monitor/ui/tests/analysis-performance.test.ts tools/stm32-monitor/src/stm32_monitor/ui_dist
git commit -m "test(STM32TK-0603): build analytics browser artifacts"
```

## Task 12: Update versions, packages, Skills, and documentation

**Files:**

- Modify: `tools/stm32-toolkit/pyproject.toml`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/__init__.py`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/cli.py`
- Modify: `tools/stm32-monitor/pyproject.toml`
- Modify: `tools/stm32-monitor/src/stm32_monitor/__init__.py`
- Modify: `tools/stm32-monitor/src/stm32_monitor/protocol.py`
- Modify: `tools/stm32-monitor/src/stm32_monitor/runtime.py`
- Modify: `tools/stm32-monitor/ui/package.json`
- Modify: `tools/stm32-monitor/ui/package-lock.json`
- Modify: `tools/stm32-monitor/ui/e2e/fake_runtime.py`
- Modify: `tools/stm32-monitor/ui/tests/bootstrap.test.ts`
- Modify: `tools/stm32-monitor/ui/tests/main.test.tsx`
- Modify: `.claude-plugin/plugin.json`
- Modify: `bin/setup-stm32-env.ps1`
- Modify: `bin/stm32-toolkit-mcp.cmd`
- Modify: `bin/stm32-monitor.cmd`
- Modify: `skills/setup-stm32-env/SKILL.md`
- Modify: `skills/stm32-monitor/SKILL.md`
- Modify: `README.md`
- Modify: `README_zh-CN.md`
- Create: `tools/stm32-monitor/README.md`
- Modify: `tools/stm32-toolkit/README.md`
- Modify: `tools/stm32-toolkit/tests/test_build_runner.py`
- Modify: `tools/stm32-toolkit/tests/test_cli.py`
- Modify: `tools/stm32-toolkit/tests/test_hardware_workflows.py`
- Modify: `tools/stm32-toolkit/tests/test_migration_plan.py`
- Modify: `tools/stm32-toolkit/tests/test_mcp_migration_build.py`
- Modify: `tools/stm32-toolkit/tests/test_probe_protocol.py`
- Modify: `tools/stm32-toolkit/tests/test_setup_runtime.py`
- Modify: `tools/stm32-toolkit/tests/test_plugin_layout.py`
- Modify: `tools/stm32-monitor/tests/test_cli.py`
- Modify: `tools/stm32-monitor/tests/test_exports.py`
- Modify: `tools/stm32-monitor/tests/test_models.py`
- Modify: `tools/stm32-monitor/tests/test_package_boundary.py`
- Modify: `tools/stm32-monitor/tests/test_runtime.py`
- Modify: `tools/stm32-monitor/tests/test_service.py`
- Modify: `tools/stm32-monitor/tests/test_ui_dist.py`

- [ ] Write failing version/inventory tests requiring `0.6.0` across Toolkit, Monitor, UI, plugin,
  CLI/MCP and active Skills; exact packaged schemas/UI dist; offline wheels; managed launcher;
  no unexpected files; accepted 0.5 history read after the non-destructive structure upgrade; and
  no model/cloud/API-key/browser AI/automatic annotation.
  Replace assertions that represent the current product version, while retaining deliberately
  named 0.5 backward-compatibility fixtures and the historical 0502 controller/verifier tests.

- [ ] Update all version surfaces atomically, align Monitor's exact Toolkit dependency to 0.6.0,
  update the thin Skill, and document limits/compatibility/quality/annotations/bundle consent and
  non-goals only after evidence exists.

- [ ] Run the changed version/package/inventory tests under both Pythons, targeted Node tests,
  build/dist verification, offline wheel/install smoke owned by those tests, and deterministic
  offline dependency audit. Prior tasks own feature correctness/coverage/performance; Task 13
  candidate owns the complete affected regression. Tests whose historical filename contains
  `hardware` or `probe` remain software-only fixture/protocol tests in this task; they must not
  connect to, reset, flash, or modify a real target.

```powershell
py -3.10 -m pytest tools/stm32-toolkit/tests/test_build_runner.py tools/stm32-toolkit/tests/test_cli.py tools/stm32-toolkit/tests/test_hardware_workflows.py tools/stm32-toolkit/tests/test_migration_plan.py tools/stm32-toolkit/tests/test_mcp_migration_build.py tools/stm32-toolkit/tests/test_probe_protocol.py tools/stm32-toolkit/tests/test_setup_runtime.py tools/stm32-toolkit/tests/test_plugin_layout.py tools/stm32-monitor/tests/test_cli.py tools/stm32-monitor/tests/test_exports.py tools/stm32-monitor/tests/test_models.py tools/stm32-monitor/tests/test_package_boundary.py tools/stm32-monitor/tests/test_runtime.py tools/stm32-monitor/tests/test_service.py tools/stm32-monitor/tests/test_ui_dist.py -q -p no:cacheprovider --basetemp C:\tmp\stm32tk-0603-package-310
py -3.12 tools/release/run_0600_gates.py dev-coverage --task-id STM32TK-0603-T12 --evidence-root C:\tmp\stm32tk-0603-t12-coverage -- tools/stm32-toolkit/tests/test_build_runner.py tools/stm32-toolkit/tests/test_cli.py tools/stm32-toolkit/tests/test_hardware_workflows.py tools/stm32-toolkit/tests/test_migration_plan.py tools/stm32-toolkit/tests/test_mcp_migration_build.py tools/stm32-toolkit/tests/test_probe_protocol.py tools/stm32-toolkit/tests/test_setup_runtime.py tools/stm32-toolkit/tests/test_plugin_layout.py tools/stm32-monitor/tests/test_cli.py tools/stm32-monitor/tests/test_exports.py tools/stm32-monitor/tests/test_models.py tools/stm32-monitor/tests/test_package_boundary.py tools/stm32-monitor/tests/test_runtime.py tools/stm32-monitor/tests/test_service.py tools/stm32-monitor/tests/test_ui_dist.py --cov=stm32_toolkit --cov=stm32_monitor -q -p no:cacheprovider --basetemp C:\tmp\stm32tk-0603-package-312
Push-Location tools/stm32-monitor/ui
try {
  npm.cmd run typecheck
  if ($LASTEXITCODE -ne 0) { throw 'typecheck failed' }
  npm.cmd run test -- tests/bootstrap.test.ts tests/main.test.tsx
  if ($LASTEXITCODE -ne 0) { throw 'package UI tests failed' }
  npm.cmd run build
  if ($LASTEXITCODE -ne 0) { throw 'UI build failed' }
  npm.cmd run verify:dist
  if ($LASTEXITCODE -ne 0) { throw 'UI dist verification failed' }
} finally {
  Pop-Location
}
py -3.12 tools/release/verify_0600_release.py dependency-audit --ui-root tools/stm32-monitor/ui --catalog tools/release/gates_0600.json --support-profile C:\tmp\stm32tk-0600-support\feasibility\profile.json --evidence C:\tmp\stm32tk-0603-audit
```

Expected: runtime dependencies have zero vulnerabilities at every severity; development dependencies
have zero high/critical vulnerabilities; advisory/cache digests match the immutable support profile;
only pre-candidate, user-approved, unexpired catalog exceptions are accepted.

- [ ] Commit:

```powershell
git add -- bin/setup-stm32-env.ps1 bin/stm32-toolkit-mcp.cmd bin/stm32-monitor.cmd .claude-plugin/plugin.json README.md README_zh-CN.md skills/setup-stm32-env/SKILL.md skills/stm32-monitor/SKILL.md tools/stm32-toolkit/pyproject.toml tools/stm32-toolkit/src/stm32_toolkit/__init__.py tools/stm32-toolkit/src/stm32_toolkit/cli.py tools/stm32-toolkit/tests/test_build_runner.py tools/stm32-toolkit/tests/test_cli.py tools/stm32-toolkit/tests/test_hardware_workflows.py tools/stm32-toolkit/tests/test_migration_plan.py tools/stm32-toolkit/tests/test_mcp_migration_build.py tools/stm32-toolkit/tests/test_probe_protocol.py tools/stm32-toolkit/tests/test_setup_runtime.py tools/stm32-toolkit/tests/test_plugin_layout.py tools/stm32-toolkit/README.md tools/stm32-monitor/pyproject.toml tools/stm32-monitor/src/stm32_monitor/__init__.py tools/stm32-monitor/src/stm32_monitor/protocol.py tools/stm32-monitor/src/stm32_monitor/runtime.py tools/stm32-monitor/tests/test_cli.py tools/stm32-monitor/tests/test_exports.py tools/stm32-monitor/tests/test_models.py tools/stm32-monitor/tests/test_package_boundary.py tools/stm32-monitor/tests/test_runtime.py tools/stm32-monitor/tests/test_service.py tools/stm32-monitor/tests/test_ui_dist.py tools/stm32-monitor/ui/package.json tools/stm32-monitor/ui/package-lock.json tools/stm32-monitor/ui/e2e/fake_runtime.py tools/stm32-monitor/ui/tests/bootstrap.test.ts tools/stm32-monitor/ui/tests/main.test.tsx tools/stm32-monitor/README.md
git commit -m "chore(STM32TK-0603): prepare version 0.6.0 surfaces"
```

## Task 13: Hand off the 0603 candidate CodeHead

**Files:**

- Modify: `tools/release/gates_0600.json`
- Modify: `tools/release/run_0600_candidate.ps1`
- Modify: `tools/release/verify_0600_release.py`
- Modify: `tools/release/path_contract_0600.ps1`
- Modify: `tools/stm32-toolkit/tests/release/test_gate_catalog_0600.py`
- Modify: `tools/stm32-toolkit/tests/release/test_gate_controller_0600.py`
- Modify: `tools/stm32-toolkit/tests/release/test_release_verifier_0600.py`

This task extends only the existing shared controller, verifier, catalog, path contract, and
native-output adapter. It must not create a 0603-specific controller, verifier, runtime,
scheduler, CI job, or evidence format.

- [ ] Audit the complete 0602 accepted-report-to-current diff, all tracked/untracked/committed/
  uncommitted/pushed/unpushed state, frozen 0601/0602 contracts, exact expected paths, package/dist
  inventories, dependency locks, version surfaces, Skills, docs, and source hashes.

- [ ] Collect the complete exact Windows Python/Vitest/Chromium Playwright/audit/install/integrity/
  artifact inventory after Task 12. Fill only reserved 0603 slots, freeze the final impact map, and add
  catalog/controller mutations proving the 0603 matrix contains exactly one Windows software
  shard and rejects Linux/hardware/import requirements, while 0601/0602 entries remain
  byte-identical. Prove every required node executes once, Playwright retries are zero, and
  missing/extra/duplicate/renamed/deselected/skip/xfail nodes fail. Add contract tests proving the
  wrapper alone creates the unique `<candidateRoot>/candidate-ledger.json`; the external
  `candidate-invocation-context.json` cannot substitute for it; context and digest sidecar are
  create-new canonical bytes, every new process checks the byte digest before parsing and then
  enforces the exact closed schema, and a changed HEAD/origin/clean state fails before use. Freeze
  the PowerShell 5.1 canonical-absolute-path helper with accept/reject contract cases, require all
  repository executables/configurations to be re-derived from the verified worktree, reject a
  changed actual verifier digest, and prohibit execution of any path supplied by context. The exact nine-field canonical
  `RecoveryRecord`, `candidate-0603` run kind, canonical lowercase hyphenated UUID, and four-event enum are
  closed; the resume-only interface binds every original
  input; a second or mutated resume fails; and reconciliation reparses the wrapper ledger and
  rejects every field/path/run-ID/CodeHead/recovery mutation. Add verifier tests for the closed
  `final-release-inputs.json` and sidecar, complete artifact-kind inventory, bytes/SHA-256 checking,
  fixed SHAs, ancestry, report-only commits, create-new canonical output, post-write digest
  verification, deterministic ordering, and closed `governance` ownership/authorization fields.
  Run the path-helper contract under Windows PowerShell 5.1: accept canonical drive-absolute and
  UNC paths; reject empty, `C:foo`, `\foo`, forward slash, `.`/`..` segments, device prefixes,
  noncanonical aliases, and any input changed by `GetFullPath`. Assert the implementation does not
  reference a newer framework-only fully-qualified-path convenience API. Add mutations for
  `skip-worktree` and working bytes of the helper/controller/verifier/catalog/performance files;
  every stage must reject committed-blob inequality before SHA-256 or execution. Include the
  Windows PowerShell 5.1 trailing-separator regression: accept a drive root, reject a non-root path
  with a trailing separator, and prove the result is stable on repeated canonicalization. Add a
  TOCTOU mutation after the first blob validation/context creation but before each real invocation;
  initial/resume/reconcile/final generation/final verification must all reject it.
  Commit this last
  contract change before candidate:

```powershell
$frozenWorktree = [IO.Path]::GetFullPath((git rev-parse --show-toplevel).Trim())
$pathContract = Join-Path $frozenWorktree 'tools\release\path_contract_0600.ps1'
$gateCatalog = Join-Path $frozenWorktree 'tools\release\gates_0600.json'
$candidateController = Join-Path $frozenWorktree 'tools\release\run_0600_candidate.ps1'
$releaseVerifier = Join-Path $frozenWorktree 'tools\release\verify_0600_release.py'
$catalogTest = Join-Path $frozenWorktree 'tools\stm32-toolkit\tests\release\test_gate_catalog_0600.py'
$controllerTest = Join-Path $frozenWorktree 'tools\stm32-toolkit\tests\release\test_gate_controller_0600.py'
$verifierTest = Join-Path $frozenWorktree 'tools\stm32-toolkit\tests\release\test_release_verifier_0600.py'
& py -3.12 -m pytest $catalogTest $controllerTest $verifierTest -q -p no:cacheprovider
if ($LASTEXITCODE -ne 0) { throw '0603 release contract tests failed' }
git -C $frozenWorktree add -- $gateCatalog $candidateController $releaseVerifier $pathContract $catalogTest $controllerTest $verifierTest
if ($LASTEXITCODE -ne 0) { throw 'staging frozen candidate contract failed' }
git -C $frozenWorktree commit -m "test(STM32TK-0603): freeze final candidate inventory"
if ($LASTEXITCODE -ne 0) { throw 'candidate inventory commit failed' }
```

- [ ] In one PowerShell session, resolve the frozen 0603 worktree and every repository-owned script,
  catalog, and configuration path absolutely from it. Validate Git HEAD, generate one lowercase
  GUID run ID, derive all runtime paths, and write only the untrusted external orchestration file
  `candidate-invocation-context.json` plus its digest sidecar, both create-new. Do not create the wrapper ledger. Run the initial Windows
  candidate with the complete frozen inputs. This fenced block is self-contained: before defining
  its local SHA-256/create-new writers, it validates HEAD/origin/clean state and committed working
  bytes, then dot-sources only the verified path-contract helper. The wrapper must create the unique ledger before any
  product child starts:

```powershell
$bootstrapWorktree = [IO.Path]::GetFullPath((git rev-parse --show-toplevel).Trim())
if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $bootstrapWorktree -PathType Container)) {
  throw 'cannot resolve repository root'
}
$gitCodeHead = (git -C $bootstrapWorktree rev-parse --verify HEAD).Trim().ToLowerInvariant()
if ($LASTEXITCODE -ne 0 -or $gitCodeHead -cnotmatch '^[0-9a-f]{40}$') {
  throw 'Git HEAD is not one full lowercase 40-hex commit SHA'
}
$bootstrapStatus = @(git -C $bootstrapWorktree status --porcelain=v1 --untracked-files=all)
if ($LASTEXITCODE -ne 0 -or $bootstrapStatus.Count -ne 0) {
  throw 'candidate requires a clean worktree'
}
$originUrl = (git -C $bootstrapWorktree remote get-url origin).Trim()
if ($LASTEXITCODE -ne 0 -or $originUrl -cne 'https://github.com/XiaoyaoLinghao/stm32-toolkit.git') {
  throw 'frozen worktree origin URL is wrong'
}
$fixedInputs = [ordered]@{ path_contract='tools/release/path_contract_0600.ps1'; controller='tools/release/run_0600_candidate.ps1'; verifier='tools/release/verify_0600_release.py'; catalog='tools/release/gates_0600.json'; performance='tools/release/performance_0600.json' }
$verifiedInputs = [ordered]@{}
$verifiedBlobs = [ordered]@{}
foreach ($entry in $fixedInputs.GetEnumerator()) {
  $absolute = [IO.Path]::GetFullPath((Join-Path $bootstrapWorktree ($entry.Value -replace '/', '\')))
  $committedBlob = (git -C $bootstrapWorktree rev-parse "$gitCodeHead`:$($entry.Value)").Trim().ToLowerInvariant()
  if ($LASTEXITCODE -ne 0 -or $committedBlob -cnotmatch '^[0-9a-f]{40}$') { throw "missing committed $($entry.Key) blob" }
  $workingBlob = (git -C $bootstrapWorktree hash-object -- $absolute).Trim().ToLowerInvariant()
  if ($LASTEXITCODE -ne 0 -or $workingBlob -cne $committedBlob) { throw "working $($entry.Key) bytes differ from committed HEAD" }
  $verifiedInputs[$entry.Key] = $absolute
  $verifiedBlobs[$entry.Key] = $committedBlob
}
. $verifiedInputs.path_contract
$frozenWorktree = ConvertTo-CanonicalAbsolutePath -Path $bootstrapWorktree -Name 'frozen_worktree'
if ($frozenWorktree -cne $bootstrapWorktree) { throw 'bootstrap worktree is noncanonical' }
function Get-LowerSha256([string]$Path) { $s=[IO.File]::OpenRead($Path); try{return ([Security.Cryptography.SHA256]::Create().ComputeHash($s)|ForEach-Object ToString x2)-join''}finally{$s.Dispose()} }
function Write-CreateNewUtf8([string]$Path,[string]$Text) { $bytes=[Text.UTF8Encoding]::new($false).GetBytes($Text); $s=[IO.File]::Open($Path,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None); try{$s.Write($bytes,0,$bytes.Length)}finally{$s.Dispose()} }

$candidateRunId = [Guid]::NewGuid().ToString('D').ToLowerInvariant()
$candidateRoot = Join-Path 'C:\tmp' ("stm32tk-0603-candidate-{0}" -f $candidateRunId)
$windowsEvidenceRoot = Join-Path $candidateRoot 'windows'
$wrapperLedgerPath = Join-Path $candidateRoot 'candidate-ledger.json'
$contextRoot = Join-Path 'C:\tmp' ("stm32tk-0603-candidate-context-{0}" -f $candidateRunId)
$invocationContextPath = Join-Path $contextRoot 'candidate-invocation-context.json'
$invocationContextDigestPath = "$invocationContextPath.sha256"
$candidateController = $verifiedInputs.controller
$releaseVerifier = $verifiedInputs.verifier
$catalog = $verifiedInputs.catalog
$performance = $verifiedInputs.performance
$supportProfile = 'C:\tmp\stm32tk-0600-support\feasibility\profile.json'
$canonicalPaths = [ordered]@{ frozen_worktree=$frozenWorktree; candidate_root=$candidateRoot; evidence_root=$windowsEvidenceRoot; support_profile=$supportProfile; wrapper_ledger=$wrapperLedgerPath }
foreach ($namedPath in $canonicalPaths.GetEnumerator()) {
  [void](ConvertTo-CanonicalAbsolutePath -Path ([string]$namedPath.Value) -Name ([string]$namedPath.Key))
}
foreach ($requiredPath in @($candidateController, $releaseVerifier, $catalog, $performance, $supportProfile)) {
  if (-not (Test-Path -LiteralPath $requiredPath -PathType Leaf)) {
    throw "missing frozen candidate input: $requiredPath"
  }
}
if ((Test-Path -LiteralPath $candidateRoot) -or (Test-Path -LiteralPath $contextRoot)) {
  throw 'candidate or invocation-context output already exists'
}
[void](New-Item -ItemType Directory -Path $contextRoot)
$context = [ordered]@{
  schema = 'stm32-candidate-invocation-context/1'
  module = 'STM32TK-0603'
  shard = 'windows'
  candidate_run_id = $candidateRunId
  code_head = $gitCodeHead
  frozen_worktree = $frozenWorktree
  origin_url = $originUrl
  candidate_root = $candidateRoot
  evidence_root = $windowsEvidenceRoot
  support_profile = $supportProfile
  wrapper_ledger = $wrapperLedgerPath
  catalog_sha256 = Get-LowerSha256 $catalog
  performance_sha256 = Get-LowerSha256 $performance
  support_profile_sha256 = Get-LowerSha256 $supportProfile
  controller_sha256 = Get-LowerSha256 $candidateController
  verifier_sha256 = Get-LowerSha256 $releaseVerifier
}
$contextJson = ($context | ConvertTo-Json -Compress) + "`n"
Write-CreateNewUtf8 $invocationContextPath $contextJson
Write-CreateNewUtf8 $invocationContextDigestPath ((Get-LowerSha256 $invocationContextPath) + "`n")
if ([IO.File]::ReadAllText($invocationContextDigestPath,[Text.UTF8Encoding]::new($false,$true)) -cne ((Get-LowerSha256 $invocationContextPath) + "`n")) { throw 'invocation context post-write verification failed' }
$env:STM32TK_0603_INVOCATION_CONTEXT = $invocationContextPath

foreach($name in $fixedInputs.Keys){$current=(git -C $frozenWorktree hash-object -- $verifiedInputs[$name]).Trim().ToLowerInvariant();if($LASTEXITCODE-ne 0-or $current-cne $verifiedBlobs[$name]){throw "TOCTOU working-byte change: $name"}}
if((Get-LowerSha256 $candidateController)-cne $context.controller_sha256-or(Get-LowerSha256 $releaseVerifier)-cne $context.verifier_sha256-or(Get-LowerSha256 $catalog)-cne $context.catalog_sha256-or(Get-LowerSha256 $performance)-cne $context.performance_sha256-or(Get-LowerSha256 $supportProfile)-cne $context.support_profile_sha256){throw 'fixed input SHA-256 changed before initial candidate'}
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $candidateController -Module 'STM32TK-0603' -Shard 'windows' -CandidateRunId $candidateRunId -EvidenceRoot $windowsEvidenceRoot -ExpectedCodeHead $gitCodeHead -Catalog $catalog -Performance $performance -SupportProfile $supportProfile
$initialCandidateExit = $LASTEXITCODE
if (-not (Test-Path -LiteralPath $wrapperLedgerPath -PathType Leaf)) {
  throw 'candidate wrapper did not create its authoritative ledger'
}
if ($initialCandidateExit -ne 0) {
  Write-Warning 'initial candidate did not PASS; classify the result before any resume'
}
```

- [ ] If and only if the initial wrapper ledger records one of the four recoverable events, a
  reviewer writes the closed canonical `RecoveryRecord` at the derived absolute path. Validate its
  exact fields against the freshly read wrapper ledger, then resume once using only the complete
  frozen resume interface; the wrapper ledger/checkpoint bind every original input:

```powershell
$bootstrapWorktree=[IO.Path]::GetFullPath((git rev-parse --show-toplevel).Trim()); $bootstrapHead=(git -C $bootstrapWorktree rev-parse --verify HEAD).Trim().ToLowerInvariant(); $bootstrapOrigin=(git -C $bootstrapWorktree remote get-url origin).Trim(); $bootstrapStatus=@(git -C $bootstrapWorktree status --porcelain=v1 --untracked-files=all)
if($LASTEXITCODE-ne 0-or $bootstrapHead-cnotmatch'^[0-9a-f]{40}$'-or $bootstrapOrigin-cne'https://github.com/XiaoyaoLinghao/stm32-toolkit.git'-or $bootstrapStatus.Count-ne 0){throw 'frozen worktree bootstrap failed'}
$fixedInputs=[ordered]@{path_contract='tools/release/path_contract_0600.ps1';controller='tools/release/run_0600_candidate.ps1';verifier='tools/release/verify_0600_release.py';catalog='tools/release/gates_0600.json';performance='tools/release/performance_0600.json'}; $verifiedInputs=[ordered]@{}; $verifiedBlobs=[ordered]@{}
foreach($entry in $fixedInputs.GetEnumerator()){$absolute=[IO.Path]::GetFullPath((Join-Path $bootstrapWorktree ($entry.Value-replace'/','\')));$committed=(git -C $bootstrapWorktree rev-parse "$bootstrapHead`:$($entry.Value)").Trim().ToLowerInvariant();if($LASTEXITCODE-ne 0-or $committed-cnotmatch'^[0-9a-f]{40}$'){throw "missing committed $($entry.Key) blob"};$working=(git -C $bootstrapWorktree hash-object -- $absolute).Trim().ToLowerInvariant();if($LASTEXITCODE-ne 0-or $working-cne $committed){throw "working $($entry.Key) bytes differ from committed HEAD"};$verifiedInputs[$entry.Key]=$absolute;$verifiedBlobs[$entry.Key]=$committed}
. $verifiedInputs.path_contract
if ((ConvertTo-CanonicalAbsolutePath -Path $bootstrapWorktree -Name 'frozen_worktree') -cne $bootstrapWorktree) { throw 'bootstrap worktree is noncanonical' }
function Get-LowerSha256([string]$Path) { $s=[IO.File]::OpenRead($Path); try { return ([Security.Cryptography.SHA256]::Create().ComputeHash($s) | ForEach-Object ToString x2) -join '' } finally { $s.Dispose() } }
function Read-VerifiedContext([string]$Path) {
  $Path = ConvertTo-CanonicalAbsolutePath -Path $Path -Name 'invocation context'
  $bytes=[IO.File]::ReadAllBytes($Path); $digestPath="$Path.sha256"
  $digest=[IO.File]::ReadAllText($digestPath,[Text.UTF8Encoding]::new($false,$true))
  if ($digest -cnotmatch '^[0-9a-f]{64}\n$' -or (Get-LowerSha256 $Path) -cne $digest.TrimEnd("`n")) { throw 'context byte digest mismatch' }
  if ($bytes.Length -lt 2 -or $bytes[0] -eq 0xef -or $bytes[$bytes.Length-1] -ne 10 -or $bytes[$bytes.Length-2] -eq 10) { throw 'context bytes are noncanonical' }
  $text=[Text.UTF8Encoding]::new($false,$true).GetString($bytes)
  $value=$text | ConvertFrom-Json
  $fields=@('schema','module','shard','candidate_run_id','code_head','frozen_worktree','origin_url','candidate_root','evidence_root','support_profile','wrapper_ledger','catalog_sha256','performance_sha256','support_profile_sha256','controller_sha256','verifier_sha256')
  if (Compare-Object ($fields|Sort-Object) (@($value.PSObject.Properties.Name)|Sort-Object)) { throw 'context fields are not exact' }
  if($value.schema-cne'stm32-candidate-invocation-context/1'-or$value.module-cne'STM32TK-0603'-or$value.shard-cne'windows'-or$value.candidate_run_id-cnotmatch'^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$'-or$value.code_head-cnotmatch'^[0-9a-f]{40}$'-or @($value.catalog_sha256,$value.performance_sha256,$value.support_profile_sha256,$value.controller_sha256,$value.verifier_sha256|Where-Object{$_-cnotmatch'^[0-9a-f]{64}$'}).Count-ne 0){throw 'context values are invalid'}
  $ordered=[ordered]@{}; foreach($field in $fields){$ordered[$field]=$value.$field}
  if ((($ordered|ConvertTo-Json -Compress)+"`n") -cne $text) { throw 'context JSON is not canonical' }
  return $value
}
$invocationContextPath = $env:STM32TK_0603_INVOCATION_CONTEXT
$context = Read-VerifiedContext $invocationContextPath
[void](ConvertTo-CanonicalAbsolutePath -Path ([string]$context.candidate_root) -Name 'candidate_root'); [void](ConvertTo-CanonicalAbsolutePath -Path ([string]$context.evidence_root) -Name 'evidence_root'); [void](ConvertTo-CanonicalAbsolutePath -Path ([string]$context.support_profile) -Name 'support_profile'); [void](ConvertTo-CanonicalAbsolutePath -Path ([string]$context.wrapper_ledger) -Name 'wrapper_ledger')
if($context.frozen_worktree-cne $bootstrapWorktree-or $context.code_head-cne $bootstrapHead-or $context.origin_url-cne $bootstrapOrigin){throw 'context worktree binding failed'}
$frozen=[ordered]@{controller=$verifiedInputs.controller;verifier=$verifiedInputs.verifier;catalog=$verifiedInputs.catalog;performance=$verifiedInputs.performance}
if((Get-LowerSha256 $frozen.controller)-cne $context.controller_sha256-or(Get-LowerSha256 $frozen.verifier)-cne $context.verifier_sha256-or(Get-LowerSha256 $frozen.catalog)-cne $context.catalog_sha256-or(Get-LowerSha256 $frozen.performance)-cne $context.performance_sha256){throw 're-derived frozen input digest mismatch'}
$wrapperLedgerPath = [string]$context.wrapper_ledger
$expectedLedgerPath = Join-Path (ConvertTo-CanonicalAbsolutePath -Path ([string]$context.candidate_root) -Name 'candidate_root') 'candidate-ledger.json'
if ((ConvertTo-CanonicalAbsolutePath -Path $wrapperLedgerPath -Name 'wrapper_ledger') -cne $expectedLedgerPath) { throw 'wrapper ledger path changed' }
$recoveryRecordPath = Join-Path ([string]$context.candidate_root) 'recovery-record.json'
$wrapperLedger = Get-Content -LiteralPath $wrapperLedgerPath -Raw | ConvertFrom-Json
$expectedLedgerFields = @('schema','module','candidate_run_id','expected_code_head','controller_path','candidate_root','evidence_root','catalog_sha256','performance_sha256','support_profile_sha256','checkpoint','state','created_at_utc','updated_at_utc')
if (Compare-Object ($expectedLedgerFields|Sort-Object) (@($wrapperLedger.PSObject.Properties.Name)|Sort-Object)) { throw 'wrapper ledger fields are not exact' }
if ((ConvertTo-CanonicalAbsolutePath -Path ([string]$wrapperLedger.controller_path) -Name 'ledger controller_path') -cne $frozen.controller -or $wrapperLedger.candidate_run_id -cne $context.candidate_run_id -or $wrapperLedger.expected_code_head -cne $context.code_head -or $wrapperLedger.candidate_root -cne $context.candidate_root -or $wrapperLedger.evidence_root -cne $context.evidence_root -or $wrapperLedger.catalog_sha256 -cne (Get-LowerSha256 $frozen.catalog) -or $wrapperLedger.performance_sha256 -cne (Get-LowerSha256 $frozen.performance) -or $wrapperLedger.support_profile_sha256 -cne (Get-LowerSha256 ([string]$context.support_profile))) { throw 'wrapper ledger binding changed' }
$recovery = Get-Content -LiteralPath $recoveryRecordPath -Raw | ConvertFrom-Json
$expectedRecoveryFields = @('classification','event','reviewer','recorded_at_utc','run_kind','run_id','code_head','checkpoint','interrupted_attempt_digest')
$actualRecoveryFields = @($recovery.PSObject.Properties.Name)
if (Compare-Object ($expectedRecoveryFields | Sort-Object) ($actualRecoveryFields | Sort-Object)) {
  throw 'RecoveryRecord fields are not exact'
}
$recoverableEvents = @('HOST_POWER_OR_REBOOT','RUNNER_LOSS_BEFORE_CHILD_RESULT','PHYSICAL_USB_OR_PROBE_REMOVAL','TARGET_POWER_LOSS')
if ($recovery.classification -cne 'RECOVERABLE_INFRA_ERROR' -or $recovery.event -cnotin $recoverableEvents) {
  throw 'RecoveryRecord classification or event is not recoverable'
}
if ($recovery.run_kind -cne 'candidate-0603' -or $recovery.run_id -cnotmatch '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$' -or $recovery.run_id -cne $context.candidate_run_id -or $recovery.code_head -cnotmatch '^[0-9a-f]{40}$' -or $recovery.code_head -cne $context.code_head) {
  throw 'RecoveryRecord run binding mismatch'
}
[void](ConvertTo-CanonicalAbsolutePath -Path ([string]$recovery.checkpoint) -Name 'recovery checkpoint')
if ($recovery.checkpoint -cne $wrapperLedger.checkpoint -or $recovery.interrupted_attempt_digest -cnotmatch '^[0-9a-f]{64}$') {
  throw 'RecoveryRecord checkpoint or interrupted-attempt digest is invalid'
}

foreach($name in $fixedInputs.Keys){$current=(git -C $bootstrapWorktree hash-object -- $verifiedInputs[$name]).Trim().ToLowerInvariant();if($LASTEXITCODE-ne 0-or $current-cne $verifiedBlobs[$name]){throw "TOCTOU working-byte change: $name"}}
if((Get-LowerSha256 $frozen.controller)-cne $context.controller_sha256-or(Get-LowerSha256 $frozen.verifier)-cne $context.verifier_sha256-or(Get-LowerSha256 $frozen.catalog)-cne $context.catalog_sha256-or(Get-LowerSha256 $frozen.performance)-cne $context.performance_sha256-or(Get-LowerSha256 ([string]$context.support_profile))-cne $context.support_profile_sha256){throw 'fixed input SHA-256 changed before resume'}
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $frozen.controller -ResumeCandidateRun -CandidateLedger $wrapperLedgerPath -RecoveryRecord $recoveryRecordPath
if ($LASTEXITCODE -ne 0) { throw 'candidate resume failed' }
```

Any other failure is deterministic and not resumable: correct it within ownership, create a new
CodeHead and run ID, rerun affected gates plus all Git/source/inventory/immutability checks, and
repeat the candidate. A repeated recoverable interruption is `BLOCKED`. After two contract-gap
cycles, stop for acceptance-architecture audit.

- [ ] Reopen both the external context and the wrapper-owned ledger after the terminal attempt,
  verify their immutable bindings, and reconcile using absolute paths from the frozen worktree.
  Pass both documents explicitly so the verifier rejects substitution or mutation:

```powershell
$bootstrapWorktree=[IO.Path]::GetFullPath((git rev-parse --show-toplevel).Trim());$bootstrapHead=(git -C $bootstrapWorktree rev-parse --verify HEAD).Trim().ToLowerInvariant();$bootstrapOrigin=(git -C $bootstrapWorktree remote get-url origin).Trim();$bootstrapStatus=@(git -C $bootstrapWorktree status --porcelain=v1 --untracked-files=all);if($LASTEXITCODE-ne 0-or $bootstrapHead-cnotmatch'^[0-9a-f]{40}$'-or $bootstrapOrigin-cne'https://github.com/XiaoyaoLinghao/stm32-toolkit.git'-or $bootstrapStatus.Count-ne 0){throw 'frozen worktree bootstrap failed'}
$fixedInputs=[ordered]@{path_contract='tools/release/path_contract_0600.ps1';controller='tools/release/run_0600_candidate.ps1';verifier='tools/release/verify_0600_release.py';catalog='tools/release/gates_0600.json';performance='tools/release/performance_0600.json'};$verifiedInputs=[ordered]@{};$verifiedBlobs=[ordered]@{};foreach($entry in $fixedInputs.GetEnumerator()){$absolute=[IO.Path]::GetFullPath((Join-Path $bootstrapWorktree ($entry.Value-replace'/','\')));$committed=(git -C $bootstrapWorktree rev-parse "$bootstrapHead`:$($entry.Value)").Trim().ToLowerInvariant();if($LASTEXITCODE-ne 0-or $committed-cnotmatch'^[0-9a-f]{40}$'){throw "missing committed $($entry.Key) blob"};$working=(git -C $bootstrapWorktree hash-object -- $absolute).Trim().ToLowerInvariant();if($LASTEXITCODE-ne 0-or $working-cne $committed){throw "working $($entry.Key) bytes differ from committed HEAD"};$verifiedInputs[$entry.Key]=$absolute;$verifiedBlobs[$entry.Key]=$committed};. $verifiedInputs.path_contract
function Get-LowerSha256([string]$Path) { $s=[IO.File]::OpenRead($Path); try{return ([Security.Cryptography.SHA256]::Create().ComputeHash($s)|ForEach-Object ToString x2)-join''}finally{$s.Dispose()} }
function Read-VerifiedContext([string]$Path) {
  $Path=ConvertTo-CanonicalAbsolutePath -Path $Path -Name 'invocation context'; $bytes=[IO.File]::ReadAllBytes($Path)
  $digest=[IO.File]::ReadAllText("$Path.sha256",[Text.UTF8Encoding]::new($false,$true))
  if($digest-cnotmatch'^[0-9a-f]{64}\n$'-or(Get-LowerSha256 $Path)-cne $digest.TrimEnd("`n")){throw 'context byte digest mismatch'}
  if($bytes.Length-lt 2-or $bytes[0]-eq 0xef-or $bytes[-1]-ne 10-or $bytes[-2]-eq 10){throw 'context bytes are noncanonical'}
  $text=[Text.UTF8Encoding]::new($false,$true).GetString($bytes); $value=$text|ConvertFrom-Json
  $fields=@('schema','module','shard','candidate_run_id','code_head','frozen_worktree','origin_url','candidate_root','evidence_root','support_profile','wrapper_ledger','catalog_sha256','performance_sha256','support_profile_sha256','controller_sha256','verifier_sha256')
  if(Compare-Object($fields|Sort-Object)(@($value.PSObject.Properties.Name)|Sort-Object)){throw 'context fields are not exact'}
  if($value.schema-cne'stm32-candidate-invocation-context/1'-or$value.module-cne'STM32TK-0603'-or$value.shard-cne'windows'-or$value.candidate_run_id-cnotmatch'^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$'-or$value.code_head-cnotmatch'^[0-9a-f]{40}$'-or @($value.catalog_sha256,$value.performance_sha256,$value.support_profile_sha256,$value.controller_sha256,$value.verifier_sha256|Where-Object{$_-cnotmatch'^[0-9a-f]{64}$'}).Count-ne 0){throw 'context values are invalid'}
  $ordered=[ordered]@{}; foreach($field in $fields){$ordered[$field]=$value.$field}; if((($ordered|ConvertTo-Json -Compress)+"`n")-cne $text){throw 'context JSON is not canonical'}; $value
}
$invocationContextPath = $env:STM32TK_0603_INVOCATION_CONTEXT
$context = Read-VerifiedContext $invocationContextPath
[void](ConvertTo-CanonicalAbsolutePath -Path ([string]$context.candidate_root) -Name 'candidate_root'); [void](ConvertTo-CanonicalAbsolutePath -Path ([string]$context.evidence_root) -Name 'evidence_root'); [void](ConvertTo-CanonicalAbsolutePath -Path ([string]$context.support_profile) -Name 'support_profile'); [void](ConvertTo-CanonicalAbsolutePath -Path ([string]$context.wrapper_ledger) -Name 'wrapper_ledger')
$repo=ConvertTo-CanonicalAbsolutePath -Path ([string]$context.frozen_worktree) -Name 'frozen_worktree';if($repo-cne $bootstrapWorktree-or $context.code_head-cne $bootstrapHead-or $context.origin_url-cne $bootstrapOrigin){throw 'context worktree binding failed'}
$candidateController=$verifiedInputs.controller;$releaseVerifier=$verifiedInputs.verifier;$catalog=$verifiedInputs.catalog;$performance=$verifiedInputs.performance
if((Get-LowerSha256 $candidateController)-cne $context.controller_sha256-or(Get-LowerSha256 $releaseVerifier)-cne $context.verifier_sha256-or(Get-LowerSha256 $catalog)-cne $context.catalog_sha256-or(Get-LowerSha256 $performance)-cne $context.performance_sha256){throw 're-derived frozen input digest mismatch'}
$wrapperLedgerPath = Join-Path ([string]$context.candidate_root) 'candidate-ledger.json'
if ($wrapperLedgerPath -cne [string]$context.wrapper_ledger) { throw 'noncanonical wrapper ledger path' }
$wrapperLedger = Get-Content -LiteralPath $wrapperLedgerPath -Raw | ConvertFrom-Json
$expectedLedgerFields = @('schema','module','candidate_run_id','expected_code_head','controller_path','candidate_root','evidence_root','catalog_sha256','performance_sha256','support_profile_sha256','checkpoint','state','created_at_utc','updated_at_utc')
if (Compare-Object ($expectedLedgerFields | Sort-Object) (@($wrapperLedger.PSObject.Properties.Name) | Sort-Object)) {
  throw 'wrapper ledger fields are not exact'
}
if ($wrapperLedger.schema -cne 'stm32-candidate-ledger/1' -or $wrapperLedger.module -cne 'STM32TK-0603' -or $wrapperLedger.candidate_run_id -cnotmatch '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$' -or $wrapperLedger.candidate_run_id -cne $context.candidate_run_id -or $wrapperLedger.expected_code_head -cnotmatch '^[0-9a-f]{40}$' -or $wrapperLedger.expected_code_head -cne $context.code_head) {
  throw 'wrapper ledger identity changed'
}
$ledgerController = ConvertTo-CanonicalAbsolutePath -Path ([string]$wrapperLedger.controller_path) -Name 'ledger controller_path'
[void](ConvertTo-CanonicalAbsolutePath -Path ([string]$wrapperLedger.checkpoint) -Name 'ledger checkpoint')
if ($ledgerController -cne $candidateController -or $wrapperLedger.candidate_root -cne $context.candidate_root -or $wrapperLedger.evidence_root -cne $context.evidence_root) {
  throw 'wrapper ledger original paths changed'
}
if ($wrapperLedger.catalog_sha256 -cne (Get-LowerSha256 $catalog) -or $wrapperLedger.performance_sha256 -cne (Get-LowerSha256 $performance) -or $wrapperLedger.support_profile_sha256 -cne (Get-LowerSha256 ([string]$context.support_profile))) {
  throw 'wrapper ledger original input digest changed'
}
if ($wrapperLedger.state -cne 'passed') { throw 'candidate ledger is not terminal PASS' }
foreach($name in $fixedInputs.Keys){$current=(git -C $repo hash-object -- $verifiedInputs[$name]).Trim().ToLowerInvariant();if($LASTEXITCODE-ne 0-or $current-cne $verifiedBlobs[$name]){throw "TOCTOU working-byte change: $name"}}
if((Get-LowerSha256 $candidateController)-cne $context.controller_sha256-or(Get-LowerSha256 $releaseVerifier)-cne $context.verifier_sha256-or(Get-LowerSha256 $catalog)-cne $context.catalog_sha256-or(Get-LowerSha256 $performance)-cne $context.performance_sha256-or(Get-LowerSha256 ([string]$context.support_profile))-cne $context.support_profile_sha256){throw 'fixed input SHA-256 changed before reconciliation'}
& py -3.12 $releaseVerifier candidate-evidence --module ([string]$context.module) --candidate-run-id ([string]$context.candidate_run_id) --evidence ([string]$context.candidate_root) --expected-code-head ([string]$context.code_head) --catalog $catalog --performance $performance --support-profile ([string]$context.support_profile)
if ($LASTEXITCODE -ne 0) { throw 'Windows candidate reconciliation failed' }
```

Expected: reconciliation reparses the canonical wrapper ledger, validates all exact fields, paths,
digests, attempts, and recovery history against the original context and results, and passes without
a Linux import or hardware shard.

- [ ] After candidate reconciliation PASS, record the full 0603 product SHA and final catalog,
  node, impact-map, performance, dependency, and support digests. This candidate is the final
  product CodeHead. Record status `SOFTWARE_COMPLETE_HARDWARE_PENDING` and hand the unchanged
  CodeHead/digests to `2026-08-14-stm32tk-0600-release-acceptance.md`. That plan alone owns the
  later unified 0.4+0.6 real-board link and accepted diagnostic scenario, hardware reconciliation,
  final `v0.6.0` decision, and final tracked report. Linux/Firefox/WebKit remain deferred beyond
  0603 and are not part of this handoff.

- [ ] Generate the create-new external `final-release-inputs.json` after reconciliation. The
  verifier resolves repository URL, fixed program base, fixed 0400 product/report SHAs, 0601 and
  0602 product/report SHAs, the 0603 product SHA, and every required artifact from the frozen
  worktree, accepted reports, catalogs, locks, and Windows software-support inputs. This immutable
  file is the software/code input to 0600 Task 1 and is not either ledger; it deliberately contains
  no invented deferred-board identity or firmware fact. Its closed `governance` object records the
  named owners and remote state, fixes `implementation_owner` to `Codex/local derived agents`, and
  leaves `remote_actions` empty absent separate user authorization:

```powershell
$bootstrapWorktree=[IO.Path]::GetFullPath((git rev-parse --show-toplevel).Trim());$bootstrapHead=(git -C $bootstrapWorktree rev-parse --verify HEAD).Trim().ToLowerInvariant();$bootstrapOrigin=(git -C $bootstrapWorktree remote get-url origin).Trim();$bootstrapStatus=@(git -C $bootstrapWorktree status --porcelain=v1 --untracked-files=all);if($LASTEXITCODE-ne 0-or $bootstrapHead-cnotmatch'^[0-9a-f]{40}$'-or $bootstrapOrigin-cne'https://github.com/XiaoyaoLinghao/stm32-toolkit.git'-or $bootstrapStatus.Count-ne 0){throw 'frozen worktree bootstrap failed'}
$fixedInputs=[ordered]@{path_contract='tools/release/path_contract_0600.ps1';controller='tools/release/run_0600_candidate.ps1';verifier='tools/release/verify_0600_release.py';catalog='tools/release/gates_0600.json';performance='tools/release/performance_0600.json'};$verifiedInputs=[ordered]@{};$verifiedBlobs=[ordered]@{};foreach($entry in $fixedInputs.GetEnumerator()){$absolute=[IO.Path]::GetFullPath((Join-Path $bootstrapWorktree ($entry.Value-replace'/','\')));$committed=(git -C $bootstrapWorktree rev-parse "$bootstrapHead`:$($entry.Value)").Trim().ToLowerInvariant();if($LASTEXITCODE-ne 0-or $committed-cnotmatch'^[0-9a-f]{40}$'){throw "missing committed $($entry.Key) blob"};$working=(git -C $bootstrapWorktree hash-object -- $absolute).Trim().ToLowerInvariant();if($LASTEXITCODE-ne 0-or $working-cne $committed){throw "working $($entry.Key) bytes differ from committed HEAD"};$verifiedInputs[$entry.Key]=$absolute;$verifiedBlobs[$entry.Key]=$committed};. $verifiedInputs.path_contract
function Get-LowerSha256([string]$Path) { $s=[IO.File]::OpenRead($Path); try{return ([Security.Cryptography.SHA256]::Create().ComputeHash($s)|ForEach-Object ToString x2)-join''}finally{$s.Dispose()} }
function Read-VerifiedContext([string]$Path) {
  $Path=ConvertTo-CanonicalAbsolutePath -Path $Path -Name 'invocation context'; $bytes=[IO.File]::ReadAllBytes($Path)
  $digest=[IO.File]::ReadAllText("$Path.sha256",[Text.UTF8Encoding]::new($false,$true))
  if($digest-cnotmatch'^[0-9a-f]{64}\n$'-or(Get-LowerSha256 $Path)-cne $digest.TrimEnd("`n")){throw 'context byte digest mismatch'}
  if($bytes.Length-lt 2-or $bytes[0]-eq 0xef-or $bytes[-1]-ne 10-or $bytes[-2]-eq 10){throw 'context bytes are noncanonical'}
  $text=[Text.UTF8Encoding]::new($false,$true).GetString($bytes); $value=$text|ConvertFrom-Json
  $fields=@('schema','module','shard','candidate_run_id','code_head','frozen_worktree','origin_url','candidate_root','evidence_root','support_profile','wrapper_ledger','catalog_sha256','performance_sha256','support_profile_sha256','controller_sha256','verifier_sha256')
  if(Compare-Object($fields|Sort-Object)(@($value.PSObject.Properties.Name)|Sort-Object)){throw 'context fields are not exact'}
  if($value.schema-cne'stm32-candidate-invocation-context/1'-or$value.module-cne'STM32TK-0603'-or$value.shard-cne'windows'-or$value.candidate_run_id-cnotmatch'^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$'-or$value.code_head-cnotmatch'^[0-9a-f]{40}$'-or @($value.catalog_sha256,$value.performance_sha256,$value.support_profile_sha256,$value.controller_sha256,$value.verifier_sha256|Where-Object{$_-cnotmatch'^[0-9a-f]{64}$'}).Count-ne 0){throw 'context values are invalid'}
  $ordered=[ordered]@{}; foreach($field in $fields){$ordered[$field]=$value.$field}; if((($ordered|ConvertTo-Json -Compress)+"`n")-cne $text){throw 'context JSON is not canonical'}; $value
}
$invocationContextPath = $env:STM32TK_0603_INVOCATION_CONTEXT
$context = Read-VerifiedContext $invocationContextPath
[void](ConvertTo-CanonicalAbsolutePath -Path ([string]$context.candidate_root) -Name 'candidate_root'); [void](ConvertTo-CanonicalAbsolutePath -Path ([string]$context.evidence_root) -Name 'evidence_root'); [void](ConvertTo-CanonicalAbsolutePath -Path ([string]$context.support_profile) -Name 'support_profile'); [void](ConvertTo-CanonicalAbsolutePath -Path ([string]$context.wrapper_ledger) -Name 'wrapper_ledger')
$repo=ConvertTo-CanonicalAbsolutePath -Path ([string]$context.frozen_worktree) -Name 'frozen_worktree';if($repo-cne $bootstrapWorktree-or $context.code_head-cne $bootstrapHead-or $context.origin_url-cne $bootstrapOrigin){throw 'context worktree binding failed'}
$candidateController=$verifiedInputs.controller;$releaseVerifier=$verifiedInputs.verifier;$catalog=$verifiedInputs.catalog;$performance=$verifiedInputs.performance
if((Get-LowerSha256 $candidateController)-cne $context.controller_sha256-or(Get-LowerSha256 $releaseVerifier)-cne $context.verifier_sha256-or(Get-LowerSha256 $catalog)-cne $context.catalog_sha256-or(Get-LowerSha256 $performance)-cne $context.performance_sha256){throw 're-derived frozen input digest mismatch'}
$wrapperLedgerPath = Join-Path ([string]$context.candidate_root) 'candidate-ledger.json'
if ($wrapperLedgerPath -cne [string]$context.wrapper_ledger) { throw 'wrapper ledger path changed' }
$finalReleaseInputsPath = 'C:\tmp\stm32tk-0600-support\final-release-inputs.json'
$finalReleaseInputsPath = ConvertTo-CanonicalAbsolutePath -Path $finalReleaseInputsPath -Name 'final release inputs'
$finalReleaseInputsDigestPath = "$finalReleaseInputsPath.sha256"
if ((Test-Path -LiteralPath $finalReleaseInputsPath) -or (Test-Path -LiteralPath $finalReleaseInputsDigestPath)) { throw 'final release inputs or digest already exist' }
foreach($name in $fixedInputs.Keys){$current=(git -C $repo hash-object -- $verifiedInputs[$name]).Trim().ToLowerInvariant();if($LASTEXITCODE-ne 0-or $current-cne $verifiedBlobs[$name]){throw "TOCTOU working-byte change before generation: $name"}}
if((Get-LowerSha256 $candidateController)-cne $context.controller_sha256-or(Get-LowerSha256 $releaseVerifier)-cne $context.verifier_sha256-or(Get-LowerSha256 $catalog)-cne $context.catalog_sha256-or(Get-LowerSha256 $performance)-cne $context.performance_sha256-or(Get-LowerSha256 ([string]$context.support_profile))-cne $context.support_profile_sha256){throw 'fixed input SHA-256 changed before final-input generation'}
& py -3.12 $releaseVerifier final-release-inputs --repo $repo --candidate-ledger $wrapperLedgerPath --invocation-context $invocationContextPath --output $finalReleaseInputsPath --digest-output $finalReleaseInputsDigestPath
if ($LASTEXITCODE -ne 0) { throw 'final release input generation failed' }
$writtenDigest=[IO.File]::ReadAllText($finalReleaseInputsDigestPath,[Text.UTF8Encoding]::new($false,$true))
if($writtenDigest-cnotmatch'^[0-9a-f]{64}\n$'-or(Get-LowerSha256 $finalReleaseInputsPath)-cne $writtenDigest.TrimEnd("`n")){throw 'final release input post-write digest verification failed'}
foreach($name in $fixedInputs.Keys){$current=(git -C $repo hash-object -- $verifiedInputs[$name]).Trim().ToLowerInvariant();if($LASTEXITCODE-ne 0-or $current-cne $verifiedBlobs[$name]){throw "TOCTOU working-byte change before verification: $name"}}
if((Get-LowerSha256 $candidateController)-cne $context.controller_sha256-or(Get-LowerSha256 $releaseVerifier)-cne $context.verifier_sha256-or(Get-LowerSha256 $catalog)-cne $context.catalog_sha256-or(Get-LowerSha256 $performance)-cne $context.performance_sha256-or(Get-LowerSha256 ([string]$context.support_profile))-cne $context.support_profile_sha256){throw 'fixed input SHA-256 changed before final-input verification'}
& py -3.12 $releaseVerifier verify-final-release-inputs --repo $repo --input $finalReleaseInputsPath --digest $finalReleaseInputsDigestPath
if ($LASTEXITCODE -ne 0) { throw 'final release input canonical/schema verification failed' }
```

Expected: the output has only the closed root fields and sorted closed artifact records from the
specification, including the closed governance object; every path/byte count/SHA-256 and Git
ancestry/report-only constraint verifies, and both output files were created new and reread.
0600 Task 1 consumes this exact file together with its later create-new
`hardware-campaign-inputs.json` and deterministically creates the single `release-ledger.json`.

- [ ] Do not change product, tests, helpers, dependencies, docs, Skills, gate catalog, performance
  configuration, or reports during handoff. Do not create a 0603 report-only commit and do not run
  any hardware or final-release gate here.
