# STM32 Toolkit 0.6 VS04-B2 Implementation Plan

## Ledger and outcome

- Accepted base: `2b8b5b166c04c59d3f0f8bf326204ac74264620e`.
- Specification: `docs/superpowers/specs/2026-08-22-stm32-toolkit-0600-vs04b2-physical-diagnostic-verification.md`.
- Specification/plan owner and reviewer: GPT-5.6-sol primary.
- Implementer: one GPT-5.6-luna agent at reasoning effort `max`.
- Python: CPython 3.12 only.
- Remote/hardware authority: none.

The slice is complete only when the same public path consumes two physical B1 records, produces a
changed Analysis/marker/bundle, completes PASSED FixVerification, resolves Diagnostics, and reloads
the complete physical graph from fresh objects. This is one vertical slice with sequential
implementation checkpoints, not independent microtasks or parallel product writers.

## File boundary

Permitted production files:

- `tools/stm32-toolkit/src/stm32_toolkit/execution_provenance.py`;
- `tools/stm32-toolkit/src/stm32_toolkit/monitor_replay_contract.py`;
- `tools/stm32-monitor/src/stm32_monitor/replay.py`;
- `tools/stm32-monitor/src/stm32_monitor/analysis.py`;
- `tools/stm32-monitor/src/stm32_monitor/analysis_workflows.py`;
- `tools/stm32-toolkit/src/stm32_toolkit/diagnostic_workflows.py`;
- `tools/stm32-toolkit/src/stm32_toolkit/cli.py`;
- `tools/stm32-toolkit/src/stm32_toolkit/mcp_server.py`.

Modify focused existing tests and create at most one physical Analysis workflow test and one B2
end-to-end test. Do not edit Diagnostic/FixVerification models, events/store, Testing publication,
History, EvidenceStore/GC, Probe/hardware/authorization, Monitor runtime/service/sampler/UI,
packaging, or release files.

## Checkpoint 1: freeze the source-record authority

Start with RED shared-contract tests for closed physical transcript fields, physical budgets,
canonical bytes, linked TestRun ID, binding/batch chain, source/flag, and replay compatibility.
Tighten only physical hardware-label rejection in `validate_execution_provenance`.

Factor Monitor's authenticated physical loader into an immutable internal result containing the
stored v2 ref, source Evidence, batches, linked TestRun ID, and reloaded physical TestRun. Keep
`load_monitor_run_reference` unchanged externally. Prove its result uses no History or raw selector
and rejects source/TestRun contradictions.

Checkpoint evidence: shared contract tests, B1 physical publication/fresh-load tests, exact v1
contract bytes, changed-source compilation and diff check.

## Checkpoint 2: make Analysis and bundle source-discriminated

Add RED pure-model tests accepting exact physical v2 pairs and rejecting subclasses, mixed union
members, source/flag drift, selector drift, and undeclared firmware changes. Generalize exact type
checks without changing `/1` payload schemas or v1 serialization.

Add one production-shaped physical workflow test that publishes two real physical TestRuns,
History windows, and B1 references, then discards all objects. Forbid `HistoryStore.query_history`
during compare. Fresh compare must use immutable transcript batches and publish physical Analysis
and marker metadata with the accepted parents.

Generalize bundle validation to reload exact transcript-linked physical TestRuns, case/inventory
scope, per-run hardware provenance, and declaration bridge. Export twice and require byte identity,
v2 refs, physical metadata, exact parents, and no raw selector. Keep replay branches and bytes
unchanged.

Checkpoint evidence: physical Analysis/bundle tests, pure Analysis tests, replay Analysis/bundle
tests, Monitor CLI one-call/parity tests, no-History assertion, raw-selector scan, compilation and
diff check.

## Checkpoint 3: generalize Target Diagnostics without schema changes

Add RED workflow tests starting a Target diagnostic from a failed physical TestRun, then reloading
the bound session. Generalize Target authority as an exact replay/physical branch; never infer the
source from names or workspace inequality.

Use the shared physical transcript validator in Toolkit's independent Monitor authority reader.
Make Analysis/marker validation copy and compare the source/flag selected by the session's failed
TestRun. Require the fixed TestRun IDs to match transcript links before plan/marker/completion
mutation. Preserve FixVerification/event/store schemas and state transitions.

Add CLI/MCP `failed-run-mode` projection with default Host and one workflow call. No adapter accepts
an execution-source or physical boolean.

Checkpoint evidence: physical target diagnostic workflow/completion tests, Toolkit CLI/MCP tests,
VS03 replay target tests, VS02 Host tests, compilation and diff check.

## Checkpoint 4: one complete fresh-reload scenario

Build one B2 end-to-end test through public product services:

1. physical failed TestRun and B1 failed reference;
2. diagnostic start/begin/hypotheses;
3. declaration plus physical passed TestRun and B1 fixed reference;
4. physical compare, marker, and deterministic bundle;
5. verification plan/start/marker attach/complete;
6. fresh reload of TestRuns, refs/source records, Analysis, marker, bundle, session, and
   FixVerification.

Assert `VALID/COMPLETED/changed`, `PASSED/VERIFICATION_PASSED`, `RESOLVED`, exact physical
source/flag at every Evidence boundary, byte-identical bundle retry, and no History access during
physical compare. Use fake capture seams only; no Probe or hardware calls.

Add compact parameterized negatives for mixed replay/physical, wrong linked physical TestRun,
selector/firmware drift, corrupt transcript/reference, provider failure, and insufficient pairs.
Each asserts the frozen error/result and zero affected derived roots/events. Do not create a release
matrix.

## Slice verification and return

Run with short Windows basetemps:

- new B2 physical Analysis and end-to-end tests;
- changed shared contract/B1 loader tests;
- directly affected Analysis/bundle/CLI tests;
- physical and replay Target diagnostic/FixVerification workflow tests;
- Toolkit diagnostic CLI/MCP tests;
- accepted VS03 Scenario B E2E and focused Host diagnostic regression;
- `py_compile` for changed source files;
- `git diff --check` from the documentation head;
- clean status and scope/raw-selector scan.

Do not run full release, coverage, packaging, Python 3.10, UI/Node/browser, platform, Probe, or
hardware matrices. Commit locally in logical checkpoint commits or one final commit; do not push or
mutate a PR. Return full commit SHAs, exact test totals/commands, changed files, deferred items, and
clean status. The Sol primary reviews the complete documentation-head-to-final-head diff in a fresh
detached worktree and issues the only acceptance verdict.
