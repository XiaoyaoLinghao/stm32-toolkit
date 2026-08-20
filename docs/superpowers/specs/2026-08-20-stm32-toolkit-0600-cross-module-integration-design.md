# STM32 Toolkit 0.6 Cross-Module Integration Design

**Status:** Written review candidate

**Discussion approval:** 2026-08-20

**Official released base:** `bb6bc5e9ee937e4ce53996b31f25bf1109ffe13f`

**Provisional integration base:** `c16538de810189272793f263197f4551a4538bae`

**Specification owner and final reviewer:** GPT-5.6-sol primary agent

**Product implementer:** GPT-5.6-luna subagent with reasoning effort `max`

## 1. Authority and purpose

This document is the single cross-module product design for STM32 Toolkit 0.6. It governs the
relationships among STM32TK-0600, STM32TK-0601, STM32TK-0602, and STM32TK-0603, the vertical delivery
order, the shared runtime policy, and the verification layers.

Existing module specifications remain authoritative for the local data structures, safety rules,
and product behavior explicitly retained in section 12. When an older 0.6 document conflicts with
this design on cross-module ownership, task decomposition, Python support, gate placement, or
delivery order, this design takes precedence.

The provisional integration base is not promoted to the released or module-accepted base by this
document. It remains the unchanged T10.1a candidate that completed independent Gate 6 review. Its
retained evidence remains valid; Gate 7 and later historical gates are not resumed.

## 2. User-visible goal and non-goals

### 2.1 Goal

STM32 Toolkit 0.6 must let a user or an authorized AI workflow execute this complete, auditable
loop:

```text
execute a Host or Target test
-> retain immutable test evidence
-> create a diagnostic session from a real failure
-> collect bounded observations
-> bind an external source change
-> rebuild and rerun the exact verification
-> compare before/after Monitor data
-> produce a traceable FixVerification
```

The loop is complete only when every transition is available through a public application service
used by CLI and MCP callers. Internal classes, unit tests, or release reports alone do not count as
a completed user scenario.

### 2.2 Non-goals

0.6 does not:

- add a second Evidence, Probe, Monitor, or diagnostic storage system;
- create a general provider or plugin platform;
- rewrite CTest, PyOCD, pyserial, Preact, ECharts, SQLite, or browser test engines;
- add new MCU families, new-project creation, remote hardware labs, or simulation claims;
- make a report, gate, catalog cache, or UI view an authoritative product state;
- allow a module to reach into another module's private database or file layout;
- use replay or fake evidence as a substitute for physical hardware evidence.

## 3. Runtime policy

STM32 Toolkit 0.6 supports one Python minor line:

```text
CPython >=3.12,<3.13
```

Python 3.12 is used at slice, integration, and release level. The reference release environment is
recorded against Python 3.12.10, but the patch number is evidence rather than a public API limit.

Toolkit and Monitor package metadata must use the same Python range. Bootstrap must reject Python
3.10 and 3.11 with a closed, actionable incompatibility result before it creates a managed runtime.
It must not silently create a runtime from an unsupported interpreter.

Python 3.10 code paths, scripts, matrices, and evidence from 0.5 and earlier 0.6 work are frozen
historical assets. They are not deleted in this migration, are not maintained, and do not qualify or
block a 0.6 candidate. Supporting another Python minor line in a later product release requires a
new compatibility decision and integration verification.

## 4. Module boundaries and dependency direction

### 4.1 STM32TK-0601: execution and facts

0601 owns:

- Project and firmware identity binding used by tests;
- Host and Target discovery and execution;
- TestRunManifest and native result conversion;
- EvidenceEnvelope, immutable artifacts, catalog projections, and GC;
- Probe v2, leases, Target transports, and exact operation authorization.

0601 does not know about DiagnosticSession, Monitor analysis, or release ledgers.

### 4.2 STM32TK-0602: diagnostic decisions

0602 owns:

- append-only DiagnosticSession events;
- hypotheses and EvidenceAssessment;
- closed ObservationPlan and VerificationPlan;
- SourceChangeDeclaration;
- FixVerification and the transition to RESOLVED.

0602 uses only 0601 public Test, Evidence, identity, and Probe v2 interfaces. It does not implement a
second probe service, test runner, evidence reader, source editor, or Monitor database writer.

### 4.3 STM32TK-0603: observation and presentation

0603 owns:

- Monitor history and immutable run references;
- bounded cross-run alignment, statistics, and deterministic decimation;
- sample quality, gaps, stages, and halt-impact analysis;
- append-only annotations and diagnostic markers;
- analysis bundles, public APIs, and UI presentation.

0603 can contribute evidence to a verification. It cannot mutate TestRunManifest, advance a
DiagnosticSession, or declare a fix successful.

### 4.4 STM32TK-0600: release proof

0600 owns final release matrices, packaging, platform checks, physical hardware acceptance, and
evidence archival. It has no product runtime API and may consume only the same public workflows used
by ordinary callers.

### 4.5 Dependency rule

```text
0603 --reads--> 0602 public diagnostic records
  |                 |
  +------reads------+--> 0601 public Evidence/Test/Identity
                              ^
0600 ----accepts through public workflows----+
```

No reverse dependency is permitted. Shared low-level identity types live below these modules rather
than being imported from 0602 or 0603 into 0601.

## 5. Public identity and data model

### 5.1 Required correlation fields

Every cross-module record carries or resolves these fields:

| Field | Meaning |
|---|---|
| `logicalProjectId` | stable logical project identity |
| `workspaceId` | identity of one canonical local project root |
| `firmwareIdentity` | Git, ELF digest, preset, target, and build identity |
| `operationId` | one idempotency and audit boundary |
| `producedAt` | normalized production timestamp |
| `producerVersion` | Toolkit component and schema version |

Cross-module references use only stable identifiers: `evidenceId`, `testRunId`,
`diagnosticSessionId`, `monitorRunId`, `analysisId`, and `fixVerificationId`. Absolute local paths,
database row numbers, process IDs, and temporary worktree paths are not public relationships.

### 5.2 Core entities and owners

| Entity | Owner | Contract |
|---|---|---|
| `ProjectIdentity` | existing Project Schema | project, workspace, and target identity |
| `FirmwareIdentity` | existing build system | source and binary identity |
| `EvidenceEnvelope` | 0601 | immutable facts and artifacts |
| `TestRunManifest` | 0601 | discovery, execution, cases, result, and native artifacts |
| `DiagnosticSession` and event | 0602 | append-only diagnostic lifecycle |
| `SourceChangeDeclaration` | 0602 | before/after source identity and diff digest |
| `MonitorRunRef` | 0603 | bounded sample window and firmware binding |
| `AnalysisResult` | 0603 | alignment, quality, statistics, and referenced inputs |
| `FixVerification` | 0602 | causal failed-before/change/fixed-after conclusion |

### 5.3 FixVerification minimum contract

A successful FixVerification contains:

- one failed-before TestRun reference;
- one SourceChangeDeclaration;
- one fixed-after TestRun reference for the same declared verification scope;
- compatible ProjectIdentity and FirmwareIdentity lineage;
- zero or more AnalysisResult references, each with explicit quality;
- the VerificationPlan digest and executed operation references;
- `PASSED`, `FAILED`, `INCONCLUSIVE`, or `CANCELLED`;
- a reason code that is closed for the schema version.

Monitor evidence is mandatory only when the VerificationPlan declares a Monitor assertion. Missing
or invalid mandatory Monitor evidence produces `INCONCLUSIVE`, never `PASSED`.

## 6. Sources of truth and lifecycle invariants

| Truth | Unique authority |
|---|---|
| project configuration and logical identity | `.stm32-project.json` |
| firmware identity | build identity record |
| immutable observations and artifacts | EvidenceStore |
| test execution result | TestRunManifest |
| diagnostic decisions and state | DiagnosticStore event chain |
| samples and analysis inputs | `monitor.sqlite3` |
| verified repair conclusion | FixVerification |
| release qualification | release ledger, outside product state |

The following invariants are mandatory:

1. Published Evidence and Diagnostic events are never edited in place.
2. Derived catalogs and analysis caches may be rebuilt and are never the sole source of truth.
3. 0602 and 0603 read Evidence through 0601 public interfaces, not catalog tables or object paths.
4. 0603 links markers through a 0602 public operation; it does not write DiagnosticStore directly.
5. Evidence referenced by a DiagnosticSession, FixVerification, retained TestRun, or exported bundle
   is a GC root.
6. Identity incompatibility fails closed. The product does not guess that two firmware or project
   identities refer to the same run.
7. Retrying a side-effecting operation creates a new attempt linked by `supersedesId`; it never
   rewrites the first attempt.
8. The same `operationId` cannot execute a flash, reset, Target test, or other side effect twice.

## 7. States and errors

### 7.1 Test states

```text
DISCOVERED -> PREPARED -> RUNNING
RUNNING -> PASSED | FAILED | ERROR | CANCELLED
```

`FAILED` means the test executed and observed incorrect product behavior. `ERROR` means the test
could not produce a trustworthy domain result because execution, environment, provider, protocol,
or evidence publication failed.

### 7.2 Diagnostic states

```text
OPEN -> INVESTIGATING -> FIX_PROPOSED -> VERIFYING -> RESOLVED
  \          \              \              \
   +----------+--------------+---------------> ABANDONED
```

Only a valid `FixVerification(PASSED)` can produce `RESOLVED`. A failed or inconclusive verification
returns the session to `INVESTIGATING` with a new append-only event; it does not erase the attempt.

### 7.3 Verification states

```text
PLANNED -> RUNNING
RUNNING -> PASSED | FAILED | INCONCLUSIVE | CANCELLED
```

Monitor quality uses `VALID`, `DEGRADED`, or `INVALID`. These are data-quality states and never
replace a verification result.

### 7.4 Closed public error classes

CLI and MCP adapters project domain outcomes through the existing versioned OperationResult with a
closed class:

- `DOMAIN_FAILURE`
- `AUTHORIZATION_REQUIRED`
- `AUTHORIZATION_DENIED`
- `ENVIRONMENT_FAILURE`
- `PROVIDER_FAILURE`
- `EVIDENCE_INTEGRITY_FAILURE`
- `INCOMPATIBLE_IDENTITY`
- `TIMEOUT`
- `CANCELLED`

Module-specific codes refine these classes without changing their meaning. Raw exceptions, native
exit codes, and absolute paths are not public error contracts.

`REPORT_FAILURE` exists only in release or governance reporting. It cannot change a TestRun,
DiagnosticSession, AnalysisResult, or FixVerification and cannot by itself invalidate unchanged
product evidence.

## 8. Public workflow and data flow

CLI, MCP, and Skill adapters are thin projections over one application-service layer. They do not
implement separate orchestration or error mappings.

The application layer exposes behavior equivalent to:

- run or query a Host/Target test and its TestRun evidence;
- start a DiagnosticSession from one failed TestRun;
- append hypotheses and execute a closed ObservationPlan;
- bind an external SourceChangeDeclaration;
- execute an authorized VerificationPlan;
- compare compatible Monitor runs and attach a diagnostic marker;
- create and query a FixVerification;
- export a deterministic analysis or diagnostic bundle.

The standard flow is:

```text
public request
-> resolve ProjectIdentity and WorkspaceIdentity
-> verify or produce FirmwareIdentity
-> execute test through 0601
-> publish TestRunManifest and native Evidence
-> explicitly create a 0602 session from a failed TestRun
-> execute bounded observations through Probe v2
-> publish EvidenceAssessment
-> bind the externally produced source change
-> execute the exact authorized build/flash/retest plan
-> ask 0603 to compare compatible before/after windows
-> create FixVerification and, only on PASS, resolve the session
```

Failure does not discard valid partial evidence. Environment or provider failure does not become a
domain test failure or advance the diagnostic state. Flash, reset, Target tests, and other MODIFY
operations require fresh authorization scoped to their exact action digest.

## 9. Executable acceptance scenarios

### 9.1 Scenario A: Host failure to verified fix

On a fixture project, the public Host workflow produces one real failing test. The product retains
the failed TestRun, native JUnit/log evidence, and source/firmware identity. A caller starts a
DiagnosticSession, records a supported hypothesis, binds an external source change, reruns the exact
failed case plus affected regression, and creates a FixVerification referencing the failed-before
and passed-after runs.

This scenario requires no hardware and runs in every integration environment.

### 9.2 Scenario B: Target replay through Monitor analysis

A frozen Target replay produces a deterministic Target test failure. A DiagnosticSession executes a
read-only Probe v2 replay observation, supports one hypothesis, and refutes another. A fixed replay
then produces a passing verification run. 0603 aligns compatible before/after Monitor windows,
emits quality and difference results, creates a diagnostic marker and deterministic analysis bundle,
and supplies evidence for a FixVerification PASS.

Replay is labeled as replay throughout and never qualifies a physical hardware claim.

### 9.3 Scenario C: physical failed-before/fixed-after

With a named supported board and explicit user authorizations, the product verifies probe, board,
project, and firmware identity; flashes a known failing firmware; runs one Target test and Monitor
window; performs bounded diagnosis; binds an external change; obtains a new authorization; rebuilds,
flashes, repeats the same test and observation; and creates a FixVerification spanning both firmware
identities and the source change.

This is an integration or release scenario, not a prerequisite for every software slice.

### 9.4 Mandatory negative scenario

Combining a TestRun and MonitorRun with incompatible FirmwareIdentity returns
`INCOMPATIBLE_IDENTITY`, creates no FixVerification, and does not move the DiagnosticSession to
RESOLVED. The original evidence remains unchanged.

## 10. Migration from the provisional base

1. Preserve all t101a-016 evidence and the clean Gate 6 review. Do not create Gate 7 or Gate 8
   artifacts.
2. Start the integration design and first slice from
   `c16538de810189272793f263197f4551a4538bae`.
3. Keep Project Schema v3, FirmwareIdentity, Evidence, TestRunManifest, Host/Target runners, Probe v2,
   authorization, transports, and the typed Evidence error ABI.
4. Reorganize the unimplemented T10 public CLI/MCP/Skill behavior into vertical slices.
5. Do not automatically integrate the historical Gate-plan amendments at
   `a9699b4ce292b1897c331b59a5d96d666dc589fb`; retain them as validation-infrastructure diagnosis.
6. If a reproducible defect described by historical T10.1b-T10.1k blocks a vertical behavior, fix it
   within that slice and its public acceptance, rather than reviving the old microtask ladder.
7. Freeze historical Python 3.10 assets without destructive cleanup.
8. Elevate a public contract to the 0.6 compatibility baseline only after an executable vertical
   scenario consumes it.

## 11. Vertical delivery slices

Each slice receives one separately reviewed implementation plan only when its predecessor has an
integrable result. The first writing-plans transition covers VS-01 only; this integration design is
not converted into one monolithic 0.6 implementation plan.

### 11.1 VS-01: Host Test Evidence public loop

**Input:** Schema v3 project and Host selector.

**Output:** public TestRun result, TestRunManifest, Evidence identifier, and public query behavior.

**Failure:** distinguish `FAILED` from environment/provider error and retain native artifacts.

**Acceptance:** scenario A runs from the public command through evidence query up to the initial
failed TestRun. Expected duration is one to two working days.

### 11.2 VS-02: failed TestRun to diagnostic session

**Input:** the failed TestRun from VS-01.

**Output:** DiagnosticSession, hypotheses, ObservationPlan, and EvidenceAssessment.

**Failure:** missing, damaged, or identity-incompatible evidence fails closed and does not advance
the session. Expected duration is two to three working days.

### 11.3 VS-03: Target replay and Monitor verification

**Input:** failed-before and fixed-after replay, Monitor windows, and SourceChangeDeclaration.

**Output:** AnalysisResult, marker, bundle, and FixVerification.

**Failure:** insufficient or incompatible data yields `INCONCLUSIVE`. Scenario B and the mandatory
negative scenario are the acceptance. Expected duration is two to three working days.

### 11.4 VS-04: physical hardware integration

**Input:** named board, probe, failing firmware, and two separately authorized MODIFY phases.

**Output:** the physical FixVerification in scenario C.

This is an integration-level slice. If the environment or authorization is absent, it remains a
named product blocker and is not recursively decomposed or replaced with fake evidence.

No slice may be decomposed into a multi-level task tree. If a software slice cannot retain a
demonstrable boundary within three working days, work returns to this design before a plan is
expanded.

## 12. Historical document disposition

### 12.1 Retained

- The 2026-07-29 architecture's project isolation, single Probe owner, authorization levels,
  Evidence principles, and Monitor product requirements.
- The 0601 Evidence, Test, transport, and Probe v2 domain contracts.
- The 0602 append-only session, hypothesis, observation, source-change, and FixVerification semantics.
- The 0603 alignment, quality, annotation, marker, bundle, and existing UI-stack decisions.
- The layered L0-L4 design and provider boundary.

### 12.2 Replaced for 0.6 execution

- the T10.1a-T10.1k and T10.2-T10.16 recursive delivery tree;
- the eight-stage gate ladder for every microtask;
- separate full candidate/recovery/release workflows inside 0601, 0602, and 0603;
- the Python 3.10/3.12 dual-runtime requirement;
- delivery that postpones all end-to-end product behavior until final 0600 acceptance.

### 12.3 Historical reference only

- the T10 project correction plan and its task grouping;
- the Evidence boundary matrix's gate orchestration, while retained safety behaviors remain valid;
- literal command ladders in the 0600 release acceptance plan;
- historical run reports, root-cause amendments, and environment-failure records.

Historical documents are not deleted. This section determines precedence when they are consulted.

## 13. Verification layers and risk triggers

### 13.1 Slice level

Each slice normally has four verification groups:

1. user-behavior target tests;
2. cross-module public-contract tests;
3. affected regression;
4. independent 5.6-sol complete-diff review.

All use Python 3.12. A slice does not run a second Python version, complete release matrix, complete
multi-platform package, hardware matrix, or unrelated browser and performance gates.

### 13.2 Integration level

Integration runs scenarios A and B, the mandatory negative identity scenario, and the applicable
authorization, cancellation, recovery, determinism, quality, and performance constraints. Tests
consume public interfaces rather than module-private storage.

### 13.3 Release level

0600 runs the complete Python 3.12 suite, Windows reference environment, available named platform
checks, browser and packaging checks, offline installation and dependency audit, release coverage,
scenario C, and final evidence archival.

A release failure invalidates only its affected layer and downstream acceptance. It does not force
unchanged slices to rerun.

### 13.4 Explicit forward triggers

| Product change | Check allowed to move forward |
|---|---|
| authorization, flash, reset, Probe lease, GC deletion, path confinement | affected security and fault-injection checks |
| persistent schema, protocol, or identity algorithm | compatibility, migration, and identity checks |
| native parser, process execution, or environment discovery | real native fixture and affected platform check |
| Node/browser resource or package path | browser build and resource-integrity check |
| measured sampling, analysis, or storage hot path | named performance workload |
| physical transport or hardware control | named hardware check with single-use authorization |
| runtime dependency | offline installation, license, and security review |

Change size, module importance, or reviewer concern without a named failure mode is not a trigger.

## 14. Stop-loss rules

- One slice has at most one implementation worktree and one independent review worktree.
- A slice verification plan normally has at most four command groups and no nested gate tree.
- A report-field, hash-transcription, or authority-description error repairs the report only; it does
  not invalidate unchanged product evidence.
- Environment and provider failures remain separate from product failures.
- Passed evidence remains valid until a relevant product byte, dependency, environment, or contract
  changes.
- If the same problem does not converge after two implementation/review rounds, stop patching and
  return to the public interface or integration design.
- A slice that exceeds three working days or needs recursive decomposition returns to design.
- If verification and reporting take longer than product implementation, the review records why. If
  this happens for two consecutive slices, product work pauses for governance review.
- Theoretical hardening cannot enlarge a slice without a reproducible defect, frozen contract, or
  explicit risk trigger.
- Historical worktree, evidence, and branch cleanup is a separately authorized governance action.

## 15. Progress and completion

Progress is reported with:

- completed runnable user scenarios;
- completed cross-module links;
- public contracts consumed by real callers and frozen;
- unresolved product blockers, separate from environment blockers;
- elapsed time from slice start to integrable result;
- product implementation, verification, and reporting time and ratio;
- current demonstrable entry point and most recent valid evidence.

The baseline at design freeze is:

| Metric | Baseline |
|---|---|
| runnable 0.6 scenarios | 0 of 3 |
| complete cross-module links | 0 |
| provisional integration base | `c16538de810189272793f263197f4551a4538bae` |
| Python runtime | 3.12 only |
| active product implementation | none |
| current historical gate | t101a-016 Gate 6 CLEAN; no later gate |
| remote and hardware authorization | none |

0.6 software integration is complete when scenarios A and B plus the mandatory negative scenario
pass through public workflows and the required contracts are frozen. 0.6 release acceptance also
requires scenario C and the applicable 0600 release layer. No push, PR mutation, merge, tag, closure,
or remote branch deletion is implicit in either state.
