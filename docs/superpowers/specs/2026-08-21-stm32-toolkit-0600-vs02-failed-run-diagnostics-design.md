# STM32 Toolkit 0.6 VS-02 Failed TestRun Diagnostics Design

**Status:** Approved by delegated 5.6-sol design authority
**Date:** 2026-08-21
**Slice:** VS-02 — failed TestRun to diagnostic session
**Accepted base:** `41afaadce2017bf92b8852a6e9462e29e9667e79`
**Specification owner and reviewer:** primary `gpt-5.6-sol`
**Implementation owner:** one `gpt-5.6-luna` subagent with reasoning effort `max`
**Remote authority:** none

## 1. Product outcome

VS-02 turns the authoritative failed Host `TestRun` produced by VS-01 into a durable,
evidence-linked diagnostic investigation. A CLI or MCP caller can:

1. start a diagnostic session from one failed Host run;
2. begin investigation and add competing hypotheses;
3. freeze and execute a read-only observation plan over that exact run;
4. attach explicit supporting or refuting assessments to hypotheses; and
5. reload the authoritative session after the original workflow objects no longer exist.

The product records facts and explicit caller judgments. It does not infer a root cause, edit
source, control hardware, declare a fix, or resolve the session in this slice.

## 2. Scope and non-goals

Included:

- append-only `stm32-diagnostic-event/1` events and materialized `DiagnosticSession` views;
- durable cross-process session storage below `WorkspacePaths.diagnostics_root`;
- immutable Evidence checkpoints and `diagnostic-session` GC roots for every accepted revision;
- hypotheses, closed TestRun observation plans, observation results, and EvidenceAssessment;
- one shared application layer with thin CLI and MCP projections;
- a runnable Host failure-to-assessment scenario and negative corruption/identity tests.

Excluded:

- Probe v2, target state, register/memory/Fault/log observations, CONTROL or MODIFY operations;
- source change declarations, build/flash/retest, Monitor reads, FixVerification, and `RESOLVED`;
- diagnostic bundles, Skills, catalog/release changes, packaging, hardware, Python 3.10, coverage
  matrices, and VS-03+ behavior;
- a second Evidence store, test runner, Monitor database, authorization system, or source editor.

The historical 0602 module specification and plan remain useful constraints, but their larger
scope is superseded for this slice by this document and the 0.6 cross-module integration design.

## 3. Architecture decision

Three approaches were considered:

1. **Append-only DiagnosticStore plus Evidence checkpoints (selected).** Diagnostic event files
   remain the unique diagnostic decision authority. Every accepted event is also ingested as an
   immutable artifact and linked by a checkpoint Evidence envelope/root, retaining all referenced
   TestRun evidence through ordinary 0601 GC traversal.
2. **Evidence-only diagnostic state.** This avoids a new store but has no clean latest-session
   authority, conflates observations with decisions, and cannot satisfy the integration design's
   `DiagnosticStore` ownership boundary.
3. **SQLite diagnostic database.** This offers indexing but creates a second mutable database and
   duplicates Monitor persistence for a small append-only slice.

The selected design follows the old 0602 append-only intent while removing its release-scale
performance, hardware, authorization, and bundle work.

```text
CLI / MCP
   -> diagnostic_workflows
      -> TestRunRepository (authoritative failed run)
      -> DiagnosticStore (append-only event chain)
      -> EvidenceStore (event artifact/checkpoint/root)
```

No adapter reads Evidence object paths or TestRun JSON directly.

## 4. Identity and storage

`DiagnosticWorkflowContext` contains `project_root`, `data_root`, and current Toolkit
`session_id`. Project v3 and `WorkspacePaths` are the only sources of logical project ID, complete
public workspace ID, private storage key, and managed roots.

A diagnostic session preserves the complete `EvidenceIdentity` of its failed TestRun. Later calls
may use a different Toolkit session ID, but their current logical project ID and complete
workspace ID must match the diagnostic identity. No caller may supply or override an Evidence,
diagnostics, or workspace path.

Session IDs are 32 lowercase hexadecimal characters generated from 16 CSPRNG bytes. Mutation
requests carry a caller-provided `operation_id` matching
`[a-z0-9][a-z0-9._-]{0,127}`. Repeating the same operation ID and identical intent is idempotent;
reusing it with different intent fails.

For `session.created`, an operation ID is unique across the workspace because the caller does not
yet know a diagnostic session ID. For every later event it is unique only within that diagnostic
session. Intent is the canonical tuple of event type, actor, and the event payload's `request`
object. Generated IDs and captured results are not part of intent. An authoritative retry first
finds the accepted operation, compares that intent, and returns its stored result; it does not
generate a replacement session or hypothesis ID.

`DiagnosticStore.create()` and `DiagnosticStore.append()` return a frozen
`DiagnosticMutationRecord` containing exactly `session`, `event`, and `appended`. `session` is the
complete current authoritative session after recovery; `event` is the exact newly appended or
previously accepted event for that operation ID; `appended` states whether this call created the
event. This lets workflows return generated entities from the accepted event on a retry even if
the session has since advanced. `DiagnosticStore.load()` returns only the complete current
session. No mutable head or separate operation index becomes authoritative.

The managed layout is:

```text
<diagnostics_root>/
  .diagnostic.lock
  sessions/<diagnostic_session_id>/
    events/00000000.json
    events/00000001.json
    ...
```

There is no mutable authoritative `head.json`. Under the store lock, authoritative load enumerates
the closed sequential filenames, verifies every canonical event and hash link, and materializes
the last revision. A missing sequence, extra file, redirect, hard link, non-canonical JSON,
oversized event, digest mismatch, or Evidence checkpoint contradiction fails closed.

The store uses a singular verified lock file and create-new event publication. Event files are
never replaced. Limits are 10,000 events per session, 64 sessions per workspace, 256 hypotheses,
64 observation plans, 64 steps per plan, 1,024 assessments per hypothesis, 1 MiB per event, and
64 KiB UTF-8 for a statement, purpose, or rationale.

## 5. Evidence checkpoint contract

After an event file is created, the store ingests its exact bytes through the public
`EvidenceStore.ingest_file()` API as:

```text
kind = diagnostic-event
media_type = application/json
```

It then publishes one `EvidenceEnvelope`:

```text
operation = diagnostic-event
identity = failed TestRun identity
parents = previous diagnostic checkpoint first, then newly referenced Evidence IDs in
          ascending lowercase digest order with duplicates removed
artifacts = exactly the event artifact
metadata = exactly diagnostic_session_id, sequence, revision, event_digest
```

For every revision it publishes one immutable `RootRecord`:

```text
root_type = diagnostic-session
root_id = <diagnostic_session_id>.<zero-padded-eight-digit-decimal-revision>
manifest_id = checkpoint Evidence ID
metadata = exactly diagnostic_session_id, revision, state, event_digest
```

Publication is replayable. If a process stops after creating an event file, the next authoritative
open reconstructs the same artifact, envelope, and root before returning the session. A mismatch
never rewrites either side. All roots are immutable, so no existing 0601 root replacement rule is
weakened. The checkpoint chain retains the initial failed TestRun and every later referenced
Evidence envelope.

## 6. Data model and lifecycle

### 6.1 Events

`DiagnosticEvent` has exactly:

```text
schema, diagnostic_session_id, operation_id, sequence, revision_before,
event_type, occurred_at_utc, actor, previous_digest, payload, digest
```

`schema` is `stm32-diagnostic-event/1`. `actor` is `user`, `tool`, or `ai-client`.
Sequence zero has `revision_before=0` and `previous_digest=null`; event file sequence `n>0` has
`revision_before=n` and binds sequence `n-1`'s digest. After sequence `n` is accepted, the
materialized session revision is `n+1`. The digest is SHA-256 of canonical JSON
without the digest field.

VS-02 accepts only these event types:

| Event | Required state | Resulting state |
|---|---|---|
| `session.created` | none | `OPEN` |
| `investigation.started` | `OPEN` | `INVESTIGATING` |
| `hypothesis.added` | `INVESTIGATING` | unchanged |
| `observation.plan_added` | `INVESTIGATING` | unchanged |
| `observation.plan_executed` | `INVESTIGATING` | unchanged |
| `hypothesis.assessed` | `INVESTIGATING` | unchanged |

No VS-02 operation can create `FIX_PROPOSED`, `VERIFYING`, `RESOLVED`, or `ABANDONED`.

Every event payload is a closed object containing exactly `request` and `result`. Their closed
shapes are:

| Event | `request` | `result` |
|---|---|---|
| `session.created` | `failed_test_run_id` | `failed_evidence_id`, complete `identity` |
| `investigation.started` | empty object | empty object |
| `hypothesis.added` | `statement` | complete `hypothesis` |
| `observation.plan_added` | ordered `steps` | complete `observation_plan` |
| `observation.plan_executed` | `plan_id` | ordered `observation_results` |
| `hypothesis.assessed` | `hypothesis_id`, `plan_id`, `step_id`, `polarity`, `rationale` | complete `assessment` |

The reducer validates both request and result rather than trusting stored generated values. The
checkpoint's newly referenced Evidence IDs are derived, never supplied separately: the failed
Evidence ID for `session.created`, result Evidence IDs for `observation.plan_executed`, the
assessment Evidence ID for `hypothesis.assessed`, and none for other events.

### 6.2 Materialized session

The public `DiagnosticSession` view contains exactly:

```text
diagnostic_session_id, revision, state, identity, failed_test_run_id,
failed_evidence_id, event_head, hypotheses, observation_plans, observation_results
```

`state` is `OPEN` or `INVESTIGATING` in this slice. `event_head` is the last event digest.
Serialization uses fresh JSON containers and closed fields.

### 6.3 Hypotheses and assessments

A `Hypothesis` contains:

```text
hypothesis_id, statement, status, confidence_basis, supporting, refuting
```

VS-02 creates hypotheses with `status="open"` and `confidence_basis="unrated"`; changing those
summaries is deferred until a later slice needs conclusions. Hypothesis IDs are 32 lowercase hex
characters from 16 CSPRNG bytes.

An `EvidenceAssessment` contains:

```text
assessment_id, hypothesis_id, plan_id, step_id, evidence_id, selector,
observed_value, polarity, rationale
```

`polarity` is `supports` or `refutes`. The assessment is explicit caller judgment. The product
verifies that the cited executed step, evidence, selector, and observed value agree, but does not
derive polarity from prose or expected values. The same `(evidence_id, selector)` cannot appear on
both sides of one hypothesis. Assessment IDs are the SHA-256 of their canonical content.

## 7. Closed observation plan

An `ObservationPlan` contains `plan_id`, `diagnostic_session_id`, `created_revision`, `steps`, and
`digest`. `plan_id` and `digest` are the same lowercase SHA-256 over the canonical plan fields
excluding both values.

Each ordered `ObservationStep` contains:

```text
step_id, selector, expected_value, purpose
```

`step_id` matches the operation-ID safe-string grammar and is unique within the plan. Selectors
are closed JSON objects:

```json
{"kind":"run-state"}
{"kind":"case-state","case_id":"exact discovered case ID"}
{"kind":"case-count","state":"passed|failed|skipped|error|timeout"}
```

`expected_value` is a TestRun state, case state, or non-negative integer as dictated by the
selector. Plan creation authoritatively reloads the initial failed TestRun, checks its Evidence ID
and complete identity against the session, and resolves every selector before appending an event.

Plan execution reloads the same TestRun again and creates one ordered `ObservationResult` per
step with exactly:

```text
plan_id, step_id, evidence_id, selector, observed_value, expected_value, matched
```

Execution is read-only and deterministic. Any missing, corrupt, incompatible, or changed binding
fails the whole operation before `observation.plan_executed` is appended. There is no partial or
fabricated observation result.

## 8. Application and public adapters

The application layer exposes:

```text
diagnostic_start(context, operation_id, failed_test_run_id)
diagnostic_show(context, diagnostic_session_id)
diagnostic_begin(context, operation_id, diagnostic_session_id, expected_revision)
diagnostic_add_hypothesis(context, operation_id, diagnostic_session_id,
                          expected_revision, statement)
diagnostic_add_plan(context, operation_id, diagnostic_session_id,
                    expected_revision, steps)
diagnostic_run_plan(context, operation_id, diagnostic_session_id,
                    expected_revision, plan_id)
diagnostic_assess_hypothesis(context, operation_id, diagnostic_session_id,
                             expected_revision, hypothesis_id, plan_id,
                             step_id, polarity, rationale)
```

Successful mutations return the complete current session plus the newly created public entity
where applicable. `diagnostic_show` returns the complete session with `authoritative=true`.

CLI uses `diagnose start|show|begin`, `diagnose hypothesis add|assess`, and
`diagnose plan add|run`. Every mutation requires `--operation-id` and `--expected-revision` except
start. Plan add accepts one required `--steps-file` containing a closed JSON array; the adapter
reads at most 1 MiB and passes the decoded value to the application layer without domain logic.
All diagnostic leaf commands use required project/data/session context and optional `--json`.

MCP exposes seven corresponding `stm32_diagnostic_*` tools. The server supplies roots from its
bound `ServerRuntime`; tools accept no filesystem roots. Every call performs the existing MCP
client-root/capability check before one application call. Input schemas reject unknown fields and
enforce basic bounds before dispatch.

CLI and MCP serialize the same `OperationResult.to_dict()` projection and do not remap diagnostic
domain codes independently.

## 9. Failures

The stable VS-02 codes and fixed meanings are:

| Code | Meaning |
|---|---|
| `DIAGNOSTIC_NOT_FOUND` | session does not exist |
| `DIAGNOSTIC_INVALID_EVENT` | event/model/operation intent is invalid |
| `DIAGNOSTIC_INVALID_TRANSITION` | event is illegal in current state |
| `DIAGNOSTIC_REVISION_CONFLICT` | expected revision is stale or future |
| `DIAGNOSTIC_CHAIN_CORRUPT` | event/checkpoint/root chain is missing or contradictory |
| `DIAGNOSTIC_LIMIT_EXCEEDED` | a diagnostic collection or byte limit is exceeded |
| `DIAGNOSTIC_EVIDENCE_MISSING` | required TestRun evidence is absent or damaged |
| `DIAGNOSTIC_IDENTITY_MISMATCH` | project/workspace/TestRun identity is incompatible |
| `DIAGNOSTIC_PLAN_INVALID` | selector, expected value, plan, or step reference is invalid |
| `DIAGNOSTIC_OPERATION_CONFLICT` | an operation ID was reused with different intent |

Messages are fixed and details are `{}`. Typed 0601 `EVIDENCE_*`, Project, and Test errors are
projected deliberately at the application boundary; raw exception text, paths, Test messages,
stdout, and stderr are never returned.

An error before append leaves the revision unchanged. A valid event that was durably created but
whose checkpoint publication was interrupted is completed idempotently on authoritative open;
retrying the same operation returns the accepted result.

## 10. Acceptance

The runnable scenario uses the VS-01 fixture and real temporary Evidence/Diagnostic stores:

1. discover and run the exact failing Host case;
2. start a diagnostic session from the returned TestRun ID;
3. begin investigation and add two hypotheses;
4. add and execute a plan reading the failed case state and failed case count;
5. attach one supporting and one refuting assessment from exact executed steps;
6. discard all workflow/store objects and reload the authoritative session;
7. verify the event/checkpoint chains and unchanged project tree.

Negative acceptance proves:

- a passed TestRun cannot start a session;
- wrong workspace or logical project identity creates no event;
- missing/corrupt TestRun/event/checkpoint/root fails closed;
- stale revision and conflicting operation-ID reuse append nothing;
- missing case/step/hypothesis and opposite-polarity duplicate append nothing;
- CLI and MCP return the same session and error projections.

Slice verification is CPython 3.12 only: focused diagnostic tests, affected VS-01
Evidence/Test/CLI/MCP regressions, runnable scenario, and complete-diff review. Release matrices,
coverage, package builds, Python 3.10, Probe, Monitor, browser, Node, Linux, and hardware remain at
their named later layers unless this slice changes one of those shared primitives.

## 11. Historical specification disposition

Retained from the 2026-08-14 0602 design: append-only events, exact revision/hash chains,
hypotheses, explicit evidence assessments, closed observation plans, no embedded AI/source edits,
bounded collections, and fail-closed evidence identity.

Deferred to later slices: hypothesis conclusions/status changes, Probe observations and controls,
authorization, source declarations, verification, bundles, Skills, performance calibration,
candidate catalog/release work, Python 3.10, and real hardware.

Replaced for VS-02: the old monolithic 13-task implementation plan, dual-runtime/release gates per
local task, Probe schema duplication, and the requirement to complete all 0602 behavior before an
integrable diagnostic result exists.
