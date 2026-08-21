# VS-03 Task 7A-R2 Durable Diagnostic Operation Semantics Plan

> **Implementation owner:** the existing `gpt-5.6-luna` / `max` Task 7A implementer. The
> GPT-5.6-sol primary owns this plan and independently reviews the complete diff.

**Goal:** Make every durable Target diagnostic session project failures by its stored mode and make
all four Task 7A mutations retryable after later state transitions without weakening conflicts or
revision control.

**Dispatch base:** the Sol-accepted local Task 7A-R1 head, recorded by full SHA before dispatch.

**Boundaries:** no Monitor producer schema change, adapters, hardware, packaging, Python 3.10,
release Gate, or remote operation. Host public result bytes must remain unchanged.

## Task 1: Durable mode-aware authoritative load

**Product files:**

- `tools/stm32-toolkit/src/stm32_toolkit/diagnostics/store.py`
- `tools/stm32-toolkit/src/stm32_toolkit/diagnostic_workflows.py`

**Tests:**

- `tools/stm32-toolkit/tests/test_diagnostic_store.py`
- `tools/stm32-toolkit/tests/test_fix_verification_workflows.py`
- `tools/stm32-toolkit/tests/test_diagnostic_workflows.py`

1. Write RED store tests for the bounded canonical creation-intent query and preservation of an
   Evidence provider `OSError` in the validation cause chain.
2. Write RED fresh-context public tests covering show, begin, hypothesis, declaration, plan,
   verification start, and marker attach after Target Evidence absence/corruption, provider I/O,
   or identity mismatch. Assert the stable Target outcome and zero session/root mutation. Assert
   existing Host outcomes are byte-identical.
3. Implement the store-owned mode query. Remove workflow raw event-file parsing and caller-selected
   `target_projection`; every bound load selects projection from durable creation intent.
4. Run the three focused files on CPython 3.12 and commit after GREEN.

## Task 2: Cross-state idempotency before transition checks

**Product files:**

- `tools/stm32-toolkit/src/stm32_toolkit/diagnostics/store.py`
- `tools/stm32-toolkit/src/stm32_toolkit/diagnostic_workflows.py`

**Tests:**

- `tools/stm32-toolkit/tests/test_diagnostic_store.py`
- `tools/stm32-toolkit/tests/test_fix_verification_workflows.py`

1. Write RED tests that advance through all four Task 7A mutations, then retry declaration, plan,
   verification start, and marker attach using their original operation ID, actor, request, and
   original stale revision. Require the original accepted payload plus current authoritative
   session and byte-identical event/root snapshots.
2. For every operation, reuse its ID with changed request or actor after state advances and require
   `DIAGNOSTIC_OPERATION_CONFLICT`. Use a fresh ID with stale revision and require
   `DIAGNOSTIC_REVISION_CONFLICT`; neither may mutate.
3. Implement an atomic store resolver over event type, actor, and canonical request. Each workflow
   invokes it after request normalization and bound authoritative load, but before state/preflight.
   Reconstruct retry response from the accepted event. Retain append-time lookup to close races.
4. Run focused store and fix-verification files, then the existing Task 7A four-file suite on
   CPython 3.12. Commit and report exact SHAs/diff/commands.

## Sol final acceptance

In a new detached clean worktree, review the complete accepted base
`9ff0f727f5997cf0ffd92c7272ffeb4e1153fccb` through final head, run the Task 7A four-file suite,
the affected Monitor replay/analysis tests, `git diff --check`, and one real producer-to-fresh-
diagnostic public probe. No release-level matrix or remote operation is authorized.

