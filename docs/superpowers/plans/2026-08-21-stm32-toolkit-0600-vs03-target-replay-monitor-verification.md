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

**Frozen design commit:** `dc304de6ef1d7efbdabe06ae37ec96a859615f84`

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

- `TestRunPublisher.publish_target_replay(manifest, descriptor_envelope)` publishes operation
  `target-test-replay`, one descriptor parent, closed metadata and a `test-run` root whose metadata
  includes mode/state/execution source/non-physical flag.
- `TestRunRepository.load()` dispatches by envelope operation and preserves the current Host path
  byte-for-byte while validating the replay Target path independently.
- `target_replay_run(context, operation_id, descriptor_file, stream_file)` uses the existing Target
  decoder/runner, is idempotent by exact intent, and returns public execution/non-physical labels.
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
- Create: `tools/stm32-monitor/tests/test_replay.py`
- Add text fixtures under: `tools/stm32-monitor/tests/fixtures/vs03/`

**Required interfaces:**

- Frozen `MonitorReplayDocument` and `MonitorRunRef` with closed canonical projections/digests.
- `ingest_monitor_replay(paths, operation_id, document_file)` validates replay/non-physical labels,
  complete 64-hex workspace identity, binding, monotonic batch chain, scenario role and fixture
  digest before calling only `HistoryStore.append_batch`.
- Failed-before and fixed-after fixtures share project/target/selector/time grid and use the exact
  firmware identities declared by the corresponding Target descriptors.
- Identical retry returns the same reference. Conflict, partial/corrupt fixture, duplicate or
  non-monotonic batch, identity mismatch, and redirect/hard-link append nothing partial.

**TDD verify:**

```powershell
py -3.12 -m pytest -q tools/stm32-monitor/tests/test_replay.py tools/stm32-monitor/tests/test_history.py tools/stm32-monitor/tests/test_models.py
```

**Commit:** `feat(monitor): ingest replay observation windows`

## Task 5: Compare windows and publish analysis, marker and bundle

**Product behavior:** Compatible windows produce one bounded AnalysisResult, marker payload and
byte-deterministic bundle; insufficient input is explicit and incompatible identity publishes
nothing derived.

**Files:**

- Create: `tools/stm32-monitor/src/stm32_monitor/analysis.py`
- Create: `tools/stm32-monitor/src/stm32_monitor/analysis_workflows.py`
- Modify: `tools/stm32-monitor/src/stm32_monitor/__init__.py`
- Create: `tools/stm32-monitor/tests/test_analysis.py`
- Create: `tools/stm32-monitor/tests/test_analysis_workflows.py`

**Required interfaces:**

- Frozen `AnalysisRequest`, `AnalysisResult`, and `DiagnosticMarker` with design fields and closed
  reason codes.
- Run-relative exact-timestamp alignment for one exact scalar selector; no interpolation.
- `compare_monitor_runs(...)` queries only public HistoryStore pages, enforces source-change
  firmware bridge, and publishes canonical AnalysisResult/marker Evidence through an injected
  EvidenceStore.
- `export_analysis_bundle(...)` returns byte-identical canonical JSON and an immutable artifact for
  identical inputs.
- Insufficient pairs create retained `INVALID/INCONCLUSIVE`; incompatible identity returns stable
  failure before analysis/marker/bundle publication.

**TDD verify:**

```powershell
py -3.12 -m pytest -q tools/stm32-monitor/tests/test_analysis.py tools/stm32-monitor/tests/test_analysis_workflows.py tools/stm32-monitor/tests/test_replay.py tools/stm32-monitor/tests/test_history.py
```

**Commit:** `feat(monitor): publish bounded replay analysis`

## Task 6: Extend the diagnostic event domain and lifecycle

**Product behavior:** Existing sessions reload unchanged while new append-only events materialize
source changes, verification plans, markers, attempts and final FixVerifications.

**Files:**

- Modify: `tools/stm32-toolkit/src/stm32_toolkit/diagnostics/model.py`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/diagnostics/events.py`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/diagnostics/store.py`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/diagnostics/__init__.py`
- Create: `tools/stm32-toolkit/tests/test_fix_verification_model.py`
- Create: `tools/stm32-toolkit/tests/test_fix_verification_events.py`

**Required interfaces:**

- Frozen `SourceChangeDeclaration`, `VerificationPlan`, `DiagnosticMarkerRef`, and
  `FixVerification`, with exact design states/reason codes and canonical IDs/digests.
- Extend session states to `FIX_PROPOSED`, `VERIFYING`, `RESOLVED`, and `ABANDONED`, and retain all
  previous states/events/bytes.
- Implement the five new event types and transitions from the design. `PASSED` alone resolves;
  other completed results return to `INVESTIGATING` while attempts remain.
- Store checkpoints include every new immutable Evidence reference as a parent. Old chains reload;
  invalid transitions, missing evidence, stale revision, or conflict append nothing.

**TDD verify:**

```powershell
py -3.12 -m pytest -q tools/stm32-toolkit/tests/test_fix_verification_model.py tools/stm32-toolkit/tests/test_fix_verification_events.py tools/stm32-toolkit/tests/test_diagnostic_model.py tools/stm32-toolkit/tests/test_diagnostic_events.py tools/stm32-toolkit/tests/test_diagnostic_store.py
```

**Commit:** `feat(diagnostics): add fix verification lifecycle`

## Task 7: Execute source-change and verification workflows

**Product behavior:** A caller binds an external source change, freezes/starts a verification,
attaches a Monitor marker, completes a FixVerification, and reloads the authoritative conclusion.

**Files:**

- Modify: `tools/stm32-toolkit/src/stm32_toolkit/diagnostic_workflows.py`
- Create: `tools/stm32-toolkit/tests/test_fix_verification_workflows.py`

**Required interfaces:**

- `diagnostic_declare_source_change`, `diagnostic_add_verification_plan`,
  `diagnostic_start_verification`, `diagnostic_attach_marker`,
  `diagnostic_complete_verification`, and `diagnostic_show_verification`.
- Generalize `diagnostic_start` from Host-only to authoritative failed Host or failed Target replay;
  reject physical/unknown Target records in VS-03.
- Validate TestRuns only through TestRunRepository and analysis/marker/bundle only through
  EvidenceStore. Enforce exact inventory/case/project/source/build/ELF lineage and plan digest.
- Derive PASSED/FAILED/INCONCLUSIVE from evidence; callers cannot select a successful status.
- Retry is idempotent. Any contradiction creates no partial event; only PASSED resolves.

**TDD verify:**

```powershell
py -3.12 -m pytest -q tools/stm32-toolkit/tests/test_fix_verification_workflows.py tools/stm32-toolkit/tests/test_diagnostic_workflows.py tools/stm32-toolkit/tests/test_target_replay_workflows.py
```

**Commit:** `feat(diagnostics): execute replay fix verification`

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
  replay/non-physical labels, VALID/COMPLETED/changed analysis, byte-identical bundle, PASSED and
  RESOLVED, and unchanged project tree.
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
