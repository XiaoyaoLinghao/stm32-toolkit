# STM32TK-0603 Monitor Cross-Run Analytics Design

**Status:** Approved module design baseline
**Date:** 2026-08-14
**Module:** `STM32TK-0603-MONITOR-ANALYTICS`
**Accepted base:** the accepted report commit of `STM32TK-0602-DIAGNOSTIC-LOOP`
**Fixed program base:** `bb6bc5e9ee937e4ce53996b31f25bf1109ffe13f` (`v0.5.0`)
**Specification owner:** Codex
**Implementation owner:** Codex and its local derived agents under the permanent project policy
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

- non-destructive Monitor history structure extension in the existing `monitor.sqlite3`, with
  read compatibility for every accepted 0.5 row;
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

## 4. History storage extension

### 4.1 Compatibility

Monitor continues to use exactly one workspace database, `monitor.sqlite3`. The implementation
performs one non-destructive transactional structural upgrade of that database: it may add tables,
columns, indexes, triggers, and internal numeric metadata needed by 0603, but it must not change,
delete, reinterpret, or change the identity of any accepted 0.5 history row. Acceptance is based
on logical observable invariants, not SQLite file, page, or row-storage byte equality. Before the
upgrade, the test records every accepted 0.5 table's original-column list, row count, primary key,
key/value tuples, and a canonical inventory SHA-256. Tables and rows are sorted by UTF-8 bytewise
table name and primary-key tuple; every table name, column name, key, and cell is encoded as an
unsigned 64-bit big-endian byte length followed by tagged bytes (`N` for null, `I` plus canonical
ASCII decimal for integer, `R` plus IEEE-754 binary64 big-endian bytes for real, `T` plus UTF-8 for
text, and `B` plus raw bytes for blob). The SHA-256 covers that complete length-prefixed stream.
After upgrade, every original-column row count, key/value tuple, and inventory hash must match and
`PRAGMA integrity_check` must return exactly one row containing `ok`.

Failure injection after every upgrade statement must roll back atomically. After reopening, the
canonical inventory of the original schema definitions and all original data must equal the
pre-upgrade inventory, and `PRAGMA integrity_check` must again return `ok`; no partial new object or
metadata version may remain. No acceptance assertion compares the database file, SQLite pages, or
physical row bytes. The public table, column, event, and payload semantics introduced by 0603 use
descriptive names rather than `v1`/`v2`; numeric versions are reserved for internal storage
metadata only.

The reader projects accepted 0.5 rows into the extended analysis view with explicit
`legacy_missing` quality metadata; it does not invent firmware, marker, stage, pause, or halt facts.
Unknown future internal storage versions fail `HISTORY_SCHEMA_UNSUPPORTED`.

The history extension adds:

- complete `FirmwareIdentity` fields and source snapshot digest;
- monotonic sample sequence and host monotonic nanoseconds;
- wall-clock UTC retained for display/export only;
- sample quality status and reason;
- stage transitions, pause/halt intervals, discontinuities, dropped/backpressured counts;
- immutable links to evidence/test/diagnostic IDs;
- annotation revision references, stored outside raw sample tables.

Raw sample rows are append-only in normal product operation: no edit, replacement, or semantic
reinterpretation is permitted. Existing bounded, explicitly controlled retention GC may delete
expired canonical rows and their dependants under the accepted 0.5 retention contract. Existing
workspace isolation rules remain. Index and watch caches are derived; a corrupt or noncanonical
index never overrides canonical rows.

### 4.2 Quality vocabulary

Every sample or interval has one primary status:

```text
valid | stale | unavailable | decode_error | probe_error | dropped |
backpressured | halted | paused | discontinuity | legacy_missing
```

Reasons use stable codes and bounded details. Quality is determined when evidence permits and
can also be derived from gaps/events. A numeric value with non-valid quality remains visible as
an excluded/flagged point and is not silently used in statistics.

When statuses overlap, the primary-status precedence from highest to lowest is:

```text
discontinuity > decode_error > probe_error > unavailable > halted > paused >
dropped > backpressured > stale > legacy_missing > valid
```

All applicable bounded reason codes remain attached even though only one primary status is used.
Status durations are clipped to the canonical request window before aggregation; zero-duration
boundaries contribute counts but no duration.

## 5. Analysis request and compatibility

### 5.1 Request bounds

The compare and quality endpoints accept one closed `AnalysisRequest` JSON object. Every object
below has `additionalProperties: false`; every listed field is required unless marked optional.
JSON integers reject booleans, fractions, exponent overflow, and values outside their stated range.
All strings are valid UTF-8 NFC without C0/C1 controls, bidi overrides, or unpaired surrogates.
String length limits below count Unicode scalar values; the 64 KiB request limit counts encoded
UTF-8 bytes.

| Type | Closed JSON fields |
|---|---|
| `AnalysisRequest` | `runs: RunSelector[2..8]`; `selectors: SelectorRef[0..16]`; `groups: GroupSelector[0..8]`; `differencePairs: DifferencePair[0..8]`; `alignment: AlignmentSpec`; `timeWindow: TimeWindow`; optional `compatibilityMode: "strict" | "allow-firmware-difference"` (omission means `strict`); `maxPlotPoints: integer 100..64000` |
| `RunSelector` | `runId: CanonicalUuid` |
| `GroupSelector` | `groupId: CanonicalUuid`; `expectedRevision: integer 1..2147483647` |
| `SelectorRef` | `selectorId: SelectorId` |
| `DifferencePair` | `baselineRunId: CanonicalUuid`; `candidateRunId: CanonicalUuid`; `selectorId: SelectorId`; `maxInterpolationGapMs: integer 1..10000` |
| `TimeWindow` | `startNs: signed 64-bit integer`; `endNs: signed 64-bit integer`, with `startNs < endNs` |

`CanonicalUuid` is the lowercase hyphenated RFC 4122 text form matching
`^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$`.
`SelectorId` is exactly 64 lowercase hexadecimal characters and refers to an immutable selector
record already stored by Monitor. The wire never accepts a raw selector expression or path.

`AlignmentSpec` is the following closed discriminated union:

| `mode` | Exact remaining fields and rules |
|---|---|
| `absolute` | no other fields |
| `run-relative` | no other fields |
| `marker-relative` with recorded marker | `markerSource: "recorded"`; `markerKind: string 1..64` matching `^[a-z][a-z0-9._-]{0,63}$`; `markerName: string 1..160`; no annotation fields |
| `marker-relative` with annotation | `markerSource: "annotation"`; `annotationId: CanonicalUuid`; optional `intervalBoundary: "start" | "end"`; no recorded-marker fields. `intervalBoundary` is required exactly when the resolved annotation anchor is an interval and forbidden otherwise. |

`TimeWindow` values are in the selected alignment coordinate: Unix epoch nanoseconds for
`absolute`, or signed nanoseconds from the resolved zero for relative modes.

Request arrays reject duplicate identity keys: `runs` by `runId`, `groups` by `groupId`, selectors
by `selectorId`, and differences by `(baselineRunId,candidateRunId,selectorId)` regardless of gap.
Every difference pair must reference two distinct selected `runId` values and one selector present
after expansion. A group is resolved at
exactly `expectedRevision`; missing, stale, empty, cross-workspace, or multiply-resolved groups fail
respectively with `ANALYSIS_GROUP_NOT_FOUND`, `ANALYSIS_GROUP_REVISION_CONFLICT`,
`ANALYSIS_GROUP_EMPTY`, `ANALYSIS_INCOMPATIBLE`, or `ANALYSIS_GROUP_AMBIGUOUS`. Direct `selectors`
may be empty only when group expansion followed by `selectorId` deduplication yields 1..16 selectors;
otherwise the request fails `ANALYSIS_REQUEST_INVALID` before any history read. A selector ID that
does not resolve to exactly one immutable selector record fails `ANALYSIS_SELECTOR_NOT_FOUND` or
`ANALYSIS_SELECTOR_AMBIGUOUS`.

The request body is limited to 64 KiB of UTF-8 JSON. Groups are expanded first, selector IDs are
deduplicated by lowercase byte value, and the sixteen-selector limit is enforced before any history
read. The 640,000 input limit means scalar observations after group expansion, not batch rows or
serialized sample objects. The service also enforces a maximum of eight runs, eight groups, eight
directed difference pairs, and 64,000 returned plot points.
The plot-point cap is hard: if mandatory endpoints, state transitions, quality boundaries, and
marker-adjacent points alone exceed it, the request fails `ANALYSIS_LIMIT_EXCEEDED` with the exact
required minimum; mandatory points are neither discarded nor returned above the cap. One
30-second monotonic absolute deadline covers validation, reads, computation, bundle preparation
when requested, and response serialization. A difference pair names a baseline run, candidate
run, and an explicit 1--10,000 ms maximum interpolation gap.

### 5.2 Selector identity

A selector has two closed stored/response identities:

| Type | Closed JSON fields |
|---|---|
| `LogicalSelectorIdentity` | `targetDevice: string 1..128`; `selectorKind: "expression" | "path"`; `normalizedSelector: string 1..4096`; `valueType: string 1..1024`; `widthBits: integer 1..1048576`; `signedness: "signed" | "unsigned" | "not-applicable"`; `encoding: "integer" | "float" | "boolean" | "enumeration" | "pointer" | "bytes"` |
| `SelectorResolutionIdentity` | `buildIdentitySha256: Sha256 | null`; `elfSha256: Sha256 | null`; `sourceSnapshotSha256: Sha256 | null`; `addressHex: HexU64 | null`; `sourceFileSha256: Sha256 | null`; `sourceLine: integer 1..2147483647 | null`; `dwarfDieOffsetHex: HexU64 | null`; `resolvedDwarfType: string 1..1024 | null` |

`Sha256` is exactly 64 lowercase hexadecimal characters. `HexU64` is exactly `0x` plus sixteen
lowercase hexadecimal digits. Null resolution fields are allowed only for projected accepted 0.5
rows and are reported as `legacy_missing`; strict comparison rejects them.

`normalizedSelector` is never normalized from analysis-wire input. New history writes use the
accepted Monitor selector canonicalizer before storing the immutable selector record; projected
0.5 rows use their already accepted canonical selector kind/text without reinterpretation.
`selectorId` is `SHA-256` of the UTF-8 bytes of RFC 8785 canonical JSON for the complete
`LogicalSelectorIdentity` object, prefixed by the ASCII domain string
`stm32-monitor-selector-id/1\n`. Thus input ordering and locale cannot affect it.

The **logical identity** is target device plus normalized expression/path and resolved value type,
width, signedness, and encoding. The **resolution identity** records build, ELF, source snapshot,
address/source location, and resolved DWARF facts.
Two signals are comparable only when their logical identities match. `strict` is the default and
also requires equal resolution and firmware identities. The explicitly requested
`allow-firmware-difference` mode permits resolution/build/ELF/firmware differences when logical
identity matches, and the response prominently records every differing resolution identity.
Type reinterpretation and automatic name-only matching are forbidden.

## 6. Alignment and display reduction

Alignment modes:

- **absolute:** UTC view after monotonic-to-wall mapping; clock uncertainty is returned;
- **run-relative:** each run's first selected valid sample is time zero;
- **marker-relative:** an exact marker kind/name or annotation ID is time zero per run; an interval
  annotation must explicitly select its `start` or `end` boundary.

A missing or ambiguous marker, including an interval annotation without an explicit boundary,
fails that run with a structured compatibility result; it does not fall back to another mode.
Alignment never changes raw timestamps. Statistics use selected raw valid scalar observations
within the window; display decimation is a separate deterministic product.

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
boundaries and marker-adjacent points are always retained.

The 64,000-point limit is one global budget across ordinary series and directed-difference series.
Budgeting first constructs every stream independently, deduplicates its mandatory points by sample
sequence (or by the canonical difference-grid key), and orders streams by this bytewise key.
Ordinary mandatory points are the endpoints, every state transition, both sides of each quality/
stage/discontinuity boundary, and the nearest point on each side of every marker. Difference-stream
mandatory points are its first/last eligible grid point and both eligible sides of each inherited
quality/stage/discontinuity boundary; missing/excluded grid positions are counts, not plot points.
The stream key is:
ordinary series `(0x00, runId, selectorId)` followed by differences
`(0x01, baselineRunId, candidateRunId, selectorId, maxInterpolationGapMs-as-uint32-be)`. It then:

1. sums all mandatory counts; if the sum exceeds `maxPlotPoints`, fail
   `ANALYSIS_LIMIT_EXCEEDED` with `requiredMinimum` equal to that sum;
2. sets `remaining = min(maxPlotPoints - mandatoryTotal, totalOptionalPoints)`;
3. for each stream with `optionalCount`, assigns
   `floor(remaining * optionalCount / totalOptionalPoints)` optional points;
4. assigns the leftover points one at a time by descending exact fractional remainder
   `(remaining * optionalCount) mod totalOptionalPoints`, breaking ties by the stream key above.

If `totalOptionalPoints` is zero, allocation ends after mandatory points and performs no division.
Zero-optional streams receive no remainder. Integer arithmetic is unbounded and locale-independent.
Each stream's decimator receives only its resulting optional quota in addition to all mandatory
points. Canonical stream sorting occurs before allocation, so permutations of runs, selectors,
groups, or difference pairs produce byte-identical allocations and returned points. The response
states raw count, eligible count, mandatory count, allocated optional count, returned count, and
algorithm version `stm32-monitor-decimation/1`.

## 7. Analytics result

`RunComparison` includes:

```python
@dataclass(frozen=True)
class SeriesAnalysis:
    run_id: str
    selector_id: str
    firmware_identity: FirmwareIdentity
    logical_identity: LogicalSelectorIdentity
    resolution_identity: SelectorResolutionIdentity
    points: tuple[PlotPoint, ...]
    statistics: Statistics
    quality: QualitySummary
    stages: tuple[StageSummary, ...]
    markers: tuple[MarkerView, ...]
```

Numeric statistics are count, finite min/max/mean, population standard deviation, p50, p95,
first/last, and delta. p50 and p95 are calculated only from valid finite scalar observations using
the frozen nearest-rank percentile rule after deterministic numeric ordering. Boolean/enumerated
statistics are dwell duration/count per state and transition count. Calculations exclude
invalid-quality and non-finite values and report excluded counts by reason. Empty eligible input
returns a series-level `ANALYSIS_NO_VALID_SAMPLES`, not zeros; the overall request fails with that
code only when no requested series has eligible input.

Quality analysis provides:

- valid ratio and excluded counts/duration by status;
- gap count, longest gap, p95 inter-sample interval, dropped/backpressured totals;
- halt/pause interval count and overlap with quality gaps;
- distribution per run and selector;
- stage summaries bounded to 128 stages/run;
- explicit warnings for legacy/missing metadata.

The p95 inter-sample interval uses only consecutive valid scalar observations inside the clipped
request window and never spans a stage, pause/halt, quality, or discontinuity boundary.

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
and can never override them. Creating/editing/tombstoning requires same-origin authentication.
Create uses no prior revision; edit and tombstone carry an explicit integer `expectedRevision` in
the request body and fail on any mismatch. These operations do not modify raw history. Diagnostic
markers must link to a verified
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
parameters, not duplicate 640,000-observation arrays for each panel.

## 11. Explicit AI analysis bundle

The user explicitly selects runs, selectors, window, alignment, annotations, and inclusion of
diagnostic links. The request also carries an explicit canonical UTC creation time frozen by the
calling operation. The server creates `stm32-monitor-analysis/1` containing:

```text
bundle.json
comparison.json
quality.json
annotations.json
artifacts/*.csv
inventory.json
```

The explicit creation time is the only creation timestamp used during serialization; bundle
generation never reads the wall clock. Identical selected canonical inputs and the same explicit
creation time produce byte-identical bundles. The bundle records complete identities, request,
compatibility results, raw/eligible/returned
counts, statistics, quality exclusions, marker/annotation revisions, evidence links, schema and
algorithm versions, UTC, Toolkit/Monitor versions, and every file's bytes/SHA-256. CSV uses fixed
UTF-8/LF/RFC4180 formatting and formula-injection-safe text cells. ZIP creation follows the 0602
deterministic/safe archive rules.

The bundle contains only the selected bounded data. It excludes auth values, browser storage,
absolute paths, unrelated runs/workspaces, source files, raw memory, and diagnostic artifacts not
explicitly selected. There is no send/share/upload button; creation returns a local verified
artifact reference.

## 12. Toolkit bridge and Skill

Toolkit adds the exact OBSERVE MCP operations `monitor_analysis_list_runs`,
`monitor_analysis_compare`, `monitor_analysis_quality`, `monitor_analysis_read_annotations`,
`monitor_analysis_read_markers`, and `monitor_analysis_create_bundle`. Their closed request and
response schemas mirror `stm32-monitor-analysis/1`; the create operation returns only a typed
workspace-scoped artifact reference, byte count, and SHA-256. The bridge
uses Monitor's existing authenticated local endpoint, exact loopback origin, bounded timeout,
and typed response validation. It cannot open Monitor storage directly.

`stm32-monitor` Skill is updated to explain compatibility, quality exclusions, annotation
ownership, and explicit bundle consent. It may use a bundle as evidence in a diagnostic session,
but cannot create annotations/groups or export data without the user's direct request.

## 13. Error model

Stable errors include:

- `ANALYSIS_REQUEST_INVALID`, `ANALYSIS_LIMIT_EXCEEDED`, `ANALYSIS_TIMEOUT`;
- `ANALYSIS_RUN_NOT_FOUND`, `ANALYSIS_SELECTOR_NOT_FOUND`, `ANALYSIS_SELECTOR_AMBIGUOUS`,
  `ANALYSIS_GROUP_NOT_FOUND`, `ANALYSIS_GROUP_REVISION_CONFLICT`, `ANALYSIS_GROUP_EMPTY`,
  `ANALYSIS_GROUP_AMBIGUOUS`, `ANALYSIS_INCOMPATIBLE`;
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
- every header/CSP directive equals the accepted 0.5 values frozen in the inherited service/auth
  tests and 0600 catalog; 0603 may add no alternative expected-value source;
- a real second-origin sentinel receives zero requests under route interception;
- analysis/bundle paths cannot cross workspaces through run, group, annotation, diagnostic, or
  evidence IDs;
- SQL wildcards, selector injection, zip/CSV injection, oversized input, unsafe archive entry
  names, case-fold collisions, and excessive bundle output fail closed;
- concurrent clients cannot observe a stale/rebound workspace or annotation revision.

## 15. Test contract

### 15.1 Python partitions

1. one-database non-destructive transactional structure upgrade, accepted 0.5 original-column
   canonical inventory/count/key/value preservation, exact `integrity_check`, per-statement failure
   injection and logical rollback, descriptive new semantics, corrupt/legacy metadata behavior,
   and future internal storage-version rejection;
2. closed wire-schema field/type/format/limit/unknown-field tests, stored selector IDs, group
   empty/ambiguity/revision behavior, request canonicalization and bounds, and the selector/type/
   logical/resolution identity compatibility matrix;
3. absolute/run/marker alignment including missing/ambiguous/clock uncertainty and explicit
   interval start/end anchors;
4. directed numeric difference/interpolation boundaries plus numeric/state statistics, frozen
   valid-scalar percentiles, quality precedence and clipped durations, stages, halt overlap, and
   series-level/overall empty data;
5. deterministic numeric/state decimation, global mandatory-first/proportional/remainder budget
   allocation, golden allocations, input-permutation invariance, and mandatory boundary preservation;
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

The reference dataset is eight runs × eight selectors × 10,000 scalar observations = 640,000
post-expansion scalar observations,
eight directed difference pairs, and no more than 64,000 returned plot points. The common program
calibration method runs independently under CPython 3.10 and 3.12 without coverage. The following
values are user-facing design maxima. A provisional result above a maximum requires implementation
improvement without changing workload or maximum; only within-maximum thresholds may be committed
as the accepted calibration before optional post-baseline optimization and candidate.

| Operation | Design maximum |
|---|---:|
| complete comparison request | p95 1,000 ms |
| quality computation | p95 750 ms |
| browser analysis update after response | p95 150 ms |
| long tasks during interaction | zero tasks >=200 ms |
| five-minute retained-heap slope | <=2 MiB/min |
| five-minute queue growth | 0 |

Each calibrated result must also stay within 15% of its accepted baseline. All 0.5 sampling,
history, export, UI responsiveness, queue, memory, and five-minute thresholds remain unchanged.
The five-minute gate retains its accepted continuous warmup/measurement windows and adds a fixed
analytics interaction cadence. The test records scalar observations, returned points, per-stage durations,
CPU, heap/retained heap, GC, queue, long tasks, browser, OS, Python, and artifact hashes.

## 17. Windows candidate and hardware-pending release handoff

Before each measured UI/backend hot path, 0603 freezes its exact performance workload and design
maximum; before candidate it freezes the within-maximum accepted calibration. After every 0603
product, packaging, Chromium, and release test exists and before candidate, it fills only its
reserved catalog families with exact commands and collected nodes and freezes the complete final
catalog/node/performance digests. It then runs one Windows-only collect-all candidate containing:

- complete 0601/0602 software contract and immutability checks plus regressions selected by the
  catalog impact map;
- Windows CPython 3.10/3.12 Monitor and Toolkit shards;
- Node typecheck, lint, unit, branch coverage, build, dist/audit, and deterministic manifest;
- Chromium functional/security/accessibility/isolation/performance at 1280 and 1024/200%;
- offline wheels, managed launchers, plugin/Skills/version/docs inventory;
- source, schema mirror, dependency, expected-path, artifact, and clean-tree checks.

Linux ownership, Linux shards, Firefox/WebKit, and Linux evidence-package transfer are outside
0603 and deferred to a later program increment. They are not prerequisites for the 0603 candidate
or for freezing its product CodeHead.

The 0601 public candidate/recovery contract is authoritative. The candidate wrapper alone creates
and mutates the one authoritative `<candidateRoot>/candidate-ledger.json`; neither orchestration nor
the verifier may pre-create, replace, repair, or synthesize it. Orchestration may create exactly one
separate `candidate-invocation-context.json` outside the candidate root to retain the original
invocation values, but that context is not evidence, is not a ledger, and can never substitute for
the wrapper ledger. The 0603 specialization uses the exact closed 0601 ledger fields `schema:
"stm32-candidate-ledger/1"`, `module:"STM32TK-0603"`, `candidate_run_id`, `expected_code_head`,
`controller_path`, `candidate_root`, `evidence_root`, `catalog_sha256`, `performance_sha256`,
`support_profile_sha256`, `checkpoint`, `state`, `created_at_utc`, and `updated_at_utc`.

The invocation context and adjacent `candidate-invocation-context.json.sha256` are both create-new.
The context is canonical compact UTF-8 JSON with no BOM and one trailing LF; the sidecar is exactly
its 64-character lowercase SHA-256 plus one LF. Its closed fields are `schema`, `module`, `shard`,
`candidate_run_id`, `code_head`, `frozen_worktree`, `origin_url`, `candidate_root`, `evidence_root`,
`support_profile`, `wrapper_ledger`, `catalog_sha256`, `performance_sha256`,
`support_profile_sha256`, `controller_sha256`, and `verifier_sha256`. Every new PowerShell process
must validate the context byte digest from the sidecar before parsing any JSON field, then reject
unknown/missing fields or noncanonical reserialization before using it.
`schema` is exactly `stm32-candidate-invocation-context/1`, `module` is exactly `STM32TK-0603`,
`shard` is exactly `windows`, `candidate_run_id` is the canonical lowercase hyphenated UUID,
`code_head` is lowercase 40-hex, all five digest fields are lowercase 64-hex, `origin_url` is the
exact repository URL below, and every path field is a canonical absolute Windows path.

Before every resume, reconciliation, or final-release-input generation, orchestration verifies that
`frozen_worktree` is a canonical absolute path, its exact HEAD equals `code_head`, its `origin` URL
is exactly `https://github.com/XiaoyaoLinghao/stm32-toolkit.git`, and its tracked/untracked status is
clean. It then re-derives controller, verifier, catalog, and performance paths from fixed relative
paths under that verified worktree and verifies their actual SHA-256 against the frozen context or
ledger value. A path or executable read from the context is never executed. Reconciliation must in
particular hash the actual re-derived verifier immediately before invocation and require equality
with `verifier_sha256`.

The initial candidate has the same pre-execution rule. Each of the four executable PowerShell
blocks is self-contained and begins from the current frozen worktree: it verifies exact HEAD,
origin URL, and clean status, then resolves the fixed POSIX-relative paths
`tools/release/path_contract_0600.ps1`, `tools/release/run_0600_candidate.ps1`,
`tools/release/verify_0600_release.py`, `tools/release/gates_0600.json`, and
`tools/release/performance_0600.json`. For every path, `git rev-parse "<HEAD>:<POSIX-path>"` must
name a committed blob and equal `git hash-object -- <absolute-working-path>`. Only after all five
comparisons pass may the process dot-source the single committed path helper and calculate SHA-256
or invoke anything. This working-blob check is mandatory even when `status` is clean and therefore
closes `skip-worktree`/index concealment. Context never supplies executable paths.
The bootstrap retains each committed blob ID. Immediately before every controller or verifier
process invocation, orchestration re-runs `git hash-object` for the path helper and all four fixed
controller/verifier/catalog/performance files and compares each result to its retained committed
blob. It then rechecks the invoked executable and all context-bound fixed inputs against their
frozen SHA-256 values, with no intervening file operation before invocation. Thus an initial
controller replacement after context construction cannot legitimize its own digest. Tests mutate
working bytes after the first validation but before execution and require fail-closed TOCTOU
rejection for initial, resume, reconciliation, generation, and post-generation verification.

All Windows absolute-path validation uses one PowerShell 5.1-compatible canonicalization contract:
the input is non-empty; drive-relative (`C:foo`), root-relative (`\foo`), device-prefix
(`\\?\`/`\\.\`), forward-slash, dot-segment, and other alias forms are rejected; then
`[IO.Path]::GetFullPath()` must succeed and its result must be ordinally identical to the input.
The newer framework fully-qualified-path convenience API is forbidden because it is unavailable in
the frozen Windows PowerShell 5.1 environment.
The only implementation is
`tools/release/path_contract_0600.ps1::ConvertTo-CanonicalAbsolutePath`; no fenced command carries
an inline substitute. Its exact call form is `ConvertTo-CanonicalAbsolutePath -Path <string>
-Name <string>`. Non-root trailing separators are rejected as aliases (a drive root such as `C:\`
remains valid). Its Windows PowerShell 5.1 tests freeze that trailing-separator behavior as
well as drive-relative, root-relative, device-prefix, forward-slash, dot-segment, and alias cases.

A candidate interruption is resumable at most once and only with a separately reviewer-authored
RFC 8785 canonical JSON `RecoveryRecord` containing exactly these fields and no others:

| Field | Frozen value/type |
|---|---|
| `classification` | literal `RECOVERABLE_INFRA_ERROR` |
| `event` | exactly one of `HOST_POWER_OR_REBOOT`, `RUNNER_LOSS_BEFORE_CHILD_RESULT`, `PHYSICAL_USB_OR_PROBE_REMOVAL`, `TARGET_POWER_LOSS` |
| `reviewer` | non-empty reviewer identity using the 0601 bounded string contract |
| `recorded_at_utc` | canonical UTC using the 0601 timestamp contract |
| `run_kind` | literal `candidate-0603` |
| `run_id` | the original 0603 candidate run ID as a canonical lowercase hyphenated UUID (`8-4-4-4-12`) |
| `code_head` | the original lowercase 40-hex 0603 CodeHead |
| `checkpoint` | the exact absolute checkpoint path recorded by the wrapper ledger |
| `interrupted_attempt_digest` | lowercase SHA-256 of the retained interrupted attempt named by the wrapper ledger |

No other event token is recoverable. Resume uses only the complete frozen interface
`-ResumeCandidateRun -CandidateLedger <absolute-wrapper-ledger> -RecoveryRecord
<absolute-recovery-record>`; no original input is accepted again on the resume command line.
Instead, the immutable wrapper ledger and checkpoint bind the original module, shard, run ID,
evidence root, CodeHead, controller, catalog, performance, and support-profile digests. Before a
resumed child starts, the wrapper validates the recovery record against its ledger and retained
attempt and rejects changed, missing, relative, cross-root, already-consumed, or second-resume
state. Legacy `-ResumeRun`, inferred-ledger, and context-as-ledger forms are forbidden.

Initial reconciliation and post-resume reconciliation both reopen the wrapper ledger from its one
canonical path; cached orchestration values are insufficient. Reconciliation rejects unknown or
missing ledger fields, a noncanonical ledger path, any run-ID/CodeHead/path/input/digest mismatch,
any recovery path/digest/history change, or any result that is not bound to the complete original
inputs. Every controller, wrapper, verifier, catalog, performance file, schema, and test path is
resolved absolutely from the frozen 0603 worktree recorded in the original invocation.

The reconciled 0603 candidate is the final product CodeHead. The candidate does not run a real-board
Monitor/analytics link or the accepted 0602 diagnostic scenario. After Windows candidate PASS,
0603 may report `SOFTWARE_COMPLETE_HARDWARE_PENDING` and hands the unchanged CodeHead and frozen
digests to the unified post-candidate 0.4+0.6 hardware activity. That activity alone owns the real
board/probe link and diagnostic scenario. Final `v0.6.0` acceptance still requires those hardware
gates to PASS against the same CodeHead. Any product, test, helper, dependency, documentation,
Skill, gate, or threshold edit invalidates the frozen CodeHead and requires a new Windows candidate
before hardware is retried.

0603 creates no report-only commit. The 0600 release-acceptance plan alone owns final readiness,
the unified hardware reconciliation, the final logical matrix, and the final tracked report.

After candidate reconciliation, 0603 emits external `final-release-inputs.json` and adjacent
`final-release-inputs.json.sha256`, both with create-new semantics. The JSON uses the same canonical
UTF-8/no-BOM/trailing-LF rule and the sidecar is its lowercase SHA-256 plus LF; generation is not
complete until rereading both proves byte/digest equality. The JSON is the immutable
software/code input to 0600 Task 1. It is not the candidate ledger and not the 0600 release ledger;
0600 combines it with a separately create-new, user-owned `hardware-campaign-inputs.json` only when
the deferred board campaign is ready, then deterministically creates the one `release-ledger.json`.
Its root object is closed and
contains exactly `repositoryUrl`, `programBase`, `0400Product`, `0400Report`, `0601Product`,
`0601Report`, `0602Product`, `0602Report`, `0603Product`, `governance`, and `artifacts`. SHA fields are lowercase
40-hex Git object IDs. `repositoryUrl` is exactly
`https://github.com/XiaoyaoLinghao/stm32-toolkit.git`; `programBase` is exactly
`bb6bc5e9ee937e4ce53996b31f25bf1109ffe13f`; `0400Product` is exactly
`96966c461e7e11bff965027d8d498dd40ea5fd55`; and `0400Report` is exactly
`0ee0a5037b3bd158eea5bd312fce7feaadecbfc6`. `0601Product`/`0601Report` and
`0602Product`/`0602Report` come from their accepted report chains; `0603Product` is the reconciled
candidate CodeHead. The root also contains required closed `governance` with exactly
`specification_owner`, `implementation_owner`, `reviewer`, `windows_evidence_owner`,
`hardware_evidence_owner`, `remote_state`, `remote_actions`, and `bounded_overrides`.
`implementation_owner` is exactly `Codex/local derived agents`; `remote_actions` is an empty array
unless the user has separately authorized exact remote actions, and no authorization is inferred
from candidate PASS. The six owner/state fields are strings; `remote_actions` and
`bounded_overrides` are arrays whose entries must come from explicit recorded authorization rather
than inferred candidate state. `artifacts` is sorted by `(kind, path)` and contains closed objects with
exactly `kind`, `path`, `bytes`, and `sha256`; `kind` is one of `catalog`, `controller`, `verifier`,
`spec`, `plan`, `lock`, or `software-support`, `bytes` is an integer `0..2^63-1`, and `sha256` is
64 lowercase hex. Repository artifacts use normalized POSIX-relative paths; external Windows
software-support inputs use normalized absolute paths. The inventory includes every frozen catalog,
controller (including the committed path-contract helper), verifier, 0600/0601/0602/0603 spec and plan, dependency lock, and Windows feasibility
profile/manifest required by the software candidate. It does not invent board or firmware facts.
The generator rejects omissions, extras,
duplicates, path aliases, byte/digest mismatches, wrong ancestry/report-only changes, or an existing
output file.

Tag creation, push, PR/merge, and remote branch cleanup are separate user-authorized actions and
are not implied by matrix PASS or this specification.

## 18. Completion conditions

The 0603 software candidate satisfies items 1--9 below. Final `v0.6.0` additionally satisfies
item 10:

1. one `monitor.sqlite3` receives a non-destructive transactional structure upgrade, accepted 0.5
   original-column row counts, keys, values, canonical inventory hashes, and meaning remain
   unchanged, and new runs write rich quality/identity metadata;
2. bounded comparisons reject false selector/type/target/firmware equivalence;
3. alignment, decimation, statistics, quality, stages, and halt impact are deterministic;
4. annotations/markers are append-only, safe, revisioned, linked, and workspace-isolated;
5. the UI is complete by keyboard, accessible at 200%, secure, and bounded for five minutes;
6. explicit AI bundles are deterministic, verified, minimally scoped, and never uploaded;
7. every changed product file meets branch coverage and all absolute/regression thresholds pass;
8. all Windows software, Chromium, install, integrity, inventory, and impact-selected inherited
   gates pass at the 0603 candidate;
9. that candidate is frozen as the final product CodeHead and may be labelled
   `SOFTWARE_COMPLETE_HARDWARE_PENDING`; its wrapper ledger/recovery history reconcile and its
   closed `final-release-inputs.json` is the immutable software/code input to 0600 Task 1;
10. final `v0.6.0` acceptance requires hardware PASS on the unchanged CodeHead, the final report is
    owned only by 0600, and every remote release action waits for explicit user authorization.
