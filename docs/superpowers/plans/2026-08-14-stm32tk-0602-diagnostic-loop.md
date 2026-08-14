# STM32TK-0602 Diagnostic Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver an append-only evidence-driven diagnostic state machine, bounded Probe v2 controls, action-specific authorization, and deterministic failed-before/fixed-after verification.

**Architecture:** Diagnostics materialize immutable hash-chained events that reference 0601 evidence IDs. Probe Service implements the already-frozen v2 debug operations and remains the only hardware boundary. Source changes are externally supplied declarations; Toolkit separately authorizes and records build, flash, test, Monitor assertion, and verification steps.

**Tech Stack:** Python 3.10/3.12, dataclasses, JSON Schema, SHA-256 canonical JSON, pyOCD, aiohttp, pytest/pytest-cov, Hypothesis-style property fixtures where already approved, PowerShell release gates.

## Global Constraints

- Begin at the accepted report commit of `STM32TK-0601-TEST-EVIDENCE`; record its full SHA in the
  work order before implementation.
- Follow `docs/superpowers/specs/2026-08-14-stm32tk-0602-diagnostic-loop-design.md`.
- Do not change frozen evidence/test schemas, Probe v2, gate schema/families, or 0601 exact entries.
  Fill only reserved 0602 catalog families and freeze their exact commands/nodes before candidate.
- Product code cannot edit source, invoke a model/cloud provider, accept a raw hardware command,
  expose arbitrary memory/register writes, or reuse authorization.
- Real reset/flash/modify acceptance gates stop unless the user authorizes their exact current-task
  action digests; this plan and prior-module evidence do not transfer authorization.
- Every changed product Python file must reach at least 90% branch coverage; correctness runs on
  CPython 3.10 and 3.12; every earlier threshold remains unchanged.
- Preserve external evidence logs and never run release gates in a dirty product worktree.
- No remote operation is authorized; commits in this plan remain local until separate approval.

---

## Task 1: Define diagnostic schemas, events, and legal transitions

**Files:**

- Create: `schemas/diagnostic-session.schema.json`
- Create: `tools/stm32-toolkit/src/stm32_toolkit/schemas/diagnostic-session.schema.json`
- Create: `tools/stm32-toolkit/src/stm32_toolkit/diagnostics/__init__.py`
- Create: `tools/stm32-toolkit/src/stm32_toolkit/diagnostics/model.py`
- Create: `tools/stm32-toolkit/src/stm32_toolkit/diagnostics/events.py`
- Create: `tools/stm32-toolkit/tests/test_diagnostic_model.py`
- Create: `tools/stm32-toolkit/tests/test_diagnostic_events.py`

- [ ] Write failing tests for exact dataclasses/enums, canonical event digest, sequence/revision/
  previous-digest binding, every legal state edge, every forbidden edge, fresh serialization,
  UTC/NFC/unknown fields, 1 MiB event and collection limits, and root/package schema equality.

```python
@pytest.mark.parametrize("before,event,after", LEGAL_TRANSITIONS)
def test_legal_transition(before, event, after):
    assert reduce_event(session(before), event).state is after
```

- [ ] Run RED:

```powershell
py -3.12 -m pytest tools/stm32-toolkit/tests/test_diagnostic_model.py tools/stm32-toolkit/tests/test_diagnostic_events.py -q -p no:cacheprovider
```

- [ ] Implement frozen `DiagnosticSession`, `DiagnosticEvent`, states, payload parsers, canonical
  digests, and pure `reduce_event`; keep persistence and side effects out of the reducer.

- [ ] Run GREEN on 3.10/3.12 with branch coverage:

```powershell
py -3.10 -m pytest tools/stm32-toolkit/tests/test_diagnostic_model.py tools/stm32-toolkit/tests/test_diagnostic_events.py -q -p no:cacheprovider
py -3.12 tools/release/run_0600_gates.py dev-coverage --task-id STM32TK-0602-T01 --evidence-root C:\tmp\stm32tk-0602-t01-coverage -- tools/stm32-toolkit/tests/test_diagnostic_model.py tools/stm32-toolkit/tests/test_diagnostic_events.py --cov=stm32_toolkit.diagnostics.model --cov=stm32_toolkit.diagnostics.events -q -p no:cacheprovider
```

- [ ] Commit:

```powershell
git add -- schemas/diagnostic-session.schema.json tools/stm32-toolkit/src/stm32_toolkit/schemas/diagnostic-session.schema.json tools/stm32-toolkit/src/stm32_toolkit/diagnostics/__init__.py tools/stm32-toolkit/src/stm32_toolkit/diagnostics/model.py tools/stm32-toolkit/src/stm32_toolkit/diagnostics/events.py tools/stm32-toolkit/tests/test_diagnostic_model.py tools/stm32-toolkit/tests/test_diagnostic_events.py
git commit -m "feat(STM32TK-0602): define append-only diagnostic events"
```

## Task 2: Persist and recover diagnostic event chains

**Files:**

- Create: `tools/stm32-toolkit/src/stm32_toolkit/diagnostics/store.py`
- Create: `tools/stm32-toolkit/src/stm32_toolkit/diagnostics/session.py`
- Create: `tools/stm32-toolkit/tests/test_diagnostic_store.py`
- Create: `tools/stm32-toolkit/tests/test_diagnostic_concurrency.py`

- [ ] Write failing tests for create/append/read/materialize, per-session lock, stale revisions,
  concurrent append winner, complete-chain verification, sequence gap/reorder/forgery, corrupt
  head/event, crash before/after event/head publication, bounded sessions/events, safe paths,
  and independent workspaces with equal session IDs.

- [ ] Run RED:

```powershell
py -3.12 -m pytest tools/stm32-toolkit/tests/test_diagnostic_store.py tools/stm32-toolkit/tests/test_diagnostic_concurrency.py -q -p no:cacheprovider
```

- [ ] Implement atomic event/head publication under an owned lock. Cold open verifies the full
  chain and creates a checkpoint bound to head, store generation, and immutable file identities;
  warm append rechecks that checkpoint, head, and latest event in O(1). Full reads/exports reverify
  the chain. Reconcile an event published before a crashed head update only when it is the unique
  valid successor; never truncate or overwrite a corrupt chain.

- [ ] Run GREEN under both Pythons and coverage:

```powershell
py -3.10 -m pytest tools/stm32-toolkit/tests/test_diagnostic_store.py tools/stm32-toolkit/tests/test_diagnostic_concurrency.py -q -p no:cacheprovider
py -3.12 tools/release/run_0600_gates.py dev-coverage --task-id STM32TK-0602-T02 --evidence-root C:\tmp\stm32tk-0602-t02-coverage -- tools/stm32-toolkit/tests/test_diagnostic_store.py tools/stm32-toolkit/tests/test_diagnostic_concurrency.py --cov=stm32_toolkit.diagnostics.store --cov=stm32_toolkit.diagnostics.session -q -p no:cacheprovider
```

- [ ] Commit:

```powershell
git add tools/stm32-toolkit/src/stm32_toolkit/diagnostics/store.py tools/stm32-toolkit/src/stm32_toolkit/diagnostics/session.py tools/stm32-toolkit/tests/test_diagnostic_store.py tools/stm32-toolkit/tests/test_diagnostic_concurrency.py
git commit -m "feat(STM32TK-0602): persist diagnostic hash chains"
```

## Task 3: Add hypotheses and evidence assessments

**Files:**

- Create: `tools/stm32-toolkit/src/stm32_toolkit/diagnostics/hypotheses.py`
- Create: `tools/stm32-toolkit/tests/test_diagnostic_hypotheses.py`

- [ ] Write failing tests for add/assess/status/conclude events, verified evidence lookup and fact
  selectors, supporting/refuting polarity, same-selector conflict, confidence vocabulary,
  competing hypotheses, unresolved questions, residual risks, missing/corrupt/wrong-workspace
  evidence, and immutable prior revisions.

- [ ] Run RED:

```powershell
py -3.12 -m pytest tools/stm32-toolkit/tests/test_diagnostic_hypotheses.py -q -p no:cacheprovider
```

- [ ] Implement typed commands that validate through the public `EvidenceStore` API and emit
  events. Do not infer facts or numeric confidence from rationale text.

- [ ] Run GREEN on 3.10 and 3.12 with coverage:

```powershell
py -3.10 -m pytest tools/stm32-toolkit/tests/test_diagnostic_hypotheses.py -q -p no:cacheprovider
py -3.12 tools/release/run_0600_gates.py dev-coverage --task-id STM32TK-0602-T03 --evidence-root C:\tmp\stm32tk-0602-t03-coverage -- tools/stm32-toolkit/tests/test_diagnostic_hypotheses.py --cov=stm32_toolkit.diagnostics.hypotheses -q -p no:cacheprovider
```

- [ ] Commit:

```powershell
git add tools/stm32-toolkit/src/stm32_toolkit/diagnostics/hypotheses.py tools/stm32-toolkit/tests/test_diagnostic_hypotheses.py
git commit -m "feat(STM32TK-0602): preserve competing evidence hypotheses"
```

## Task 4: Implement closed observation plans

**Files:**

- Create: `tools/stm32-toolkit/src/stm32_toolkit/diagnostics/observations.py`
- Create: `tools/stm32-toolkit/src/stm32_toolkit/diagnostics/policy.py`
- Create: `tools/stm32-toolkit/tests/test_observation_plans.py`

- [ ] Write failing tests for the closed operation enum, typed args, dependency DAG/cycle
  rejection, OBSERVE/CONTROL/MODIFY classification, independent concurrency, per-probe
  serialization, deadline/cancellation, prerequisite BLOCKED records, artifact/evidence linking,
  response limits, and rejection of shell/raw backend/model/cloud operations.

- [ ] Run RED:

```powershell
py -3.12 -m pytest tools/stm32-toolkit/tests/test_observation_plans.py -q -p no:cacheprovider
```

- [ ] Implement `ObservationPlan.validate()` and `ObservationExecutor.run()` using registered
  typed handlers for existing build/source/evidence/debug/test/Monitor APIs; every attempted step
  emits a result event even when blocked or cancelled.

- [ ] Run GREEN and branch coverage on both interpreters:

```powershell
py -3.10 -m pytest tools/stm32-toolkit/tests/test_observation_plans.py -q -p no:cacheprovider
py -3.12 tools/release/run_0600_gates.py dev-coverage --task-id STM32TK-0602-T04 --evidence-root C:\tmp\stm32tk-0602-t04-coverage -- tools/stm32-toolkit/tests/test_observation_plans.py --cov=stm32_toolkit.diagnostics.observations --cov=stm32_toolkit.diagnostics.policy -q -p no:cacheprovider
```

- [ ] Commit:

```powershell
git add tools/stm32-toolkit/src/stm32_toolkit/diagnostics/observations.py tools/stm32-toolkit/src/stm32_toolkit/diagnostics/policy.py tools/stm32-toolkit/tests/test_observation_plans.py
git commit -m "feat(STM32TK-0602): execute bounded observation plans"
```

## Task 5: Implement Probe v2 observation reads

**Files:**

- Create: `tools/stm32-toolkit/src/stm32_toolkit/debug/registers.py`
- Create: `tools/stm32-toolkit/src/stm32_toolkit/debug/logs.py`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/debug/fault.py`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/probe/service.py`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/probe/client.py`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/probe/backend.py`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/probe/pyocd_backend.py`
- Create: `tools/stm32-toolkit/tests/test_probe_v2_observe.py`
- Create: `tools/stm32-toolkit/tests/test_debug_logs.py`

- [ ] Write failing tests for target state, allowlisted registers, declared RAM/peripheral ranges,
  destructive peripheral denial, <=4 KiB reads, Fault stack bounds, named log channels, 10 MiB/
  five-minute limits, backpressure, deadline/disconnect cleanup, backend exception redaction, and
  unknown-field/version/lease/workspace rejection.

- [ ] Run RED:

```powershell
py -3.12 -m pytest tools/stm32-toolkit/tests/test_probe_v2_observe.py tools/stm32-toolkit/tests/test_debug_logs.py -q -p no:cacheprovider
```

- [ ] Implement only the frozen OBSERVE operations and backend methods; range-check before the
  backend call and return bounded typed evidence artifacts.

- [ ] Run GREEN under dual Python with affected Fault/read/sample/probe regressions and coverage:

```powershell
py -3.10 -m pytest tools/stm32-toolkit/tests/test_probe_v2_observe.py tools/stm32-toolkit/tests/test_debug_logs.py tools/stm32-toolkit/tests/test_fault.py tools/stm32-toolkit/tests/test_debug_read.py -q -p no:cacheprovider
py -3.12 tools/release/run_0600_gates.py dev-coverage --task-id STM32TK-0602-T05 --evidence-root C:\tmp\stm32tk-0602-t05-coverage -- tools/stm32-toolkit/tests/test_probe_v2_observe.py tools/stm32-toolkit/tests/test_debug_logs.py tools/stm32-toolkit/tests/test_fault.py tools/stm32-toolkit/tests/test_debug_read.py --cov=stm32_toolkit.debug --cov=stm32_toolkit.probe -q -p no:cacheprovider
```

- [ ] Commit:

```powershell
git add -- tools/stm32-toolkit/src/stm32_toolkit/debug/registers.py tools/stm32-toolkit/src/stm32_toolkit/debug/logs.py tools/stm32-toolkit/src/stm32_toolkit/debug/fault.py tools/stm32-toolkit/src/stm32_toolkit/probe/service.py tools/stm32-toolkit/src/stm32_toolkit/probe/client.py tools/stm32-toolkit/src/stm32_toolkit/probe/backend.py tools/stm32-toolkit/src/stm32_toolkit/probe/pyocd_backend.py tools/stm32-toolkit/tests/test_probe_v2_observe.py tools/stm32-toolkit/tests/test_debug_logs.py
git commit -m "feat(STM32TK-0602): add bounded debug observations"
```

## Task 6: Implement exact authorized debug controls

**Files:**

- Create: `tools/stm32-toolkit/src/stm32_toolkit/debug/control.py`
- Create: `tools/stm32-toolkit/src/stm32_toolkit/debug/breakpoints.py`
- Create: `tools/stm32-toolkit/src/stm32_toolkit/diagnostics/actions.py`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/probe/service.py`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/probe/client.py`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/probe/backend.py`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/probe/pyocd_backend.py`
- Create: `tools/stm32-toolkit/tests/test_diagnostic_authorization.py`
- Create: `tools/stm32-toolkit/tests/test_probe_v2_control.py`

- [ ] Write failing mutation tests proving session/revision/workspace/project/target/probe/firmware/
  state/operation/arguments/expiry are digest-bound; authorization consumes once on success,
  denial, backend failure, and timeout; replay/retry/rebind fail.

- [ ] Write failing halt/resume/single-step/temporary-breakpoint tests for legal target states,
  executable address, eight-breakpoint limit, five-second step timeout, cleanup in every exit,
  disconnect recovery, reversible restoration, cleanup-required lockout, and no write/raw command.

- [ ] Run RED:

```powershell
py -3.12 -m pytest tools/stm32-toolkit/tests/test_diagnostic_authorization.py tools/stm32-toolkit/tests/test_probe_v2_control.py -q -p no:cacheprovider
```

- [ ] Implement `prepare_action()` returning exact digest/summary and `execute_action()` requiring
  current revision plus one authorization. Keep cleanup owned by Probe Service and always record
  action/cleanup evidence events.

- [ ] Run GREEN on both Pythons with branch coverage and existing probe lease/process tests:

```powershell
py -3.10 -m pytest tools/stm32-toolkit/tests/test_diagnostic_authorization.py tools/stm32-toolkit/tests/test_probe_v2_control.py tools/stm32-toolkit/tests/test_probe_lease.py tools/stm32-toolkit/tests/test_process.py -q -p no:cacheprovider
py -3.12 tools/release/run_0600_gates.py dev-coverage --task-id STM32TK-0602-T06 --evidence-root C:\tmp\stm32tk-0602-t06-coverage -- tools/stm32-toolkit/tests/test_diagnostic_authorization.py tools/stm32-toolkit/tests/test_probe_v2_control.py tools/stm32-toolkit/tests/test_probe_lease.py tools/stm32-toolkit/tests/test_process.py --cov=stm32_toolkit.debug.control --cov=stm32_toolkit.debug.breakpoints --cov=stm32_toolkit.diagnostics.actions --cov=stm32_toolkit.probe -q -p no:cacheprovider
```

- [ ] Commit:

```powershell
git add -- tools/stm32-toolkit/src/stm32_toolkit/debug/control.py tools/stm32-toolkit/src/stm32_toolkit/debug/breakpoints.py tools/stm32-toolkit/src/stm32_toolkit/diagnostics/actions.py tools/stm32-toolkit/src/stm32_toolkit/probe/service.py tools/stm32-toolkit/src/stm32_toolkit/probe/client.py tools/stm32-toolkit/src/stm32_toolkit/probe/backend.py tools/stm32-toolkit/src/stm32_toolkit/probe/pyocd_backend.py tools/stm32-toolkit/tests/test_diagnostic_authorization.py tools/stm32-toolkit/tests/test_probe_v2_control.py
git commit -m "feat(STM32TK-0602): authorize bounded debug controls"
```

## Task 7: Bind external source changes and deterministic verification

**Files:**

- Create: `tools/stm32-toolkit/src/stm32_toolkit/diagnostics/verification.py`
- Create: `tools/stm32-toolkit/tests/test_source_change_declaration.py`
- Create: `tools/stm32-toolkit/tests/test_fix_verification.py`

- [ ] Write failing declaration tests for canonical tracked paths, exact diff artifact, complete
  before/after build-input snapshots, changed-path equality, expected revision, unrelated inputs,
  missing/corrupt artifacts, and proof Toolkit neither writes nor applies a source file.

- [ ] Write a complete verification truth table: failed-before required, plan frozen before
  declaration, new build/ELF/source identity, separate action authorization chain, exact Host/
  Target tests, Monitor operator/threshold/duration/quality, regression IDs, stale/skipped/blocked/
  corrupt/missing evidence, failed verification returning to INVESTIGATING, and PASS-only resolve.

- [ ] Run RED:

```powershell
py -3.12 -m pytest tools/stm32-toolkit/tests/test_source_change_declaration.py tools/stm32-toolkit/tests/test_fix_verification.py -q -p no:cacheprovider
```

- [ ] Implement frozen `SourceChangeDeclaration`, `VerificationPlan`, `MonitorAssertion`, and pure
  `evaluate_fix()` over verified evidence. Build/flash/test remain calls to existing authorized
  workflows and each result appends its own event.

- [ ] Run GREEN on both Pythons with coverage and affected build/flash/test/Monitor bridge tests:

```powershell
py -3.10 -m pytest tools/stm32-toolkit/tests/test_source_change_declaration.py tools/stm32-toolkit/tests/test_fix_verification.py tools/stm32-toolkit/tests/test_build_runner.py tools/stm32-toolkit/tests/test_hardware_workflows.py tools/stm32-toolkit/tests/test_monitor_observation.py -q -p no:cacheprovider
py -3.12 tools/release/run_0600_gates.py dev-coverage --task-id STM32TK-0602-T07 --evidence-root C:\tmp\stm32tk-0602-t07-coverage -- tools/stm32-toolkit/tests/test_source_change_declaration.py tools/stm32-toolkit/tests/test_fix_verification.py --cov=stm32_toolkit.diagnostics.verification -q -p no:cacheprovider
```

- [ ] Commit:

```powershell
git add tools/stm32-toolkit/src/stm32_toolkit/diagnostics/verification.py tools/stm32-toolkit/tests/test_source_change_declaration.py tools/stm32-toolkit/tests/test_fix_verification.py
git commit -m "feat(STM32TK-0602): verify identity-bound firmware fixes"
```

## Task 8: Export and verify portable diagnostic bundles

**Files:**

- Create: `tools/stm32-toolkit/src/stm32_toolkit/diagnostics/bundle.py`
- Create: `tools/stm32-toolkit/tests/test_diagnostic_bundle.py`

- [ ] Write failing tests for deterministic repeated ZIP bytes, fixed ordering/times/modes,
  complete reachability/inventory/hash, 1 GiB and entry limits, corrupt/missing objects, secret/
  absolute-path/environment redaction, zip-slip, drive/ADS/casefold/duplicate names, symlinks,
  compression bomb, atomic import, existing same/different session heads, and no partial publish.

- [ ] Run RED:

```powershell
py -3.12 -m pytest tools/stm32-toolkit/tests/test_diagnostic_bundle.py -q -p no:cacheprovider
```

- [ ] Implement `export_bundle(session_id, selection, output)` and `verify_import_bundle(path)`;
  verify every entry and complete graph before importing through public evidence/session APIs.

- [ ] Run GREEN dual Python with coverage:

```powershell
py -3.10 -m pytest tools/stm32-toolkit/tests/test_diagnostic_bundle.py -q -p no:cacheprovider
py -3.12 tools/release/run_0600_gates.py dev-coverage --task-id STM32TK-0602-T08 --evidence-root C:\tmp\stm32tk-0602-t08-coverage -- tools/stm32-toolkit/tests/test_diagnostic_bundle.py --cov=stm32_toolkit.diagnostics.bundle -q -p no:cacheprovider
```

- [ ] Commit:

```powershell
git add tools/stm32-toolkit/src/stm32_toolkit/diagnostics/bundle.py tools/stm32-toolkit/tests/test_diagnostic_bundle.py
git commit -m "feat(STM32TK-0602): export verified diagnostic bundles"
```

## Task 9: Expose diagnostic CLI, MCP, and Skill

**Files:**

- Modify: `tools/stm32-toolkit/src/stm32_toolkit/cli.py`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/mcp_server.py`
- Create: `skills/diagnose-firmware/SKILL.md`
- Create: `tools/stm32-toolkit/tests/test_diagnostic_cli.py`
- Create: `tools/stm32-toolkit/tests/test_diagnostic_mcp.py`
- Modify: `tools/stm32-toolkit/tests/test_plugin_layout.py`

- [ ] Write failing CLI/MCP tests for every typed surface, expected revision, exact error codes,
  bounded artifact references, prepare/execute authorization dialogue, denial, cross-workspace/
  session/evidence isolation, response mutation safety, and redaction.

- [ ] Write Skill contract tests requiring reproduce→hypotheses→discriminating observations→
  authorization→declared change→frozen verification and prohibiting “fixed” without deterministic
  PASS, implicit edits/flash, raw commands, model/cloud code, or stored authorization.

- [ ] Run RED, implement thin adapters/Skill, then run GREEN:

```powershell
py -3.12 -m pytest tools/stm32-toolkit/tests/test_diagnostic_cli.py tools/stm32-toolkit/tests/test_diagnostic_mcp.py tools/stm32-toolkit/tests/test_plugin_layout.py -q -p no:cacheprovider
py -3.10 -m pytest tools/stm32-toolkit/tests/test_diagnostic_cli.py tools/stm32-toolkit/tests/test_diagnostic_mcp.py tools/stm32-toolkit/tests/test_plugin_layout.py -q -p no:cacheprovider
py -3.12 tools/release/run_0600_gates.py dev-coverage --task-id STM32TK-0602-T09 --evidence-root C:\tmp\stm32tk-0602-t09-coverage -- tools/stm32-toolkit/tests/test_diagnostic_cli.py tools/stm32-toolkit/tests/test_diagnostic_mcp.py --cov=stm32_toolkit.cli --cov=stm32_toolkit.mcp_server -q -p no:cacheprovider
```

- [ ] Commit:

```powershell
git add tools/stm32-toolkit/src/stm32_toolkit/cli.py tools/stm32-toolkit/src/stm32_toolkit/mcp_server.py skills/diagnose-firmware/SKILL.md tools/stm32-toolkit/tests/test_diagnostic_cli.py tools/stm32-toolkit/tests/test_diagnostic_mcp.py tools/stm32-toolkit/tests/test_plugin_layout.py
git commit -m "feat(STM32TK-0602): expose evidence-first diagnostics"
```

## Task 10: Characterize and calibrate diagnostic performance

**Files:**

- Create: `tools/stm32-toolkit/tests/test_diagnostic_performance.py`
- Modify: `tools/release/performance_0600.json`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/diagnostics/events.py`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/diagnostics/store.py`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/diagnostics/session.py`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/diagnostics/bundle.py`
- Modify: `tools/stm32-toolkit/tests/test_diagnostic_events.py`
- Modify: `tools/stm32-toolkit/tests/test_diagnostic_store.py`
- Modify: `tools/stm32-toolkit/tests/test_diagnostic_bundle.py`

- [ ] Add correctness-first end-to-end workloads for append/reload, materialized read, authoritative
  full-chain verify, and export/reverify at the exact datasets. Do not optimize yet.

- [ ] Calibrate separately on 3.10/3.12 using the common three-batch nearest-rank method and retain
  raw JSON externally:

```powershell
py -3.10 tools/release/run_0600_gates.py performance --module STM32TK-0602 --test-file tools/stm32-toolkit/tests/test_diagnostic_performance.py --mode calibrate --output C:\tmp\stm32tk-0602-perf-310.json
py -3.12 tools/release/run_0600_gates.py performance --module STM32TK-0602 --test-file tools/stm32-toolkit/tests/test_diagnostic_performance.py --mode calibrate --output C:\tmp\stm32tk-0602-perf-312.json
py -3.12 tools/release/verify_0600_release.py performance-calibration --profile STM32TK-0602 --input C:\tmp\stm32tk-0602-perf-310.json --input C:\tmp\stm32tk-0602-perf-312.json --output tools/release/performance_0600.json
```

Expected: all calculated absolute thresholds are at/below their design maxima and the environment,
workload, batch, p95, MAD, and relative-limit calculations verify.

- [ ] The calibration verifier must update `performance_0600.json` atomically only when all
  calculated thresholds are within their predeclared maxima. On failure it leaves the tracked file
  byte-identical; improve the implementation without changing workloads or maxima, then repeat the
  provisional characterization.

- [ ] Commit the performance test and accepted baseline/threshold entries before any optional
  post-baseline optimization:

```powershell
git add -- tools/release/performance_0600.json tools/stm32-toolkit/tests/test_diagnostic_performance.py
git commit -m "test(STM32TK-0602): freeze diagnostic performance"
```

- [ ] Profile the correct reference and add only necessary local/thread-safe optimizations with
  event-chain, concurrency, bundle, and corruption regressions. Global GC state is forbidden.

- [ ] Always verify calibrated performance under both Pythons without coverage:

```powershell
py -3.10 tools/release/run_0600_gates.py performance --module STM32TK-0602 --test-file tools/stm32-toolkit/tests/test_diagnostic_performance.py --mode verify --performance-config tools/release/performance_0600.json --output C:\tmp\stm32tk-0602-perf-verify-310.json
py -3.12 tools/release/run_0600_gates.py performance --module STM32TK-0602 --test-file tools/stm32-toolkit/tests/test_diagnostic_performance.py --mode verify --performance-config tools/release/performance_0600.json --output C:\tmp\stm32tk-0602-perf-verify-312.json
```

- [ ] If and only if profiling produced product/test edits, run per-file coverage and commit exact
  optimized paths. If no optimization is necessary, record that fact externally and do not create
  an empty commit:

```powershell
py -3.12 tools/release/run_0600_gates.py dev-coverage --task-id STM32TK-0602-T10 --evidence-root C:\tmp\stm32tk-0602-t10-coverage -- tools/stm32-toolkit/tests/test_diagnostic_events.py tools/stm32-toolkit/tests/test_diagnostic_store.py tools/stm32-toolkit/tests/test_diagnostic_bundle.py --cov=stm32_toolkit.diagnostics -q -p no:cacheprovider
git add -- tools/stm32-toolkit/src/stm32_toolkit/diagnostics/events.py tools/stm32-toolkit/src/stm32_toolkit/diagnostics/store.py tools/stm32-toolkit/src/stm32_toolkit/diagnostics/session.py tools/stm32-toolkit/src/stm32_toolkit/diagnostics/bundle.py tools/stm32-toolkit/tests/test_diagnostic_events.py tools/stm32-toolkit/tests/test_diagnostic_store.py tools/stm32-toolkit/tests/test_diagnostic_bundle.py
git commit -m "perf(STM32TK-0602): meet calibrated diagnostic budgets"
```

## Task 11: Close real-board failed-before/fixed-after acceptance

**Files:**

- Create: `tools/stm32-toolkit/tests/hardware/test_diagnostic_loop_real.py`
- Create: `tools/stm32-toolkit/tests/fixtures/diagnostic-loop/.stm32-project.json`
- Create: `tools/stm32-toolkit/tests/fixtures/diagnostic-loop/Src/main.c`
- Create: `tools/stm32-toolkit/tests/fixtures/diagnostic-loop/Tests/test_fault.c`
- Create: `tools/stm32-toolkit/tests/fixtures/diagnostic-loop/expected-fix.patch`
- Create: `tools/stm32-toolkit/tests/fixtures/diagnostic-loop/README.md`
- Modify: `README.md`
- Modify: `tools/stm32-toolkit/README.md`

- [ ] Add a deterministic real-board faulty fixture bound to the feasibility hardware profile and
  test the nine-step scenario from the spec:
  failed test/Monitor evidence, two hypotheses, observations, authorized halt/breakpoint/step/
  resume/cleanup, external change declaration, separately authorized build/flash/test, new identity,
  passing exact test/assertion, resolved session, and verified bundle.

- [ ] Run the newly added real-board scenario once before documenting it. Prior tasks already own
  dual-Python correctness, per-file coverage, and calibrated performance; Task 12 candidate owns
  the complete affected security/isolation/offline/install regression. Do not rerun unchanged 0601
  hardware gates unless the frozen impact map selects a shared surface.

```powershell
$env:STM32TK_FEASIBILITY_PROFILE='C:\tmp\stm32tk-0600-support\feasibility\profile.json'
try {
  py -3.12 -m pytest tools/stm32-toolkit/tests/hardware/test_diagnostic_loop_real.py -q -p no:cacheprovider
  if ($LASTEXITCODE -ne 0) { throw 'real diagnostic loop acceptance failed' }
} finally {
  Remove-Item Env:STM32TK_FEASIBILITY_PROFILE -ErrorAction SilentlyContinue
}
```

- [ ] Update documentation only after real evidence exists. Document the diagnostic state machine,
  evidence reasoning, exact authorization, source-edit boundary, verification truth, bundle limits,
  and prohibited operations.

- [ ] Commit:

```powershell
git add -- tools/stm32-toolkit/tests/hardware/test_diagnostic_loop_real.py tools/stm32-toolkit/tests/fixtures/diagnostic-loop/.stm32-project.json tools/stm32-toolkit/tests/fixtures/diagnostic-loop/Src/main.c tools/stm32-toolkit/tests/fixtures/diagnostic-loop/Tests/test_fault.c tools/stm32-toolkit/tests/fixtures/diagnostic-loop/expected-fix.patch tools/stm32-toolkit/tests/fixtures/diagnostic-loop/README.md README.md tools/stm32-toolkit/README.md
git commit -m "test(STM32TK-0602): close diagnostic loop acceptance"
```

## Task 12: Freeze and accept the 0602 CodeHead

**Files:**

- Modify: `tools/release/gates_0600.json`
- Modify: `tools/stm32-toolkit/tests/release/test_gate_catalog_0600.py`
- Create after PASS only: `docs/openclaw/returns/STM32TK-0602-DIAGNOSTIC-LOOP/r001-implementation-report.md`

- [ ] Audit the full 0601 accepted-report-to-current diff and all tracked/untracked, committed/
  uncommitted, and pushed/unpushed state. Verify frozen 0601 schemas/catalog semantics byte-for-
  byte and confirm no arbitrary write/raw command/model/cloud surface exists.

- [ ] Collect every exact 0602 node after Task 11, replace only reserved 0602 slots with closed
  argv/owners/platforms/timeouts/evidence/coverage/prerequisites/impact edges, and add mutation tests
  proving all 0601 entries remain byte-identical and missing/extra/duplicate/renamed/deselected/
  skip/xfail 0602 nodes fail. Commit the final 0602 test contract before candidate:

```powershell
py -3.12 -m pytest tools/stm32-toolkit/tests/release/test_gate_catalog_0600.py -q -p no:cacheprovider
git add -- tools/release/gates_0600.json tools/stm32-toolkit/tests/release/test_gate_catalog_0600.py
git commit -m "test(STM32TK-0602): freeze exact candidate inventory"
```

- [ ] Generate one `candidateRunId`, then run affected collect-all Windows/Linux shards and the
  hardware shard selected by the frozen impact map. Each wrapper first runs the non-executing
  CodeHead/catalog/node/performance/support/tool/owner/hardware/evidence-root precheck and refuses to
  start a product body if it fails:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File tools/release/run_0600_candidate.ps1 -Module STM32TK-0602 -Shard windows -CandidateRunId <candidateRunId> -EvidenceRoot C:\tmp\stm32tk-0602-candidate-<candidateRunId>\windows -ExpectedCodeHead <full-codehead> -Catalog tools/release/gates_0600.json -Performance tools/release/performance_0600.json -SupportProfile C:\tmp\stm32tk-0600-support\feasibility\profile.json
powershell.exe -NoProfile -ExecutionPolicy Bypass -File tools/release/run_0600_candidate.ps1 -Module STM32TK-0602 -Shard hardware -CandidateRunId <candidateRunId> -EvidenceRoot C:\tmp\stm32tk-0602-candidate-<candidateRunId>\hardware -ExpectedCodeHead <full-codehead> -Catalog tools/release/gates_0600.json -Performance tools/release/performance_0600.json -SupportProfile C:\tmp\stm32tk-0600-support\feasibility\profile.json
```

```bash
./tools/release/run_0600_candidate.sh --module STM32TK-0602 --shard linux --candidate-run-id <candidateRunId> --evidence-root /tmp/stm32tk-0602-candidate-<candidateRunId>/linux --expected-code-head <full-codehead> --catalog tools/release/gates_0600.json --performance tools/release/performance_0600.json --support-profile /tmp/stm32tk-0600-support/feasibility/profile.json
```

The Linux owner returns `linux/shard-package.zip` and its SHA-256 through the user-designated
evidence channel; place it unchanged at
`C:\tmp\stm32tk-0602-candidate-<candidateRunId>\imports\linux.zip`. No controller performs transfer.

- [ ] On failure, do not write a report. One enumerated external event may resume only its affected
  shard once at the same candidate run ID/frozen inputs with a reviewer recovery record; retain both
  attempts. A repeat is BLOCKED. Any deterministic gate failure or product/test/helper correction
  creates a new CodeHead and reruns affected gates plus integrity/inventory. After two contract-gap
  cycles, stop for acceptance-architecture audit.

- [ ] After all shards PASS, reconcile their common run ID and exact inventories:

```powershell
py -3.12 tools/release/verify_0600_release.py candidate-evidence --module STM32TK-0602 --candidate-run-id <candidateRunId> --evidence C:\tmp\stm32tk-0602-candidate-<candidateRunId> --import-shard C:\tmp\stm32tk-0602-candidate-<candidateRunId>\imports\linux.zip --expected-code-head <full-codehead> --catalog tools/release/gates_0600.json --performance tools/release/performance_0600.json --support-profile C:\tmp\stm32tk-0600-support\feasibility\profile.json
```

  Only after reconciliation PASS create a report whose sole change is its return path. Record
  accepted base/product CodeHead, `candidateRunId`, per-gate owner/platform/tool/command/result,
  coverage/performance, recovery attempts if any, and external paths/bytes/SHA-256. Verify
  `git diff --check` and the staged path, then commit locally:

```powershell
git add docs/openclaw/returns/STM32TK-0602-DIAGNOSTIC-LOOP/r001-implementation-report.md
git diff --cached --name-only
git commit -m "docs(STM32TK-0602): record accepted diagnostic CodeHead"
```

Expected: report-only child commit becomes 0603's accepted base. Stop without remote actions.
