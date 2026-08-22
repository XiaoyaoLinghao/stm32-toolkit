# STM32 Toolkit 0.6 VS-03 Task9 Scenario B Plan

## Ownership ledger

- Module/phase: `0600 / VS-03 / Task9`, runnable Scenario B integration slice.
- Accepted base / plan-start CodeHead: `1ca0938398cea2b3f33ec827ca1b120fdcee6199`.
- Specification owner and final reviewer: GPT-5.6-sol primary agent.
- Implementer and slice-test evidence owner: one GPT-5.6-luna agent at reasoning effort `max`.
- Active implementation branch: `codex/STM32TK-0600-VS03-SCENARIO-B`, created from the exact accepted base in a clean isolated worktree.
- Remote authority: none. No push, PR mutation, merge, close, or remote branch operation is authorized.
- Runtime: CPython 3.12 only. Python 3.10 remains frozen.

## Product behavior

Prove the complete non-physical Target replay -> diagnostic loop -> Monitor analysis -> verification
loop through public services, then discard all in-memory service objects and prove every durable
public boundary can be reloaded. The same integration slice also proves the two mandatory
fail-closed outcomes: incompatible identity produces no append/mutation, and compatible but
insufficient evidence remains inconclusive and returns the session to investigation.

This task adds integration evidence; it does not add another product feature, adapter, release
gate, physical hardware behavior, Python runtime, or report workflow.

## File boundary

- Create only `tools/stm32-toolkit/tests/test_vs03_end_to_end.py`.
- Existing product files are read-only.
- The four existing fixture files under `tools/stm32-toolkit/tests/fixtures/vs03/target/` are
  read-only by default. If a fixture contradicts the frozen public contract, stop and report the
  exact contradiction to the Sol owner; do not silently change product code or fixtures.

## Implementation sequence

### 1. Write the public-service fixture helpers

Build one temporary Project v3 workspace and use the existing `failed-before` and `fixed-after`
Target replay descriptor/stream fixtures. Helpers may remove repetition, but must call public
workflow/service APIs rather than repositories or private storage mutation. Capture the initial
project-tree digest before the first public operation.

### 2. Prove the positive Scenario B path

In one test, execute in this order:

1. publish the failed Target replay;
2. open and begin the diagnostic session, add two hypotheses, and retain their stable IDs;
3. ingest the failed Monitor replay, support one hypothesis, and refute the other;
4. declare the source change;
5. publish the fixed Target replay and ingest its Monitor replay;
6. compare the failed/fixed windows and publish the AnalysisResult and DiagnosticMarker;
7. export the deterministic analysis bundle and attach the marker;
8. add/freeze the verification plan, start verification, and complete it using the executed
   operation IDs;
9. discard all service/workflow/repository objects and reconstruct fresh contexts;
10. reload both TestRuns and replay descriptors, Monitor windows/history, AnalysisResult, marker,
    bundle, DiagnosticSession events/checkpoint/roots, and FixVerification.

Assert exact `target` and non-physical replay provenance, complete and distinct origin/import
workspace IDs at every derived public boundary, `VALID`/`COMPLETED`/changed analysis,
byte-identical bundle output, `PASSED` verification, `RESOLVED` diagnostic state, and an unchanged
project tree.

### 3. Prove the mandatory negatives without new Gates

Add two more tests in the same file:

- An incompatible project or undeclared firmware returns `INCOMPATIBLE_IDENTITY`; compare the
  session revision, event names/input digests, Evidence roots, and derived artifacts before/after
  to prove no append or mutation.
- A compatible insufficient pair retains `INVALID`/`INCONCLUSIVE`, produces an inconclusive
  FixVerification, and returns the diagnostic session to `INVESTIGATING`.

These are acceptance behaviors inside the Scenario B slice, not separate subtasks or Gates.

### 4. Slice verification and handoff

The Luna implementer runs only:

```powershell
py -3.12 -m pytest -q --basetemp=<fresh-bounded-temp> tools/stm32-toolkit/tests/test_vs03_end_to_end.py
py -3.12 -m py_compile tools/stm32-toolkit/tests/test_vs03_end_to_end.py
git diff --check 1ca0938398cea2b3f33ec827ca1b120fdcee6199..HEAD
git status --short
```

The source roots must resolve to this isolated worktree, not stale site-package `.pth` entries.
The implementer commits one test-only result and reports the full SHA and exact test count.

The Sol primary then reviews the complete accepted-base-to-candidate diff in a separate clean,
detached exact-head worktree and reruns only the Scenario B file plus directly affected adapter
contract tests if the integration test exposes an ambiguity. A genuine product defect returns to
its owning Luna implementation slice; Task9 itself must not become a repair umbrella. No release
matrix, packaging, hardware, Python 3.10, coverage, or remote action is part of Task9.
