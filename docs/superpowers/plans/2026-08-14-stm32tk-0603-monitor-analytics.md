# STM32TK-0603 Monitor Analytics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver history v2, bounded cross-run analytics, quality/stage/halt analysis, safe annotations and markers, accessible UI, and explicit deterministic AI bundles without regressing 0.5 live monitoring.

**Architecture:** Python owns canonical history reads, compatibility, alignment, statistics, decimation, annotations, and bundle creation. The Preact UI renders bounded typed responses and never opens storage. 0603 predeclares workloads/maxima, characterizes correct measured paths, and freezes within-maximum accepted calibration before optional post-baseline optimization; after every 0603 test exists and before candidate, it fills reserved gate families and freezes the exact final nodes, then hands one catalog to non-executing readiness and the logical multi-platform final run.

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
- Any impact-selected real reset/flash/modify gate requires a current-task exact user authorization;
  this plan and prior-module evidence do not transfer authorization.
- Preserve frozen gate families and 0601/0602 entries; fill only reserved 0603 families and freeze
  the complete catalog/node/performance digests before candidate.
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
py -3.12 tools/release/run_0600_gates.py dev-coverage --task-id STM32TK-0603-T01 --evidence-root C:\tmp\stm32tk-0603-t01-coverage -- tools/stm32-monitor/tests/test_history_v2.py tools/stm32-monitor/tests/test_history.py tools/stm32-monitor/tests/test_storage.py --cov=stm32_monitor.models --cov=stm32_monitor.history --cov=stm32_monitor.storage -q -p no:cacheprovider
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
- Create: `tools/stm32-monitor/src/stm32_monitor/analysis/__init__.py`
- Create: `tools/stm32-monitor/src/stm32_monitor/analysis/model.py`
- Create: `tools/stm32-monitor/src/stm32_monitor/analysis/query.py`
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

- [ ] Add a correctness-first Python workload for 640,000 raw/64,000 plotted samples and eight
  directed difference pairs. Provisionally characterize comparison/quality under 3.10/3.12 with
  the common three-batch method. Extend the continuous five-minute browser fixture with a
  fixed analytics cadence while preserving the exact 0.5 warmup/measurement windows.

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
accessibility/isolation pass; product frameworks report zero hidden retries. The candidate, not
this task-local GREEN, owns mandatory Linux Firefox/WebKit evidence.

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
  no unexpected files; v1 history read; and no model/cloud/API-key/browser AI/automatic annotation.
  Replace assertions that represent the current product version, while retaining deliberately
  named 0.5 backward-compatibility fixtures and the historical 0502 controller/verifier tests.

- [ ] Update all version surfaces atomically, align Monitor's exact Toolkit dependency to 0.6.0,
  update the thin Skill, and document limits/compatibility/quality/annotations/bundle consent and
  non-goals only after evidence exists.

- [ ] Run the changed version/package/inventory tests under both Pythons, targeted Node tests,
  build/dist verification, offline wheel/install smoke owned by those tests, and deterministic
  offline dependency audit. Prior tasks own feature correctness/coverage/performance; Task 13
  candidate owns the complete affected regression.

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
- Modify: `tools/stm32-toolkit/tests/release/test_gate_catalog_0600.py`
- Modify: `tools/stm32-toolkit/tests/release/test_gate_controller_0600.py`

- [ ] Audit the complete 0602 accepted-report-to-current diff, all tracked/untracked/committed/
  uncommitted/pushed/unpushed state, frozen 0601/0602 contracts, exact expected paths, package/dist
  inventories, dependency locks, version surfaces, Skills, docs, and source hashes.

- [ ] Collect the complete exact Python/Vitest/Playwright/audit/install/hardware/integrity/artifact
  inventory after Task 12. Fill only reserved 0603 slots, freeze the final impact map, and add
  catalog/controller mutations proving 0601/0602 entries are byte-identical, every required node
  executes once, Playwright retries are zero, and missing/extra/duplicate/renamed/deselected/skip/
  xfail nodes fail. Commit this last contract change before candidate:

```powershell
py -3.12 -m pytest tools/stm32-toolkit/tests/release/test_gate_catalog_0600.py tools/stm32-toolkit/tests/release/test_gate_controller_0600.py -q -p no:cacheprovider
git add -- tools/release/gates_0600.json tools/stm32-toolkit/tests/release/test_gate_catalog_0600.py tools/stm32-toolkit/tests/release/test_gate_controller_0600.py
git commit -m "test(STM32TK-0603): freeze final candidate inventory"
```

- [ ] Generate one `candidateRunId`, then run the collect-all Windows, Linux, and hardware candidate
  shards at one product CodeHead. Task 12 changes shared package/runtime/launcher surfaces, so the
  frozen impact map must select installed-product hardware smoke rather than reusing 0602 evidence.
  Each wrapper runs its non-executing precheck and refuses to start a product body on failure:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File tools/release/run_0600_candidate.ps1 -Module STM32TK-0603 -Shard windows -CandidateRunId <candidateRunId> -EvidenceRoot C:\tmp\stm32tk-0603-candidate-<candidateRunId>\windows -ExpectedCodeHead <full-codehead> -Catalog tools/release/gates_0600.json -Performance tools/release/performance_0600.json -SupportProfile C:\tmp\stm32tk-0600-support\feasibility\profile.json
powershell.exe -NoProfile -ExecutionPolicy Bypass -File tools/release/run_0600_candidate.ps1 -Module STM32TK-0603 -Shard hardware -CandidateRunId <candidateRunId> -EvidenceRoot C:\tmp\stm32tk-0603-candidate-<candidateRunId>\hardware -ExpectedCodeHead <full-codehead> -Catalog tools/release/gates_0600.json -Performance tools/release/performance_0600.json -SupportProfile C:\tmp\stm32tk-0600-support\feasibility\profile.json
```

```bash
./tools/release/run_0600_candidate.sh --module STM32TK-0603 --shard linux --candidate-run-id <candidateRunId> --evidence-root /tmp/stm32tk-0603-candidate-<candidateRunId>/linux --expected-code-head <full-codehead> --catalog tools/release/gates_0600.json --performance tools/release/performance_0600.json --support-profile /tmp/stm32tk-0600-support/feasibility/profile.json
```

The Linux owner returns `linux/shard-package.zip` and its SHA-256 through the user-designated
evidence channel; place it unchanged at
`C:\tmp\stm32tk-0603-candidate-<candidateRunId>\imports\linux.zip`. No controller performs transfer.

- [ ] If one shard reports an enumerated external event, a reviewer may resume only that shard once
  at the same candidate run ID/frozen inputs; retain both attempts. A repeat is BLOCKED. For any
  deterministic failure, do not freeze: correct within ownership, create a new CodeHead, rerun
  affected gates plus all Git/source/inventory/immutability checks, and repeat candidate. After two
  contract-gap cycles, stop for acceptance-architecture audit.

- [ ] Reconcile all three candidate shards before final readiness:

```powershell
py -3.12 tools/release/verify_0600_release.py candidate-evidence --module STM32TK-0603 --candidate-run-id <candidateRunId> --evidence C:\tmp\stm32tk-0603-candidate-<candidateRunId> --import-shard C:\tmp\stm32tk-0603-candidate-<candidateRunId>\imports\linux.zip --expected-code-head <full-codehead> --catalog tools/release/gates_0600.json --performance tools/release/performance_0600.json --support-profile C:\tmp\stm32tk-0600-support\feasibility\profile.json
```

- [ ] After candidate reconciliation PASS, record the full 0603 product SHA and final catalog,
  node, impact-map, performance, dependency, and support digests. Hand them to
  `2026-08-14-stm32tk-0600-release-acceptance.md`, which alone owns non-executing final readiness,
  final CodeHead freeze, and the logical complete final matrix.

- [ ] Do not change product, tests, helpers, dependencies, docs, Skills, gate catalog, performance
  configuration, or reports during handoff. Do not run any final gate here.
