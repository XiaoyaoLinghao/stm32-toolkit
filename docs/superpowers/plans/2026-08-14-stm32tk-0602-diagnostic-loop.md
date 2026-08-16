# STM32TK-0602 Diagnostic Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver an append-only evidence-driven diagnostic state machine, bounded Probe v2 controls, action-specific authorization, and deterministic failed-before/fixed-after software verification on Windows, leaving real-board closure to the post-0603 unified activity.

**Architecture:** Diagnostics materialize immutable hash-chained events that reference 0601 evidence IDs. The accepted 0601 Probe v2 public client is the only diagnostic read/control boundary; its Probe Service, backend adapters, protocol, lease, identity, and authorization implementation are frozen inputs rather than 0602 deliverables. Source changes are externally supplied declarations; Toolkit separately authorizes and records build, flash, test, Monitor assertion, and verification steps.

**Tech Stack:** Python 3.10/3.12, dataclasses, JSON Schema, SHA-256 canonical JSON, pyOCD, aiohttp, pytest/pytest-cov, Hypothesis-style property fixtures where already approved, PowerShell release gates.

## Global Constraints

- Begin at the accepted report commit of `STM32TK-0601-TEST-EVIDENCE`; record its full SHA in the
  work order before implementation.
- Codex and Codex-derived agents permanently own implementation, review, and acceptance. Do not
  use OpenClaw branches, attempts, report paths, or handoffs.
- Follow `docs/superpowers/specs/2026-08-14-stm32tk-0602-diagnostic-loop-design.md`.
- Do not change frozen evidence/test schemas, Probe v2, gate schema/families, or 0601 exact entries.
  Fill only reserved 0602 catalog families and freeze their exact commands/nodes before candidate.
- Product code cannot edit source, invoke a model/cloud provider, accept a raw hardware command,
  expose arbitrary memory/register writes, or reuse authorization.
- Prepared CONTROL/MODIFY actions persist a CSPRNG 32-byte nonce encoded as exactly 64 lowercase
  hex characters, exact action digest, and UTC `expiresAt` no later than five minutes. Prepare
  performs exactly one OBSERVE identity/state snapshot and no CONTROL/MODIFY; execute rejects any
  changed identity/state. A live process additionally enforces a monotonic deadline. Success,
  mismatch, failure, refusal, and timeout close the preparation and require a fresh one.
- 0602 runs Windows software, fake-backend, replay, and candidate gates only. It has no Linux
  shard/owner/ZIP/browser handoff and no real-hardware candidate gate.
- Real reset/flash/modify actions are not authorized by this plan. The mandatory real failed-before/
  fixed-after scenario runs only in the unified 0.4+0.6 real-hardware activity after the 0603
  candidate, and final v0.6.0 remains blocked until it passes.
- Every changed product Python file must reach at least 90% branch coverage; correctness runs on
  CPython 3.10 and 3.12; every earlier threshold remains unchanged.
- Preserve external evidence logs and never run release gates in a dirty product worktree.
- No remote operation is authorized; commits in this plan remain local until separate approval.
- 0602 is diagnostic-domain L3 work. It may add diagnostic events, hypotheses, observation plans,
  evidence assessment, action preparation/consumption, source binding, fix verification, bundles,
  and public diagnostic adapters. It must not create or modify a probe backend, Probe Service,
  Probe v2 client/protocol/schema, GDB-server manager, debugger engine, or second authorization
  implementation.

---

## Mandatory pre-implementation gate: layer and component reuse record

Before Task 0, record and independently review this closed mapping:

| 0602 work | Layer | Reused frozen input | New 0602 ownership |
|---|---|---|---|
| Tasks 0--2 | L3/L4 | 0601 Evidence and shared performance controller | diagnostic event model, store, recovery, workloads |
| Tasks 3--4 | L3 | 0601 Evidence APIs and existing build/test/Monitor public APIs | hypotheses, assessment, closed observation plan |
| Tasks 5--6 | L3 | accepted 0601 Probe v2 public client and authorization contract | diagnostic adapters, action/event binding, error mapping |
| Tasks 7--9 | L3 | existing build/flash/test/Monitor and one CLI/MCP framework | source declaration, fix truth, bundle, diagnostic surfaces |
| Tasks 10--12 | L4 | the one 0600 controller/verifier/catalog | calibration, replay, candidate inventory and report |

The record must name every external component reached by the diagnostic loop. For each newly
proposed component it must include exact version and license, retained offline source/digest,
actual Windows argv and exit code, a real version-produced sanitized native-output fixture, closed
parser and error mapping, path/credential/network/concurrency/timeout/partial-output safety,
identity/Evidence/authorization binding, performance/package cost, maintenance benefit, and the
complete 0.2--0.5 regression result. Reuse the accepted 0601 PyOCD/Probe v2 admission evidence
from `tools/stm32-toolkit/tests/fixtures/component-admission/target-transports/
admission-manifest.json` and its digest-bound installed-version/API observation fixtures instead
of rerunning or widening its implementation. These are component-fit inputs, not physical native
transport evidence. This plan admits
no new 0602 execution component; record that closed outcome. Any later proposal requires a plan
amendment and the complete gate above before coding. A component that fails any item is not
admitted, requirements are not reduced, and no silent fallback is allowed. Hand-authored
approximations of pytest, CTest, PyOCD, Monitor, or other native output are forbidden.

---

## Task 0: Freeze measured diagnostic workloads before hot-path implementation

**Files:**

- Create: `tools/stm32-toolkit/tests/test_diagnostic_performance.py`
- Modify: `tools/release/performance_0600.json`

- [ ] Add the exact correctness-first generators and measurements for warm append/reload at 10,000
  events, materialized read at 1,000 events/64 hypotheses, authoritative 10,000-event verification,
  and export/reverify with 10 MiB reachable artifacts. Freeze setup/teardown, warm/cold boundary,
  sample count, three-batch nearest-rank p95/MAD calculation, CPython separation, 15% regression
  limit, and the spec maxima. Keep collection data-only so it succeeds before the product APIs
  exist; execution may fail until those APIs are implemented. Neither workload nor maximum may
  later change to make product code pass.

- [ ] Run the collection/contract test without executing a measured product body:

```powershell
py -3.12 -m pytest tools/stm32-toolkit/tests/test_diagnostic_performance.py --collect-only -q -p no:cacheprovider
```

- [ ] Commit the frozen workload contract before Task 1 changes any measured hot path:

```powershell
git add -- tools/release/performance_0600.json tools/stm32-toolkit/tests/test_diagnostic_performance.py
git commit -m "test(STM32TK-0602): freeze diagnostic workloads"
```

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

- [ ] Write failing tests for exact dataclasses/enums, canonical event digest, creation at
  sequence/revision zero, synchronized later sequence/revision/previous-digest binding, the full
  state table, terminal `RESOLVED`/`ABANDONED`, fresh serialization, UTC/NFC/unknown fields, 1 MiB
  event and collection limits, and root/package schema equality.

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
  typed handlers for existing build/source/evidence/test/Monitor APIs and the accepted 0601 Probe
  v2 public client. Diagnostic handlers may validate and map the public result but cannot call or
  modify a backend/service directly; every attempted step emits a result event even when blocked
  or cancelled.

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

## Task 5: Bind diagnostic observations to the frozen Probe v2 client

**Files:**

- Create: `tools/stm32-toolkit/src/stm32_toolkit/diagnostics/probe_adapter.py`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/diagnostics/observations.py`
- Create: `tools/stm32-toolkit/tests/test_probe_v2_observe.py`
- Create: `tools/stm32-toolkit/tests/test_debug_logs.py`

The OBSERVE rows copied from 0601 are:

| Operation | Exact operation arguments | Exact success result |
|---|---|---|
| `target.state.read` | `{}` | `{state,reason}` |
| `target.registers.read` | `{names}` | `{registers:[{name,value,width_bits}]}` |
| `target.memory.read` | `{address,length}` | `{address,length,data_base64,sha256}` |
| `target.fault.capture` | `{max_stack_bytes}` | `{fault_registers,stack_artifact,stack_bytes,truncated}` |
| `target.logs.capture` | `{channel,max_bytes,duration_ms}` | `{channel,artifact,bytes,duration_ms,truncated}` |

- [ ] Load 0601's frozen root and packaged `stm32-toolkit-probe/2` schemas and assert they are
  byte-identical before writing an adapter. Freeze the exact OBSERVE inventory as
  `target.state.read`, `target.registers.read`, `target.memory.read`, `target.fault.capture`, and
  `target.logs.capture`. Copy the 0601 exact request arguments, success results, stable errors,
  common-envelope fields, unknown-field behavior, and limits into parameterized contract tests;
  0602 must not edit either schema.

- [ ] Assert every Probe failure is exactly `{code,message,details}` with a code from
  `PROBE_PROTOCOL_INVALID`, `PROBE_VERSION_MISMATCH`, `PROBE_OPERATION_UNAVAILABLE`,
  `PROBE_LEASE_INVALID`, `PROBE_AUTHORIZATION_REQUIRED`, `PROBE_AUTHORIZATION_INVALID`,
  `PROBE_IDENTITY_MISMATCH`, `PROBE_LIMIT_EXCEEDED`, `PROBE_TIMEOUT`, `PROBE_BACKPRESSURE`, or
  `PROBE_BACKEND_ERROR`; reject partial success and ad-hoc errors.

- [ ] Write failing behavior tests for `target.state.read` with the exact state/reason enums;
  `target.registers.read` with 1..64 unique profile-allowlisted names and request-order results;
  `target.memory.read` with 1..4096 bytes inside a declared readable RAM/peripheral region and
  destructive peripheral denial; `target.fault.capture` with `max_stack_bytes` 0..4096 and exactly
  `cfsr|hfsr|dfsr|afsr|mmfar|bfar|shcsr|icsr`; and
  `target.logs.capture` with channel exactly `rtt|uart|semihosting|swo|probe`,
  `max_bytes` 1..10485760, and `duration_ms` 1..300000. Cover backpressure, deadline/disconnect
  cleanup, backend exception redaction, and exact version/lease/workspace rejection from 0601.

- [ ] Run RED:

```powershell
py -3.12 -m pytest tools/stm32-toolkit/tests/test_probe_v2_observe.py tools/stm32-toolkit/tests/test_debug_logs.py -q -p no:cacheprovider
```

- [ ] Implement a diagnostic adapter that calls only those five operations through the accepted
  0601 Probe v2 public client. Parse the exact 0601 argument objects before the client call, map the
  exact closed success/error shapes into diagnostic result events, and return bounded Evidence
  references. Assert the accepted 0601 schema and Probe client/service/backend blobs are unchanged
  before and after the task. If implementation needs a backend, service, client, schema, result,
  error, or limit change, stop rather than modifying Probe v2.

- [ ] Run GREEN under dual Python with affected Fault/read/sample/probe regressions and coverage:

```powershell
py -3.10 -m pytest tools/stm32-toolkit/tests/test_probe_v2_observe.py tools/stm32-toolkit/tests/test_debug_logs.py tools/stm32-toolkit/tests/test_fault.py tools/stm32-toolkit/tests/test_debug_read.py -q -p no:cacheprovider
py -3.12 tools/release/run_0600_gates.py dev-coverage --task-id STM32TK-0602-T05 --evidence-root C:\tmp\stm32tk-0602-t05-coverage -- tools/stm32-toolkit/tests/test_probe_v2_observe.py tools/stm32-toolkit/tests/test_debug_logs.py tools/stm32-toolkit/tests/test_fault.py tools/stm32-toolkit/tests/test_debug_read.py --cov=stm32_toolkit.diagnostics.probe_adapter --cov=stm32_toolkit.diagnostics.observations -q -p no:cacheprovider
```

- [ ] Commit:

```powershell
git add -- tools/stm32-toolkit/src/stm32_toolkit/diagnostics/probe_adapter.py tools/stm32-toolkit/src/stm32_toolkit/diagnostics/observations.py tools/stm32-toolkit/tests/test_probe_v2_observe.py tools/stm32-toolkit/tests/test_debug_logs.py
git commit -m "feat(STM32TK-0602): bind bounded diagnostic observations"
```

## Task 6: Bind exact authorized diagnostic controls to frozen Probe v2

**Files:**

- Create: `tools/stm32-toolkit/src/stm32_toolkit/diagnostics/actions.py`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/diagnostics/probe_adapter.py`
- Create: `tools/stm32-toolkit/tests/test_diagnostic_authorization.py`
- Create: `tools/stm32-toolkit/tests/test_probe_v2_control.py`

The CONTROL rows copied from 0601 are:

| Operation | Exact operation arguments | Exact success result |
|---|---|---|
| `target.halt` | `{}` | `{state:"halted",reason}` |
| `target.resume` | `{}` | `{state:"running"}` |
| `target.step` | `{}` | `{state:"halted",reason,pc_before,pc_after}` |
| `target.breakpoint.set` | `{address,kind:"temporary",size}` | `{breakpoint_id,address,kind:"temporary",size}` |
| `target.breakpoint.clear` | `{breakpoint_id}` | `{breakpoint_id,cleared:true}` |

- [ ] Write failing mutation tests proving the diagnostic adapter delegates nonce generation and
  enforcement to the accepted 0601 Probe v2 public authorization client. Its returned persistent
  one-time nonce is exactly 32 CSPRNG bytes encoded as 64 lowercase hex characters; its action
  digest binds issued-at UTC, `expiresAt` no later than five minutes, session/revision/workspace/
  project/target/probe/firmware/state/operation/arguments. Assert the public prepare result records
  exactly one OBSERVE identity/state read with counters `identity_state_read=1`, `control=0`,
  `modify=0`, `reset=0`, `halt=0`, `write=0`, and `flash=0`. The diagnostic layer persists that
  result and its session/revision binding but neither generates a nonce nor repeats the snapshot.
  Execute passes the exact preparation and single authorization to the public client, which
  immediately re-observes identity/state and rejects change without executing. Assert UTC and live
  monotonic deadlines, no restart extension, and closure on success, mismatch, refusal, backend
  failure, or timeout; replay/retry/rebind/later approval requires a fresh public prepare.

- [ ] Load the same byte-identical 0601 schemas and freeze the exact CONTROL inventory as
  `target.halt`, `target.resume`, `target.step`, `target.breakpoint.set`, and
  `target.breakpoint.clear`. Copy their exact 0601 request arguments, success results, stable
  errors, common-envelope checks, and limits into parameterized tests; 0602 cannot edit the schema.

- [ ] Write failing tests proving `target.halt` and `target.resume` use `{}` arguments and one legal
  transition; `target.step` uses `{}` arguments, performs exactly one instruction step, and has a
  five-second maximum; `target.breakpoint.set` creates only a temporary executable breakpoint with
  size 1, 2, or 4 and at most eight owned breakpoints per session; and
  `target.breakpoint.clear` clears the exact owned ID. Cover cleanup on every exit, disconnect
  recovery, reversible restoration, cleanup-required
  lockout, exact 0601 results/errors, and rejection of writes, raw commands, renamed operations,
  extra arguments, multi-step counts, and widened limits.

- [ ] Run RED:

```powershell
py -3.12 -m pytest tools/stm32-toolkit/tests/test_diagnostic_authorization.py tools/stm32-toolkit/tests/test_probe_v2_control.py -q -p no:cacheprovider
```

- [ ] Implement diagnostic `prepare_action()` as validation plus one call to the accepted 0601
  Probe v2 public authorization prepare method; persist its nonce/digest/UTC-expiry/snapshot result
  with the diagnostic session/revision and emit the diagnostic preparation event. Implement
  diagnostic `execute_action()` as validation plus one call to the public authorization execute
  method with the exact preparation and user authorization; map its closed outcome to action and
  cleanup Evidence events. Do not generate a nonce, observe target state independently, keep a
  second deadline, consume authorization locally, or call a backend/service. Invoke only the five
  canonical `target.*` CONTROL operations with exact 0601 arguments/results/errors/limits. Probe
  Service retains identity recheck, single-use enforcement, backend cleanup, deadline, and atomic
  closure. Assert all accepted 0601 Probe schema/client/service/backend blobs remain unchanged.
  Stop rather than modifying Probe v2 or adding a debugger engine.

- [ ] Run GREEN on both Pythons with branch coverage and existing probe lease/process tests:

```powershell
py -3.10 -m pytest tools/stm32-toolkit/tests/test_diagnostic_authorization.py tools/stm32-toolkit/tests/test_probe_v2_control.py tools/stm32-toolkit/tests/test_probe_lease.py tools/stm32-toolkit/tests/test_process.py -q -p no:cacheprovider
py -3.12 tools/release/run_0600_gates.py dev-coverage --task-id STM32TK-0602-T06 --evidence-root C:\tmp\stm32tk-0602-t06-coverage -- tools/stm32-toolkit/tests/test_diagnostic_authorization.py tools/stm32-toolkit/tests/test_probe_v2_control.py tools/stm32-toolkit/tests/test_probe_lease.py tools/stm32-toolkit/tests/test_process.py --cov=stm32_toolkit.diagnostics.actions --cov=stm32_toolkit.diagnostics.probe_adapter -q -p no:cacheprovider
```

- [ ] Commit:

```powershell
git add -- tools/stm32-toolkit/src/stm32_toolkit/diagnostics/actions.py tools/stm32-toolkit/src/stm32_toolkit/diagnostics/probe_adapter.py tools/stm32-toolkit/tests/test_diagnostic_authorization.py tools/stm32-toolkit/tests/test_probe_v2_control.py
git commit -m "feat(STM32TK-0602): bind authorized diagnostic controls"
```

## Task 7: Bind external source changes and deterministic verification

**Files:**

- Create: `tools/stm32-toolkit/src/stm32_toolkit/diagnostics/verification.py`
- Create: `tools/stm32-toolkit/tests/test_source_change_declaration.py`
- Create: `tools/stm32-toolkit/tests/test_fix_verification.py`

- [ ] Write failing declaration tests for canonical tracked paths, exact diff artifact, complete
  before/after build-input snapshots, changed-path equality, expected revision, unrelated inputs,
  missing/corrupt artifacts, and proof Toolkit neither writes nor applies a source file. The test
  harness may create a temporary fixture and apply a fixed in-test patch there; assert the source
  inputs and product worktree remain byte-identical.

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

## Task 8: Export, verify, and atomically import portable diagnostic bundles

**Files:**

- Create: `tools/stm32-toolkit/src/stm32_toolkit/diagnostics/bundle.py`
- Create: `tools/stm32-toolkit/tests/test_diagnostic_bundle.py`

- [ ] Write failing tests for deterministic repeated ZIP bytes, ascending UTF-8 member ordering,
  DOS epoch timestamps, `0644` modes, DEFLATE level 9, no platform extras, complete reachability/
  inventory/member hashes, at most 65,536 entries and 1 GiB uncompressed content, corrupt/missing
  objects, secret/absolute-path/environment redaction, zip-slip, Unicode-normalization, drive/ADS/
  casefold/duplicate names, links/special files, compression bombs, and no partial publish.

- [ ] Write the two-phase import truth table. `verify_import_bundle(path)` performs no publish and
  returns the expected whole-bundle digest plus bounded summary. `import_verified_bundle(path,
  expected_digest, authorization)` re-verifies, requires a fresh destination-bound MODIFY nonce/
  digest, publishes atomically through public evidence/session APIs, treats the same bundle digest
  as idempotent, rejects logical-ID/content conflicts, and never edits source, touches hardware,
  or creates/changes Monitor groups or annotations.

- [ ] Run RED:

```powershell
py -3.12 -m pytest tools/stm32-toolkit/tests/test_diagnostic_bundle.py -q -p no:cacheprovider
```

- [ ] Implement `export_bundle(session_id, selection, output)`, `verify_import_bundle(path)`, and
  `import_verified_bundle(path, expected_digest, authorization)` with the exact deterministic
  encoding, limits, two-phase authorization, conflict, idempotency, and atomicity contracts above.

- [ ] Run GREEN dual Python with coverage:

```powershell
py -3.10 -m pytest tools/stm32-toolkit/tests/test_diagnostic_bundle.py -q -p no:cacheprovider
py -3.12 tools/release/run_0600_gates.py dev-coverage --task-id STM32TK-0602-T08 --evidence-root C:\tmp\stm32tk-0602-t08-coverage -- tools/stm32-toolkit/tests/test_diagnostic_bundle.py --cov=stm32_toolkit.diagnostics.bundle -q -p no:cacheprovider
```

- [ ] Commit:

```powershell
git add tools/stm32-toolkit/src/stm32_toolkit/diagnostics/bundle.py tools/stm32-toolkit/tests/test_diagnostic_bundle.py
git commit -m "feat(STM32TK-0602): verify and import diagnostic bundles"
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
  session/evidence isolation, response mutation safety, and redaction. Include CLI and MCP bundle
  verify/import: verify is read-only; import requires its exact expected bundle digest and a fresh
  destination-bound MODIFY authorization, re-verifies, and returns idempotent/conflict outcomes.

- [ ] Write Skill contract tests requiring reproduce→hypotheses→discriminating observations→
  authorization→declared change→frozen verification and prohibiting “fixed” without deterministic
  PASS, implicit edits/flash, raw commands, model/cloud code, or storing/reusing the user's
  approval flag. Persisting the prepared nonce/digest/UTC expiry is required and is not approval.

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

- Modify: `tools/release/performance_0600.json`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/diagnostics/events.py`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/diagnostics/store.py`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/diagnostics/session.py`
- Modify: `tools/stm32-toolkit/src/stm32_toolkit/diagnostics/bundle.py`
- Modify: `tools/stm32-toolkit/tests/test_diagnostic_events.py`
- Modify: `tools/stm32-toolkit/tests/test_diagnostic_store.py`
- Modify: `tools/stm32-toolkit/tests/test_diagnostic_bundle.py`

- [ ] Verify the Task 0 committed workload contract is byte-identical, then run the exact
  correctness-first append/reload, materialized-read, authoritative-verification, and export/
  reverify workloads. Do not alter a workload or design maximum during characterization.

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

- [ ] Commit only the accepted baseline/threshold entries before any optional post-baseline
  optimization; the workload test was already committed in Task 0:

```powershell
git add -- tools/release/performance_0600.json
git commit -m "test(STM32TK-0602): calibrate diagnostic performance"
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

## Task 11: Close the Windows fake/replay loop and stage deferred hardware inputs

**Files:**

- Create: `tools/stm32-toolkit/tests/test_diagnostic_loop_replay.py`
- Create: `tools/stm32-toolkit/tests/fixtures/diagnostic-loop/.stm32-project.json`
- Create: `tools/stm32-toolkit/tests/fixtures/diagnostic-loop/Src/main.c`
- Create: `tools/stm32-toolkit/tests/fixtures/diagnostic-loop/Tests/test_fault.c`
- Create: `tools/stm32-toolkit/tests/fixtures/diagnostic-loop/expected-fix.patch`
- Create: `tools/stm32-toolkit/tests/fixtures/diagnostic-loop/README.md`
- Modify: `README.md`
- Modify: `tools/stm32-toolkit/README.md`

- [ ] Add a deterministic faulty fixture and Windows fake/replay test for the nine-step causal
  chain: failed Target/Monitor evidence, two hypotheses, register/Fault/log observations, prepared
  halt/breakpoint/step/resume/cleanup controls, external change declaration, separately prepared
  build/flash/test evidence, new identity, passing exact test/assertion, resolved session, and
  verified bundle. No test in this task opens a real probe, resets, flashes, or modifies hardware.

- [ ] In a fresh temporary copy of the fixture, have the test harness—not Toolkit—apply
  `expected-fix.patch`; register the resulting snapshots/diff declaration and prove the repository
  fixture and product worktree remain byte-identical. Preserve deterministic failed-before and
  fixed-after evidence so the later unified real-hardware activity can reuse the same contract.

- [ ] Run the Windows fake/replay scenario under both Pythons:

```powershell
py -3.10 -m pytest tools/stm32-toolkit/tests/test_diagnostic_loop_replay.py -q -p no:cacheprovider
py -3.12 -m pytest tools/stm32-toolkit/tests/test_diagnostic_loop_replay.py -q -p no:cacheprovider
```

- [ ] Update documentation after fake/replay evidence exists. Document the diagnostic state
  machine, persistent one-time authorization, source-edit boundary, verification truth, two-phase
  bundle import, prohibited operations, and the exact `SOFTWARE_COMPLETE_HARDWARE_PENDING` status.
  State that the unified 0.4+0.6 activity after the 0603 candidate owns the real board run and that
  final v0.6.0 cannot pass without it.

- [ ] Commit:

```powershell
git add -- tools/stm32-toolkit/tests/test_diagnostic_loop_replay.py tools/stm32-toolkit/tests/fixtures/diagnostic-loop/.stm32-project.json tools/stm32-toolkit/tests/fixtures/diagnostic-loop/Src/main.c tools/stm32-toolkit/tests/fixtures/diagnostic-loop/Tests/test_fault.c tools/stm32-toolkit/tests/fixtures/diagnostic-loop/expected-fix.patch tools/stm32-toolkit/tests/fixtures/diagnostic-loop/README.md README.md tools/stm32-toolkit/README.md
git commit -m "test(STM32TK-0602): close Windows diagnostic replay"
```

## Task 12: Freeze the Windows software CodeHead

**Files:**

- Modify: `tools/release/gates_0600.json`
- Modify: `tools/stm32-toolkit/tests/release/test_gate_catalog_0600.py`
- Modify: `tools/stm32-toolkit/tests/release/test_gate_controller_0600.py`
- Modify: `tools/stm32-toolkit/tests/release/test_release_verifier_0600.py`
- Create after PASS only: `docs/codex/returns/STM32TK-0602-DIAGNOSTIC-LOOP/implementation-report.md`

- [ ] Audit the full 0601 accepted-report-to-current diff and all tracked/untracked, committed/
  uncommitted, and pushed/unpushed state. Verify frozen 0601 schemas/catalog semantics byte-for-
  byte and confirm no arbitrary write/raw command/model/cloud surface exists.

- [ ] Collect every exact 0602 node after Task 11, replace only reserved 0602 slots with closed
  argv/owners/platforms/timeouts/evidence/coverage/prerequisites/impact edges, and add mutation tests
  proving all 0601 entries remain byte-identical and missing/extra/duplicate/renamed/deselected/
  skip/xfail 0602 nodes fail. Commit the final 0602 test contract before candidate:

```powershell
py -3.12 -m pytest tools/stm32-toolkit/tests/release/test_gate_catalog_0600.py tools/stm32-toolkit/tests/release/test_gate_controller_0600.py tools/stm32-toolkit/tests/release/test_release_verifier_0600.py -q -p no:cacheprovider
git add -- tools/release/gates_0600.json tools/stm32-toolkit/tests/release/test_gate_catalog_0600.py tools/stm32-toolkit/tests/release/test_gate_controller_0600.py tools/stm32-toolkit/tests/release/test_release_verifier_0600.py
git commit -m "test(STM32TK-0602): freeze exact candidate inventory"
```

  The controller test must invoke Windows PowerShell 5.1 and reuse 0601's one frozen
  `tools/release/path_contract_0600.ps1` implementation of `ConvertTo-CanonicalAbsolutePath`
  without any newer-runtime-only path API. It accepts only an already-canonical rooted path whose
  `Path.GetFullPath()` result is ordinal-identical to the input. It rejects null/empty/whitespace,
  drive-relative and root-relative paths, device/extended/NT aliases, mixed separators, trailing
  separators, dot segments, and every other normalization mismatch. Mutation tests must also prove
  recovery and reconciliation never execute a controller/verifier path supplied by the external
  context or ledger, reject dirty/untracked or wrong-HEAD/wrong-origin worktrees, and reject an
  actual verifier digest different from the frozen invocation-context digest.

- [ ] Resolve every controller input from the frozen worktree, validate the lowercase 40-hex Git
  CodeHead, generate one canonical lowercase hyphenated UUID run ID, and create only the external input context
  named exactly `candidate-invocation-context.json`. The context is outside the new candidate root;
  caller code must not create or write `candidate-ledger.json`. All controller/script paths are
  absolute paths resolved beneath the frozen worktree:

```powershell
$module = 'STM32TK-0602'
$shard = 'windows'
$repoRoot = (Resolve-Path -LiteralPath '.').Path
$pathContract = Join-Path $repoRoot 'tools\release\path_contract_0600.ps1'
. $pathContract
$repoRoot = ConvertTo-CanonicalAbsolutePath -Path $repoRoot -Name 'repository root'
$codeHead = (git -C $repoRoot rev-parse --verify 'HEAD^{commit}').Trim().ToLowerInvariant()
if ($LASTEXITCODE -ne 0 -or $codeHead -cnotmatch '^[0-9a-f]{40}$') {
  throw 'Git HEAD is not one lowercase 40-hex commit'
}
$candidateRunId = [Guid]::NewGuid().ToString('D')
if ($candidateRunId -cnotmatch '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$') { throw 'candidate run ID is not a canonical lowercase UUID' }
$shortCodeHead = $codeHead.Substring(0, 12)
$candidateRoot = ConvertTo-CanonicalAbsolutePath -Path (Join-Path 'C:\tmp' "stm32tk-0602-candidate-$candidateRunId-$shortCodeHead") -Name 'candidate root'
$windowsEvidence = ConvertTo-CanonicalAbsolutePath -Path (Join-Path $candidateRoot 'windows') -Name 'evidence root'
$candidateLedgerPath = ConvertTo-CanonicalAbsolutePath -Path (Join-Path $candidateRoot 'candidate-ledger.json') -Name 'candidate ledger'
$inputRoot = ConvertTo-CanonicalAbsolutePath -Path (Join-Path 'C:\tmp' "stm32tk-0602-candidate-input-$candidateRunId-$shortCodeHead") -Name 'candidate input root'
if (Test-Path -LiteralPath $inputRoot) { throw 'candidate input root already exists' }
[IO.Directory]::CreateDirectory($inputRoot) | Out-Null
$invocationContextPath = ConvertTo-CanonicalAbsolutePath -Path (Join-Path $inputRoot 'candidate-invocation-context.json') -Name 'invocation context'
$recoveryRecordPath = ConvertTo-CanonicalAbsolutePath -Path (Join-Path $inputRoot 'recovery-record.json') -Name 'recovery record'
$catalog = ConvertTo-CanonicalAbsolutePath -Path (Join-Path $repoRoot 'tools\release\gates_0600.json') -Name 'catalog'
$performance = ConvertTo-CanonicalAbsolutePath -Path (Join-Path $repoRoot 'tools\release\performance_0600.json') -Name 'performance contract'
$supportProfile = ConvertTo-CanonicalAbsolutePath -Path 'C:\tmp\stm32tk-0600-support\feasibility\profile.json' -Name 'support profile'
$runner = ConvertTo-CanonicalAbsolutePath -Path (Join-Path $repoRoot 'tools\release\run_0600_candidate.ps1') -Name 'candidate controller'
$verifier = ConvertTo-CanonicalAbsolutePath -Path (Join-Path $repoRoot 'tools\release\verify_0600_release.py') -Name 'release verifier'
foreach ($frozenPath in @($catalog,$performance,$supportProfile,$runner,$verifier)) {
  if (-not (Test-Path -LiteralPath $frozenPath -PathType Leaf)) { throw "missing frozen input: $frozenPath" }
}
foreach ($repoFile in @($catalog,$performance,$runner,$verifier)) {
  if (-not $repoFile.StartsWith($repoRoot + [IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) {
    throw "controller input is outside frozen worktree: $repoFile"
  }
}
$invocationContext = [ordered]@{
  module = $module
  shard = $shard
  phase = 'candidate'
  candidate_run_id = $candidateRunId
  expected_code_head = $codeHead
  repo_root = $repoRoot
  candidate_root = $candidateRoot
  evidence_root = $windowsEvidence
  candidate_ledger = $candidateLedgerPath
  recovery_record = $recoveryRecordPath
  catalog = $catalog
  catalog_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $catalog).Hash.ToLowerInvariant()
  performance = $performance
  performance_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $performance).Hash.ToLowerInvariant()
  support_profile = $supportProfile
  support_profile_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $supportProfile).Hash.ToLowerInvariant()
  runner = $runner
  runner_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $runner).Hash.ToLowerInvariant()
  verifier = $verifier
  verifier_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $verifier).Hash.ToLowerInvariant()
}
[IO.File]::WriteAllText(
  $invocationContextPath,
  (($invocationContext | ConvertTo-Json -Depth 4 -Compress) + [Environment]::NewLine),
  [Text.UTF8Encoding]::new($false)
)
$invocationContextDigest = (Get-FileHash -Algorithm SHA256 -LiteralPath $invocationContextPath).Hash.ToLowerInvariant()
if (Test-Path -LiteralPath $candidateRoot) { throw 'candidate root must not exist before wrapper invocation' }
```

- [ ] Run the Windows-only collect-all candidate with the frozen base variables. The external
  invocation context is non-authoritative and is not passed as a ledger or controller input. The
  wrapper alone creates `<candidateRoot>/candidate-ledger.json` with exactly
  `schema:"stm32-candidate-ledger/1"`, `module:"STM32TK-0602"`,
  `candidate_run_id`, `expected_code_head`, `controller_path`, `candidate_root`, `evidence_root`,
  `catalog_sha256`, `performance_sha256`, `support_profile_sha256`, `checkpoint`, `state`,
  `created_at_utc`, and `updated_at_utc`. The
  wrapper first runs the non-executing CodeHead/catalog/node/performance/support/tool/owner/
  evidence-root precheck and refuses to start a product body if it fails. The catalog and precheck
  must reject any Linux, browser-handoff, ZIP-transfer, or real-hardware node for module 0602:

```powershell
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $runner -Module $module -Shard $shard -CandidateRunId $candidateRunId -EvidenceRoot $windowsEvidence -ExpectedCodeHead $codeHead -Catalog $catalog -Performance $performance -SupportProfile $supportProfile
$candidateExit = $LASTEXITCODE
if (-not (Test-Path -LiteralPath $candidateLedgerPath -PathType Leaf)) { throw 'wrapper did not create candidate-ledger.json' }
if ($candidateExit -ne 0) { throw '0602 Windows candidate stopped; classify before any resume' }
$terminalLedgerDigest = (Get-FileHash -Algorithm SHA256 -LiteralPath $candidateLedgerPath).Hash.ToLowerInvariant()
```

- [ ] On failure, do not write a report. Only `RECOVERABLE_INFRA_ERROR` may resume once. The
  reviewer-authored canonical recovery record contains exactly `classification`, `event`,
  `reviewer`, `recorded_at_utc`, `run_kind`, `run_id`, `code_head`, `checkpoint`, and
  `interrupted_attempt_digest`; `event` is exactly one of `HOST_POWER_OR_REBOOT`,
  `RUNNER_LOSS_BEFORE_CHILD_RESULT`, `PHYSICAL_USB_OR_PROBE_REMOVAL`, or `TARGET_POWER_LOSS`.
  `run_kind` is exactly `candidate-0602`. Resume uses only the complete closed interface
  `-ResumeCandidateRun -CandidateLedger <absolute JSON> -RecoveryRecord <absolute JSON>`; the
  wrapper reconstructs the original base inputs from its ledger and rejects any changed input,
  completed child result, legacy resume form, orchestration-context-as-ledger form, or second resume:

```powershell
$candidateLedgerPath = ConvertTo-CanonicalAbsolutePath -Path $candidateLedgerPath -Name 'candidate ledger'
$recoveryRecordPath = ConvertTo-CanonicalAbsolutePath -Path $recoveryRecordPath -Name 'recovery record'
$candidateLedger = Get-Content -Raw -LiteralPath $candidateLedgerPath | ConvertFrom-Json
$recoveryRecord = Get-Content -Raw -LiteralPath $recoveryRecordPath | ConvertFrom-Json
$requiredRecoveryFields = @('classification','event','reviewer','recorded_at_utc','run_kind','run_id','code_head','checkpoint','interrupted_attempt_digest')
$actualRecoveryFields = @($recoveryRecord.PSObject.Properties.Name | Sort-Object)
if ([string]::Join("`n",$actualRecoveryFields) -cne [string]::Join("`n",($requiredRecoveryFields | Sort-Object))) {
  throw 'recovery record does not contain exactly the canonical fields'
}
$recoverableEvents = @('HOST_POWER_OR_REBOOT','RUNNER_LOSS_BEFORE_CHILD_RESULT','PHYSICAL_USB_OR_PROBE_REMOVAL','TARGET_POWER_LOSS')
$ledgerControllerBootstrap = [string]$candidateLedger.controller_path
if ([string]::IsNullOrWhiteSpace($ledgerControllerBootstrap) -or
    $ledgerControllerBootstrap -match '^[A-Za-z]:[^\\/]' -or
    $ledgerControllerBootstrap -match '^[\\/](?![\\/])' -or
    $ledgerControllerBootstrap.StartsWith('\\?\') -or
    $ledgerControllerBootstrap.StartsWith('\\.\') -or
    $ledgerControllerBootstrap.StartsWith('\??\') -or
    -not [System.IO.Path]::IsPathRooted($ledgerControllerBootstrap) -or
    [System.IO.Path]::GetFullPath($ledgerControllerBootstrap) -cne $ledgerControllerBootstrap) {
  throw 'invalid bootstrap controller path'
}
$bootstrapWorktree = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $ledgerControllerBootstrap))
$resumeHead = (git -C $bootstrapWorktree rev-parse --verify 'HEAD^{commit}').Trim().ToLowerInvariant()
if ($LASTEXITCODE -ne 0 -or $resumeHead -cnotmatch '^[0-9a-f]{40}$' -or $resumeHead -cne $codeHead) { throw 'resume worktree HEAD changed' }
$resumeOrigin = ((git -C $bootstrapWorktree config --get remote.origin.url) | Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or $resumeOrigin -cne 'https://github.com/XiaoyaoLinghao/stm32-toolkit.git') { throw 'resume worktree origin changed' }
$resumeStatus = @(git -C $bootstrapWorktree status --porcelain=v1 --untracked-files=all)
if ($LASTEXITCODE -ne 0 -or $resumeStatus.Count -ne 0) { throw 'resume worktree is not clean' }
$pathContract = Join-Path $bootstrapWorktree 'tools\release\path_contract_0600.ps1'
if (-not (Test-Path -LiteralPath $pathContract -PathType Leaf)) { throw 'missing path contract' }
$pathContractBlob = (git -C $bootstrapWorktree rev-parse "$codeHead`:tools/release/path_contract_0600.ps1").Trim()
$workingPathContractBlob = (git -C $bootstrapWorktree hash-object -- $pathContract).Trim()
if ($pathContractBlob -cnotmatch '^[0-9a-f]{40}$' -or $workingPathContractBlob -cne $pathContractBlob) { throw 'path contract is not committed at CodeHead' }
. $pathContract
$frozenWorktree = ConvertTo-CanonicalAbsolutePath -Path $bootstrapWorktree -Name 'frozen worktree'
$checkpointPath = ConvertTo-CanonicalAbsolutePath -Path ([string]$candidateLedger.checkpoint) -Name 'checkpoint'
$checkpointState = Get-Content -Raw -LiteralPath $checkpointPath | ConvertFrom-Json
if ($recoveryRecord.classification -cne 'RECOVERABLE_INFRA_ERROR' -or
    $recoveryRecord.event -cnotin $recoverableEvents -or
    $recoveryRecord.run_kind -cne 'candidate-0602' -or
    $recoveryRecord.run_id -cne $candidateRunId -or
    $recoveryRecord.code_head -cnotmatch '^[0-9a-f]{40}$' -or
    $recoveryRecord.code_head -cne $codeHead -or
    $recoveryRecord.interrupted_attempt_digest -cnotmatch '^[0-9a-f]{64}$' -or
    $recoveryRecord.checkpoint -cne $candidateLedger.checkpoint -or
    $recoveryRecord.checkpoint -cne $checkpointPath -or
    $recoveryRecord.interrupted_attempt_digest -cne $checkpointState.interrupted_attempt_digest) {
  throw 'recovery record does not bind the interrupted candidate attempt'
}
$ledgerControllerEvidence = ConvertTo-CanonicalAbsolutePath -Path ([string]$candidateLedger.controller_path) -Name 'ledger controller evidence'
$derivedResumeController = ConvertTo-CanonicalAbsolutePath -Path (Join-Path $frozenWorktree 'tools\release\run_0600_candidate.ps1') -Name 're-derived resume controller'
$committedResumeControllerBlob = (git -C $frozenWorktree rev-parse "$codeHead`:tools/release/run_0600_candidate.ps1").Trim()
$workingResumeControllerBlob = (git -C $frozenWorktree hash-object -- $derivedResumeController).Trim()
if ($committedResumeControllerBlob -cnotmatch '^[0-9a-f]{40}$' -or $workingResumeControllerBlob -cne $committedResumeControllerBlob) { throw 'resume controller bytes differ from CodeHead' }
$contextAtResume = Get-Content -Raw -LiteralPath $invocationContextPath | ConvertFrom-Json
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $invocationContextPath).Hash.ToLowerInvariant() -cne $invocationContextDigest -or
    $ledgerControllerEvidence -cne $derivedResumeController -or
    [string]$contextAtResume.runner -cne $derivedResumeController -or
    (Get-FileHash -Algorithm SHA256 -LiteralPath $derivedResumeController).Hash.ToLowerInvariant() -cne [string]$contextAtResume.runner_sha256) {
  throw 're-derived resume controller does not match frozen inputs'
}
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $derivedResumeController -ResumeCandidateRun -CandidateLedger $candidateLedgerPath -RecoveryRecord $recoveryRecordPath
if ($LASTEXITCODE -ne 0) { throw '0602 Windows candidate resume failed' }
$terminalLedgerDigest = (Get-FileHash -Algorithm SHA256 -LiteralPath $candidateLedgerPath).Hash.ToLowerInvariant()
```

  A repeat infrastructure interruption is BLOCKED. Any deterministic gate failure or product/test/
  helper correction creates a new CodeHead and run ID and reruns affected gates plus integrity/
  inventory. After two contract-gap cycles, stop for acceptance-architecture audit.

  Setup, candidate, optional recovery, and reconciliation run in one Windows PowerShell 5.1
  process; if an infrastructure restart requires a fresh process, the operator first reloads the
  verified, CodeHead-bound `path_contract_0600.ps1` before reading any recovery path.

- [ ] After the Windows shard passes, reconcile its exact inventory and require the explicit module
  outcome `SOFTWARE_COMPLETE_HARDWARE_PENDING`:

```powershell
$invocationContextPath = ConvertTo-CanonicalAbsolutePath -Path $invocationContextPath -Name 'invocation context'
$candidateLedgerPath = ConvertTo-CanonicalAbsolutePath -Path $candidateLedgerPath -Name 'candidate ledger'
$contextAtReconcile = Get-Content -Raw -LiteralPath $invocationContextPath | ConvertFrom-Json
$ledgerAtReconcile = Get-Content -Raw -LiteralPath $candidateLedgerPath | ConvertFrom-Json
$currentLedgerDigest = (Get-FileHash -Algorithm SHA256 -LiteralPath $candidateLedgerPath).Hash.ToLowerInvariant()
$requiredLedgerFields = @('schema','module','candidate_run_id','expected_code_head','controller_path','candidate_root','evidence_root','catalog_sha256','performance_sha256','support_profile_sha256','checkpoint','state','created_at_utc','updated_at_utc')
$actualLedgerFields = @($ledgerAtReconcile.PSObject.Properties.Name | Sort-Object)
if ([string]::Join("`n",$actualLedgerFields) -cne [string]::Join("`n",($requiredLedgerFields | Sort-Object))) {
  throw 'wrapper ledger does not contain exactly the canonical fields'
}
if ($currentLedgerDigest -cne $terminalLedgerDigest) { throw 'candidate ledger changed after terminal wrapper result' }
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $invocationContextPath).Hash.ToLowerInvariant() -cne $invocationContextDigest) {
  throw 'candidate invocation context changed'
}
$ledgerControllerBootstrap = [string]$ledgerAtReconcile.controller_path
if ([string]::IsNullOrWhiteSpace($ledgerControllerBootstrap) -or
    $ledgerControllerBootstrap -match '^[A-Za-z]:[^\\/]' -or
    $ledgerControllerBootstrap -match '^[\\/](?![\\/])' -or
    $ledgerControllerBootstrap.StartsWith('\\?\') -or
    $ledgerControllerBootstrap.StartsWith('\\.\') -or
    $ledgerControllerBootstrap.StartsWith('\??\') -or
    -not [System.IO.Path]::IsPathRooted($ledgerControllerBootstrap) -or
    [System.IO.Path]::GetFullPath($ledgerControllerBootstrap) -cne $ledgerControllerBootstrap) {
  throw 'invalid bootstrap controller path'
}
$bootstrapWorktree = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $ledgerControllerBootstrap))
$currentHead = (git -C $bootstrapWorktree rev-parse --verify 'HEAD^{commit}').Trim().ToLowerInvariant()
$expectedBootstrapHead = [string]$ledgerAtReconcile.expected_code_head
if ($LASTEXITCODE -ne 0 -or $currentHead -cnotmatch '^[0-9a-f]{40}$' -or
    $expectedBootstrapHead -cnotmatch '^[0-9a-f]{40}$' -or
    $currentHead -cne $expectedBootstrapHead -or
    $currentHead -cne [string]$contextAtReconcile.expected_code_head) {
  throw 'frozen worktree is not at the exact candidate HEAD'
}
$currentOrigin = ((git -C $bootstrapWorktree config --get remote.origin.url) | Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or $currentOrigin -cne 'https://github.com/XiaoyaoLinghao/stm32-toolkit.git') {
  throw 'frozen worktree origin is not the canonical repository URL'
}
$currentStatus = @(git -C $bootstrapWorktree status --porcelain=v1 --untracked-files=all)
if ($LASTEXITCODE -ne 0 -or $currentStatus.Count -ne 0) { throw 'frozen worktree is not clean' }
$pathContract = Join-Path $bootstrapWorktree 'tools\release\path_contract_0600.ps1'
if (-not (Test-Path -LiteralPath $pathContract -PathType Leaf)) { throw 'missing path contract' }
$pathContractBlob = (git -C $bootstrapWorktree rev-parse "$currentHead`:tools/release/path_contract_0600.ps1").Trim()
$workingPathContractBlob = (git -C $bootstrapWorktree hash-object -- $pathContract).Trim()
if ($pathContractBlob -cnotmatch '^[0-9a-f]{40}$' -or $workingPathContractBlob -cne $pathContractBlob) { throw 'path contract is not committed at CodeHead' }
. $pathContract
$frozenWorktree = ConvertTo-CanonicalAbsolutePath -Path $bootstrapWorktree -Name 'frozen worktree'
$fixedPaths = [ordered]@{
  controller = 'tools/release/run_0600_candidate.ps1'
  verifier = 'tools/release/verify_0600_release.py'
  catalog = 'tools/release/gates_0600.json'
  performance = 'tools/release/performance_0600.json'
}
$resolved = @{}
foreach ($name in $fixedPaths.Keys) {
  $relative = $fixedPaths[$name]
  $absolute = ConvertTo-CanonicalAbsolutePath -Path (Join-Path $frozenWorktree ($relative -replace '/', '\')) -Name "re-derived $name"
  if (-not (Test-Path -LiteralPath $absolute -PathType Leaf)) { throw "missing re-derived $name" }
  $committedBlob = (git -C $frozenWorktree rev-parse "$currentHead`:$relative").Trim()
  $workingBlob = (git -C $frozenWorktree hash-object -- $absolute).Trim()
  if ($committedBlob -cnotmatch '^[0-9a-f]{40}$' -or $workingBlob -cne $committedBlob) { throw "$name bytes differ from CodeHead" }
  $resolved[$name] = $absolute
}
$derivedController = $resolved.controller
$derivedVerifier = $resolved.verifier
$derivedCatalog = $resolved.catalog
$derivedPerformance = $resolved.performance
$ledgerControllerEvidence = ConvertTo-CanonicalAbsolutePath -Path ([string]$ledgerAtReconcile.controller_path) -Name 'ledger controller evidence'
$candidateRoot = ConvertTo-CanonicalAbsolutePath -Path ([string]$contextAtReconcile.candidate_root) -Name 'candidate root'
$supportProfile = ConvertTo-CanonicalAbsolutePath -Path ([string]$contextAtReconcile.support_profile) -Name 'support profile'
$actualControllerDigest = (Get-FileHash -Algorithm SHA256 -LiteralPath $derivedController).Hash.ToLowerInvariant()
$actualVerifierDigest = (Get-FileHash -Algorithm SHA256 -LiteralPath $derivedVerifier).Hash.ToLowerInvariant()
$actualCatalogDigest = (Get-FileHash -Algorithm SHA256 -LiteralPath $derivedCatalog).Hash.ToLowerInvariant()
$actualPerformanceDigest = (Get-FileHash -Algorithm SHA256 -LiteralPath $derivedPerformance).Hash.ToLowerInvariant()
$actualSupportDigest = (Get-FileHash -Algorithm SHA256 -LiteralPath $supportProfile).Hash.ToLowerInvariant()
if ($ledgerAtReconcile.candidate_run_id -cne $contextAtReconcile.candidate_run_id -or
    $ledgerAtReconcile.schema -cne 'stm32-candidate-ledger/1' -or
    $ledgerAtReconcile.module -cne 'STM32TK-0602' -or
    $ledgerAtReconcile.expected_code_head -cne $contextAtReconcile.expected_code_head -or
    $currentHead -cne $contextAtReconcile.expected_code_head -or
    [string]$contextAtReconcile.repo_root -cne $frozenWorktree -or
    $ledgerControllerEvidence -cne $derivedController -or
    [string]$contextAtReconcile.runner -cne $derivedController -or
    [string]$contextAtReconcile.verifier -cne $derivedVerifier -or
    [string]$contextAtReconcile.catalog -cne $derivedCatalog -or
    [string]$contextAtReconcile.performance -cne $derivedPerformance -or
    $ledgerAtReconcile.candidate_root -cne $contextAtReconcile.candidate_root -or
    $ledgerAtReconcile.evidence_root -cne $contextAtReconcile.evidence_root -or
    $actualControllerDigest -cne [string]$contextAtReconcile.runner_sha256 -or
    $actualVerifierDigest -cne [string]$contextAtReconcile.verifier_sha256 -or
    $actualCatalogDigest -cne [string]$contextAtReconcile.catalog_sha256 -or
    $actualCatalogDigest -cne [string]$ledgerAtReconcile.catalog_sha256 -or
    $actualPerformanceDigest -cne [string]$contextAtReconcile.performance_sha256 -or
    $actualPerformanceDigest -cne [string]$ledgerAtReconcile.performance_sha256 -or
    $actualSupportDigest -cne [string]$contextAtReconcile.support_profile_sha256 -or
    $actualSupportDigest -cne [string]$ledgerAtReconcile.support_profile_sha256 -or
    $ledgerAtReconcile.state -cne 'passed') {
  throw 'wrapper ledger differs from original candidate inputs'
}
# The exact ledger has no verifier_sha256 field: verifier binds to the immutable context digest;
# catalog, performance, and support profile bind to both context and ledger digests above.
$candidateRunId = [string]$ledgerAtReconcile.candidate_run_id
$codeHead = [string]$ledgerAtReconcile.expected_code_head
& py -3.12 $derivedVerifier candidate-evidence --module $module --candidate-run-id $candidateRunId --expected-shards windows --expected-outcome SOFTWARE_COMPLETE_HARDWARE_PENDING --evidence $candidateRoot --expected-code-head $codeHead --catalog $derivedCatalog --performance $derivedPerformance --support-profile $supportProfile
if ($LASTEXITCODE -ne 0) { throw '0602 candidate evidence reconciliation failed' }
```

  Only after reconciliation PASS create a report whose sole change is its return path. Record
  accepted base/product CodeHead, `candidateRunId`, per-gate owner/platform/tool/command/result,
  coverage/performance, recovery attempts if any, Windows evidence paths/bytes/SHA-256, the exact
  `SOFTWARE_COMPLETE_HARDWARE_PENDING` outcome, and the post-0603 unified 0.4+0.6 hardware gate
  required for final v0.6.0. Do not claim Linux or real-hardware PASS. Verify `git diff --check`
  and the staged path, then commit locally:

```powershell
git add docs/codex/returns/STM32TK-0602-DIAGNOSTIC-LOOP/implementation-report.md
git diff --cached --name-only
git commit -m "docs(STM32TK-0602): record accepted diagnostic CodeHead"
```

Expected: the Codex report-only child commit becomes 0603's accepted base while preserving the
hardware-pending gate. Stop without remote actions.
