# STM32 Toolkit 1001 Task 8 physical time-budget correction design

## Ledger

- Module/phase: `STM32TK-1001`, Task 8 physical Step 4 continuation.
- Toolkit accepted base: `215bfe13ee556509cca907bde5a00b8132982149` (tree
  `4ae441a7e2f33bd72c95c653335f0e9e98f75a14`).
- Project accepted base: `8c4aa0a6d6787e08d1e8f656b653677772ea0c6d` (tree
  `a366933972e1fd70f5bb3fce14563ad694c1b409`).
- Specification/plan owner and independent reviewer: GPT-5.6-sol primary.
- Implementation owner: one GPT-5.6-luna agent at reasoning effort `max`.
- Toolkit branch: `codex/STM32TK-1001-LEGACY-HARDWARE-CLOSED-LOOP-impl`.
- Project branch: `codex/STM32TK-1001-P1C-STANDARD-MATH-CORRECTED`.
- Remote action: none authorized.
- Hardware action: none authorized by this correction. The preceding one-shot recovery
  authorization was consumed and must not be retried.

## Trigger and classification

The accepted static recovery-prepare correction reached the real programming operation through
the exact 100 kHz SWD/connect-under-reset profile. The single authorized execute consumed its
authorization and returned `TEST_TIMEOUT` while PyOCD was still reporting programming progress.
It published no TestRun and no new flash result.

The action bound `timeout_ms=10000` from the project's
`testing.target.timeout_seconds=10`. `TargetTestRunner.run()` intentionally applies that value as
one absolute deadline over identity, flash/readback, transport execution, evidence publication,
and cleanup. The physical flash adapter also caps its own request at 30 seconds. Existing tests
protect this single-deadline fail-closed behavior.

The retained successful recovery flash for the same board/probe/profile ran from
`2026-09-03T07:31:54.854170Z` to `2026-09-03T07:32:09.604783Z`, about 14.75 seconds, before any
Task 8 target-protocol collection. Therefore the project's 10-second total budget is already
shorter than a known successful flash alone.

Classification: `PROJECT CONFIGURATION`. The Toolkit deadline contract is operating as designed;
changing it would widen public behavior without evidence. The Task 8 project introduced the
10-second value with its mailbox emitter and must instead bind a realistic total budget.

## Runnable scenarios

### Scenario 1 - frozen Toolkit semantics remain unchanged

No Toolkit product or test file changes. One absolute Target-run deadline remains authoritative,
late operations still return `TEST_TIMEOUT`, the physical flash request remains capped at 30
seconds, and consumed authorizations remain terminal.

### Scenario 2 - the Task 8 project owns enough total time

The project changes only `testing.target.timeout_seconds` from `10` to `60`. This gives the
existing flash sub-operation at most its unchanged 30-second cap and leaves up to the remaining
total budget for post-flash identity, mailbox protocol collection, evidence publication, and
cleanup. It does not change probe frequency, connect mode, retry policy, firmware logic, or the
mailbox protocol.

### Scenario 3 - project generation and firmware remain reproducible

The exact pinned runtime validates the updated project, performs a configure dry-run, and applies
only the fresh authorized plan if necessary. A public Debug build succeeds. The generated
inventory remains consistent, while the firmware load image and MAP-relevant firmware/linker
behavior remain unchanged. In the implementation worktree, where existing Debug objects are
reused, the ELF SHA-256 remains
`10df523425dbe8567d5876e5e790714d1314a5dd3d545e4d43a063c300fd6ead`. A clean detached Debug
build may encode a different absolute compilation path in non-loadable debug metadata; such a
review build must instead prove its `objcopy -O binary` load image is byte-identical to the
implementation build and pass the committed semantic verifier. The expected case inventory digest
remains
`966a489bdde16562885cc4ac3c3e2b9b9bde0b477f9c06aae25f4916be52c2b5`.

### Scenario 4 - physical continuation stays separately authorized

No probe attach, target read, reset, halt, resume, program, erase, or target execute is run while
implementing or reviewing this configuration correction. A future prepare/execute needs one new
explicit user authorization and must again execute at most once.

## Frozen change boundary

Allowed project changes are:

- `.stm32-project.json`: only `testing.target.timeout_seconds`, from `10` to `60`;
- `.stm32-toolkit/generated-files.json`: only deterministic generation metadata made stale by the
  project-model change, if the exact pinned public configure operation requires it.

No Toolkit product/test/schema/CLI/MCP/runtime source, project C source, linker script, CMake
behavior, fixture, verifier, protocol, target facts, probe selector, or hardware profile may
change. If configure proposes any additional tracked path or build changes the ELF bytes, stop and
classify the discrepancy instead of widening scope.

## Verification and acceptance

The Luna/max owner must audit tracked/untracked state, commit the bounded project change, and run
only: project validation/configure dry-run and necessary apply, public Debug build, committed
offline verifier, exact timeout projection, `git diff --check`, `git diff --name-only`, and final
status. Existing untracked build outputs are preserved as run-owned evidence and are not staged.

The Sol reviewer reviews the complete project-base-to-final-head diff in a clean detached
worktree. Acceptance requires exactly the allowed project paths, a 60-second projected binding,
successful public build/offline verification, a byte-identical firmware load image despite any
path-dependent non-loadable Debug metadata, no unresolved product/safety/scope finding, and no
hardware or remote action.

## Non-goals

- No split flash/test timeout, deadline reset, retry, fallback, arbitrary clock, second worker,
  second runtime, backend/provider/controller, schema, CLI/MCP surface, or Agent-specific logic.
- No firmware, linker, mailbox, Monitor, package, release, Python range, CI, or collaboration
  automation change.
- No hardware action, push, PR mutation, merge, tag, release, or remote branch action.
