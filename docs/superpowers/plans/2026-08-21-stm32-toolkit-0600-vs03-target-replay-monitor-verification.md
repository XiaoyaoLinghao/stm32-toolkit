# STM32 Toolkit 0.6 VS-03 Target Replay and Monitor Verification Implementation Plan

> **For Codex:** Execute with subagent-driven-development artifacts. One named
> `gpt-5.6-luna` implementer at `max` reasoning owns all product code and implementation tests;
> the primary `gpt-5.6-sol` agent independently reviews every task diff and the complete slice diff.

**Goal:** Execute the approved Scenario B from explicitly non-physical Target/Probe-v2 replay
through Monitor comparison, diagnostic marker and deterministic bundle to a durable
`FixVerification(PASSED)`, while proving the incompatible-identity negative.

**Architecture:** 0601 publishes operation-discriminated Target replay TestRuns using
`transport="replay"` plus a parent ReplayDescriptor. 0603 ingests frozen Monitor replay batches
through HistoryStore and publishes bounded AnalysisResult/marker/bundle evidence. 0602 extends its
append-only state machine with source-change and verification events and is the only owner of
FixVerification/session resolution. Modules exchange closed JSON and stable IDs only.

**Tech stack:** CPython 3.12, frozen dataclasses, canonical JSON/SHA-256, existing Target frame
runner, EvidenceStore/TestRunRepository, Monitor HistoryStore/SQLite v2, DiagnosticStore,
OperationResult, argparse/FastMCP, pytest.

**Frozen design:**
`docs/superpowers/specs/2026-08-21-stm32-toolkit-0600-vs03-target-replay-monitor-verification-design.md`

**Frozen design commits:** base `dc304de6ef1d7efbdabe06ae37ec96a859615f84`; portable replay
identity clarification `69a37196280f034a236053b42f7338711faebc18`.

**Plan-start SHA:** `dc304de6ef1d7efbdabe06ae37ec96a859615f84`

## Global constraints

- Execute Tasks 1-9 in order on branch `codex/STM32TK-0600-VS03-TARGET-MONITOR` in the isolated
  worktree `C:\tmp\stm32tk-0601-t10-1a`.
- Before each task, create one bounded task brief containing the exact task-start SHA, allowed
  files, commands, and exclusions. The same named Luna max implementer owns all VS-03 code; it must
  not spawn nested agents.
- Test first. Each task report records the RED command/output, implementation, GREEN commands and
  counts, self-review, commit(s), and concerns. Each accepted task ends in a local commit.
- Sol reviews the complete task-start-to-head diff for specification and code quality, runs a
  focused independent check, and either accepts it or returns one bounded correction to the same
  implementer. Sol does not edit product code.
- Use only CPython 3.12. Every command sets both source roots:
  `$env:PYTHONPATH="$(Resolve-Path 'tools/stm32-toolkit/src');$(Resolve-Path 'tools/stm32-monitor/src')"`.
  A missing `/src` loads stale installed packages and is invalid evidence.
- No physical Probe/board access, OBSERVE/MODIFY lease, flash/reset/halt/resume, Python 3.10,
  packaging, Node/browser, coverage, release matrix, remote operation, PR mutation, or merge.
- Replay is labeled `replay` and `physical_transport_evidence=false` in every public record. No
  replay result may satisfy a physical claim.
- Existing VS-01 Host result bytes and VS-02 event bytes remain compatible. Unknown fields and
  identity contradictions fail closed without partial append/publication.
- No recursive task split or added Gate. If a task cannot preserve its boundary, return to the
  frozen design.

## Task 1: Freeze the complete workspaceId contract in Monitor

**Product behavior:** Current Toolkit and Monitor source trees run together using the complete
64-hex public `workspaceId`; the first 24 hex remains only `workspace_storage_key` for directories.

**Files:**

- Modify: `tools/stm32-monitor/src/stm32_monitor/models.py`
- Modify: `tools/stm32-monitor/tests/test_models.py`
- Modify only if needed for a stable legacy failure assertion:
  `tools/stm32-monitor/tests/test_storage.py`

**Required behavior:**

- `ObservationBinding` and every public Monitor workspace-ID validator accept exactly lowercase
  64-hex values and reject 24-hex values.
- Fresh Monitor metadata/history continues to use `WorkspacePaths.workspace_id`; storage paths
  remain unchanged and use the existing storage key.
- A legacy 24-hex public binding fails with a stable validation/storage result; do not rewrite
  historical raw batches.
- Add a regression proving a `WorkspacePaths.from_roots()` binding round trip and explicitly
  distinguishing `workspace_id` from `workspace_storage_key`.

**TDD verify:**

```powershell
py -3.12 -m pytest -q tools/stm32-monitor/tests/test_models.py tools/stm32-monitor/tests/test_storage.py
py -3.12 -m pytest -q tools/stm32-monitor/tests/test_exports.py tools/stm32-monitor/tests/test_history.py tools/stm32-monitor/tests/test_runtime.py
```

**Commit:** `fix(monitor): use complete public workspace identity`

## Task 2: Closed Target replay input domain and frozen fixtures

**Product behavior:** A caller can parse and validate failed-before/fixed-after replay descriptors
and their exact Target frame bytes without executing or publishing them.

**Files:**

- Create: `tools/stm32-toolkit/src/stm32_toolkit/testing/replay.py`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/testing/__init__.py`
- Create: `tools/stm32-toolkit/tests/test_target_replay.py`
- Add text fixtures under: `tools/stm32-toolkit/tests/fixtures/vs03/target/`

**Required interfaces:**

- Frozen `TargetReplayDescriptor` with the exact design fields and closed `from_value()`/`to_dict()`.
- `canonical_replay_json_bytes`, `calculate_replay_id`, and a bounded fixture loader that requires a
  regular, single-link, non-redirect descriptor/hex-stream file and verifies byte count/SHA-256.
- Two frozen streams share inventory/case scope but have distinct declared source/build/ELF
  identity: failed-before ends in `failed`; fixed-after ends in `passed`.
- Descriptor source is fixed, transport is replay, and physical evidence is exactly false.

**TDD verify:**

```powershell
py -3.12 -m pytest -q tools/stm32-toolkit/tests/test_target_replay.py tools/stm32-toolkit/tests/test_target_protocol.py tools/stm32-toolkit/tests/test_target_runner.py
```

**Commit:** `feat(testing): define frozen target replay inputs`

## Task 3: Publish and reload Target replay TestRuns

**Product behavior:** The public testing workflow executes either frozen stream through the existing
Target runner, publishes a replay-labeled TestRun, and reloads it authoritatively after object loss.

**Files:**

- Modify: `tools/stm32-toolkit/src/stm32_toolkit/testing/publication.py`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/testing_workflows.py`
- Modify as required: `tools/stm32-toolkit/src/stm32_toolkit/testing/__init__.py`
- Create: `tools/stm32-toolkit/tests/test_target_replay_publication.py`
- Create: `tools/stm32-toolkit/tests/test_target_replay_workflows.py`

**Required interfaces:**

- `TestRunPublisher.publish_target_replay(manifest, descriptor_envelope, import_workspace_id)`
  publishes operation
  `target-test-replay`, one descriptor parent, closed metadata and a `test-run` root whose metadata
  includes mode/state/execution source/non-physical flag plus distinct origin/import workspace IDs.
- `TestRunRepository.load()` dispatches by envelope operation and preserves the current Host path
  byte-for-byte while validating the replay Target path independently.
- `target_replay_run(context, operation_id, descriptor_file, stream_file)` uses the existing Target
  decoder/validator without `TargetTestRunner` or Probe, is idempotent by exact intent, and returns
  public execution/non-physical plus origin/import identity labels. The frozen origin identity stays
  in the TestRunManifest; it is not required to equal the current import workspace ID.
- Damage, expected-state contradiction, wrong scope/identity, operation conflict, and publication
  interruption fail closed or recover idempotently as specified; no Probe or authorization object
  is created.

**TDD verify:**

```powershell
py -3.12 -m pytest -q tools/stm32-toolkit/tests/test_target_replay_publication.py tools/stm32-toolkit/tests/test_target_replay_workflows.py tools/stm32-toolkit/tests/test_testing_publication.py tools/stm32-toolkit/tests/test_testing_workflows.py
```

**Commit:** `feat(testing): publish target replay runs`

## Task 4: Ingest Probe-v2 Monitor replay windows

**Product behavior:** A frozen non-physical Probe-v2 transcript is validated and ingested through
HistoryStore, returning a durable MonitorRunRef without touching Probe services.

**Files:**

- Create: `tools/stm32-monitor/src/stm32_monitor/replay.py`
- Modify: `tools/stm32-monitor/src/stm32_monitor/__init__.py`
- Modify: `tools/stm32-monitor/src/stm32_monitor/history.py`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/evidence/gc.py`
- Create: `tools/stm32-monitor/tests/test_replay.py`
- Modify: `tools/stm32-monitor/tests/test_history.py`
- Modify: `tools/stm32-toolkit/tests/test_evidence_gc.py`
- Add text fixtures under: `tools/stm32-monitor/tests/fixtures/vs03/`

**Required interfaces:**

- Frozen `MonitorReplayDocument` and `MonitorRunRef` with closed canonical projections/digests.
- `ingest_monitor_replay(paths, evidence_store, operation_id, document_file)` validates
  replay/non-physical labels, complete 64-hex recorded origin identity, binding, monotonic batch
  chain, scenario role and fixture digest; publishes the unchanged origin transcript as Evidence;
  then creates a deterministic local replay projection and calls only `HistoryStore.append_batch`.
- Projection replaces only workspace/session storage identity, keeps firmware/source/target and all
  samples/times, and uses explicit replay probe/physical-target/flash/lease values. MonitorRunRef
  exposes both origin and import workspace IDs and the origin transcript digest.
- One `monitor-run` Evidence root binds operation ID to the exact transcript/ref intent. Projection
  equality alone never establishes idempotency. `HistoryStore.append_batches()` validates and
  commits the complete bounded replay window in one transaction, preserving `append_batch()`.
- Failed-before and fixed-after fixtures share project/target/selector/time grid and use the exact
  firmware identities declared by the corresponding Target descriptors.
- Identical retry returns the same reference. Conflict, partial/corrupt fixture, duplicate or
  non-monotonic batch, identity mismatch, and redirect/hard-link append nothing partial.

**TDD verify:**

```powershell
py -3.12 -m pytest -q tools/stm32-monitor/tests/test_replay.py tools/stm32-monitor/tests/test_history.py tools/stm32-monitor/tests/test_models.py tools/stm32-toolkit/tests/test_evidence_gc.py
```

**Commit:** `feat(monitor): ingest replay observation windows`

## Task 5A: Freeze bounded run-relative comparison

**Product behavior:** Two already-loaded compatible replay windows produce one deterministic,
closed AnalysisComputation without storage or publication side effects; insufficient input is explicit.

**Files:**

- Create: `tools/stm32-monitor/src/stm32_monitor/analysis.py`
- Modify: `tools/stm32-monitor/src/stm32_monitor/__init__.py`
- Create: `tools/stm32-monitor/tests/test_analysis.py`

**Required interfaces:**

- Frozen `AnalysisRequest` and non-authoritative `AnalysisComputation` with exact closed quality,
  conclusion and reason codes. The computation carries no firmware authorization, analysis ID or
  Evidence ID.
- Run-relative exact-timestamp alignment for one exact scalar selector; no interpolation.
- `analyze_monitor_windows(...)` accepts two exact non-empty bounded SampleBatch tuples, validates
  them against the two MonitorRunRefs, and performs no storage, Evidence, diagnostic or clock I/O.
- Trustworthy pairs require exact selector/type identity and finite non-boolean numeric values.
  Insufficient pairs return deterministic `INVALID/INCONCLUSIVE` with null statistics.

**TDD verify:**

```powershell
py -3.12 -m pytest -q tools/stm32-monitor/tests/test_analysis.py tools/stm32-monitor/tests/test_replay.py tools/stm32-monitor/tests/test_models.py
```

**Commit:** `feat(monitor): compare bounded replay windows`

## Task 6A: Freeze fix-verification value objects

**Product behavior:** Callers can construct, round-trip and digest the four closed immutable values
used at the 0602/0603 boundary without changing any existing diagnostic session or event bytes.

**Files:**

- Modify: `tools/stm32-toolkit/src/stm32_toolkit/diagnostics/model.py`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/diagnostics/__init__.py`
- Create: `tools/stm32-toolkit/tests/test_fix_verification_model.py`

**Required interfaces:**

- Frozen `SourceChangeDeclaration`, `VerificationPlan`, `DiagnosticMarkerRef`, and
  `FixVerification` with the corrected design envelope references, exact closed states/reasons and
  canonical IDs/digests.
- Diff, failed/fixed TestRun and required analysis references always pair domain IDs with exact
  Evidence envelope IDs. ArtifactRef alone is never accepted as a checkpoint authority.
- Project-relative changed paths and every tuple are canonical, bounded, ordered and unique.
- Existing DiagnosticSession/Event construction, serialization and canonical bytes remain exact.

**TDD verify:**

```powershell
py -3.12 -m pytest -q tools/stm32-toolkit/tests/test_fix_verification_model.py tools/stm32-toolkit/tests/test_diagnostic_model.py
```

**Commit:** `feat(diagnostics): freeze fix verification values`

## Task 6B1: Extend the diagnostic event domain and lifecycle

**Product behavior:** Existing sessions reload unchanged while new append-only events materialize
source changes, verification plans, markers, attempts and final FixVerifications in pure reduction.

**Files:**

- Modify: `tools/stm32-toolkit/src/stm32_toolkit/diagnostics/model.py`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/diagnostics/events.py`
- Create: `tools/stm32-toolkit/tests/test_fix_verification_events.py`

**Required interfaces:**

- Extend session states to `FIX_PROPOSED`, `VERIFYING`, `RESOLVED`, and `ABANDONED`, and retain all
  previous states/events/bytes. Legacy session serialization remains byte-identical; extended
  fields appear only after the first new event.
- Implement the five new event types and transitions from the design. `PASSED` alone resolves;
  other completed results return to `INVESTIGATING` while attempts remain.
- Pure event validation/reduction enforces the exact payloads, references, unique collections and
  active-plan transitions without reading Evidence or storage.

**TDD verify:**

```powershell
py -3.12 -m pytest -q tools/stm32-toolkit/tests/test_fix_verification_events.py tools/stm32-toolkit/tests/test_fix_verification_model.py tools/stm32-toolkit/tests/test_diagnostic_model.py tools/stm32-toolkit/tests/test_diagnostic_events.py
```

**Commit:** `feat(diagnostics): add fix verification lifecycle`

## Task 6B2: Persist verification Evidence parents

**Product behavior:** Every accepted new event is durably checkpointed with its exact Evidence
parents and can be reloaded/repaired without changing old event or parent bytes.

**Files:**

- Modify: `tools/stm32-toolkit/src/stm32_toolkit/diagnostics/store.py`
- Modify: `tools/stm32-toolkit/tests/test_fix_verification_events.py`

**Required interfaces:**

- New event parents follow stable first-seen payload order after the prior checkpoint parent; old
  event reference ordering remains exact.
- Store validates exact failed identity and only the design's closed declared after-firmware scope
  for diff/fixed/analysis/marker Evidence, including the declared diff ArtifactRef.
- Missing/corrupt/wrong-scope Evidence, stale revision and operation conflict append no event/root;
  interrupted checkpoint publication remains repairable from immutable event bytes.

**TDD verify:**

```powershell
py -3.12 -m pytest -q tools/stm32-toolkit/tests/test_fix_verification_events.py tools/stm32-toolkit/tests/test_diagnostic_store.py tools/stm32-toolkit/tests/test_diagnostic_events.py
```

**Commit:** `feat(diagnostics): persist verification evidence parents`

## Task 5B1: Freeze authoritative analysis publication values

**Product behavior:** A validated request/computation/lineage becomes a closed, canonical
AnalysisResult, and marker payloads and Evidence references cross the 0603/0602 boundary without a
content-addressing cycle.

**Files:**

- Modify: `tools/stm32-monitor/src/stm32_monitor/analysis.py`
- Modify: `tools/stm32-monitor/src/stm32_monitor/__init__.py`
- Modify: `tools/stm32-monitor/tests/test_analysis.py`

**Required interfaces:**

- Add exact `AnalysisLineage`, `AnalysisResult`, `AnalysisEvidenceRef`, and `DiagnosticMarker`
  values from the corrected design; all are closed, canonical, immutable and fail closed.
- Result and marker IDs are canonical digests excluding only their own ID field. Payloads never
  self-embed their containing Evidence envelope ID.
- Result construction requires an exact `AnalysisRequest`, exact `AnalysisComputation` with the
  same request digest, and exact lineage; no History/Evidence lookup or publication occurs here.
- Existing AnalysisRequest/AnalysisComputation bytes and pure comparison behavior remain exact.

**TDD verify:**

```powershell
py -3.12 -m pytest -q tools/stm32-monitor/tests/test_analysis.py tools/stm32-monitor/tests/test_replay.py
```

**Commit:** `feat(monitor): freeze analysis publication values`

## Task 5B2: Compare History and publish analysis plus marker

**Product behavior:** Compatible History windows produce one reloadable AnalysisResult and marker
publication; incompatible identity publishes nothing derived.

**Files:**

- Modify: `.gitattributes`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/evidence/gc.py`
- Modify: `tools/stm32-toolkit/tests/test_evidence_gc.py`
- Create: `tools/stm32-monitor/src/stm32_monitor/analysis_workflows.py`
- Modify: `tools/stm32-monitor/src/stm32_monitor/__init__.py`
- Create: `tools/stm32-monitor/tests/test_analysis_workflows.py`

**Required interfaces:**

- Use the frozen Task 5B1 values and publish the Toolkit `DiagnosticMarkerRef`; no payload
  self-embeds its Evidence ID.
- Register `monitor-analysis` and `diagnostic-marker` statically in the Toolkit GC root registry;
  Monitor import must not mutate the process-global Toolkit registry. Pin VS-03 canonical JSON
  fixtures to LF for byte-identical clean Windows checkouts.
- Cross-check each canonical transcript against every run-ref binding field, group/revision, exact
  captured window, and projected batch digest before derived mutation. Map ordinary Evidence write
  provider exceptions to stable `ENVIRONMENT_FAILURE` and make any exact retained prefix repairable
  without exposing provider exception text.
- `compare_monitor_runs(...)` queries only public HistoryStore pages, validates any firmware change
  only through the Task 6 `SourceChangeDeclaration`, and publishes canonical AnalysisResult and
  marker Evidence through an injected EvidenceStore.
- Insufficient pairs publish retained `INVALID/INCONCLUSIVE`; incompatible identity returns stable
  `INCOMPATIBLE_IDENTITY` before analysis or marker publication.

**TDD verify:**

```powershell
py -3.12 -m pytest -q tools/stm32-monitor/tests/test_analysis_workflows.py tools/stm32-monitor/tests/test_analysis.py tools/stm32-monitor/tests/test_history.py
```

**Commit:** `feat(monitor): publish bounded replay analysis`

## Task 5B3: Export deterministic rooted analysis bundle

**Product behavior:** One accepted publication exports byte-identical canonical bundle bytes and a
reloadable immutable bundle root for identical inputs.

**Files:**

- Modify: `.gitattributes`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/evidence/gc.py`
- Modify: `tools/stm32-toolkit/tests/test_evidence_gc.py`
- Modify: `tools/stm32-monitor/src/stm32_monitor/analysis_workflows.py`
- Modify: `tools/stm32-monitor/src/stm32_monitor/__init__.py`
- Modify: `tools/stm32-monitor/tests/test_analysis_workflows.py`

**Required interfaces:**

- Implement the exact bundle/digest table and `AnalysisBundleRef` from the design.
- Use the exact seven-argument `export_analysis_bundle(...)` signature and deterministic after-run
  captured time; statically register `monitor-analysis-bundle` in Toolkit GC; pin Target replay
  JSON/HEX fixtures to LF for clean Windows checkout.
- `export_analysis_bundle(...)` revalidates all request/publication/declaration/TestRun references,
  including valid non-UUID TestRun IDs, failed Target replay before/passed Target replay after
  cross-domain identity (with separate Target/Monitor session authorities), TestRun root labels,
  and exact analysis/marker root/envelope/artifact bytes, emits canonical bytes,
  ingests the exact artifact and publishes/reloads the deterministic envelope/root with the exact
  closed metadata and no self-reference.
- Identical calls are byte/ref idempotent; missing exact checkpoint parts repair, conflicts fail
  without overwriting; no absolute path, credential, mutable database key or physical claim leaks.

**TDD verify:**

```powershell
py -3.12 -m pytest -q tools/stm32-monitor/tests/test_analysis_workflows.py tools/stm32-monitor/tests/test_analysis.py tools/stm32-monitor/tests/test_replay.py
```

**Commit:** `feat(monitor): export deterministic analysis bundle`

## Task 7A: Prepare a replay verification checkpoint

**Product behavior:** A caller opens diagnostics from a failed Target replay, binds an external
source change, freezes/starts a verification and attaches every required genuine Monitor marker.
Fresh reload exposes one authoritative `VERIFYING` checkpoint ready for completion.

**Files:**

- Modify: `tools/stm32-toolkit/src/stm32_toolkit/diagnostic_workflows.py`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/diagnostics/model.py`
- Modify: `tools/stm32-toolkit/tests/test_fix_verification_model.py`
- Create: `tools/stm32-toolkit/tests/test_fix_verification_workflows.py`

**Required interfaces:**

- `diagnostic_declare_source_change`, `diagnostic_add_verification_plan`,
  `diagnostic_start_verification`, and `diagnostic_attach_marker`.
- Generalize `diagnostic_start` from Host-only to authoritative failed Host or failed Target replay;
  reject physical/unknown Target records in VS-03.
- Validate TestRuns only through TestRunRepository and analysis/marker only through EvidenceStore.
  Toolkit must not import Monitor; it consumes exact closed canonical analysis and marker JSON
  through their root/envelope/artifact contracts. The bundle is not a completion input. Enforce
  exact inventory/case/project/source/build/ELF lineage and plan digest.
- Require one genuine marker for every required analysis/evidence pair, and canonicalize the pair
  list together rather than sorting the two parallel tuples independently. Apply the exact unsigned
  ID versus full-artifact digest equations and marker payload/ref projection from design 3.7.
- Retry is idempotent. Any contradiction creates no partial event.
- Preserve existing Host behavior; accept only failed, replay, explicitly non-physical Target
  TestRuns at diagnostic start. Keep Target, Monitor and Diagnostic session IDs independent.
- Freeze the four preparation signatures, operation names, returned projections and
  error-classification rules from design section 3.7; do not invent a new adapter, bundle field,
  platform matrix or Gate.

**TDD verify:**

```powershell
py -3.12 -m pytest -q tools/stm32-toolkit/tests/test_fix_verification_model.py tools/stm32-toolkit/tests/test_fix_verification_workflows.py tools/stm32-toolkit/tests/test_diagnostic_workflows.py tools/stm32-toolkit/tests/test_target_replay_workflows.py
```

**Commit:** `feat(diagnostics): prepare replay fix verification`

## Task 7B: Complete and reload the replay verification

**Product behavior:** A caller completes the active checkpoint without selecting its outcome;
Toolkit reloads all mandatory Evidence, derives one deterministic FixVerification, applies the
frozen state transition, and shows the complete authoritative history.

**Files:**

- Modify: `tools/stm32-toolkit/src/stm32_toolkit/diagnostic_workflows.py`
- Modify: `tools/stm32-toolkit/tests/test_fix_verification_workflows.py`

**Required interfaces and behavior:**

- Implement `diagnostic_complete_verification` and `diagnostic_show_verification` with the exact
  signatures, operation names and result projections in design 3.7.
- Reload failed/fixed TestRuns, declaration, each closed analysis payload and its already-attached
  marker before the sole append. Enforce the exact unsigned ID/full artifact hash distinction.
- Derive completion time from fixed-after TestRun and derive PASSED/FAILED/INCONCLUSIVE/CANCELLED
  using the frozen priority. Only PASSED resolves; retry returns the same conclusion.
- Missing/corrupt mandatory Evidence becomes the named INCONCLUSIVE conclusion; incompatible
  identity and environment failure append nothing. Keep Host and Task 7A behavior compatible.

**TDD verify:**

```powershell
py -3.12 -m pytest -q tools/stm32-toolkit/tests/test_fix_verification_workflows.py tools/stm32-toolkit/tests/test_diagnostic_workflows.py tools/stm32-toolkit/tests/test_target_replay_workflows.py
```

**Commit:** `feat(diagnostics): complete replay fix verification`

## Task 8: Thin CLI and MCP projections

**Product behavior:** Shell and MCP callers invoke the same replay/analysis/verification application
services without adapter-owned orchestration or path authority.

**Files:**

- Modify: `tools/stm32-toolkit/src/stm32_toolkit/cli.py`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/mcp_server.py`
- Modify: `tools/stm32-monitor/src/stm32_monitor/cli.py`
- Create: `tools/stm32-toolkit/tests/test_fix_verification_cli.py`
- Create: `tools/stm32-toolkit/tests/test_fix_verification_mcp.py`
- Create: `tools/stm32-monitor/tests/test_analysis_cli.py`

**Required behavior:**

- Toolkit CLI exposes Target replay run plus diagnostic change/verification/marker/show commands.
- Monitor CLI exposes replay ingest, compare and bundle operations.
- Toolkit MCP exposes Target replay and all new diagnostic operations; server runtime supplies
  project/data/session roots and accepts no arbitrary server path.
- Adapters invoke one workflow once, return its unchanged result projection, enforce existing
  bounded file/JSON/schema rules, and never leak paths, exceptions or physical claims.
- Existing VS-01/VS-02 CLI/MCP behavior remains compatible.

**TDD verify:**

```powershell
py -3.12 -m pytest -q tools/stm32-toolkit/tests/test_fix_verification_cli.py tools/stm32-toolkit/tests/test_fix_verification_mcp.py tools/stm32-toolkit/tests/test_testing_cli.py tools/stm32-toolkit/tests/test_testing_mcp.py tools/stm32-toolkit/tests/test_diagnostic_cli.py tools/stm32-toolkit/tests/test_diagnostic_mcp.py tools/stm32-monitor/tests/test_analysis_cli.py tools/stm32-monitor/tests/test_cli.py
```

**Commit:** `feat(api): expose replay verification loop`

## Task 9: Runnable Scenario B and mandatory negatives

**Product behavior:** One integration test proves the complete VS-03 loop through public services
and fresh-object reload; named negatives prove fail-closed identity and insufficient-data behavior.

**Files:**

- Create: `tools/stm32-toolkit/tests/test_vs03_end_to_end.py`
- Modify only to correct a fixture/contract defect discovered by the end-to-end test: the VS-03
  fixture files and their owning test file from Tasks 2 or 4.

**Required acceptance:**

- Run failed Target replay, open/begin session, add two hypotheses, ingest failed Monitor replay,
  support one/refute one, bind source change, run fixed replay, ingest fixed Monitor replay, compare,
  publish/attach marker and bundle, freeze/start/complete verification, then discard all objects.
- Reload TestRuns, replay descriptors, Monitor windows/history, AnalysisResult, marker, bundle,
  DiagnosticSession events/checkpoints/roots and FixVerification from fresh objects. Assert exact
  replay/non-physical labels, distinct stable origin/import workspace IDs at every derived public
  boundary, VALID/COMPLETED/changed analysis, byte-identical bundle, PASSED and RESOLVED, and
  unchanged project tree.
- Incompatible project or undeclared firmware returns `INCOMPATIBLE_IDENTITY`, appends nothing and
  leaves session revision/input digests unchanged.
- Compatible insufficient pairs retain `INVALID/INCONCLUSIVE`, produce
  FixVerification(INCONCLUSIVE), and return the session to INVESTIGATING.

**TDD verify:**

```powershell
py -3.12 -m pytest -q tools/stm32-toolkit/tests/test_vs03_end_to_end.py
```

**Commit:** `test(integration): prove VS-03 replay verification`

## Final Sol review and slice verification

Sol reviews `dc304de6ef1d7efbdabe06ae37ec96a859615f84..HEAD` in full. Required review
points: module ownership, explicit replay provenance, no physical side effects, complete 64-hex
workspace identity, immutable source/evidence lineage, idempotency, state transitions, deterministic
bundle bytes, negative no-append behavior, adapter parity, old VS-01/VS-02 compatibility, and no
VS-04/release/remote scope.

Run with both source roots and CPython 3.12:

```powershell
py -3.12 -m pytest -q `
  tools/stm32-toolkit/tests/test_target_protocol.py `
  tools/stm32-toolkit/tests/test_target_runner.py `
  tools/stm32-toolkit/tests/test_target_transports.py `
  tools/stm32-toolkit/tests/test_target_replay.py `
  tools/stm32-toolkit/tests/test_target_replay_publication.py `
  tools/stm32-toolkit/tests/test_target_replay_workflows.py `
  tools/stm32-toolkit/tests/test_fix_verification_model.py `
  tools/stm32-toolkit/tests/test_fix_verification_events.py `
  tools/stm32-toolkit/tests/test_fix_verification_workflows.py `
  tools/stm32-toolkit/tests/test_fix_verification_cli.py `
  tools/stm32-toolkit/tests/test_fix_verification_mcp.py `
  tools/stm32-toolkit/tests/test_vs03_end_to_end.py `
  tools/stm32-toolkit/tests/test_diagnostic_model.py `
  tools/stm32-toolkit/tests/test_diagnostic_events.py `
  tools/stm32-toolkit/tests/test_diagnostic_store.py `
  tools/stm32-toolkit/tests/test_diagnostic_workflows.py `
  tools/stm32-toolkit/tests/test_diagnostic_cli.py `
  tools/stm32-toolkit/tests/test_diagnostic_mcp.py `
  tools/stm32-toolkit/tests/test_testing_model.py `
  tools/stm32-toolkit/tests/test_testing_publication.py `
  tools/stm32-toolkit/tests/test_testing_workflows.py `
  tools/stm32-toolkit/tests/test_testing_cli.py `
  tools/stm32-toolkit/tests/test_testing_mcp.py `
  tools/stm32-monitor/tests
git diff --check dc304de6ef1d7efbdabe06ae37ec96a859615f84..HEAD
git status --short
```

The complete Monitor suite is required because Task 1 changes the shared Monitor public identity
validator and the current-source baseline proved that risk trigger. Do not add coverage, packaging,
Python 3.10, Node/browser, hardware or release gates.

## VS-04 transition

After final Sol acceptance, freeze the VS-03 CodeHead and write the VS-04 physical integration
design/plan. Do not execute a real flash, Probe connection, Target run, or Monitor observation until
the user supplies the named hardware environment and separately authorizes each required MODIFY
phase.
