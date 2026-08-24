# STM32 Toolkit VS08-A Versioned Scenario Adapters Design

**Status:** Approved just-in-time vertical-slice specification

**Date:** 2026-08-24

**Accepted base:** `8f7bcb5c860998bc8459c7b33690d9a297319a6c`

**Specification owner and final reviewer:** GPT-5.6-sol primary agent

**Implementation owner:** one GPT-5.6-luna subagent, reasoning effort `max`

**Branch:** `codex/STM32TK-0801-VS08-A`

**Remote, installation, release, and hardware authority:** none

## 1. Purpose and authority

This specification is the immediate VS08-A product decision under the approved
0.7-1.0 integrated product design and vertical delivery plan. It freezes the
smallest product surface that lets callers describe, finalize, and later query
two versioned software acceptance scenarios:

1. `legacy-keil-migration` version `1`;
2. `new-cubemx-project` version `1`.

The adapter validates and projects results already produced by the existing
Project, Build, Test, Evidence, and Diagnostic public workflows. It does not
schedule those workflows, launch tools, edit source, acquire a Probe, or own a
second lifecycle. A completed record is an immutable root in the existing
`EvidenceStore` whose content contains stable references, not copied Test,
Diagnostic, Monitor, or FixVerification payloads.

This specification supersedes the monolithic acceptance-runner decomposition
in the retained 2026-08-04 plan. The retained plan remains a requirements
source, but VS08-A does not create `acceptance/runner.py`, a 0.8 controller, a
daemon, a scheduler, a provider registry, or a release gate.

## 2. Runnable user scenarios

### Scenario 1: inspect the supported scenario contract

A project-bound CLI or MCP caller asks for one scenario ID and version. The
Toolkit returns the closed `AcceptanceScenario` definition, its canonical
digest, required project origin, ordered completed-stage vocabulary, and the
fixed software execution policy. Unknown IDs or versions fail closed and do
not create workspace state.

### Scenario 2: finalize and query a legacy Keil migration

The caller has already used the existing public migration/configure/build and
0.6 replay/diagnostic workflows. It supplies one failed-before Target replay
run ID, one fixed-after Target replay run ID, and one resolved diagnostic
session ID. The adapter verifies the current project origin is `keil`, reloads
all three references through existing public workflow readers, proves a
`PASSED` FixVerification binds the exact failed and fixed runs, publishes one
immutable software-only acceptance record, and returns its record ID. A fresh
process can query the same record by ID.

### Scenario 3: finalize and query a new CubeMX project

The same operation is performed for a project whose authoritative project
origin is `cubemx`. The record uses the `new-cubemx-project` version `1`
definition and otherwise consumes the same Test/Evidence/Diagnostic contracts.
Creation provenance remains owned by the project manifest and generation
ownership manifest; the acceptance adapter does not copy or reinterpret them.

### Scenario 4: refuse an untrustworthy completion

Physical Target evidence, non-replay evidence, unresolved or non-passing
diagnosis, reversed failed/fixed states, mismatched project/workspace/target
identity, wrong project origin, stale or corrupt evidence roots, unknown
fields, and reuse of one record ID for different content all fail closed. No
acceptance root is published and prior Evidence remains unchanged.

## 3. Explicit non-goals

VS08-A does not:

- implement interruption recovery, step timeouts, resume tokens, lease/target
  cleanup, or human checkpoints; those are VS08-B and must build on the
  accepted immutable record contract;
- execute migration, creation, configure, build, test, diagnosis, Monitor, or
  verification actions on behalf of a caller;
- add a controller, scheduler, daemon, provider platform, Evidence store,
  Probe backend, release ledger, gate catalog, CI workflow, or remote runner;
- add Python 3.10/3.11 or any Python range outside `>=3.12,<3.13` to active
  product scope;
- add a physical success state or convert fixture/replay evidence into a
  physical PASS;
- install tools or dependencies, use hardware, or perform push, PR, merge,
  tag, release, close, or remote branch deletion.

## 4. Frozen public models

All JSON objects are closed, canonical, NFC-normalized, integer-only where a
number is allowed, and bounded by existing Evidence JSON limits. Python-only
tuple containers are rejected at JSON-facing model boundaries.

### 4.1 `AcceptanceScenario`

Schema: `stm32-acceptance-scenario/1`.

Exact public fields:

| Field | Type | Contract |
|---|---|---|
| `schema` | string | exactly `stm32-acceptance-scenario/1` |
| `scenarioId` | string | `legacy-keil-migration` or `new-cubemx-project` |
| `scenarioVersion` | string | exactly `1` |
| `scenarioDigest` | lowercase SHA-256 | digest of the canonical object without this field |
| `projectOrigin` | string | `keil` for legacy, `cubemx` for new-project |
| `executionProfile` | string | exactly `software-replay` |
| `requiredStages` | array of strings | exact ordered stages below |
| `physicalTransportEvidence` | boolean | exactly `false` |

The exact `requiredStages` are:

1. `project-materialized`;
2. `firmware-built-before`;
3. `target-failure-replayed`;
4. `diagnosis-completed`;
5. `firmware-built-after`;
6. `target-fix-verified`.

The two definitions differ only in ID and required project origin. They are
code-owned immutable definitions, not user-provided YAML and not a provider
registry.

The version-1 canonical digests are frozen:

| Scenario | Digest |
|---|---|
| `legacy-keil-migration` | `e6fc21a053645f6ae3af8be59ed95941f1dddb57921baeff4263b4276e1cd6cb` |
| `new-cubemx-project` | `5650cf942b41f7e6d281cdd836f5ff7320434557998906065c133830701402b3` |

### 4.2 `AcceptanceRecord`

Schema: `stm32-acceptance-record/1`.

Exact public fields:

| Field | Type | Contract |
|---|---|---|
| `schema` | string | exactly `stm32-acceptance-record/1` |
| `recordId` | canonical lowercase UUID | caller operation/idempotency boundary |
| `scenarioId` | string | exact supported ID |
| `scenarioVersion` | string | exactly `1` |
| `scenarioDigest` | lowercase SHA-256 | exact current definition digest |
| `workspaceId` | lowercase SHA-256 | current import workspace identity |
| `logicalProjectId` | canonical lowercase UUID | authoritative project identity |
| `projectOrigin` | string | exact origin required by the scenario |
| `executionSource` | string | exactly `replay` |
| `physicalTransportEvidence` | boolean | exactly `false` |
| `completedStages` | array of strings | exactly the scenario's ordered stages |
| `failedBeforeTestRunId` | canonical UUID | authoritative failed Target replay |
| `fixedAfterTestRunId` | canonical UUID | authoritative passed Target replay |
| `diagnosticSessionId` | canonical UUID | authoritative resolved session |
| `fixVerificationId` | lowercase SHA-256 | the session's exact passing verification |
| `failedBeforeEvidenceId` | lowercase SHA-256 | existing TestRun evidence root target |
| `fixedAfterEvidenceId` | lowercase SHA-256 | existing TestRun evidence root target |
| `beforeBuildId` | lowercase SHA-256 | failed replay firmware build identity |
| `afterBuildId` | lowercase SHA-256 | fixed replay firmware build identity |
| `beforeElfSha256` | lowercase SHA-256 | failed replay ELF identity |
| `afterElfSha256` | lowercase SHA-256 | fixed replay ELF identity |
| `verdict` | string | exactly `SOFTWARE_PASSED` |
| `producedAtUtc` | UTC microsecond timestamp | publication time |

`recordId` is the caller-supplied operation ID. Repeating the same request is
idempotent and returns the identical record. Reusing the same ID with any
different canonical content returns `ACCEPTANCE_RECORD_CONFLICT`; it never
overwrites the first record.

## 5. Public operations

CLI and MCP are thin projections over the same functions.

### 5.1 Describe

- CLI: `stm32-toolkit ... scenario describe --scenario-id <id> --scenario-version 1`
- MCP: `stm32_acceptance_scenario_describe(scenarioId, scenarioVersion)`
- OperationResult operation: `acceptance.scenario.describe`

This operation is read-only and creates no data root.

### 5.2 Record completion

- CLI: `stm32-toolkit ... scenario record --record-id <uuid> --scenario-id
  <id> --scenario-version 1 --failed-before-test-run-id <uuid>
  --fixed-after-test-run-id <uuid> --diagnostic-session-id <uuid>`
- MCP: `stm32_acceptance_scenario_record(...)` with the same six camelCase
  fields and no root/path/environment override
- OperationResult operation: `acceptance.scenario.record`

The workflow reloads the current project and all referenced records. It derives
every identity, evidence ID, build ID, ELF digest, verification ID, stage list,
execution-source field, and verdict. Those values are never accepted from the
caller.

### 5.3 Show

- CLI: `stm32-toolkit ... scenario show --record-id <uuid>`
- MCP: `stm32_acceptance_scenario_show(recordId)`
- OperationResult operation: `acceptance.scenario.show`

Show loads the existing `acceptance-scenario` root and envelope, validates
their exact correspondence and canonical record, revalidates that the record
belongs to the currently bound workspace/project, and returns the record with
`authoritative: true`. It does not rerun product actions.

## 6. Validation and publication algorithm

For `record`, validation order is fixed:

1. validate closed scalar input syntax without creating workspace state;
2. load the project through the existing project model and require the exact
   origin for the selected definition;
3. call existing public `test_show` for both run IDs and require authoritative
   Target replay results: failed-before state `failed`, fixed-after state
   `passed`, `execution_source == replay`, and
   `physical_transport_evidence is false`;
4. require both runs' import workspace ID and logical project ID to equal the
   currently bound project; require compatible target identity; derive the
   before/after build and ELF identities from those authoritative runs;
5. call existing public diagnostic show and verification-show operations;
   require session state `RESOLVED` and exactly one selected `PASSED`
   FixVerification binding the supplied failed-before and fixed-after run IDs;
6. construct the record, an `EvidenceEnvelope(operation="acceptance-scenario")`
   with the fixed-after identity, and parents containing the existing failed,
   fixed, and final diagnostic evidence references without duplicates;
7. publish through the existing `EvidenceStore`, then publish a
   `RootRecord(root_type="acceptance-scenario", root_id=recordId, ...)`;
8. reload and verify envelope/root/record bytes before returning success.

Publication must tolerate retry after a crash between identical immutable
object writes. Any non-identical existing object is corruption/conflict, not a
replacement opportunity. The existing Evidence mutation lock and root
publication primitives remain authoritative; VS08-A adds no lock or store.

## 7. State and lifecycle

VS08-A has no mutable scenario state machine:

```text
SUPPORTED DEFINITION
    -> validate already-completed public workflow chain
    -> immutable SOFTWARE_PASSED AcceptanceRecord
```

Any validation failure leaves no acceptance record. Existing Test, Evidence,
Diagnostic, Monitor, and FixVerification records remain untouched. An
AcceptanceRecord is a GC root and its Evidence parents remain reachable.

Interrupted attempts, checkpoint authorization, resume, timeout, and cleanup
are deliberately absent. VS08-B may add immutable attempt/checkpoint records
that reference this versioned definition and completed-record contract, but it
must not mutate an accepted VS08-A record or change the two version-1 digests.

## 8. Error semantics

Public failures use the existing `OperationResult` envelope and exact
operation names. The slice adds these closed module codes:

| Code | Meaning/classification |
|---|---|
| `ACCEPTANCE_INPUT_INVALID` | malformed/unknown-field request; INPUT |
| `ACCEPTANCE_SCENARIO_UNKNOWN` | unsupported ID; INPUT |
| `ACCEPTANCE_SCENARIO_VERSION_UNSUPPORTED` | unsupported version; INPUT |
| `ACCEPTANCE_PROJECT_ORIGIN_MISMATCH` | scenario/project mismatch; PRODUCT/INPUT boundary |
| `ACCEPTANCE_REFERENCE_INVALID` | missing, wrong-state, or wrong-kind public record; PRODUCT |
| `ACCEPTANCE_IDENTITY_MISMATCH` | project/workspace/target lineage mismatch; PRODUCT |
| `ACCEPTANCE_PHYSICAL_EVIDENCE_FORBIDDEN` | physical or ambiguously sourced evidence supplied to software profile; PRODUCT |
| `ACCEPTANCE_NOT_COMPLETE` | diagnosis or verification is not resolved and passed; PRODUCT |
| `ACCEPTANCE_RECORD_CONFLICT` | same record ID denotes different content; PRODUCT |
| `ACCEPTANCE_EVIDENCE_INTEGRITY_FAILED` | existing root/envelope/reference is corrupt; PRODUCT |

Messages are stable and contain no raw exception text or absolute host path.
Environment, platform, infrastructure, hardware, and report failures remain
separate classifications and cannot be converted to `SOFTWARE_PASSED`.

## 9. Dependency direction and source of truth

```text
CLI/MCP
  -> acceptance workflow adapter
       -> Project model (origin and logical identity)
       -> existing Test public show workflow
       -> existing Diagnostic public show workflows
       -> existing EvidenceStore / RootRecord publication
```

The acceptance package may import lower-level Project/Test/Diagnostic/Evidence
public interfaces. None of those modules may import the acceptance package.

Unique authorities remain:

- project origin and logical identity: `.stm32-project.json`;
- firmware/build identity: existing TestRun/FirmwareIdentity records;
- replay/physical policy: authoritative TestRun evidence metadata;
- diagnosis and passing verification: DiagnosticStore event chain;
- immutable observations: existing EvidenceStore;
- scenario definition and completed projection: versioned VS08-A models;
- release or physical qualification: later release ledger/hardware campaign,
  never the VS08-A record.

## 10. Verification and evidence ownership

### Slice evidence — Luna/max implementer

- strict model/digest/closed-field tests;
- workflow success for both project origins using real existing
  Test/Evidence/Diagnostic components and replay fixtures;
- refusal tests for physical evidence, wrong states, unresolved verification,
  cross-workspace/project references, corruption, and record-ID conflict;
- CLI and MCP parity/closed-schema/root-binding tests;
- Evidence GC retention for the new root type;
- affected VS03, creation, Test, Diagnostic, CLI, MCP, and Evidence regressions;
- Python 3.12 compileall and `git diff --check`.

RED evidence must show the new behavior failing before production code. GREEN
evidence belongs only to the returned product CodeHead. Fixtures and replay are
software evidence and must be labeled non-physical.

### Independent acceptance — GPT-5.6-sol primary agent

- inspect the complete accepted-base-to-CodeHead diff in a clean detached
  review worktree;
- rerun the focused VS08-A model/workflow/CLI/MCP/GC tests and proportionate
  affected regression;
- independently probe cross-workspace rejection, replay/physical rejection,
  idempotent reload, and corruption/conflict behavior;
- verify report/SDD facts, clean branch, no upstream, and no remote, hardware,
  release, or installation action.

No full release matrix, package/install test, browser suite, performance gate,
or hardware run is triggered: the slice changes no runtime dependency, browser
surface, package/bootstrap inventory, Probe backend, or physical transport.

## 11. Acceptance criteria

VS08-A is `ACCEPTED` only when:

1. both version-1 scenario definitions are public and stable;
2. both software scenarios can be finalized from real existing workflow
   records and queried after a fresh reload;
3. every returned record is `executionSource: replay`,
   `physicalTransportEvidence: false`, and `verdict: SOFTWARE_PASSED`;
4. invalid/cross-workspace/physical/corrupt inputs publish no acceptance root;
5. existing Evidence remains the sole store and GC retains accepted records;
6. CLI and MCP expose the same three operations with closed project-bound
   inputs;
7. required slice and affected-regression tests pass on Python 3.12;
8. the independent complete diff has no unresolved product defect;
9. the tracked implementation report and SDD ledger state the exact base,
   product CodeHead, evidence owners, classifications, and non-physical scope;
10. the local branch is clean, has no upstream, and remains unpushed.
