# STM32TK-1001 Task 8 Target Recovery Profile Implementation Plan

**Goal:** Bind the existing exact under-reset recovery profile into the Target two-phase action so
the proven board can run one future guarded physical test without changing default behavior.

**Architecture:** Prepare owns the only new choice and includes an exact boolean in the existing
canonical authorization binding. Execute has no new public input; it derives either the existing
normal worker or `for_under_reset_recovery()` solely from the consumed binding. All flash,
readback, transport, publication, service, and backend behavior remains shared.

**Accepted base:** `9d51b841a150d50a4323432d4fd118c8399efa4f` (tree
`764458944b24b0a5cbdc9503346ffc0c3781d1af`).

**Specification:**
`docs/superpowers/specs/2026-09-07-stm32-toolkit-1001-task8-target-recovery-profile-design.md`.

**Implementation owner:** existing Task 8 GPT-5.6-luna/max agent.

**Reviewer:** GPT-5.6-sol primary.

**Remote/hardware authority:** none for this implementation.

## Task 1 - Commit public-contract RED

- [ ] In `test_testing_cli.py`, prove prepare defaults false, one
  `--recovery-under-reset` forwards true, duplicate/value forms are rejected, and execute has no
  recovery option.
- [ ] In `test_testing_mcp.py`, prove the registered prepare tool exposes strict optional
  `recoveryUnderReset=false`, forwards exact true, rejects strings/integers/null, and execute gains
  no independent selector.
- [ ] Commit only these RED tests before product changes.

## Task 2 - Commit workflow/safety RED

- [ ] In `test_physical_target_workflows.py`, prove prepare stores exact false/true in the prepared
  binding and recovery prepare still performs zero program calls.
- [ ] Prove default execute passes the current normal worker configuration and recovery execute
  passes exactly `for_under_reset_recovery()` with 100000 Hz and the closed under-reset policy.
- [ ] Prove missing/non-boolean binding data fails before supervisor/service/program, identity
  mismatch remains zero-program, a matching flow programs once, and no retry occurs.
- [ ] Use the existing fake Probe seams and genuine prepared/consumed authorization records; do not
  forge a physical PASS schema or weaken existing assertions.
- [ ] Commit the workflow RED separately.

## Task 3 - Implement the bounded GREEN

- [ ] Add keyword-only `recovery_under_reset: object = False` to `target_test_prepare()`. Validate
  exact `bool` before `_target_state()` or supervisor construction and include it in the canonical
  binding passed to `TargetTestRunner.prepare()`.
- [ ] In `target_test_execute()`, after loading the binding but before supervisor construction,
  require `type(binding.get("recovery_under_reset")) is bool`. Include the field in immutable-input
  validation. Derive the worker configuration from the binding: normal unchanged for false,
  existing `for_under_reset_recovery()` for true.
- [ ] Extend `_target_supervisor()` only as needed to accept a frozen worker configuration; keep
  fake seams and one-service topology intact.
- [ ] Add the duplicate-rejecting prepare-only CLI flag and forward it. Do not alter execute CLI.
- [ ] Add the prepare-only MCP strict boolean and forward it. Do not alter execute MCP.
- [ ] Do not modify worker/backend, Target runner/flash adapter, schemas, inventories, or project.
- [ ] Commit only the three allowed product files as GREEN.

## Task 4 - Proportionate verification and return

- [ ] Run the affected tests under CPython 3.12 with source/test `PYTHONPATH`,
  `-p no:cacheprovider`, `-o addopts=''`, and a short unique external basetemp:
  `test_physical_target_workflows.py`, `test_testing_cli.py`, `test_testing_mcp.py`, plus only the
  relevant public-v2 nodes if needed by the changed adapter contract.
- [ ] Run `git diff --check`, `git diff --name-only`, exact HEAD/tree/status, and review the complete
  accepted-base-to-code-head diff. Any path outside the frozen allowlist stops implementation.
- [ ] Clean or explicitly classify only the run-owned basetemp; leave campaign/runtime/project and
  hardware evidence untouched.
- [ ] Return RED/GREEN commits, exact tests, cleanup, and no-hardware/no-remote statement to Sol.

## Independent Sol review

- [ ] Create a fresh detached clean worktree at the returned code head.
- [ ] Review the complete
  `9d51b841a150d50a4323432d4fd118c8399efa4f..CODE_HEAD` diff, not a summary.
- [ ] Re-run the same focused matrix with a new short Sol-owned basetemp.
- [ ] Verify default compatibility, action-bound recovery, exact 100 kHz/under-reset derivation,
  identity-before-program, one-attempt behavior, unchanged schemas/inventory, accurate SDD, and
  clean status.
- [ ] Issue `ACCEPTED`, `REVISION_REQUIRED`, or `REWRITE_REQUIRED`. Do not run hardware or perform
  remote actions.

## Physical continuation boundary

After software acceptance, stop. The failed attempt consumed the only current guarded-flash
authorization. A future public prepare/execute retry requires one new explicit user authorization;
on that future attempt, run exactly once and stop on any failure.
