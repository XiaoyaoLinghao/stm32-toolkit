# STM32TK-1001 Task 8 Target RAM Profile Order Correction Plan

**Specification:** `docs/superpowers/specs/2026-09-07-stm32-toolkit-1001-task8-target-ram-profile-order-design.md`

**Dispatch base:** `5b2f1f5650c4166bcb64bfa6f361c8e4c080f27c`

**Implementation owner:** existing Task 8 GPT-5.6-luna/max agent

**Independent reviewer:** GPT-5.6-sol

## Boundaries

Product ownership is limited to
`tools/stm32-toolkit/src/stm32_toolkit/testing_workflows.py`. Test ownership is limited to the
smallest existing physical Target workflow test file that can exercise the production support
profile, expected to be `tools/stm32-toolkit/tests/test_physical_target_workflows.py`. The agent may
stop and report a test-design conflict, but may not widen files or behavior without a new Sol
decision.

No hardware, push, PR, merge, tag, release, remote branch, project-repository mutation, runtime
replacement, or report acceptance is authorized by this plan.

## Steps

1. Audit the dispatch base, tracked/untracked state, and the two owned files. Reproduce the exact
   four-region support-profile ordering in a focused test without editing production code.
2. Commit the RED test separately. It must call the production support-profile composition and
   existing capability preflight; asserting only a hand-built sorted list is insufficient.
3. Implement the smallest correction: sort only the private writable `{start, size}` records by
   `(start, size)` before returning the Target support profile. Do not change the project model or
   the Probe validator.
4. Run the new focused test, the complete physical Target workflow test file, and the existing
   PyOCD capability-profile tests that cover RAM ordering/overlap. Use one run-owned external
   basetemp and clean only that run's disposable output after preserving minimum failure evidence.
5. Run `git diff --check`, `git diff --name-only`, and inspect the complete dispatch-base-to-head
   diff. Stop on any product path outside the two owned files or any changed public/error behavior.
6. Commit product/tests, then return exact RED/GREEN commands, results, code head/tree, changed
   paths, failure classifications, and cleanup state. Do not write the implementation report and
   do not self-accept.
7. Sol reviews the complete accepted-base-to-code-head diff in a clean isolated worktree and runs
   only the same risk-based focused checks. A physical retry is permitted only after `ACCEPTED`.

## Required evidence

- Before/after writable RAM order for the accepted four-region model.
- Existing preflight rejects the unsorted RED input and accepts the normalized GREEN profile.
- No change to duplicate/overlap/invalid-range rejection.
- Focused test counts and durations, exact Python/runtime identity, clean diff-check, exact changed
  paths, and verified run-scoped cleanup.
