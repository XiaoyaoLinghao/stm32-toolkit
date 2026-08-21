# STM32 Toolkit 0.6 VS-03 Target Replay and Monitor Verification Design

**Status:** Frozen for local implementation under the approved 0.6 integration design  
**Runtime:** CPython >=3.12,<3.13 only  
**Accepted base:** `2664f0ec903a6a0db1f2f55ab7ed07996a8f6862`  
**Specification/review owner:** primary `gpt-5.6-sol` agent  
**Implementation owner:** one `gpt-5.6-luna` subagent at `max` reasoning  
**Remote authority:** none; no push, PR mutation, merge, close, or remote branch operation

## 1. Slice outcome and boundary

VS-03 makes the approved integration design's Scenario B executable through public application
services. A frozen, explicitly non-physical Target replay produces a failed-before TestRun. A second
replay produces a fixed-after TestRun. Compatible Monitor replay windows are aligned and compared,
one hypothesis is supported and one is refuted, a diagnostic marker and deterministic bundle are
published, and one `FixVerification(PASSED)` resolves the diagnostic session.

The mandatory negative scenario combines incompatible firmware identities. It returns
`INCOMPATIBLE_IDENTITY`, creates no `FixVerification`, does not resolve the session, and leaves all
input evidence unchanged.

This slice does not:

- flash, reset, halt, resume, or access a physical probe or board;
- claim physical transport or hardware qualification;
- implement VS-04, release acceptance, Monitor UI analytics, arbitrary statistics, or general
  archive export;
- change Python 3.10 assets, package metadata, Node/browser code, or remote state;
- produce or modify source code as part of diagnosis. `SourceChangeDeclaration` only binds an
  externally supplied immutable change identity.

## 2. Architectural decisions

### 2.1 Replay provenance

Three approaches were considered:

1. Add an execution-source union and a new TestRun schema version. This is expressive but forces a
   migration through every Host/Target consumer before Scenario B needs it.
2. Keep `stm32-test/1`, require `mode="target"` and `transport="replay"`, and bind an immutable
   `TargetReplayDescriptor` as an Evidence parent. **Selected.** It is explicit in the TestRun,
   public summary, Evidence operation, root metadata, and descriptor without changing accepted Host
   bytes.
3. Put replay provenance only in envelope metadata. Rejected because a detached manifest could be
   mistaken for a physical Target result.

`transport="replay"` is therefore a closed semantic value, not a free-form convention. A replay
TestRun is valid only when all four statements agree:

- its manifest is `mode="target"` and `transport="replay"`;
- its Evidence operation is `target-test-replay`;
- its sole parent is a validated `TargetReplayDescriptor` envelope;
- descriptor and root metadata say `physical_transport_evidence=false`.

Any contradiction is `EVIDENCE_INTEGRITY_FAILURE`. Replay can never satisfy a physical claim.

#### Portable replay import identity

`workspaceId` includes the canonical local project root, so a frozen replay's recorded
`EvidenceIdentity.workspace_id` cannot equal every machine's local workspace ID. Replay import
therefore has two explicit, non-interchangeable identities:

- `originIdentity` is the immutable identity recorded in the replay descriptor and Target frames.
  It remains the TestRunManifest identity and the authority for before/after causal compatibility.
- `importWorkspaceId` is the complete current `WorkspacePaths.workspace_id` whose EvidenceStore or
  Monitor store owns the imported objects. It is storage/audit provenance, not an execution claim.

The public replay result, Evidence metadata/root, MonitorRunRef, AnalysisResult, marker, bundle, and
FixVerification expose both IDs plus `execution_source="replay"` and
`physical_transport_evidence=false`. They never replace the origin ID with the import ID and never
describe import as a physical execution in the local workspace. A caller that needs current-local
physical identity must use VS-04.

### 2.2 Module ownership without import cycles

- 0601 (`stm32_toolkit.testing`) owns replay descriptor validation, Target frame execution,
  TestRun publication, and authoritative reload.
- 0603 (`stm32_monitor`) owns replay-window ingestion into `monitor.sqlite3`, compatibility,
  alignment, quality, `AnalysisResult`, marker payload, and bundle bytes.
- 0602 (`stm32_toolkit.diagnostics`) owns source-change declarations, verification plans,
  diagnostic events/state, and `FixVerification`.
- The Scenario B acceptance test composes these public services using stable IDs and Evidence
  objects. 0602 never imports Monitor storage internals; 0603 never writes DiagnosticStore.

Each package can be tested independently. Cross-module values cross the boundary as closed JSON or
Evidence identifiers, not Python object identity, database row IDs, or filesystem paths.

### 2.3 Derived evidence and authorities

Raw Target replay bytes and Monitor sample batches remain immutable inputs. TestRunManifest remains
the authority for test outcome; `monitor.sqlite3` remains the authority for sample windows;
DiagnosticStore remains the authority for diagnostic decisions; and `FixVerification` remains the
authority for the repair conclusion. `AnalysisResult`, marker payload, and bundle are derived
Evidence and can never overwrite an input.

## 3. Public data contracts

All IDs are lowercase SHA-256 unless an existing run/session UUID contract is named. All JSON
objects reject unknown fields, tuples, non-finite numbers, invalid Unicode, and over-limit values.
`to_dict()` returns fresh containers.

### 3.1 TargetReplayDescriptor (0601)

```text
schema                       "stm32tk-target-replay/1"
replay_id                    digest of canonical descriptor intent
scenario_role                "failed-before" | "fixed-after"
source                       "toolkit-generated-protocol-replay"
physical_transport_evidence  false
identity                     EvidenceIdentity
inventory_digest             sha256
stream                       ArtifactRef(kind="target-replay-stream")
stream_format                "stm32-target-frame/1"
expected_terminal_state      "failed" | "passed"
```

The descriptor is published before execution with operation `target-replay-input`. Its `identity`
is the recorded `originIdentity`; publication metadata additionally binds the current complete
`importWorkspaceId`. The replay
workflow verifies the supplied regular, single-link, non-redirect fixture, exact byte count and
digest, descriptor identity, and expected terminal state. It runs the existing Target decoder and
runner without creating a Probe service, transport device, authorization, or hardware lease.

`target_replay_run(context, operation_id, descriptor_file, stream_file)` is idempotent by operation
intent and returns a normal public TestRun record plus `origin_workspace_id`,
`import_workspace_id`, `execution_source="replay"`, and `physical_transport_evidence=false`.
The TestRunManifest retains the recorded origin identity exactly; its enclosing Evidence/root bind
the current import workspace separately. `TestRunRepository.load()` accepts existing Host records
and the new replay Target record; it validates the correct closed envelope shape for each.

### 3.2 MonitorReplayWindow and MonitorRunRef (0603)

A Monitor replay fixture is a closed canonical JSON document:

```text
schema                       "stm32-monitor-replay/1"
source                       "toolkit-generated-probe-v2-replay"
physical_transport_evidence  false
scenario_role                "failed-before" | "fixed-after"
binding                      ObservationBinding
batches                      [SampleBatch, ...]
fixture_sha256               sha256 over the document without this field
```

It represents a frozen read-only Probe v2 observation transcript. Its binding is the recorded
origin binding. Ingestion first publishes the unchanged canonical transcript as imported replay
Evidence. It then creates a deterministic local replay projection for HistoryStore: only
`workspace_id` and `session_id` become the current import values, while firmware/source/target,
sample values, timestamps, ordering, and transcript digest remain bound to the origin. The replay
projection uses an explicit replay probe/physical-target/flash/lease vocabulary and cannot be
created by the live physical observation path. Ingestion validates the complete origin binding and
batch chain, requires replay labeling, then uses the public `HistoryStore.append_batch` path. It
never calls `open_monitor_observation`, ProbeService, or an OBSERVE/MODIFY backend.

`MonitorRunRef` contains `origin_workspace_id`, `import_workspace_id`, origin and projected Monitor
session/run IDs, firmware identity fields, the half-open sequence/time window, fixture digest,
ordered batch digests, source `replay`, the false physical flag, and scenario role. Repeating an
identical ingestion returns the same reference; same operation with different intent fails.

The durable operation authority is one immutable Evidence root of type `monitor-run`, keyed by the
frozen origin run UUID. It points to the unchanged transcript Evidence envelope and binds the
fixture/ref intent digest plus origin/import identity. History rows alone are never allowed to
define or adopt an operation intent because the local projection deliberately removes origin
workspace/session identity. Ingestion publishes the expected envelope/root before History mutation,
then uses one public atomic `HistoryStore.append_batches()` transaction. An exact root with absent
History is a recoverable interrupted attempt; a missing/different root with pre-existing History,
a partial window, or different intent is a conflict. A failed batch transaction appends no subset.

### 3.3 AnalysisRequest and AnalysisResult (0603)

VS-03 supports one bounded scalar selector per comparison. It deliberately does not introduce a
general analytics query language.

```text
AnalysisRequest
  before_run, after_run       MonitorRunRef
  selector_kind, selector     exact existing WatchItem identity
  alignment                   "run-relative"
  minimum_valid_pairs         integer >= 2

AnalysisResult
  schema                      "stm32-monitor-analysis/1"
  analysis_id                 canonical digest
  request_digest              canonical digest
  before_run_id, after_run_id stable references
  identity                    exact AnalysisLineage value
  quality                     "VALID" | "DEGRADED" | "INVALID"
  conclusion                  "COMPLETED" | "INCONCLUSIVE"
  reason_code                 closed code
  aligned_pair_count          bounded integer
  before_first/last/min/max   finite number or null
  after_first/last/min/max    finite number or null
  delta_first/last            finite number or null
  changed                     boolean or null
```

`AnalysisLineage` uses schema `stm32-monitor-analysis-lineage/1` and has the exact closed fields
`origin_workspace_id`, `import_workspace_id`, `logical_project_id`, `target_device`,
`before_input_snapshot_sha256`, `before_build_id`, `before_elf_sha256`,
`after_input_snapshot_sha256`, `after_build_id`, `after_elf_sha256`, and nullable
`source_change_declaration_id`. The workspace/project/target fields must be equal across both run
references. The before/after firmware triples are copied exactly from those references. The
declaration ID is null only when both triples are identical; when a triple differs it is non-null
and the publication workflow must validate the exact Task 6 `SourceChangeDeclaration` bridge.

The authoritative `AnalysisResult` retains all pure `AnalysisComputation` fields, including
`aligned_position_count` and `excluded_position_count`; the abbreviated list above is not a license
to discard them. `analysis_id` is SHA-256 of the canonical closed result fields excluding
`analysis_id`. `before_run_id` and `after_run_id` are the respective immutable
`MonitorRunRef.run_ref_sha256` values, not mutable History keys or projected UUID aliases.
`AnalysisEvidenceRef` has exact closed schema
`stm32-monitor-analysis-evidence-ref/1` and fields `analysis_id` plus `evidence_id`. Neither the
result nor the marker payload embeds the Evidence ID that contains itself.

`AnalysisResult` is the canonical derived payload and therefore never embeds the ID of the
Evidence envelope that contains it; doing so would create a content-addressing cycle. Publication
returns a separate frozen `AnalysisEvidenceRef(analysis_id, evidence_id)`. Markers and verification
plans carry both IDs where they cross the 0603/0602 boundary.

The reusable pure algorithm returns an `AnalysisComputation` containing only alignment quality,
conclusion, reason, counts, statistics and `changed`; it does not assert firmware authorization or
carry an analysis/Evidence ID. After Task 6 freezes `SourceChangeDeclaration`, the application
workflow validates identity and firmware authorization, then combines the request, computation and
validated lineage into `AnalysisResult`. Thus an unvalidated computation can never masquerade as a
published cross-firmware conclusion.

For VS-03 the request is exactly two `MonitorRunRef` values, one exact `WatchItem` identity,
`alignment="run-relative"`, and `minimum_valid_pairs` in `2..10000`. The pure comparison input is
two exact non-empty bounded `SampleBatch` tuples already loaded for those references. An `OK`
sample is trustworthy only when its closed typed value is exactly `{type, value}`, the type text is
equal across the pair, and `value` is a finite non-boolean integer or float. The aligned-pair count
counts trustworthy pairs only. A completed comparison is `VALID` when every aligned position is
trustworthy and `DEGRADED` when the requested minimum is met but positions were missing or excluded;
otherwise it is `INVALID/INCONCLUSIVE`. Closed reason codes are `VALUES_CHANGED`,
`VALUES_UNCHANGED`, `VALUES_CHANGED_WITH_EXCLUSIONS`, `VALUES_UNCHANGED_WITH_EXCLUSIONS`, and
`INSUFFICIENT_VALID_PAIRS`. Inconclusive results expose null statistics and `changed=null`.

Run-relative alignment subtracts each run's first scheduled timestamp, matches samples at identical
relative nanoseconds, and preserves input order. `VALID` requires the requested minimum pairs and
all paired samples `ok`; recoverable missing/error samples produce `DEGRADED`; no trustworthy pair
produces `INVALID` plus `INCONCLUSIVE`. No interpolation or identity guessing is permitted.

Origin project/workspace, import workspace, target device, selector, and declared firmware lineage
must be compatible. The before and after inputs must have the same origin and import workspace IDs;
an origin ID is never compared to an import ID.
Before and after build/ELF digests may differ only when the supplied SourceChangeDeclaration names
those exact before/after firmware identities. A compare request without that declaration requires
identical firmware. Incompatible identity returns `INCOMPATIBLE_IDENTITY` before derived Evidence is
published.

The implementation sequence freezes the pure comparison computation first, then the 0602
`SourceChangeDeclaration`, and only then the authoritative `AnalysisResult` plus History/Evidence
workflow. This prevents a temporary duplicate firmware-bridge type from becoming a second authority.

### 3.4 SourceChangeDeclaration and VerificationPlan (0602)

Their schemas are `stm32-source-change-declaration/1` and `stm32-verification-plan/1`.

```text
SourceChangeDeclaration
  declaration_id
  before_source_sha256, after_source_sha256
  before_build_id, before_elf_sha256
  after_build_id, after_elf_sha256
  changed_paths               sorted project-relative paths, 1..128
  diff_evidence_id            Evidence envelope containing the diff artifact
  diff_artifact               existing Evidence ArtifactRef
  claimed_hypothesis_ids      1..16 existing hypothesis IDs
  validation_plan_id          verification plan ID

VerificationPlan
  verification_plan_id
  diagnostic_session_id
  failed_before_run_id
  failed_before_evidence_id
  fixed_after_run_id
  fixed_after_evidence_id
  source_change_declaration_id
  required_analysis_ids       bounded tuple, non-empty in VS-03
  required_analysis_evidence_ids parallel bounded tuple
  required_monitor_quality    "VALID"
  expected_changed            true
  plan_digest
```

`verification_plan_id` is an independently allocated immutable 64-hex identifier, chosen before
the declaration is frozen; it is not the plan digest. `plan_digest` hashes the complete canonical
plan fields including that ID and the resulting declaration ID. This breaks the otherwise
impossible circular equation between `SourceChangeDeclaration.validation_plan_id` and
`VerificationPlan.source_change_declaration_id`. FixVerification binds both ID and digest and never
requires their bytes to be equal.

The declaration records facts supplied by the caller; Toolkit does not edit or inspect source to
invent them. Exact project-relative paths are retained, while absolute paths are rejected from
public output. The diff artifact must already belong to the exact `diff_evidence_id` envelope and
its digest is immutable. VerificationPlan run/evidence and analysis/evidence tuples are parallel,
closed and unique; the plan binds the exact source-change declaration it verifies. These envelope
IDs, not catalog search results or bare artifact paths, become DiagnosticStore checkpoint parents.

### 3.5 DiagnosticMarker and deterministic bundle (0603/0602 boundary)

`DiagnosticMarker` uses schema `stm32-diagnostic-marker/1` and contains marker ID, analysis
ID/evidence ID, diagnostic session ID, one existing
hypothesis ID, polarity (`supports` or `refutes`), a closed label, and bounded rationale. 0603
creates the marker payload and publishes it as Evidence. The caller then invokes the 0602 public
`diagnostic_attach_marker` operation; only that operation appends `analysis.marker_attached`.

Publication returns a separate `DiagnosticMarkerRef` with schema
`stm32-diagnostic-marker-ref/1`: it snapshots the marker fields and additionally pairs
`marker_id` with `marker_evidence_id`. The published marker payload never embeds its own envelope ID.
The attach event stores this ref, and its checkpoint parents include marker Evidence followed by
analysis Evidence in first-seen order.

The public comparison operation is
`compare_monitor_runs(paths, evidence_store, request, diagnostic_session_id, hypothesis_id,
polarity, rationale, source_change_declaration=None)`. It accepts exact base types. It reads both
windows only through paged public `HistoryStore.query_history` calls bounded by each run reference,
reconstructs only complete batches, and calls the pure comparison. Changed firmware requires the
exact declaration before/after source/build/ELF bridge and the named hypothesis in its claimed
set; identical firmware requires no declaration. Scope, replay/non-physical labels, run windows,
batch digests and selector vocabulary are validated before derived publication.

The return is a frozen `AnalysisPublication` containing exact `analysis_result`,
`analysis_evidence_ref`, `diagnostic_marker`, and Toolkit `diagnostic_marker_ref`. Analysis
Evidence is rooted as `monitor-analysis/<analysis_id>` and has the two transcript Evidence IDs plus
the declaration diff Evidence ID, when present, as ordered parents. Marker Evidence is rooted as
`diagnostic-marker/<marker_id>` with analysis Evidence as its sole parent. Both canonical payload
artifacts and roots are content-addressed and idempotent; an exact partial publication is repaired,
while different bytes at the same root are an operation conflict. Evidence identity is the exact
after-run **origin** workspace/project/origin-session/source/build/ELF/target/git identity; the
import workspace/session is only the local History query location and never replaces provenance.
`stm32_toolkit.evidence.gc.REGISTERED_ROOT_TYPES` remains the single authoritative root-type
registry: it statically includes `monitor-analysis` and `diagnostic-marker`. Monitor imports must
not mutate that Toolkit registry at process runtime. Repository attributes pin the canonical VS-03
Monitor JSON and Target replay JSON/HEX fixtures to LF so a clean Windows checkout preserves the
accepted fixture bytes.
Each transcript parent is also cross-checked against its run reference: every binding field,
group/revision, exact captured window, and every projected batch digest must agree with the
canonical transcript projection. Valid transcript and History objects that contradict each other
are an Evidence-integrity failure, not two independently acceptable inputs. Provider exceptions at
derived publication map to a stable `ENVIRONMENT_FAILURE`; an exact immutable prefix may remain
and must be repairable on retry, while provider exception text is never exposed.
Identity or
declaration incompatibility occurs before any derived artifact, envelope or root publication.

The analysis bundle is canonical JSON, not a platform-dependent archive. It contains a version,
the two MonitorRunRefs, AnalysisResult, marker, referenced TestRun IDs, SourceChangeDeclaration ID,
and an ordered digest table. It contains no absolute path, raw credential, mutable database key, or
physical claim. Canonical byte ordering makes repeated export byte-identical.

The exact bundle schema is `stm32-monitor-analysis-bundle/1` with fields, in canonical object form:
`schema`, `before_run`, `after_run`, `analysis_request`, `analysis_result`,
`analysis_evidence_ref`, `diagnostic_marker`, `diagnostic_marker_ref`,
`failed_before_test_run_id`, `fixed_after_test_run_id`, `source_change_declaration_id`, and
`digest_table`. The ordered digest roles are `before-run-ref`, `after-run-ref`,
`before-transcript-evidence`, `after-transcript-evidence`, `analysis-request`, `analysis-result`,
`analysis-evidence`, `diagnostic-marker`, `marker-evidence`, followed by
`source-change-declaration` only when present. Each entry is exactly `{role, sha256}`.

`AnalysisBundleRef` is frozen and slotted, uses schema
`stm32-monitor-analysis-bundle-ref/1`, and has the exact fields `schema`, `bundle_id`, `evidence_id`,
and `artifact`. The public operation is:

```python
export_analysis_bundle(
    paths: WorkspacePaths,
    evidence_store: EvidenceStore,
    request: AnalysisRequest,
    publication: AnalysisPublication,
    failed_before_test_run_id: str,
    fixed_after_test_run_id: str,
    source_change_declaration: SourceChangeDeclaration | None = None,
) -> tuple[bytes, AnalysisBundleRef]
```

It reloads both runs through public `TestRunRepository.load` using their valid public string IDs;
the exporter adds no UUID-only restriction. Failed-before is a failed Target replay TestRun and
fixed-after is the equivalent passed TestRun. Each TestRun identity equals its Monitor run on
origin workspace, project, source/build/ELF, target and git fields. Target-test and Monitor capture
sessions remain their separate authoritative session domains and are not compared to each other;
the two Target TestRuns must share their own origin session. Both roots retain exact
replay/non-physical labels, origin workspace and the current import workspace. The operation
revalidates the request, both transcript publications, the analysis and marker
root/envelope/canonical artifact bytes, declaration and TestRuns before mutation, then publishes an envelope/root
`monitor-analysis-bundle/<bundle_id>`. `bundle_id` and the sole artifact SHA-256 equal the canonical
byte digest; artifact kind is `monitor-analysis-bundle` and media type is `application/json`.
Ordered parents are before/after transcript Evidence, analysis Evidence, marker Evidence, and
declaration diff Evidence when present. Identity is the after-run origin identity and
`produced_at_utc = unix_ns_to_utc(after.end_captured_unix_ns_exclusive - 1)`.

Envelope and root use the same exact metadata fields: `bundle_id`, `analysis_id`,
`failed_before_test_run_id`, `fixed_after_test_run_id`, `source_change_declaration_id`,
`origin_workspace_id`, `import_workspace_id`, `origin_session_id`, `execution_source`, and
`physical_transport_evidence`. The last two values are `replay` and false. Toolkit's static GC
registry is the sole authority and includes `monitor-analysis-bundle`; Monitor never registers it
at import time. The bundle payload does not contain its own bundle/evidence reference, so no
content-addressing cycle exists.

### 3.6 FixVerification (0602)

```text
schema                       "stm32-fix-verification/1"
fix_verification_id          canonical digest
diagnostic_session_id
failed_before_run_id/evidence_id
source_change_declaration_id
fixed_after_run_id/evidence_id
verification_plan_id/digest
analysis_ids/evidence_ids
executed_operation_ids
status                       PASSED | FAILED | INCONCLUSIVE | CANCELLED
reason_code                  closed for schema version
completed_at_utc
```

VS-03 returns `PASSED` only when:

1. failed-before is an authoritative failed Target replay;
2. fixed-after is an authoritative passed Target replay for the same case/inventory scope;
3. the declaration exactly bridges their source/build/ELF identities;
4. every required operation and AnalysisResult is present and identity-compatible;
5. every required analysis has `quality=VALID`, `conclusion=COMPLETED`, and `changed=true`;
6. both replays and Monitor windows remain explicitly non-physical.

A trustworthy fixed-after test that still fails or an analysis that validly contradicts the plan is
`FAILED`. Missing, damaged, degraded/invalid, or untrusted mandatory evidence is `INCONCLUSIVE`.
Caller cancellation is `CANCELLED`. Only `PASSED` transitions the session to `RESOLVED`.

The status/reason pairing is closed: `PASSED/VERIFICATION_PASSED`; `FAILED` with
`FIXED_TEST_FAILED` or `ANALYSIS_CONTRADICTED`; `INCONCLUSIVE` with
`MANDATORY_EVIDENCE_MISSING`, `MANDATORY_EVIDENCE_CORRUPT`, or `ANALYSIS_NOT_VALID`; and
`CANCELLED/CALLER_CANCELLED`. Incompatible identity is rejected before a FixVerification exists.

### 3.7 Diagnostic verification workflow boundary

Toolkit implements the 0602 application boundary without importing `stm32_monitor`. Monitor remains
an independently installable producer of closed JSON Evidence. Toolkit reloads a required analysis
through `monitor-analysis/<analysis_id>`, requires the exact root and envelope, operation
`monitor-analysis`, one canonical `application/json` artifact of kind `monitor-analysis`, schema
`stm32-monitor-analysis/1`, and a payload SHA-256 equal to `analysis_id`. It validates the closed
payload fields needed by the frozen contract, including exact before/after run IDs, identity,
`quality`, `conclusion`, and `changed`. A marker is reloaded in the same way through
`diagnostic-marker/<marker_id>`, operation/kind `diagnostic-marker`, schema
`stm32-diagnostic-marker/1`, and must reproduce the supplied `DiagnosticMarkerRef` projection by
the exact unequal-schema/ref-only rule below. This closed-Evidence projection is the only
0603-to-0602 dependency.

The two producer IDs are digests of unsigned projections, not artifact digests. Toolkit therefore
uses these exact validation equations instead of equating either ID to the full artifact SHA:

```text
analysis_id = sha256(canonical JSON(analysis payload without analysis_id))
marker_id   = sha256(canonical JSON(marker payload without marker_id))
artifact.sha256 = sha256(the complete canonical payload bytes, including its ID)
```

The analysis payload has the exact Monitor `AnalysisResult.to_dict()` field set. Its `identity`
object has schema `stm32-monitor-analysis-lineage/1` and exact origin/import workspace, logical
project, target, before/after input snapshot, build, ELF and declaration fields. Those values must
equal the failed/fixed TestRun identities and the SourceChangeDeclaration bridge; Monitor and
Target run/session IDs remain separate and are not compared.

The marker payload schema is `stm32-diagnostic-marker/1`; the supplied ref schema is
`stm32-diagnostic-marker-ref/1`. Comparison deliberately excludes those unequal schema values and
the ref-only `marker_evidence_id`. It requires equality of marker ID, analysis ID/evidence ID,
diagnostic session ID, hypothesis ID, polarity, label and rationale. The marker envelope ID equals
`marker_evidence_id`, its sole parent is the analysis Evidence ID, and its identity/metadata agree
with the reloaded analysis envelope. A full marker payload must never be compared directly with a
marker ref dictionary.

The public workflow signatures are:

```python
diagnostic_declare_source_change(
    context: DiagnosticWorkflowContext, *, operation_id: str,
    diagnostic_session_id: str, expected_revision: int,
    source_change_declaration: SourceChangeDeclaration | dict[str, object],
    actor: str = "user",
) -> OperationResult[object]

diagnostic_add_verification_plan(
    context: DiagnosticWorkflowContext, *, operation_id: str,
    diagnostic_session_id: str, expected_revision: int,
    verification_plan: VerificationPlan | dict[str, object],
    actor: str = "user",
) -> OperationResult[object]

diagnostic_start_verification(
    context: DiagnosticWorkflowContext, *, operation_id: str,
    diagnostic_session_id: str, expected_revision: int,
    verification_plan_id: str, actor: str = "tool",
) -> OperationResult[object]

diagnostic_attach_marker(
    context: DiagnosticWorkflowContext, *, operation_id: str,
    diagnostic_session_id: str, expected_revision: int,
    diagnostic_marker_ref: DiagnosticMarkerRef | dict[str, object],
    actor: str = "tool",
) -> OperationResult[object]

diagnostic_complete_verification(
    context: DiagnosticWorkflowContext, *, operation_id: str,
    diagnostic_session_id: str, expected_revision: int,
    executed_operation_ids: list[str], cancelled: bool = False,
    actor: str = "tool",
) -> OperationResult[object]

diagnostic_show_verification(
    context: DiagnosticWorkflowContext, *, diagnostic_session_id: str,
) -> OperationResult[object]
```

Their exact operation names are respectively `diagnostic.source-change.declare`,
`diagnostic.verification-plan.add`, `diagnostic.verification.start`,
`diagnostic.marker.attach`, `diagnostic.verification.complete`, and
`diagnostic.verification.show`. Mutation results return the authoritative reloaded `session` plus
the declared/added/started/attached/completed value; show returns `session`, all historical
`fix_verifications`, and `authoritative=true`.

The caller never supplies a completion status, reason or timestamp. Completion derives
`completed_at_utc` from the authoritative fixed-after TestRun `ended_at_utc`, so retrying an exact
operation is deterministic. Identity incompatibility returns `INCOMPATIBLE_IDENTITY` before an
event exists. Provider or filesystem inability returns `ENVIRONMENT_FAILURE`; structurally
contradictory Evidence outside completion returns `EVIDENCE_INTEGRITY_FAILURE`. During completion,
missing or corrupt mandatory Evidence is instead recorded as the already frozen
`INCONCLUSIVE/MANDATORY_EVIDENCE_MISSING` or `INCONCLUSIVE/MANDATORY_EVIDENCE_CORRUPT` conclusion.

Completion requires one attached, byte-validated marker covering every parallel
`(required_analysis_id, required_analysis_evidence_id)` pair. A valid completed analysis with
`changed=false` contradicts the expected-change plan and produces
`FAILED/ANALYSIS_CONTRADICTED`; degraded, invalid or inconclusive analysis produces
`INCONCLUSIVE/ANALYSIS_NOT_VALID`. The analysis bundle remains a deterministic export artifact and
is not a VerificationPlan or FixVerification parent because neither frozen model contains a bundle
field. Verification plan and FixVerification analysis/evidence tuples are canonicalized by sorting
the pairs by analysis ID and then unzipping them; the two tuple positions must never be sorted
independently.

`diagnostic_start` retains the accepted Host behavior and additionally accepts only an
authoritative failed Target replay. Its public application-service input is extended with the
closed `failed_run_mode` value `host|target`. The default is `host`, so every accepted VS-02 Host
call, event and result remains byte-compatible; a Target caller must pass `target` explicitly.
The declared mode is routing intent, not evidence authority: after loading, the TestRun manifest
must have the same mode or the operation fails before creating a DiagnosticStore event.

```python
diagnostic_start(
    context: DiagnosticWorkflowContext,
    *,
    operation_id: str,
    failed_test_run_id: str,
    failed_run_mode: Literal["host", "target"] = "host",
    actor: str = "user",
) -> OperationResult[object]
```

An invalid mode is `DIAGNOSTIC_INVALID_EVENT`. The omitted/default Host path retains the existing
Host loader and returns the existing `DIAGNOSTIC_INVALID_EVENT` when the loaded record is not a
failed Host run. An explicitly declared Target mode that loads a Host record is
`EVIDENCE_INTEGRITY_FAILURE`. All three contradictions are rejected with zero DiagnosticStore
mutation.

For `failed_run_mode=target`, a missing or corrupt immutable TestRun is
`EVIDENCE_INTEGRITY_FAILURE`, provider or filesystem unavailability is `ENVIRONMENT_FAILURE`, and
an identity contradiction is `INCOMPATIBLE_IDENTITY`. Those classifications are selected from the
explicit request even when the root itself cannot be read; they must never be inferred from root
metadata, target-device spelling, or whether origin and import workspace IDs happen to differ.
The authoritative Target root, when readable, must state `mode=target`, `state=failed`,
`execution_source=replay`, `physical_transport_evidence=false`, the current import workspace, and
the manifest origin workspace. The DiagnosticSession retains that origin identity. Target,
Monitor, and Diagnostic session identifiers remain separate authority domains and are never
compared for equality.

The accepted mode is durably bound by `session.created` and reduced into
`DiagnosticSession.failed_run_mode`. A historical `session.created` event and serialized session
without the field decode as `host`; newly created Host events and public session dictionaries omit
the default field and therefore preserve their accepted bytes. A Target `session.created` request
and serialized session include `failed_run_mode=target`. Event validation accepts only the exact
legacy Host shape or the exact Target extension, and `_advance` carries the value unchanged.

Every later diagnostic operation, including the existing `diagnostic_begin` and
`diagnostic_show`, reloads the session's `failed_run_id` before applying identity authority and
selects failure semantics from the durable `failed_run_mode`. Host sessions retain the existing
exact local-workspace rule and result bytes. For a Target session, the reloaded TestRun must still
be Target/replay/failed/non-physical, its manifest identity must equal the DiagnosticSession
identity, its root `origin_workspace_id` must equal that identity, and its root
`import_workspace_id` must equal the current WorkspacePaths ID. Only project/target/source facts
are compared across those objects; origin workspace is never required to equal import workspace.
This is the common session-load rule for begin, hypothesis, plan, marker and show, not a special
case used only while creating the session.

## 4. Diagnostic events and state transitions

VS-02's accepted events remain byte-compatible. The session model is extended with source changes,
verification plans, markers, and verification attempts. New append-only events are:

```text
source_change.declared       INVESTIGATING -> FIX_PROPOSED
verification.plan_added      FIX_PROPOSED  -> FIX_PROPOSED
verification.started         FIX_PROPOSED  -> VERIFYING
analysis.marker_attached     VERIFYING     -> VERIFYING
verification.completed PASS  VERIFYING     -> RESOLVED
verification.completed else  VERIFYING     -> INVESTIGATING
```

The five new event payloads retain the existing exact `{request,result}` envelope. The mode-binding
extension uses the following two closed `session.created` shapes alongside them:

```text
session.created Host      request {failed_test_run_id}; result {failed_evidence_id,identity}
session.created Target    request {failed_test_run_id,failed_run_mode="target"}; result {failed_evidence_id,identity}
source_change.declared   request {source_change_declaration}; result {declaration_id}
verification.plan_added  request {verification_plan}; result {verification_plan_id,plan_digest}
verification.started     request {verification_plan_id}; result {verification_plan_id}
analysis.marker_attached request {diagnostic_marker_ref}; result {marker_id}
verification.completed   request {fix_verification}; result {fix_verification_id,status,reason_code}
```

The extended session adds exact tuples `source_change_declarations`, `verification_plans`,
`diagnostic_marker_refs`, `fix_verifications`, plus nullable `active_verification_plan_id`. These
fields are omitted only for a legacy session that has never accepted a new event. The source change
must name existing hypotheses; its validation plan ID must equal the subsequently added plan ID.
The plan must bind that declaration and the session; start selects one stored plan. A marker must
bind an existing hypothesis and one required analysis/evidence pair in the active plan. Completion
must exactly repeat the active plan's declaration, run/evidence, plan digest, and analysis/evidence
tuples. IDs are unique in their collections. Completion clears the active plan; only PASSED resolves.

Evidence identity validation is role-specific. The failed TestRun remains exactly equal to the
session EvidenceIdentity. Every new parent must retain the same workspace, project and target
device. The source-change diff envelope must contain the exact declared ArtifactRef. Fixed TestRun,
analysis and marker parents additionally bind the declaration's after source/build/ELF identity;
the analysis/marker relationship is checked through their exact domain/evidence pairs. This is a
closed relaxation for declared firmware change, not a general cross-identity bypass.

Each event is checkpointed through the existing DiagnosticStore/Evidence root chain. Legacy
sessions/events retain their exact old canonical fields and bytes: the extended session fields are
serialized only after the first new event, while the loader accepts exactly the legacy or extended
shape. New checkpoint parents are appended after the previous checkpoint parent in stable payload
order and never change parent ordering for old events. Invalid
transition, stale revision, operation conflict, or missing referenced Evidence appends nothing.
Failed or inconclusive attempts remain visible after the session returns to `INVESTIGATING`.

## 5. Error and failure semantics

Public application results use the existing stable OperationResult shape. Slice-specific codes map
to the integration design's closed classes:

| Condition | Public result | State/evidence effect |
|---|---|---|
| Target test executes and fails | successful operation carrying TestRun `failed` | retain TestRun |
| replay fixture malformed/damaged | `EVIDENCE_INTEGRITY_FAILURE` | no TestRun root |
| Monitor samples insufficient | AnalysisResult `INCONCLUSIVE`/`INVALID` | retain input and result |
| incompatible identity | `INCOMPATIBLE_IDENTITY` | no derived analysis or verification |
| provider/environment unavailable | `ENVIRONMENT_FAILURE` | no domain failure, no transition |
| valid verification contradiction | FixVerification `FAILED` | return to INVESTIGATING |
| mandatory evidence untrustworthy | FixVerification `INCONCLUSIVE` | return to INVESTIGATING |
| report/rendering issue | governance-only `REPORT_FAILURE` | product objects unchanged |

Raw exception messages, native exit codes, absolute paths, and fixture locations never cross the
public boundary.

## 6. Public workflow composition

The accepted Scenario B executes in this order:

```text
publish failed-before replay descriptor
-> target_replay_run -> failed Target TestRun
-> diagnostic_start / diagnostic_begin
-> add two hypotheses
-> ingest failed-before Probe-v2 replay window
-> assess failed-run observation: support one, refute one
-> declare externally produced source change
-> publish fixed-after replay descriptor
-> target_replay_run -> passed Target TestRun
-> ingest fixed-after Probe-v2 replay window
-> compare compatible windows -> AnalysisResult
-> create marker + deterministic bundle
-> add VerificationPlan and start verification
-> attach marker through diagnostic public operation
-> complete FixVerification(PASSED)
-> reload session, analysis, bundle, TestRuns and verification from fresh objects
```

CLI and MCP adapters are thin projections over these workflows. They accept project/data/session
context through their existing trusted runtime mechanisms. File-taking CLI commands apply the
existing regular/single-link/non-redirect/size guards; MCP accepts canonical JSON values or stable
IDs, never arbitrary server paths.

## 7. Executable acceptance

### 7.1 Scenario B positive

Repository fixtures contain two deterministic Target frame streams and two deterministic Monitor
replay documents. The failed stream has one failed case; the fixed stream has the same inventory
and a passed case. Both Monitor windows use the same selector/time grid; the chosen value changes in
the declared direction. The end-to-end test uses public services, discards all service/store/model
objects, reloads everything, and proves:

- failed-before and passed-after states plus replay/non-physical labels at every public boundary;
- one supported and one refuted hypothesis;
- a `VALID`, `COMPLETED`, changed AnalysisResult;
- a marker linked through a diagnostic event;
- byte-identical repeated bundle export;
- `FixVerification(PASSED)` and session `RESOLVED`;
- all referenced Evidence/root chains remain authoritative;
- the fixture project tree is unchanged.

### 7.2 Mandatory incompatible-identity negative

Replace the fixed Monitor/TestRun identity with another project or undeclared firmware lineage.
Public compare/verification returns `INCOMPATIBLE_IDENTITY`; no new analysis, marker,
FixVerification, or resolved event appears; input digests and session revision remain unchanged.

### 7.3 Insufficient-data negative

Use a compatible window with fewer than two valid aligned pairs. Analysis is retained as
`INCONCLUSIVE`/`INVALID`; completing the plan creates `FixVerification(INCONCLUSIVE)` and returns the
session to `INVESTIGATING`. It never becomes a provider error or a passed verification.

## 8. Migration and compatibility

- Existing Host `stm32-test/1`, VS-01 workflows/adapters, and VS-02 event bytes remain accepted.
- `TestRunRepository` becomes operation-discriminated, not Host-only. It retains the exact Host
  validation path and adds a separate Target-replay path.
- Existing Target runner/protocol/transports are reused; replay publication adds no hardware
  behavior.
- Existing Monitor schema v2 and HistoryStore remain the sample authority. New analysis/bundle
  artifacts are additive; no migration of accepted raw history is required.
- Monitor's public `ObservationBinding.workspace_id` is corrected from the historical 24-hex
  storage-key grammar to the integration contract's complete 64-hex `workspaceId`. Filesystem
  locations continue to use `WorkspacePaths.workspace_storage_key` (the first 24 hex) and do not
  move. Fresh/current databases store the complete ID. A pre-0.6 database whose metadata or raw
  batch payload still exposes only the 24-hex value fails closed as a legacy identity mismatch; it
  is not silently rewritten because that would change immutable history bytes. A future explicit
  data-migration product slice may import it while preserving the original as evidence.
- Existing DiagnosticStore event enumeration/reducer is extended append-only. Old sessions reload
  with empty VS-03 collections and their original digest chain.
- Historical 0602 source-change/FixVerification semantics and 0603 alignment/quality/marker/bundle
  semantics remain normative where this document names them. Their old task ladders, UI expansion,
  release matrices, Python 3.10 work, and per-exception microtasks are superseded for VS-03.

## 9. Verification boundary and risk triggers

Normal slice verification is limited to new Target replay, Monitor analysis, diagnostic extension,
public adapter, end-to-end, and directly affected VS-01/VS-02/Monitor regression tests plus full diff
review. Previously accepted unaffected evidence is not invalidated.

Escalate only when the implementation introduces the named risk:

- Evidence store/GC production change -> full Evidence group.
- existing Monitor storage/history production change -> complete Monitor Python suite.
- shared TestRun model change -> complete testing group.
- shared CLI/MCP runtime change outside registration -> complete corresponding adapter group.
- Probe/hardware/authorization, packaging, Node/browser, platform-specific code, or runtime metadata
  change -> stop and return to this design; do not silently pull release gates into VS-03.

A report-only issue is corrected and rechecked at the report layer. An environment failure is
recorded separately from product behavior. Two non-converging implementation/review rounds on the
same contract return to this design instead of adding tasks or gates.

## 10. VS-04 handoff

VS-03 hands VS-04 stable replay/public contracts and a runnable non-physical Scenario B. It grants
no hardware authorization. VS-04 must replace replay inputs with a named supported board/probe and
two separately authorized MODIFY phases while consuming the same TestRun, MonitorRunRef,
AnalysisResult, marker, VerificationPlan, and FixVerification contracts.
