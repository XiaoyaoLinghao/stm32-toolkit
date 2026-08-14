# STM32TK-0603 Monitor Analytics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver history v2, bounded cross-run analytics, quality/stage/halt analysis, safe annotations and markers, accessible UI, and explicit deterministic AI bundles without regressing 0.5 live monitoring.

**Architecture:** Python owns canonical history reads, compatibility, alignment, statistics, decimation, annotations, and bundle creation. The Preact UI renders bounded typed responses and never opens storage. Toolkit reaches Monitor through its authenticated loopback API; immutable evidence/diagnostics remain external sources of truth.

**Tech Stack:** Python 3.10/3.12, SQLite, aiohttp, dataclasses, pytest/pytest-cov, TypeScript 5.9, Preact, ECharts, Vitest/V8 coverage, Playwright, axe-core, Vite, Chromium/Firefox/WebKit.

## Global Constraints

- Begin at the accepted report commit of `STM32TK-0602-DIAGNOSTIC-LOOP`; record its full SHA.
- Follow `docs/superpowers/specs/2026-08-14-stm32tk-0603-monitor-analytics-design.md`.
- Write history v2; read v1/v2; never rewrite a 0.5 history database in place.
- Keep loopback/random-port/auth/origin/CSP/static protections and every 0.5 threshold unchanged.
- Maximum request is 8 runs, 8 groups, 16 selectors, 640,000 raw samples, and 64,000 returned
  points; no implementation may bypass these limits.
- Every changed Python and TypeScript product file must reach at least 90% branch coverage in its
  owning shard; correctness runs on Python 3.10/3.12 and supported browsers.
- No browser/model/cloud/API-key/automatic-annotation or automatic group creation is permitted.
- No remote Git action is authorized by this plan.

---

## Task 1: Add history v2 identity and quality metadata

**Files:**

- Modify: `tools/stm32-monitor/src/stm32_monitor/models.py`
- Modify: `tools/stm32-monitor/src/stm32_monitor/history.py`
- Modify: `tools/stm32-monitor/src/stm32_monitor/storage.py`
- Create: `tools/stm32-monitor/tests/test_history_v2.py`
- Modify: `tools/stm32-monitor/tests/test_history.py`
- Modify: `tools/stm32-monitor/tests/test_storage.py`

- [ ] Write failing tests for v2-only writes; v1/v2 reads; unknown version failure; firmware/source
  identity; monotonic sequence/time; UTC display time; all quality codes; stage/pause/halt/gap/
  dropped/backpressure events; evidence/test/diagnostic links; v1 `legacy_missing`; immutable raw
  samples; forged/corrupt index/cache rejection; and no in-place v1 mutation.

- [ ] Run RED:

```powershell
py -3.12 -m pytest tools/stm32-monitor/tests/test_history_v2.py tools/stm32-monitor/tests/test_history.py tools/stm32-monitor/tests/test_storage.py -q -p no:cacheprovider
```

Expected: v2 fields/schema are absent.

- [ ] Implement frozen v2 row/event models, storage migrations for newly created databases only,
  a read adapter for v1, and explicit quality/identity/link writes in the existing append path.
  Do not toggle process-global GC or weaken append locking.

- [ ] Run GREEN on 3.10/3.12, concurrent history regressions, and branch coverage:

```powershell
py -3.10 -m pytest tools/stm32-monitor/tests/test_history_v2.py tools/stm32-monitor/tests/test_history.py tools/stm32-monitor/tests/test_storage.py -q -p no:cacheprovider
py -3.12 -m pytest tools/stm32-monitor/tests/test_history_v2.py tools/stm32-monitor/tests/test_history.py tools/stm32-monitor/tests/test_storage.py --cov=stm32_monitor.models --cov=stm32_monitor.history --cov=stm32_monitor.storage --cov-branch --cov-report=term-missing --cov-fail-under=90 -q -p no:cacheprovider
```

- [ ] Commit:

```powershell
git add tools/stm32-monitor/src/stm32_monitor/models.py tools/stm32-monitor/src/stm32_monitor/history.py tools/stm32-monitor/src/stm32_monitor/storage.py tools/stm32-monitor/tests/test_history_v2.py tools/stm32-monitor/tests/test_history.py tools/stm32-monitor/tests/test_storage.py
git commit -m "feat(STM32TK-0603): write monitor history v2"
```

## Task 2: Define bounded analysis requests and compatibility

**Files:**

- Create: `schemas/monitor-analysis.schema.json`
- Create: `tools/stm32-monitor/src/stm32_monitor/schemas/monitor-analysis.schema.json`
- Create: `tools/stm32-monitor/src/stm32_monitor/analysis/{__init__,model,query}.py`
- Modify: `tools/stm32-monitor/pyproject.toml`
- Create: `tools/stm32-monitor/tests/test_analysis_model.py`
- Create: `tools/stm32-monitor/tests/test_analysis_query.py`

- [ ] Write failing tests for canonical `ComparisonRequest`, exact unknown/duplicate/type rejection,
  64 KiB body, all cardinality/sample/point/deadline bounds, stable selector identity, strict and
  allow-firmware-difference compatibility, type/target/selector mismatches, deterministic order,
  zero-to-eight directed difference pairs, interpolation-gap bounds, workspace isolation, corrupt
  history, byte-identical root/packaged schema, and no raw SQL/expression surface.

```python
def test_name_only_match_does_not_override_type_identity(history):
    result = compare(history, request_for_same_name_different_type())
    assert result.error.code == "ANALYSIS_INCOMPATIBLE"
```

- [ ] Run RED:

```powershell
py -3.12 -m pytest tools/stm32-monitor/tests/test_analysis_model.py tools/stm32-monitor/tests/test_analysis_query.py -q -p no:cacheprovider
```

- [ ] Implement immutable request/result/compatibility models, schema validation, canonical
  selector IDs, bounded public HistoryStore query methods, and exact compatibility matrix.

- [ ] Run GREEN dual Python and branch coverage:

```powershell
py -3.10 -m pytest tools/stm32-monitor/tests/test_analysis_model.py tools/stm32-monitor/tests/test_analysis_query.py -q -p no:cacheprovider
py -3.12 -m pytest tools/stm32-monitor/tests/test_analysis_model.py tools/stm32-monitor/tests/test_analysis_query.py --cov=stm32_monitor.analysis.model --cov=stm32_monitor.analysis.query --cov-branch --cov-report=term-missing --cov-fail-under=90 -q -p no:cacheprovider
```

- [ ] Commit:

```powershell
git add schemas/monitor-analysis.schema.json tools/stm32-monitor/src/stm32_monitor/schemas/monitor-analysis.schema.json tools/stm32-monitor/src/stm32_monitor/analysis tools/stm32-monitor/pyproject.toml tools/stm32-monitor/tests/test_analysis_model.py tools/stm32-monitor/tests/test_analysis_query.py
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
  exact marker/annotation anchors, missing/ambiguous markers, multiple runs, empty/no-valid input,
  no fallback, and proof raw timestamps remain unchanged.

- [ ] Write failing numeric/state statistic tests for finite filtering, population deviation,
  p50/p95, delta, dwell/transition counts, excluded-quality counts, empty result error, deterministic
  float serialization, and raw-versus-eligible counts.

- [ ] Write failing decimation tests for first/min/max/last order, transition/endpoints, quality
  boundaries, marker adjacency, duplicate elimination by sequence, exact total budget allocation,
  repeatability, adversarial spikes, and statistics remaining raw-data based.

- [ ] Write failing directed-difference tests using baseline timestamps: `candidate - baseline`,
  bounded linear interpolation, no extrapolation, no interpolation across invalid quality/stage/
  discontinuity or excessive gaps, excluded counts/reasons, numeric-only compatibility, and
  statistics computed before difference decimation.

- [ ] Run RED:

```powershell
py -3.12 -m pytest tools/stm32-monitor/tests/test_analysis_alignment.py tools/stm32-monitor/tests/test_analysis_decimation.py tools/stm32-monitor/tests/test_analysis_statistics.py -q -p no:cacheprovider
```

- [ ] Implement pure alignment/statistic/decimation functions and assemble `RunComparison` with
  algorithm version `stm32-monitor-decimation/1`.

- [ ] Run GREEN on both Pythons and per-file branch coverage:

```powershell
py -3.10 -m pytest tools/stm32-monitor/tests/test_analysis_alignment.py tools/stm32-monitor/tests/test_analysis_decimation.py tools/stm32-monitor/tests/test_analysis_statistics.py -q -p no:cacheprovider
py -3.12 -m pytest tools/stm32-monitor/tests/test_analysis_alignment.py tools/stm32-monitor/tests/test_analysis_decimation.py tools/stm32-monitor/tests/test_analysis_statistics.py --cov=stm32_monitor.analysis.alignment --cov=stm32_monitor.analysis.decimation --cov=stm32_monitor.analysis.query --cov-branch --cov-report=term-missing --cov-fail-under=90 -q -p no:cacheprovider
```

- [ ] Commit:

```powershell
git add tools/stm32-monitor/src/stm32_monitor/analysis tools/stm32-monitor/tests/test_analysis_alignment.py tools/stm32-monitor/tests/test_analysis_decimation.py tools/stm32-monitor/tests/test_analysis_statistics.py
git commit -m "feat(STM32TK-0603): align and reduce monitor comparisons"
```

## Task 4: Add quality, stage, gap, and halt-impact analysis

**Files:**

- Create: `tools/stm32-monitor/src/stm32_monitor/analysis/quality.py`
- Create: `tools/stm32-monitor/tests/test_analysis_quality.py`

- [ ] Write failing tests for valid ratio, counts/duration by every status, longest gap, p95
  interval, dropped/backpressure totals, pause/halt overlaps, discontinuities, 128-stage bound,
  recorded-only stage boundaries, v1 missing metadata warning, mixed-quality samples, overflow/
  zero-duration intervals, and deterministic ordering.

- [ ] Run RED:

```powershell
py -3.12 -m pytest tools/stm32-monitor/tests/test_analysis_quality.py -q -p no:cacheprovider
```

- [ ] Implement `analyze_quality(samples, events, stages, window)` without heuristic stage names or
  silently accepting invalid-quality numeric values.

- [ ] Run GREEN on both Python versions with branch coverage:

```powershell
py -3.10 -m pytest tools/stm32-monitor/tests/test_analysis_quality.py -q -p no:cacheprovider
py -3.12 -m pytest tools/stm32-monitor/tests/test_analysis_quality.py --cov=stm32_monitor.analysis.quality --cov-branch --cov-report=term-missing --cov-fail-under=90 -q -p no:cacheprovider
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
  edit/tombstone, stale concurrent writers, crash recovery, text-only content, workspace/run link
  isolation, Toolkit diagnostic/evidence validation, unavailable bridge, and no raw-history update.

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
py -3.12 -m pytest tools/stm32-monitor/tests/test_annotations.py tools/stm32-monitor/tests/test_annotation_concurrency.py --cov=stm32_monitor.annotations --cov-branch --cov-report=term-missing --cov-fail-under=90 -q -p no:cacheprovider
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
  request IDs, body/result limits, deadline, unknown field/Unicode/non-finite input, all errors,
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
py -3.12 -m pytest tools/stm32-monitor/tests/test_analysis_service.py tools/stm32-monitor/tests/test_annotation_service.py tools/stm32-monitor/tests/test_service.py tools/stm32-monitor/tests/test_auth.py --cov=stm32_monitor.protocol --cov=stm32_monitor.service --cov-branch --cov-report=term-missing --cov-fail-under=90 -q -p no:cacheprovider
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
  identities/request/compatibility/counts/stats/quality/markers/revisions/evidence/schema versions,
  fixed CSV/ZIP, formula injection, inventory hashes, corrupt/link/casefold/zip-slip/bomb input,
  secret/path/source/raw-memory/unselected-data exclusion, and no upload/share action.

- [ ] Write failing bridge tests using a real local fake Monitor server for exact loopback origin,
  token header not URL, response schema, timeout/size/error, artifact references, unavailable
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
py -3.12 -m pytest tools/stm32-monitor/tests/test_analysis_bundle.py tools/stm32-monitor/tests/test_exports.py tools/stm32-toolkit/tests/test_monitor_analysis.py --cov=stm32_monitor.analysis.bundle --cov=stm32_monitor.exports --cov=stm32_toolkit.monitor_analysis --cov-branch --cov-report=term-missing --cov-fail-under=90 -q -p no:cacheprovider
```

- [ ] Commit:

```powershell
git add tools/stm32-monitor/src/stm32_monitor/analysis/bundle.py tools/stm32-monitor/src/stm32_monitor/exports.py tools/stm32-toolkit/src/stm32_toolkit/monitor_analysis.py tools/stm32-monitor/tests/test_analysis_bundle.py tools/stm32-toolkit/tests/test_monitor_analysis.py
git commit -m "feat(STM32TK-0603): create explicit monitor analysis bundles"
```

## Task 8: Add typed frontend analysis state and API client

**Files:**

- Create: `tools/stm32-monitor/ui/src/analysis/{model,selectors,alignment,quality,bundle}.ts`
- Modify: `tools/stm32-monitor/ui/src/api/{contract,client,wire}.ts`
- Modify: `tools/stm32-monitor/ui/src/state/{model,reducer,selectors}.ts`
- Create: `tools/stm32-monitor/ui/tests/analysis-contract.test.ts`
- Create: `tools/stm32-monitor/ui/tests/analysis-state.test.ts`

- [ ] Write failing decoder tests for exact schemas, limits, unknown/missing/wrong/non-finite
  fields, fresh results, and all error responses. Write reducer tests for selection bounds,
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
git add tools/stm32-monitor/ui/src/analysis tools/stm32-monitor/ui/src/api tools/stm32-monitor/ui/src/state tools/stm32-monitor/ui/tests/analysis-contract.test.ts tools/stm32-monitor/ui/tests/analysis-state.test.ts
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
  bounded canonical time window, keyboard start/end equivalent, visible identity differences,
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
git add tools/stm32-monitor/ui/src/components tools/stm32-monitor/ui/src/app.tsx tools/stm32-monitor/ui/src/styles.css tools/stm32-monitor/ui/tests/run-comparison.test.tsx tools/stm32-monitor/ui/tests/quality-panel.test.tsx
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
  validation/limits, revision conflicts, text-only malicious content, evidence link states, dialog
  focus trap/restoration, explicit export selection/summary/confirmation, minimal result reference,
  cancellation, and absence of send/share/upload/automatic creation.

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

## Task 11: Close real browser security, accessibility, isolation, and performance

**Files:**

- Create: `tools/stm32-monitor/ui/e2e/analysis.spec.ts`
- Create: `tools/stm32-monitor/ui/e2e/analysis-security.spec.ts`
- Create: `tools/stm32-monitor/ui/e2e/analysis-accessibility.spec.ts`
- Create: `tools/stm32-monitor/ui/e2e/analysis-isolation.spec.ts`
- Modify: `tools/stm32-monitor/ui/e2e/performance.spec.ts`
- Modify: `tools/stm32-monitor/ui/e2e/fake_runtime.py`

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

- [ ] Extend five-minute performance with the 640,000/64,000 dataset, eight directed difference
  pairs, and frozen thresholds:
  comparison p95 <=1,000 ms, quality p95 <=750 ms, UI update p95 <=150 ms, zero long tasks >=200
  ms, retained heap slope <=2 MiB/min, queue growth zero, <=15% regression, plus unchanged 0.5
  live/history/export thresholds.

- [ ] Before implementing a new analytics hot path, capture 3.10/3.12 baseline JSON on the frozen
  Windows reference profile. Record CPU, memory, NVMe, OS build, power/AC state, antivirus state,
  Python/Node/browser, GC, serialized bytes, database size, CPU, heap, queue, and long tasks. An
  environment change requires prior-CodeHead calibration before implementation, never after FAIL.

- [ ] Run all Node/browser gates and retain screenshots, traces, axe JSON, performance JSON, and
  sentinel counts outside the worktree:

```powershell
Push-Location tools/stm32-monitor/ui
npm.cmd run typecheck
npm.cmd run typecheck:e2e
npm.cmd run lint
npm.cmd run test:coverage
npm.cmd run coverage:check
npm.cmd run build
npm.cmd run verify:dist
npm.cmd run test:e2e:windows
npm.cmd run test:e2e:performance
Pop-Location
```

Expected: all Chromium flows pass at both viewports; Linux Firefox/WebKit core flows are captured
by the candidate owner; all thresholds and security/accessibility/isolation assertions pass.

- [ ] Commit:

```powershell
git add -- tools/stm32-monitor/ui/e2e/analysis.spec.ts tools/stm32-monitor/ui/e2e/analysis-security.spec.ts tools/stm32-monitor/ui/e2e/analysis-accessibility.spec.ts tools/stm32-monitor/ui/e2e/analysis-isolation.spec.ts tools/stm32-monitor/ui/e2e/performance.spec.ts tools/stm32-monitor/ui/e2e/fake_runtime.py tools/stm32-monitor/src/stm32_monitor/ui_dist
git commit -m "test(STM32TK-0603): close browser analytics acceptance"
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
  no unexpected files; v1 history read; and no model/cloud/API-key/browser AI/automatic annotation.
  Replace assertions that represent the current product version, while retaining deliberately
  named 0.5 backward-compatibility fixtures and the historical 0502 controller/verifier tests.

- [ ] Update all version surfaces atomically, align Monitor's exact Toolkit dependency to 0.6.0,
  update the thin Skill, and document limits/compatibility/quality/annotations/bundle consent and
  non-goals only after evidence exists.

- [ ] Run dual-Python complete product suites, Node build/dist, offline wheel/install smoke, and
  quick matrix:

```powershell
py -3.10 -m pytest tools/stm32-toolkit/tests tools/stm32-monitor/tests -q -p no:cacheprovider --basetemp C:\tmp\stm32tk-0603-bt-310
py -3.12 -m pytest tools/stm32-toolkit/tests tools/stm32-monitor/tests -q -p no:cacheprovider --basetemp C:\tmp\stm32tk-0603-bt-312
powershell.exe -NoProfile -ExecutionPolicy Bypass -File tools/release/run_0600_quick.ps1 -Module STM32TK-0603 -EvidenceRoot C:\tmp\stm32tk-0603-quick
```

- [ ] Commit:

```powershell
git add -- bin/setup-stm32-env.ps1 bin/stm32-toolkit-mcp.cmd bin/stm32-monitor.cmd .claude-plugin/plugin.json README.md README_zh-CN.md skills/setup-stm32-env/SKILL.md skills/stm32-monitor/SKILL.md tools/stm32-toolkit/pyproject.toml tools/stm32-toolkit/src/stm32_toolkit/__init__.py tools/stm32-toolkit/src/stm32_toolkit/cli.py tools/stm32-toolkit/tests/test_build_runner.py tools/stm32-toolkit/tests/test_cli.py tools/stm32-toolkit/tests/test_hardware_workflows.py tools/stm32-toolkit/tests/test_migration_plan.py tools/stm32-toolkit/tests/test_mcp_migration_build.py tools/stm32-toolkit/tests/test_probe_protocol.py tools/stm32-toolkit/tests/test_setup_runtime.py tools/stm32-toolkit/tests/test_plugin_layout.py tools/stm32-toolkit/README.md tools/stm32-monitor/pyproject.toml tools/stm32-monitor/src/stm32_monitor/__init__.py tools/stm32-monitor/src/stm32_monitor/protocol.py tools/stm32-monitor/src/stm32_monitor/runtime.py tools/stm32-monitor/tests/test_cli.py tools/stm32-monitor/tests/test_exports.py tools/stm32-monitor/tests/test_models.py tools/stm32-monitor/tests/test_package_boundary.py tools/stm32-monitor/tests/test_runtime.py tools/stm32-monitor/tests/test_service.py tools/stm32-monitor/tests/test_ui_dist.py tools/stm32-monitor/ui/package.json tools/stm32-monitor/ui/package-lock.json tools/stm32-monitor/ui/e2e/fake_runtime.py tools/stm32-monitor/ui/tests/bootstrap.test.ts tools/stm32-monitor/ui/tests/main.test.tsx tools/stm32-monitor/README.md
git commit -m "chore(STM32TK-0603): prepare version 0.6.0 surfaces"
```

## Task 13: Freeze the 0603 product CodeHead

**Files:** none; this task creates evidence outside the repository.

- [ ] Audit the complete 0602 accepted-report-to-current diff, all tracked/untracked/committed/
  uncommitted/pushed/unpushed state, frozen 0601/0602 contracts, exact expected paths, package/dist
  inventories, dependency locks, version surfaces, Skills, docs, and source hashes.

- [ ] Run the collect-all 0603 candidate matrix at one product CodeHead:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File tools/release/run_0600_candidate.ps1 -Module STM32TK-0603 -EvidenceRoot C:\tmp\stm32tk-0603-candidate-<full-codehead>
```

- [ ] If any gate fails, do not report or freeze. Correct within ownership, create a new CodeHead,
  rerun affected gates plus all Git/source/inventory/immutability checks, and repeat candidate.
  After two contract-gap cycles, stop for acceptance-architecture audit.

- [ ] After candidate PASS, run every final gate once in ordered preflight at identical CodeHead,
  gate-catalog digest, support-manifest digest, lock digests, and tools. Reconcile all node/artifact
  inventories and clean-tree checks.

- [ ] Record the full immutable 0603 product SHA as the sole final `0.6.0` CodeHead. Do not change
  product, tests, helpers, dependencies, docs, Skills, gate catalog, or reports. Hand off to
  `2026-08-14-stm32tk-0600-release-acceptance.md`; do not run the complete final matrix here.
