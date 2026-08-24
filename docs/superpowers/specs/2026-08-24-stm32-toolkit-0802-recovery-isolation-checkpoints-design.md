# STM32 Toolkit VS08-B Recovery, Isolation, and Human Checkpoints Design

**Status:** Approved just-in-time vertical-slice specification

**Date:** 2026-08-24

**Accepted base:** `eea72a46d9fcdcd7abd8ebfac5b09a8e921f6ba2`

**Specification owner and final reviewer:** GPT-5.6-sol primary agent

**Implementation owner:** one GPT-5.6-luna subagent, reasoning effort `max`

**Branch:** `codex/STM32TK-0802-VS08-B`

**Remote, installation, release, and hardware authority:** none

## 1. Purpose and authority

This specification is the immediate VS08-B product decision after independent
acceptance of VS08-A. It adds one bounded, append-only recovery adapter around
the two accepted version-1 software scenarios. A caller can begin an attempt,
record already-completed public workflow outputs one stage at a time, recover
the latest verified prefix after process interruption, pass one explicit
source-change checkpoint, and bind the completed attempt to the immutable
VS08-A `AcceptanceRecord`.

The adapter records references and canonical identities in the existing
`EvidenceStore`. It never executes a scenario stage. It does not acquire a
Probe lease, invoke a target, edit source, flash firmware, launch a tool,
schedule work, or add a mutable ledger. Existing Project, Build, Test,
Diagnostic, Evidence, and VS08-A records remain the sole authorities for their
own facts.

The exact slice accepted base is the accepted VS08-A head
`eea72a46d9fcdcd7abd8ebfac5b09a8e921f6ba2`. The two VS08-A version-1 scenario
digests remain unchanged:

- `legacy-keil-migration`: `e6fc21a053645f6ae3af8be59ed95941f1dddb57921baeff4263b4276e1cd6cb`;
- `new-cubemx-project`: `5650cf942b41f7e6d281cdd836f5ff7320434557998906065c133830701402b3`.

## 2. Runnable user scenarios

### Scenario 1: recover an interrupted software attempt

A caller begins a version-1 attempt and checkpoints the project, before-build,
failed Target replay, and diagnosis outputs already produced by existing
public workflows. The process exits. A fresh process calls `resume`; the
adapter reloads and verifies the immutable revision chain, returns the exact
latest prefix, the next required action, and whether explicit authorization is
required. It neither repeats nor fabricates any external action.

### Scenario 2: pass an explicit source-change checkpoint and complete

After `diagnosis-completed`, `resume` returns a deterministic action digest for
the proposed source-change boundary. A caller separately submits that exact
digest with `authorized: true`. Only then may the attempt accept an authoritative
after-build whose diagnostic source-change declaration is newer than the
authorized diagnostic revision and binds the before/after identities. The
final checkpoint references a queryable VS08-A `SOFTWARE_PASSED` record with
the same complete lineage.

### Scenario 3: run two workspaces without cross-talk

Two independent workspaces may use the same `attemptId` and advance concurrently.
Each resolves only its workspace-scoped Evidence roots. Copying or naming a
checkpoint, TestRun, Diagnostic session, or AcceptanceRecord from the other
workspace fails closed. Concurrent writers in one workspace cannot overwrite
one another: one canonical next revision wins, an identical retry returns the
winner, and a different transition reports a revision conflict.

### Scenario 4: fail closed after timeout, corruption, or authority loss

An advancement after its stage deadline, a missing/gapped revision, a corrupt
root/envelope, project identity drift, stale build, lease/target evidence
misclassification, or mismatched public output returns a stable error and
leaves all prior revisions untouched. Replay and fixtures remain software-only
evidence and are never reported as physical PASS.

## 3. Explicit non-goals

VS08-B does not:

- execute, sequence, poll, retry, or schedule project, build, test, diagnosis,
  source modification, verification, or finalization actions;
- add a controller, runner, scheduler, daemon, provider, Evidence store,
  mutable database/index, Probe backend, transport, or background timer;
- acquire, renew, release, or replace the existing Probe lease and target
  cleanup ownership; applicable existing workflow regressions verify those
  boundaries;
- authorize or perform flash. Software-replay scenarios declare flash
  inapplicable and delegate any separately requested physical flash to the
  existing Probe action-digest contract;
- claim a verified human identity. `authorized: true` is a separate explicit
  caller checkpoint, not authentication or attestation;
- change the accepted VS08-A definitions, records, digests, or verdict;
- add Python 3.10/3.11 or any support outside `>=3.12,<3.13`;
- use hardware, install dependencies, or perform push, PR, merge, tag,
  release, close, or remote branch deletion.

## 4. Recovery policy

The code-owned canonical policy is closed and is not a provider registry:

```json
{"attemptSchema":"stm32-acceptance-attempt/1","intrusiveActions":{"flash":{"applicable":false,"authorization":"existing-probe-action-digest","reason":"software-replay"},"source-change":{"afterStage":"diagnosis-completed","applicable":true,"authorization":"explicit-single-use","beforeStage":"firmware-built-after"}},"physicalTransportEvidence":false,"schema":"stm32-acceptance-recovery-policy/1","stageTimeoutSeconds":{"diagnosis-completed":900,"firmware-built-after":900,"firmware-built-before":900,"project-materialized":60,"target-failure-replayed":300,"target-fix-verified":300}}
```

Its frozen SHA-256 digest is
`af7495c012b2a9e9a6bcda65250922eec30eb4b7e6c1aac342a0e07ef8e28b4c`.
Both version-1 scenarios use this same policy. The six ordered stages remain
exactly the VS08-A `requiredStages` tuple.

## 5. Immutable `AcceptanceAttempt`

Schema: `stm32-acceptance-attempt/1`.

Each revision is a complete, small, canonical snapshot containing references
and digests only. Its exact public fields are:

| Field | Type | Contract |
|---|---|---|
| `schema` | string | exactly `stm32-acceptance-attempt/1` |
| `attemptId` | canonical lowercase UUID | caller idempotency/isolation key |
| `revision` | integer | `0..7`, with no boolean or gap |
| `checkpointId` | lowercase SHA-256 | digest of the canonical snapshot without this field |
| `previousCheckpointId` | null or lowercase SHA-256 | null only at revision 0; exact prior checkpoint otherwise |
| `scenarioId` | string | an accepted VS08-A scenario ID |
| `scenarioVersion` | string | exactly `1` |
| `scenarioDigest` | lowercase SHA-256 | exact accepted VS08-A definition digest |
| `recoveryPolicyDigest` | lowercase SHA-256 | exact frozen policy digest |
| `workspaceId` | lowercase SHA-256 | current import workspace identity |
| `logicalProjectId` | canonical lowercase UUID | authoritative project identity |
| `projectOrigin` | string | exact scenario-required origin |
| `executionSource` | string | exactly `replay` |
| `physicalTransportEvidence` | boolean | exactly `false` |
| `status` | string | `ACTIVE` or `COMPLETED` |
| `completedStages` | array | an exact prefix of the six scenario stages |
| `stageOutputs` | object | exact closed output keys for that prefix |
| `sourceChangeAuthorization` | null or object | exact authorization record below |
| `openedAtUtc` | timestamp | server UTC microseconds at begin |
| `deadlineAtUtc` | null or timestamp | current next-stage deadline; null only when completed |
| `updatedAtUtc` | timestamp | server UTC microseconds for this revision |

Revision 0 is the begun attempt and has no completed stages. Revisions 1-4
checkpoint `project-materialized` through `diagnosis-completed`; revision 5 is
the source-change authorization; revisions 6-7 checkpoint
`firmware-built-after` and `target-fix-verified`. The authorization revision
does not invent a seventh scenario stage.

`stageOutputs` has exactly these keys, with absent values represented by null:

- `projectModelDigest`;
- `beforeBuildId`, `beforeElfSha256`, `beforeInputSnapshotSha256`;
- `failedBeforeTestRunId`, `failedBeforeEvidenceId`;
- `diagnosticSessionId`, `diagnosticRevision`, `diagnosticEventHead`;
- `afterBuildId`, `afterElfSha256`, `afterInputSnapshotSha256`,
  `sourceChangeDeclarationId`;
- `acceptanceRecordId`.

`sourceChangeAuthorization`, when non-null, is closed and contains exactly
`action`, `actionDigest`, `authorized`, `authorizedAtUtc`,
`diagnosticSessionId`, `diagnosticRevision`, and `diagnosticEventHead`.
`action` is exactly `source-change`; `authorized` is exactly `true`. The digest
binds the attempt ID, revision-4 checkpoint ID, scenario identity, workspace
and project identity, before-build identity, failed run identity, diagnostic
session/revision/event head, and action string. It does not authorize flash or
any other attempt.

All objects reject unknown/missing fields, tuple JSON containers,
noncanonical UUID/hash/time values, invalid prefixes, inconsistent nulls,
changed fixed policy, changed VS08-A digest, timestamp reversal, and a
checkpoint digest that does not match its content.

## 6. Storage and recovery algorithm

The slice registers exactly one new existing-Evidence root type:
`acceptance-attempt`. A revision root ID is
`<attemptId>.<revision-as-eight-decimal-digits>`, for example
`00000000-0000-4000-8000-000000000001.00000004`. No mutable head, index,
database, directory lock, or side file is created.

All begin/show/resume/advance operations first derive the current project and
workspace identities. Loading an attempt scans only the bounded revision IDs
0 through 7. It requires revision 0, a contiguous prefix, exact root IDs,
root/envelope correspondence, the `acceptance-attempt` operation, canonical
snapshot bytes, valid checkpoint links, and the current workspace/project
identity. A gap, later revision after a gap, corrupt envelope, or conflicting
canonical object is an integrity failure. At most eight roots are read.

Publication uses the existing Evidence mutation lock and immutable
`EvidenceStore`/`RootRecord` primitives. The workflow writes an envelope and
then the deterministic revision root. A retry first reloads the chain. If the
requested canonical transition is already the latest revision, it returns
that exact stored snapshot even though its server timestamp is not reproduced.
If the expected revision is stale and revision+1 represents another
transition, the operation returns `ACCEPTANCE_ATTEMPT_REVISION_CONFLICT`.
Publication never overwrites a root. An orphan envelope after interruption is
harmless and retryable; it is not an attempt revision until its root exists.

Two workspace stores therefore admit the same attempt ID independently. In a
single workspace, concurrent calls with the same expected revision serialize
under the existing Evidence mutation lock; identical requests converge on one
revision, while distinct requests cannot both publish the same revision root.

## 7. Public operations

CLI and MCP are thin project-bound projections over one workflow context.
MCP accepts no root/path/environment/command/transport override.

### 7.1 Begin

- CLI: `scenario attempt begin --attempt-id <uuid> --scenario-id <id> --scenario-version 1`
- MCP: `stm32_acceptance_attempt_begin(attemptId, scenarioId, scenarioVersion)`
- operation: `acceptance.attempt.begin`

Begin validates the supported scenario and current project origin/identity,
then publishes revision 0. Identical retry returns revision 0; same ID with a
different scenario or identity conflicts.

### 7.2 Checkpoint

- CLI: `scenario attempt checkpoint --attempt-id <uuid> --expected-revision <n> --stage <stage>` plus the one applicable reference option
- MCP: `stm32_acceptance_attempt_checkpoint(attemptId, expectedRevision, stage, testRunId?, diagnosticSessionId?, acceptanceRecordId?)`
- operation: `acceptance.attempt.checkpoint`

All optional properties are present in the closed MCP schema but null unless
required. `target-failure-replayed` requires only `testRunId`;
`diagnosis-completed` requires only `diagnosticSessionId`;
`target-fix-verified` requires only `acceptanceRecordId`; project and build
stages accept no reference. The server derives every other value.

### 7.3 Authorize source change

- CLI: `scenario attempt authorize-source-change --attempt-id <uuid> --expected-revision 4 --action-digest <sha256> --authorized`
- MCP: `stm32_acceptance_attempt_authorize_source_change(attemptId, expectedRevision, actionDigest, authorized)`
- operation: `acceptance.attempt.authorize-source-change`

Authorization is valid only after `diagnosis-completed`, for the exact digest
returned by show/resume, with the literal boolean `true`. It is single-use
because it creates revision 5. False, coercible values, wrong digest, wrong
revision, timeout, or any other stage fail without publication.

### 7.4 Show and resume

- CLI: `scenario attempt show|resume --attempt-id <uuid>`
- MCP: `stm32_acceptance_attempt_show|resume(attemptId)`
- operations: `acceptance.attempt.show` and `acceptance.attempt.resume`

Show returns the authoritative latest snapshot. Resume additionally returns a
closed projection: `nextStage`, `authorizationRequired`, `actionDigest`,
`timedOut`, and `recoveryPolicy`. It never advances state. After the last
stage, `nextStage` and `actionDigest` are null. After diagnosis and before
authorization, `nextStage` remains `firmware-built-after` but
`authorizationRequired` is true. `timedOut` is derived from the server clock;
the stored snapshot is not mutated.

## 8. Stage authorities and transitions

Every advancement reloads the current chain and validates the whole prefix.
It then verifies exactly one next authority:

1. `project-materialized`: load the authoritative v3 project manifest; require
   scenario origin/workspace/project match; record its canonical model digest.
2. `firmware-built-before`: call `build_project_context`; require a fresh
   `Debug` build for this project and record input snapshot, build, and ELF
   digests.
3. `target-failure-replayed`: call existing `test_show` and its real Evidence
   reader; require Target `failed`, execution source `replay`, physical flag
   false, exact workspace/project/target lineage, and exact before build/ELF.
4. `diagnosis-completed`: call existing `diagnostic_show`; require the same
   failed run/workspace/project/target, state `INVESTIGATING`, and no source
   change declaration. Record its current revision and event head.
5. authorization: require the deterministic source-change action digest and
   explicit true; record the exact diagnostic revision/event head it approved.
6. `firmware-built-after`: call `build_project_context`; require a fresh
   `Debug` build different from before. Reload the diagnostic session and
   require exactly one source-change declaration added after the authorized
   revision, whose before and after source/build/ELF lineage equals the stored
   before and current after identities. Record its declaration ID.
7. `target-fix-verified`: call accepted VS08-A show and root validation;
   require the same scenario/workspace/project, failed run, diagnostic
   session, before/after builds and ELFs, replay/nonphysical policy, and
   `SOFTWARE_PASSED`. Record its ID and set status `COMPLETED`.

The adapter never accepts caller-supplied build hashes, project identity,
workspace identity, physical flags, diagnostic revision, event head,
declaration ID, or verdict.

## 9. Timeout and cleanup semantics

At begin, the server clock sets `openedAtUtc`, `updatedAtUtc`, and the deadline
for `project-materialized`. Every successful stage or authorization revision
sets `updatedAtUtc` and the next action's deadline using the frozen policy.
The authorization checkpoint uses the `firmware-built-after` timeout because
it guards that next stage. Completion sets `deadlineAtUtc` to null.

A mutating operation compares the server clock to the stored deadline before
reading a new stage authority. A time strictly later than the deadline returns
`ACCEPTANCE_ATTEMPT_TIMED_OUT`; equality remains permitted. Show/resume may
derive `timedOut: true` but never append a timeout event. There is no timer,
worker, scheduler, or automatic cleanup.

The adapter owns no Probe lease, target process, transport, or temporary
resource, so it has nothing to release. Existing hardware workflow contracts
remain responsible for per-call timeout and cleanup. This slice preserves and
reruns their focused fake/in-memory regression tests, including action-digest
authorization, release-after-failure, lease successor, and cross-process
authorization one-winner behavior. No test invokes physical hardware, and no
fixture result becomes physical PASS.

## 10. Error semantics

All public failures use `OperationResult` and stable, sanitized messages:

| Code | Meaning |
|---|---|
| `ACCEPTANCE_ATTEMPT_INPUT_INVALID` | malformed or unknown-field input |
| `ACCEPTANCE_ATTEMPT_NOT_FOUND` | no valid revision 0 for the ID |
| `ACCEPTANCE_ATTEMPT_REVISION_CONFLICT` | stale expected revision or different concurrent transition |
| `ACCEPTANCE_ATTEMPT_STAGE_INVALID` | not the exact next stage or wrong reference shape |
| `ACCEPTANCE_ATTEMPT_TIMED_OUT` | deadline expired before advancement |
| `ACCEPTANCE_ATTEMPT_AUTHORIZATION_REQUIRED` | after-build attempted before the checkpoint |
| `ACCEPTANCE_ATTEMPT_ACTION_DIGEST_MISMATCH` | authorization digest does not bind current state |
| `ACCEPTANCE_ATTEMPT_OUTPUT_INVALID` | public workflow output has wrong state, freshness, lineage, or policy |
| `ACCEPTANCE_ATTEMPT_IDENTITY_MISMATCH` | current project/workspace or referenced lineage differs |
| `ACCEPTANCE_ATTEMPT_EVIDENCE_INTEGRITY_FAILED` | root, envelope, chain, or public evidence is corrupt |
| `ACCEPTANCE_ATTEMPT_CONFLICT` | attempt/revision ID denotes different immutable content |

Raw exceptions, commands, environment values, and absolute host paths never
appear in messages. Pure product failures are not deferred. Missing hardware
is a named external evidence boundary, not a software failure and not PASS.

## 11. Dependency direction and sources of truth

```text
CLI/MCP
  -> acceptance recovery adapter
       -> accepted VS08-A scenario/record readers
       -> Project model and build_project_context
       -> existing Test and Diagnostic public readers
       -> existing EvidenceStore / RootRecord
```

Lower modules never import acceptance recovery. Unique authorities are:

- project origin and logical identity: project manifest;
- current build freshness/identity: existing build context;
- replay result and physical policy: existing Test/Evidence record;
- diagnosis, revision, event head, and source declaration: DiagnosticStore;
- completed software verdict: immutable VS08-A AcceptanceRecord;
- attempt prefix and explicit checkpoint: immutable VS08-B revision chain;
- Probe lease, target timeout/cleanup, and flash authorization: existing Probe
  and hardware workflows, outside this adapter;
- physical or release qualification: later real hardware/release owner.

## 12. Verification ownership

### Slice evidence — one Luna/max implementer

- literal model/policy/digest and closed-field RED/GREEN tests;
- interrupted-process resume from each prefix, exact timeout boundaries,
  idempotent retry, orphan-envelope recovery, corruption/gap detection, and
  same-workspace concurrent one-winner tests;
- two workspace concurrent isolation and cross-workspace copy/refusal tests;
- real existing Project/Build/Test/Evidence/Diagnostic/VS08-A reader tests for
  both scenario origins, with replay fixtures explicitly nonphysical;
- explicit source-change authorization ordering/digest/single-use tests;
- CLI/MCP parity, closed schema, and project-root binding;
- GC reachability for `acceptance-attempt`;
- focused existing lease, target cleanup/timeout, flash action-digest, Test,
  Diagnostic, VS08-A, CLI/MCP, and Evidence regressions;
- Python 3.12 compileall and accepted-base `git diff --check`.

RED evidence must precede production implementation. GREEN evidence belongs
to the returned product CodeHead. Tests may use fake clocks and existing
software/fake execution seams; they may not use hardware or label replay as a
physical PASS.

### Independent acceptance — GPT-5.6-sol primary agent

- review the complete accepted-base-to-CodeHead diff in a clean detached
  worktree;
- rerun focused VS08-B and proportionate affected tests;
- independently probe chain corruption, cross-workspace rejection, timeout
  non-mutation, authorization-before-source-change, concurrent conflict, and
  the absence of lease/endpoint/transport state under attempt storage;
- verify unchanged VS08-A digests, accurate report/SDD ledger, clean local
  branch, no upstream, and no prohibited action.

No release matrix, install/package test, browser/performance gate, or hardware
campaign is triggered by this slice.

## 13. Acceptance criteria

VS08-B is `ACCEPTED` only when:

1. an interrupted attempt reloads the exact latest verified immutable prefix;
2. every transition accepts only its authoritative public output and exact
   expected revision;
3. timeout, corruption, identity drift, and mismatched outputs preserve all
   prior revisions and fail closed;
4. the source-change checkpoint is explicit, digest-bound, ordered, and
   single-use; flash remains inapplicable/delegated;
5. two workspaces are concurrently isolated and one-workspace conflicting
   writers cannot overwrite a revision;
6. a completed attempt binds the exact immutable VS08-A
   `SOFTWARE_PASSED`/replay/nonphysical record and remains queryable fresh;
7. no controller, scheduler, provider, new Evidence store, Probe backend,
   Python support expansion, or physical success surface exists;
8. required slice and affected tests pass on Python 3.12;
9. independent complete-diff review has no unresolved product defect;
10. implementation report and SDD ledger accurately distinguish software
    PASS from deferred external hardware evidence; and
11. the branch is clean, local, unpushed, and has no upstream.
