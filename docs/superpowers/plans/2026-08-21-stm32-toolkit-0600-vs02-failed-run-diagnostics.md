# STM32 Toolkit 0.6 VS-02 Failed TestRun Diagnostics Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use subagent-driven-development to implement this plan task-by-task. Product code and implementation tests are owned by one `gpt-5.6-luna` subagent at `max` reasoning; the primary `gpt-5.6-sol` reviews every task and the complete diff.

**Goal:** Turn one authoritative failed VS-01 Host `TestRun` into a durable, reloadable diagnostic investigation with hypotheses, read-only observations, explicit evidence assessments, and CLI/MCP access.

**Architecture:** Add a closed `stm32_toolkit.diagnostics` domain and an append-only file `DiagnosticStore`. Each accepted event is checkpointed through the existing public `EvidenceStore` and an immutable `diagnostic-session` root. A single application layer reloads the authoritative VS-01 TestRun and is projected unchanged by thin CLI and MCP adapters.

**Tech Stack:** CPython 3.12, frozen dataclasses, canonical JSON/SHA-256, existing `EvidenceStore`, `TestRunRepository`, `OperationResult`, argparse CLI, FastMCP server, pytest.

**Frozen design:** `docs/superpowers/specs/2026-08-21-stm32-toolkit-0600-vs02-failed-run-diagnostics-design.md`

**Frozen design commit:** `30b3ce9fc4648f56990a42be57bb76c036f0f4a3`

**Execution authority:** The user delegated plan approval and local execution to the primary agent. No push, PR mutation, merge, close, remote branch operation, Python 3.10 work, release matrix, hardware, Probe, or Monitor work is authorized.

## Operating rules

- Execute Tasks 1–8 in order on the same isolated feature worktree and one local branch.
- Before each task, the primary agent writes a bounded task brief containing the task text, accepted task-start SHA, allowed files, verification commands, and explicit exclusions.
- The Luna implementer follows test-driven development: add the named failing test, run it and capture the expected failure, implement only enough behavior, then run the task verification.
- The primary agent reviews the complete task-start-to-task-head diff, tests the public behavior independently, and either accepts the task or returns one bounded correction brief to the same implementer.
- Do not create nested implementation agents or recursively split a task. If a task cannot stay within its stated product boundary, stop and revise this plan or the frozen design.
- Each accepted task ends in one local commit. A documentation-only primary-agent correction is allowed only before implementation starts; product corrections remain Luna-owned.
- Use CPython 3.12 only. Run commands from the repository root with
  `$env:PYTHONPATH=(Resolve-Path 'tools/stm32-toolkit/src').Path`; existing tests load root
  `schemas/` fixtures by relative path.
- Do not run release suites, coverage, Node, browser, packaging, Linux, hardware, or Python 3.10 checks unless the changed code crosses one of the explicit risk triggers in the final section.

## Task 1: Closed diagnostic domain and event reducer

**Product behavior:** Callers can construct, serialize, parse, hash, and reduce the complete VS-02 diagnostic event vocabulary without filesystem or workflow state.

**Files:**

- Create: `tools/stm32-toolkit/src/stm32_toolkit/diagnostics/__init__.py`
- Create: `tools/stm32-toolkit/src/stm32_toolkit/diagnostics/model.py`
- Create: `tools/stm32-toolkit/src/stm32_toolkit/diagnostics/events.py`
- Create: `tools/stm32-toolkit/tests/test_diagnostic_model.py`
- Create: `tools/stm32-toolkit/tests/test_diagnostic_events.py`

**Required interfaces:**

- Frozen public values: `DiagnosticEvent`, `DiagnosticSession`, `Hypothesis`, `ObservationStep`, `ObservationPlan`, `ObservationResult`, and `EvidenceAssessment`.
- Closed `to_dict()`/`from_value()` projections with fresh JSON containers, exact-field rejection, Unicode/byte bounds, collection bounds, selector validation, ID validation, and immutable nested values.
- `canonical_diagnostic_json_bytes(value)`, `calculate_event_digest(event_without_digest)`, and `calculate_plan_digest(plan_without_ids)`.
- `create_event(...)` validates sequence/revision/previous digest and returns a fully hashed event.
- `reduce_event(session_or_none, event)` implements only the six frozen event transitions and produces a new `DiagnosticSession`.
- Define the ten stable `DIAGNOSTIC_*` codes and one typed `DiagnosticValidationError` that carries only code and fixed public message.

**TDD acceptance:**

1. First tests prove a valid `session.created` reduces to revision 1 / `OPEN`, then `investigation.started` reduces to revision 2 / `INVESTIGATING`.
2. Round trips preserve exact canonical bytes and hashes while returned dictionaries cannot mutate the model.
3. Wrong fields, IDs, selectors, bounds, event sequence/hash links, state transitions, assessment references, and plan digests fail with the specified stable code.
4. Opposite-polarity use of one `(evidence_id, selector)` for one hypothesis is rejected by the reducer.

**Verify:**

```powershell
py -3.12 -m pytest -q tools/stm32-toolkit/tests/test_diagnostic_model.py tools/stm32-toolkit/tests/test_diagnostic_events.py
```

**Commit:** `feat(diagnostics): add closed event domain`

## Task 2: Durable DiagnosticStore and Evidence checkpoints

**Product behavior:** One process can append events and a later process can authoritatively reload the same session while the event, Evidence checkpoint, and root chains remain mutually consistent.

**Files:**

- Create: `tools/stm32-toolkit/src/stm32_toolkit/diagnostics/store.py`
- Create: `tools/stm32-toolkit/tests/test_diagnostic_store.py`
- Modify only if export is required: `tools/stm32-toolkit/src/stm32_toolkit/diagnostics/__init__.py`

**Required interfaces:**

- Frozen `DiagnosticMutationRecord(session, event, appended)` with fresh closed JSON projection.
- `DiagnosticStore(diagnostics_root, evidence_store)` with `create(event)`, `append(diagnostic_session_id, event, expected_revision)`, and `load(diagnostic_session_id)`. Create/append return `DiagnosticMutationRecord`; load returns `DiagnosticSession`.
- The store derives and validates every managed path, owns one `.diagnostic.lock`, uses the repository's safe atomic/create-new primitives where public, and never follows redirects or accepts multi-link/extra files.
- Authoritative load enumerates exactly `00000000.json` onward, validates canonical bytes and the whole reducer/hash/revision chain, then verifies or idempotently finishes the matching event artifact, `diagnostic-event` envelope, and revision root.
- Each checkpoint uses the failed TestRun identity, previous checkpoint plus newly referenced evidence parents, exact metadata, and root ID `<session>.<revision:08d>`.
- Repeating an accepted identical `operation_id` returns the complete current session plus the exact accepted event with `appended=false`; different intent returns `DIAGNOSTIC_OPERATION_CONFLICT`.

**TDD acceptance:**

1. Create two events, discard both store objects, reload, and obtain the identical revision/state/head.
2. Verify exact artifact bytes, envelope parents/metadata, and two immutable roots through public Evidence APIs.
3. Simulate interruption after event creation and prove load publishes the missing checkpoint/root without rewriting the event.
4. Missing sequence, non-canonical bytes, extra file, redirect/hard-link, digest/checkpoint/root contradiction, stale/future revision, limit overflow, and operation conflict fail closed without appending another event.

**Verify:**

```powershell
py -3.12 -m pytest -q tools/stm32-toolkit/tests/test_diagnostic_model.py tools/stm32-toolkit/tests/test_diagnostic_events.py tools/stm32-toolkit/tests/test_diagnostic_store.py tools/stm32-toolkit/tests/test_evidence_store.py tools/stm32-toolkit/tests/test_evidence_gc.py
```

**Commit:** `feat(diagnostics): persist evidence-linked sessions`

## Task 3: Start, show, and begin a failed-run investigation

**Product behavior:** A caller can start a session only from an authoritative failed VS-01 Host TestRun, reload it, and transition it from `OPEN` to `INVESTIGATING`.

**Files:**

- Create: `tools/stm32-toolkit/src/stm32_toolkit/diagnostic_workflows.py`
- Create: `tools/stm32-toolkit/tests/test_diagnostic_workflows.py`
- Modify only for public exports if required: `tools/stm32-toolkit/src/stm32_toolkit/diagnostics/__init__.py`

**Required interfaces:**

- Frozen `DiagnosticWorkflowContext(project_root, data_root, session_id)` resolving Project v3 and `WorkspacePaths`; no caller-controlled store path.
- `diagnostic_start(context, operation_id, failed_test_run_id, actor="user")`.
- `diagnostic_show(context, diagnostic_session_id)`.
- `diagnostic_begin(context, operation_id, diagnostic_session_id, expected_revision, actor="user")`.
- Load TestRuns only through `TestRunRepository.load()`. Require Host scope and failed terminal run state, preserve its complete identity/evidence ID, and deliberately project lower-layer errors to the frozen diagnostic codes/messages/details `{}`.
- Success uses existing `OperationResult` and returns the complete session; show also returns `authoritative=true`.

**TDD acceptance:**

1. Use the existing VS-01 fixture/workflow to create a real failed Host TestRun, then start/show/begin it and reload revision 2 from fresh workflow objects.
2. A passed, absent, corrupt, wrong-scope, wrong-project, or wrong-workspace TestRun creates no diagnostic event.
3. A stale revision, invalid transition, or operation conflict leaves the existing session unchanged.
4. Results contain no raw paths, stdout/stderr, exception strings, or mutable internal mappings.

**Verify:**

```powershell
py -3.12 -m pytest -q tools/stm32-toolkit/tests/test_diagnostic_workflows.py tools/stm32-toolkit/tests/test_testing_workflows.py tools/stm32-toolkit/tests/test_testing_publication.py
```

**Commit:** `feat(diagnostics): start failed-run investigations`

## Task 4: Add competing hypotheses

**Product behavior:** An investigating session accepts bounded, durable hypotheses and returns them after a clean reload.

**Files:**

- Modify: `tools/stm32-toolkit/src/stm32_toolkit/diagnostic_workflows.py`
- Modify: `tools/stm32-toolkit/tests/test_diagnostic_workflows.py`

**Required interface:**

- `diagnostic_add_hypothesis(context, operation_id, diagnostic_session_id, expected_revision, statement, actor="user")`.
- Generate the hypothesis ID inside the application operation, encode it in event intent for idempotent replay, and return both the complete session and `hypothesis`.
- Require `INVESTIGATING`; enforce exact statement/collection limits; never infer status, confidence, or evidence.

**TDD acceptance:**

1. Add two distinct hypotheses, discard objects, and reload both in event order with `open`/`unrated` defaults.
2. Retry of identical intent returns the same hypothesis ID and revision.
3. Empty/oversized statement, stale revision, wrong state/session/identity, limit overflow, and conflicting operation ID append nothing.

**Verify:**

```powershell
py -3.12 -m pytest -q tools/stm32-toolkit/tests/test_diagnostic_workflows.py -k "hypothesis or start or begin"
```

**Commit:** `feat(diagnostics): record competing hypotheses`

## Task 5: Freeze and execute TestRun observation plans

**Product behavior:** A caller can freeze a closed plan over the original failed TestRun and execute it later to obtain deterministic, evidence-bound observations.

**Files:**

- Modify: `tools/stm32-toolkit/src/stm32_toolkit/diagnostic_workflows.py`
- Modify: `tools/stm32-toolkit/tests/test_diagnostic_workflows.py`

**Required interfaces:**

- `diagnostic_add_plan(context, operation_id, diagnostic_session_id, expected_revision, steps, actor="user")`.
- `diagnostic_run_plan(context, operation_id, diagnostic_session_id, expected_revision, plan_id, actor="tool")`.
- On both operations, reload the initial TestRun through `TestRunRepository`, verify exact Evidence ID and identity, and resolve only the three frozen selectors.
- Plan creation validates all selectors before append. Execution creates all ordered results or none, cites the TestRun Evidence ID, and returns both complete session and the created plan/results.

**TDD acceptance:**

1. Freeze and execute a two-step plan for the failed case state and failed case count; assert observed values, matches, order, plan digest, event revision, and checkpoint parent.
2. A missing/duplicate case, invalid selector/value, duplicate step, absent plan, repeat execution, damaged TestRun Evidence, or identity mismatch appends no partial event/result.
3. Identical operation retry returns the same plan/results while conflicting intent fails.

**Verify:**

```powershell
py -3.12 -m pytest -q tools/stm32-toolkit/tests/test_diagnostic_workflows.py -k "plan or observation"
```

**Commit:** `feat(diagnostics): execute failed-run observations`

## Task 6: Attach explicit EvidenceAssessments

**Product behavior:** A caller can bind an executed observation to one hypothesis as explicit supporting or refuting evidence and recover that assessment later.

**Files:**

- Modify: `tools/stm32-toolkit/src/stm32_toolkit/diagnostic_workflows.py`
- Modify: `tools/stm32-toolkit/tests/test_diagnostic_workflows.py`

**Required interface:**

- `diagnostic_assess_hypothesis(context, operation_id, diagnostic_session_id, expected_revision, hypothesis_id, plan_id, step_id, polarity, rationale, actor="user")`.
- Resolve the exact executed result; copy its Evidence ID, selector, and observed value; compute assessment ID from canonical content; do not derive polarity from `matched` or prose.
- Return complete session and `assessment`.

**TDD acceptance:**

1. Attach one support and one refutation to two hypotheses from exact executed steps, then reload the same canonical assessments.
2. Missing hypothesis/plan/step/result, empty/oversized rationale, invalid polarity, stale revision, and operation conflict append nothing.
3. The same evidence/selector cannot occupy both sides of one hypothesis; an exact idempotent retry remains accepted.

**Verify:**

```powershell
py -3.12 -m pytest -q tools/stm32-toolkit/tests/test_diagnostic_workflows.py -k "assess or hypothesis"
```

**Commit:** `feat(diagnostics): assess hypothesis evidence`

## Task 7: Thin CLI projection

**Product behavior:** A shell caller can complete the VS-02 investigation using stable commands and the same application result/error projections.

**Files:**

- Modify: `tools/stm32-toolkit/src/stm32_toolkit/cli.py`
- Create: `tools/stm32-toolkit/tests/test_diagnostic_cli.py`

**Required commands:**

- `diagnose start`, `diagnose show`, `diagnose begin`.
- `diagnose hypothesis add`, `diagnose hypothesis assess`.
- `diagnose plan add`, `diagnose plan run`.
- Reuse existing required testing context options and JSON output conventions. Mutation commands require operation ID and expected revision except start.
- `plan add --steps-file` accepts one regular, single-link, non-redirect file of at most 1 MiB whose JSON value is passed unchanged to the workflow.
- Parse/grammar/read errors use existing CLI usage behavior; domain failures serialize the untouched `OperationResult`.

**TDD acceptance:**

1. Drive the complete start-to-assessment scenario through `main()` with JSON output and compare each payload to direct workflow output.
2. Verify required options, unknown options/JSON fields, unsafe/oversized/malformed steps file, invalid enum/revision, and non-JSON rendering without traceback/path leakage.
3. Existing VS-01 test CLI commands remain byte-for-byte compatible at the result projection boundary.

**Verify:**

```powershell
py -3.12 -m pytest -q tools/stm32-toolkit/tests/test_diagnostic_cli.py tools/stm32-toolkit/tests/test_testing_cli.py tools/stm32-toolkit/tests/test_cli.py
```

**Commit:** `feat(cli): expose failed-run diagnostics`

## Task 8: MCP parity and runnable end-to-end scenario

**Product behavior:** An MCP client can perform the same diagnostic investigation, and one real scenario proves the VS-01-to-VS-02 chain survives complete object/process-boundary reconstruction.

**Files:**

- Modify: `tools/stm32-toolkit/src/stm32_toolkit/mcp_server.py`
- Create: `tools/stm32-toolkit/tests/test_diagnostic_mcp.py`
- Create: `tools/stm32-toolkit/tests/test_diagnostic_end_to_end.py`

**Required MCP tools:**

- `stm32_diagnostic_start`, `stm32_diagnostic_show`, `stm32_diagnostic_begin`.
- `stm32_diagnostic_hypothesis_add`, `stm32_diagnostic_hypothesis_assess`.
- `stm32_diagnostic_plan_add`, `stm32_diagnostic_plan_run`.
- Bind Project/data/session roots only from `ServerRuntime`; accept no path arguments; perform the existing client-roots/capability check once; invoke one workflow function once; return its unchanged dictionary projection.
- Register all seven tools in the server catalog with closed, bounded input schemas.

**TDD acceptance:**

1. Direct tool helpers and registered FastMCP tools match direct workflow success/error dictionaries.
2. Unknown fields, absent client roots, invalid bounds, wrong workspace, and domain failures never invoke a second workflow or leak paths/raw errors.
3. The end-to-end test creates a real VS-01 failed Host TestRun, opens/begins a session, adds two hypotheses, adds/runs two observations, adds support/refutation, discards all objects, reloads through a new context, validates every event/checkpoint/root, and proves the project tree is unchanged.

**Verify:**

```powershell
py -3.12 -m pytest -q tools/stm32-toolkit/tests/test_diagnostic_mcp.py tools/stm32-toolkit/tests/test_diagnostic_end_to_end.py tools/stm32-toolkit/tests/test_testing_mcp.py tools/stm32-toolkit/tests/test_mcp_server.py
```

**Commit:** `feat(mcp): expose diagnostic investigation`

## Final Sol review and slice verification

The primary agent reviews the entire plan-start-to-final-head diff in a clean isolated worktree. It verifies design conformance, public API closure, event/Evidence/root durability, identity handling, idempotency, adapter parity, no product-tree writes, and absence of VS-03+ scope.

Run from `tools/stm32-toolkit` on CPython 3.12:

```powershell
py -3.12 -m pytest -q `
  tools/stm32-toolkit/tests/test_diagnostic_model.py `
  tools/stm32-toolkit/tests/test_diagnostic_events.py `
  tools/stm32-toolkit/tests/test_diagnostic_store.py `
  tools/stm32-toolkit/tests/test_diagnostic_workflows.py `
  tools/stm32-toolkit/tests/test_diagnostic_cli.py `
  tools/stm32-toolkit/tests/test_diagnostic_mcp.py `
  tools/stm32-toolkit/tests/test_diagnostic_end_to_end.py `
  tools/stm32-toolkit/tests/test_testing_model.py `
  tools/stm32-toolkit/tests/test_testing_publication.py `
  tools/stm32-toolkit/tests/test_testing_workflows.py `
  tools/stm32-toolkit/tests/test_testing_cli.py `
  tools/stm32-toolkit/tests/test_testing_mcp.py `
  tools/stm32-toolkit/tests/test_evidence_model.py `
  tools/stm32-toolkit/tests/test_evidence_store.py `
  tools/stm32-toolkit/tests/test_evidence_gc.py `
  tools/stm32-toolkit/tests/test_paths.py `
  tools/stm32-toolkit/tests/test_cli.py `
  tools/stm32-toolkit/tests/test_mcp_server.py
```

Then run `git diff --check`, verify the original feature worktree is clean, and record test counts and any platform skip. Do not create VS-03 automatically.

## Risk-triggered verification escalation

Run only the named additional layer when the corresponding risk is actually introduced:

- If Evidence model/store/GC production files change, run the complete Evidence test group; otherwise the affected Evidence tests above are sufficient.
- If TestRun model/repository production files change, run the complete testing test group; otherwise the affected VS-01 tests above are sufficient.
- If shared CLI parsing or MCP runtime/catalog infrastructure changes outside diagnostic registration, run all CLI or MCP tests respectively.
- If project/path safety primitives change, run the full Project/paths/context suite and require a fresh clean-worktree review.
- If packaging metadata, runtime constraints, Node/browser code, Probe/hardware code, or platform-specific code changes, stop the slice and revise the design before running its release-level matrix.
- A report-only or test-fixture-only issue does not invalidate an unchanged product candidate; correct it and rerun only the affected layer.
