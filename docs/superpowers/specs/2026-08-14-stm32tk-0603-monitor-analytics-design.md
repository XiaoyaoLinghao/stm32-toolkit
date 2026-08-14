# STM32TK-0603 Monitor Cross-Run Analytics Design

**Status:** Approved module design baseline
**Date:** 2026-08-14
**Module:** `STM32TK-0603-MONITOR-ANALYTICS`
**Accepted base:** the accepted report commit of `STM32TK-0602-DIAGNOSTIC-LOOP`
**Fixed program base:** `bb6bc5e9ee937e4ce53996b31f25bf1109ffe13f` (`v0.5.0`)
**Specification owner:** Codex
**Implementation owner:** OpenClaw, when a work order is authorized
**Review and acceptance owner:** Codex
**Remote actions authorized by this document:** none

## 1. Objective

Extend the 0.5 local Monitor from single-run history into bounded, identity-safe cross-run
analysis. Users can compare selected signals, inspect data quality, record explicit annotations
and diagnostic markers, and export a deterministic AI-readable bundle. The live sampling path,
loopback/auth security, and every 0.5 performance threshold remain unchanged.

Monitor is a read/analysis surface, not the diagnostic source of truth. It links to 0601/0602
evidence IDs through public APIs and never opens the shared evidence catalog or diagnostic event
files directly.

## 2. Scope

### 2.1 Included

- Monitor history schema v2 with read compatibility for v1 and v2;
- bounded multi-run, multi-group, and multi-firmware comparison;
- absolute, run-relative, and marker-relative alignment;
- deterministic decimation for display without discarding canonical raw samples;
- quality timeline, distribution, stage, gap, and halt-impact analysis;
- append-only annotations, bookmarks, and diagnostic markers;
- authenticated HTTP/WebSocket analysis APIs and keyboard-accessible UI;
- explicit deterministic `stm32-monitor-analysis/1` AI bundle;
- Toolkit MCP bridge using Monitor's authenticated public API;
- dual-Python, browser, security, accessibility, performance, isolation, install, and final
  0.6 release evidence.

### 2.2 Excluded

- browser-side AI, model SDK, cloud upload, or automatic analysis;
- automatically creating groups, annotations, hypotheses, or source changes;
- unbounded queries or arbitrary SQL/expression execution;
- rewriting or mutating 0.5 history files in place;
- treating incompatible types/targets/firmware as comparable without an explicit mode;
- weakening any 0.5 security, coverage, or performance threshold.

## 3. Source layout and boundaries

```text
tools/stm32-monitor/src/stm32_monitor/
├── analysis/{__init__,model,query,alignment,decimation,quality,bundle}.py
├── annotations.py
├── {models,history,storage,protocol,service,exports}.py
└── cli.py

tools/stm32-monitor/ui/src/
├── analysis/{model,selectors,alignment,quality,bundle}.ts
├── components/{RunComparison,QualityPanel,AnnotationPanel,AnalysisExport}.tsx
├── state/{model,reducer,selectors}.ts
├── api/{contract,client,wire}.ts
├── app.tsx
└── styles.css

tools/stm32-toolkit/src/stm32_toolkit/monitor_analysis.py
skills/stm32-monitor/SKILL.md
schemas/monitor-analysis.schema.json
tools/stm32-monitor/src/stm32_monitor/schemas/monitor-analysis.schema.json
```

The root and packaged analysis schemas are byte-identical. Python performs canonical filtering,
compatibility checks, quality computation, display-point
selection, and bundle creation. TypeScript renders already bounded responses and manages UI
state. The browser receives no database path, filesystem root, raw auth token in a URL, or
unbounded history.

## 4. History schema v2

### 4.1 Compatibility

New runs write history schema v2. Existing schema v1 databases remain read-only compatible and
are never migrated in place. The reader normalizes a v1 run into a v2 view with explicit
`legacy_missing` quality metadata; it does not invent firmware, marker, stage, or pause facts.
Unknown future versions fail `HISTORY_SCHEMA_UNSUPPORTED`.

History v2 adds:

- complete `FirmwareIdentity` fields and source snapshot digest;
- monotonic sample sequence and host monotonic nanoseconds;
- wall-clock UTC retained for display/export only;
- sample quality status and reason;
- stage transitions, pause/halt intervals, discontinuities, dropped/backpressured counts;
- immutable links to evidence/test/diagnostic IDs;
- annotation revision references, stored outside raw sample tables.

Raw sample rows are append-only. Existing retention and workspace isolation rules remain. Index
and watch caches are derived; a corrupt or noncanonical index never overrides canonical rows.

### 4.2 Quality vocabulary

Every sample or interval has one primary status:

```text
valid | stale | unavailable | decode_error | probe_error | dropped |
backpressured | halted | paused | discontinuity | legacy_missing
```

Reasons use stable codes and bounded details. Quality is determined when evidence permits and
can also be derived from gaps/events. A numeric value with non-valid quality remains visible as
an excluded/flagged point and is not silently used in statistics.

## 5. Analysis request and compatibility

### 5.1 Request bounds

```python
@dataclass(frozen=True)
class ComparisonRequest:
    run_ids: tuple[str, ...]                 # 2..8
    selectors: tuple[str, ...]               # 1..16
    group_ids: tuple[str, ...]               # 0..8
    difference_pairs: tuple[DifferencePair, ...]  # 0..8
    alignment: AlignmentSpec
    time_window: TimeWindow
    compatibility_mode: Literal["strict", "allow-firmware-difference"]
    max_plot_points: int                     # 100..64_000 total
```

The request is canonical JSON, rejects duplicates and unknown fields, and is limited to 64 KiB.
The service enforces a maximum of eight runs, eight groups, sixteen canonical selectors, 640,000
raw input samples, eight directed difference pairs, 64,000 returned plot points, and a 30-second
absolute query deadline. A difference pair names a baseline run, candidate run, and an explicit
1--10,000 ms maximum interpolation gap.

### 5.2 Selector identity

A selector's canonical identity includes normalized expression/path, resolved DWARF type,
width/signedness/encoding, target device, and address/source identity. Two signals are comparable
only if selector identity and value type match. Strict mode additionally requires equal target,
build, ELF, and firmware identities. `allow-firmware-difference` permits different build/ELF
only when target device, selector identity, and value type match; the response prominently
records the differing identities. Type reinterpretation and automatic name-only matching are
forbidden.

## 6. Alignment and display reduction

Alignment modes:

- **absolute:** UTC view after monotonic-to-wall mapping; clock uncertainty is returned;
- **run-relative:** each run's first selected valid sample is time zero;
- **marker-relative:** an exact marker kind/name or annotation ID is time zero per run.

A missing or ambiguous marker fails that run with a structured compatibility result; it does not
fall back to another mode. Alignment never changes raw timestamps. Statistics use selected raw
valid points within the window; display decimation is a separate deterministic product.

For an explicitly requested compatible numeric difference pair, baseline valid sample times are
the comparison grid. The candidate value is linearly interpolated only between two valid samples
whose total gap does not exceed the pair's maximum; there is no extrapolation or interpolation
across a quality, stage, or discontinuity boundary. The directed value is
`candidate - baseline`. Missing matches are quality-excluded with counts and reasons. Boolean,
enumerated, incompatible, or ambiguous selectors reject difference creation rather than coercing
values. Difference statistics use eligible pre-decimation difference points.

For line plots, the service divides each run/selector window into monotonic buckets and preserves
the first, minimum, maximum, and last point in source order, deduplicated by sample sequence.
Boolean/enumerated/state signals preserve every transition plus endpoints. Quality transition
boundaries and marker-adjacent points are always retained. The response states raw count,
eligible count, returned count, and algorithm version `stm32-monitor-decimation/1`.

## 7. Analytics result

`RunComparison` includes:

```python
@dataclass(frozen=True)
class SeriesAnalysis:
    run_id: str
    selector_id: str
    identity: FirmwareIdentity
    points: tuple[PlotPoint, ...]
    statistics: Statistics
    quality: QualitySummary
    stages: tuple[StageSummary, ...]
    markers: tuple[MarkerView, ...]
```

Numeric statistics are count, finite min/max/mean, population standard deviation, p50, p95,
first/last, and delta. Boolean/enumerated statistics are dwell duration/count per state and
transition count. Calculations exclude invalid-quality and non-finite values and report excluded
counts by reason. Empty eligible input returns `ANALYSIS_NO_VALID_SAMPLES`, not zeros.

Quality analysis provides:

- valid ratio and excluded counts/duration by status;
- gap count, longest gap, p95 inter-sample interval, dropped/backpressured totals;
- halt/pause interval count and overlap with quality gaps;
- distribution per run and selector;
- stage summaries bounded to 128 stages/run;
- explicit warnings for legacy/missing metadata.

Stage boundaries come only from recorded events/markers. There is no heuristic stage naming.

## 8. Annotations and diagnostic markers

Annotations are append-only revisions with tombstones:

```python
@dataclass(frozen=True)
class AnnotationRevision:
    annotation_id: str
    revision: int
    workspace_id: str
    run_id: str
    kind: Literal["note", "bookmark", "diagnostic-marker"]
    anchor: AnnotationAnchor
    title: str
    body: str
    tags: tuple[str, ...]
    diagnostic_session_id: str | None
    evidence_ids: tuple[str, ...]
    previous_digest: str | None
    tombstone: bool
    digest: str
```

Anchors are an exact sample sequence, a monotonic interval, or a run event ID. Titles are at
most 160 characters, bodies 8 KiB, tags 16 values of 64 characters, and evidence links 64.
The authoritative revision objects live under the 0601 shared evidence root's `annotations/`
namespace and are published through its safe public store API. Monitor may maintain a derived
workspace/run index for queries, but that index can be rebuilt from verified annotation revisions
and can never override them. Creating/editing/tombstoning requires same-origin authentication and
an expected revision; it does not modify raw history. Diagnostic markers must link to a verified
0602 session/evidence ID through Toolkit's bridge; unavailable validation fails rather than
creating an unverified link.

User text is rendered only as text. No HTML/Markdown execution, URL auto-navigation, scriptable
attributes, or rich embedded content is permitted. Exported annotation revisions retain their
hash chain and tombstones.

## 9. Service and wire protocol

New loopback-authenticated endpoints:

```text
POST /api/v1/analysis/compare
POST /api/v1/analysis/quality
GET  /api/v1/analysis/runs/<run-id>/markers
POST /api/v1/annotations
PUT  /api/v1/annotations/<id>
DELETE /api/v1/annotations/<id>
POST /api/v1/analysis/bundles
```

All POST/PUT/DELETE calls use the existing same-origin token/header and content-type rules.
Responses use versioned exact schemas, request IDs, size limits, deadlines, and cache-control
`no-store`. Cross-origin, no/incorrect token, wrong content type, oversized body, unknown field,
invalid Unicode, and non-finite number requests fail before query or mutation work.

WebSocket messages may announce `analysis.invalidated` and annotation revisions; they do not
push bulk comparison data. Clients refetch with a request revision. Backpressure retains at most
one invalidation per run and one latest revision notification per annotation.

## 10. UI behavior and accessibility

The History panel adds a Comparison workspace:

1. select two to eight runs and up to sixteen selectors/eight groups;
2. review compatibility results before running analysis;
3. choose alignment and bounded time window;
4. optionally choose directed baseline/candidate differences and brush a chart interval to replace
   the bounded query time window;
5. inspect overlaid/difference charts, per-run statistics, quality, stages, and markers;
6. add/edit/tombstone explicit annotations;
7. export an AI bundle through a deliberate button and confirmation summary.

Brush selection changes only the request's canonical `TimeWindow`, is keyboard-editable through
start/end fields, and never retains or queries an unbounded hidden range. The UI never silently
chooses an incompatible run or hidden selector. Series have redundant
color, dash, label, and accessible table identity. Quality never relies on color alone. At 200%
zoom on 1024×768 there is no two-dimensional page scrolling; panels reflow and charts retain an
accessible data table. Keyboard-only users can complete select→compare→inspect quality→add note→
export. Focus order, dialog trapping/restoration, live notices, reduced motion, and axe zero
critical/serious violations are mandatory.

Analysis state is bounded and released when the workspace closes. The UI stores IDs and request
parameters, not duplicate 640,000-sample arrays for each panel.

## 11. Explicit AI analysis bundle

The user explicitly selects runs, selectors, window, alignment, annotations, and inclusion of
diagnostic links. The server creates `stm32-monitor-analysis/1` containing:

```text
bundle.json
comparison.json
quality.json
annotations.json
artifacts/*.csv
inventory.json
```

The bundle records complete identities, request, compatibility results, raw/eligible/returned
counts, statistics, quality exclusions, marker/annotation revisions, evidence links, schema and
algorithm versions, UTC, Toolkit/Monitor versions, and every file's bytes/SHA-256. CSV uses fixed
UTF-8/LF/RFC4180 formatting and formula-injection-safe text cells. ZIP creation follows the 0602
deterministic/safe archive rules.

The bundle contains only the selected bounded data. It excludes auth values, browser storage,
absolute paths, unrelated runs/workspaces, source files, raw memory, and diagnostic artifacts not
explicitly selected. There is no send/share/upload button; creation returns a local verified
artifact reference.

## 12. Toolkit bridge and Skill

Toolkit adds OBSERVE MCP tools to list compatible Monitor runs, request a comparison/quality
result, read selected annotations/markers, and create an explicit analysis bundle. The bridge
uses Monitor's existing authenticated local endpoint, exact loopback origin, bounded timeout,
and typed response validation. It cannot open Monitor storage directly.

`stm32-monitor` Skill is updated to explain compatibility, quality exclusions, annotation
ownership, and explicit bundle consent. It may use a bundle as evidence in a diagnostic session,
but cannot create annotations/groups or export data without the user's direct request.

## 13. Error model

Stable errors include:

- `ANALYSIS_REQUEST_INVALID`, `ANALYSIS_LIMIT_EXCEEDED`, `ANALYSIS_TIMEOUT`;
- `ANALYSIS_RUN_NOT_FOUND`, `ANALYSIS_SELECTOR_NOT_FOUND`, `ANALYSIS_INCOMPATIBLE`;
- `ANALYSIS_MARKER_MISSING`, `ANALYSIS_MARKER_AMBIGUOUS`, `ANALYSIS_NO_VALID_SAMPLES`;
- `ANALYSIS_HISTORY_CORRUPT`, `HISTORY_SCHEMA_UNSUPPORTED`;
- `ANNOTATION_NOT_FOUND`, `ANNOTATION_REVISION_CONFLICT`, `ANNOTATION_LINK_INVALID`;
- `ANALYSIS_BUNDLE_INVALID`, `MONITOR_BRIDGE_UNAVAILABLE`.

Partial per-run compatibility results may accompany an overall failed comparison, but no partial
response is labelled PASS. Errors never include SQL, local roots, token values, or raw exceptions.

## 14. Security and isolation

All 0.5 protections remain: loopback-only random port, explicit `serve/open`, capability token,
exact origin, CSP and other headers, safe static assets, no remote dependencies, and workspace-
scoped storage. New tests additionally assert:

- annotation text cannot enter executable DOM, attributes, URL, console, cookies, local/session
  storage, or IndexedDB names;
- every header/CSP directive equals the frozen expected value;
- a real second-origin sentinel receives zero requests under route interception;
- analysis/bundle paths cannot cross workspaces through run, group, annotation, diagnostic, or
  evidence IDs;
- SQL wildcards, selector injection, zip/CSV injection, oversized input, and decompression bombs
  fail closed;
- concurrent clients cannot observe a stale/rebound workspace or annotation revision.

## 15. Test contract

### 15.1 Python partitions

1. v1/v2 history read and v2-only write; corrupt/legacy metadata behavior;
2. request canonicalization, bounds, selector/type/identity compatibility matrix;
3. absolute/run/marker alignment including missing/ambiguous/clock uncertainty;
4. directed numeric difference/interpolation boundaries plus numeric/state statistics, quality
   exclusions, stages, halt overlap, and empty data;
5. deterministic numeric/state decimation and mandatory boundary preservation;
6. annotation revision chain, optimistic concurrency, tombstones, link validation;
7. bundle determinism, inventory/hashes, redaction, CSV safety, archive attacks;
8. service auth/origin/content/size/deadline/error and two-workspace isolation;
9. Toolkit bridge schema/timeout/auth/reference behavior;
10. branch coverage at or above 90% for every changed Python product file.

### 15.2 TypeScript and browser partitions

1. wire decoder exactness and malformed/oversize/non-finite rejection;
2. reducer/selectors bounded state and compatibility visibility;
3. chart/table equivalence, directed difference, bounded brush/time fields, redundant identity,
   quality and marker rendering;
4. annotation dialogs, revision conflicts, text-only rendering, focus restoration;
5. 1280×720 and 1024×768@200% complete keyboard workflows;
6. axe accessibility, reduced motion, contrast, live status, chart table alternative;
7. real HTTP/WebSocket comparison, invalidation/backpressure, reconnect, isolation;
8. exact CSP/security-storage/DOM checks and real second-origin zero-request sentinel;
9. deterministic distribution and installed-wheel UI smoke;
10. five-minute live plus analytics performance acceptance.

Every changed Python file and every changed TypeScript product file must meet at least 90% branch
coverage in its owning shard. Generated `ui_dist` is tested by manifest and installed-product
smoke, not counted as handwritten source.

## 16. Performance contract

The reference dataset is eight runs × eight selectors × 10,000 raw samples = 640,000 samples,
eight directed difference pairs, and no more than 64,000 returned plot points. Tests use at least
three warmups and ten measured runs under CPython 3.10 and 3.12 without coverage.

| Operation | Ceiling |
|---|---:|
| complete comparison request | p95 1,000 ms |
| quality computation | p95 750 ms |
| browser analysis update after response | p95 150 ms |
| long tasks during interaction | zero tasks >=200 ms |
| five-minute retained-heap slope | <=2 MiB/min |
| five-minute queue growth | 0 |

Each also permits at most 15% regression from its accepted baseline. All 0.5 sampling, history,
export, UI responsiveness, queue, memory, and five-minute thresholds remain unchanged. The test
records raw samples, returned points, per-stage durations, CPU, heap/retained heap, GC, queue,
long tasks, browser, OS, Python, and artifact hashes.

## 17. Candidate and final release matrix

0603 first runs a collect-all candidate matrix containing:

- complete 0601 and 0602 regression/immutability contracts;
- Windows/Linux CPython 3.10/3.12 Monitor and Toolkit shards;
- Node typecheck, lint, unit, branch coverage, build, dist/audit, and deterministic manifest;
- Chromium functional/security/accessibility/isolation/performance at 1280 and 1024/200%;
- Firefox/WebKit core comparison and annotation flows on Linux;
- real-board live/analytics link to the accepted 0602 diagnostic scenario;
- offline wheels, managed launchers, plugin/Skills/version/docs inventory;
- source, schema mirror, dependency, expected-path, artifact, and clean-tree checks.

After candidate PASS, ordered preflight runs every final gate individually at the same CodeHead
and catalog/support digests. The 0603 product CodeHead is then frozen. No optimization, product,
test, helper, dependency, documentation, Skill, or acceptance correction is allowed without a new
CodeHead and a new preflight. Exactly one complete fail-fast final matrix is run on the frozen
CodeHead. A final tracked report is created only after overall PASS and is report-only.

Tag creation, push, PR/merge, and remote branch cleanup are separate user-authorized actions and
are not implied by matrix PASS or this specification.

## 18. Completion conditions

0603 and the 0.6 product succeed when:

1. history v2 writes rich quality/identity metadata while v1 remains safely readable;
2. bounded comparisons reject false selector/type/target/firmware equivalence;
3. alignment, decimation, statistics, quality, stages, and halt impact are deterministic;
4. annotations/markers are append-only, safe, revisioned, linked, and workspace-isolated;
5. the UI is complete by keyboard, accessible at 200%, secure, and bounded for five minutes;
6. explicit AI bundles are deterministic, verified, minimally scoped, and never uploaded;
7. every changed product file meets branch coverage and all absolute/regression thresholds pass;
8. all 0.5, 0601, 0602, platform, browser, hardware, install, integrity, and inventory gates pass;
9. one immutable CodeHead passes ordered preflight and exactly one complete final matrix;
10. the final report-only commit records the evidence, and any remote release action waits for
    explicit user authorization.
