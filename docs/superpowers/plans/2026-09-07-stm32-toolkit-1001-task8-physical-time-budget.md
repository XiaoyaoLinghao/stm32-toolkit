# STM32 Toolkit 1001 Task 8 physical time-budget correction plan

**Goal:** Replace the Task 8 project's demonstrably insufficient 10-second total Target-run budget
with 60 seconds while preserving every Toolkit deadline, flash, protocol, and safety behavior.

**Architecture:** This is a project-configuration-only correction. The existing single absolute
Target deadline remains authoritative. Its existing physical flash adapter keeps the 30-second
sub-operation cap; the larger project budget supplies time for the rest of the already frozen
one-lease lifecycle.

**Accepted bases:** Toolkit `215bfe13ee556509cca907bde5a00b8132982149` (tree
`4ae441a7e2f33bd72c95c653335f0e9e98f75a14`); project
`8c4aa0a6d6787e08d1e8f656b653677772ea0c6d` (tree
`a366933972e1fd70f5bb3fce14563ad694c1b409`).

**Ownership:** GPT-5.6-sol owns this plan and independent acceptance. One GPT-5.6-luna/max owner
implements the project change. No remote or hardware action is authorized.

## Task 1 - audit and freeze evidence

- Record project HEAD/tree/status and separate the known untracked public build outputs from
  candidate changes.
- Verify the current project value is exactly 10 seconds.
- Verify the retained same-board recovery flash duration is about 14.75 seconds and the active
  Target runner uses one absolute deadline.
- Stop if any unaccounted tracked or untracked source change exists.

## Task 2 - implement the bounded project correction

- Change only `.stm32-project.json` `testing.target.timeout_seconds` from `10` to `60`.
- Use the exact active pinned runtime to validate and generate a configure dry-run.
- If the plan is clean and touches only allowed deterministic generation metadata, apply that
  exact fresh plan with the existing local authorization boundary.
- Stop if configure proposes another tracked product path.
- Commit only the allowed project files. Do not stage build outputs or historical evidence.

## Task 3 - proportionate offline verification

- Run the exact public Debug build once.
- Confirm build success, target `STM32F429ZGTx`, MAILBOX reservation/usage, no warning, and exact
  implementation-worktree ELF SHA-256 unchanged from
  `10df523425dbe8567d5876e5e790714d1314a5dd3d545e4d43a063c300fd6ead`.
- Run the committed offline verifier once and confirm the v2 fixture, case digest, MAP/ELF/mailbox,
  startup, generated inventory, CMake, and no-write checks pass.
- Project the public prepare binding through a non-hardware seam or the existing focused unit
  boundary and prove `timeout_ms=60000`. Do not access a probe.
- Run `git diff --check`, `git diff --name-only`, and final status. Clean only exact run-owned
  disposable output when policy permits; preserve minimum failure evidence.

## Task 4 - independent Sol review

- Create a fresh clean detached project worktree at the returned code head.
- Review the complete `8c4aa0a6d6787e08d1e8f656b653677772ea0c6d..CODE_HEAD` diff.
- Re-run only the public build, offline verifier, and exact timeout projection needed by the risk.
  Because a clean Debug build may embed a different absolute source path in non-loadable debug
  metadata, compare its `objcopy -O binary` load image byte-for-byte with the implementation
  build instead of requiring cross-worktree raw ELF hash equality.
- Reconcile hashes/status and issue `ACCEPTED`, `REVISION_REQUIRED`, or `REWRITE_REQUIRED`.
- Perform no hardware or remote action.

## Stop boundary

After software acceptance, update only the local SDD ledger and stop at the physical gate. The
previous recovery authorization is consumed. A future recovery prepare/execute requires a new
explicit one-attempt authorization; no automatic retry is permitted.
