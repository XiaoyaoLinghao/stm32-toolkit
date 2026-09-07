# STM32TK-1001 Task 8 Target RAM Profile Order Correction

**Status:** frozen for approval

**Specification owner/reviewer:** GPT-5.6-sol

**Implementation owner:** existing Task 8 GPT-5.6-luna/max agent

**Full accepted base:** `5b2f1f5650c4166bcb64bfa6f361c8e4c080f27c`

**Physical reproduction project:** `C:\tmp\stm32tk-vs10a-legacy-campaign\project-standard-math` at `8c4aa0a6d6787e08d1e8f656b653677772ea0c6d`

## Problem and evidence

Task 8 P2 legitimately preserves the linker/model order `IROM1`, `IRAM1`, `MAILBOX`, `IRAM2`.
The public Target prepare path currently filters writable regions without normalizing their address
order. That produces `IRAM1`, `MAILBOX`, `IRAM2`, while the existing PyOCD capability preflight
requires RAM intervals in ascending address order. On the real STM32F429ZGTx project, public
`test target prepare` therefore returns `TEST_IDENTITY_MISMATCH` before attach even though passive
probe discovery and a separate no-programming 1 MHz SWD attach both resolve the expected
`STM32F429ZGTx` target successfully. No programming occurred.

## Runnable scenarios

1. A Project v3 model declares writable, non-overlapping RAM regions in linker order rather than
   numerical address order. The public Target support profile supplies the same regions to the
   Probe capability boundary in ascending `(start, size)` order, and prepare reaches the physical
   identity gate.
2. A model already declares writable RAM regions in ascending address order. Public prepare and
   execute retain their accepted request, identity, authorization, and transport behavior.
3. Invalid or overlapping RAM remains rejected by the existing project/schema or Probe capability
   gates. The correction must not sort away, merge, trim, or otherwise repair invalid intervals.
4. The Task 8 STM32F429ZGTx four-region model yields writable RAM in exact numerical order:
   `IRAM2` at `0x10000000`, `IRAM1` at `0x20000000`, then `MAILBOX` at `0x2002EFF0`.

## Frozen behavior

- Normalize only the private Target Probe support-profile `ram` list produced by
  `_target_support_profile()`.
- Sort the complete `{start, size}` records by `start`, with `size` as a deterministic tie-breaker.
- Do not mutate or reorder `ProjectModel.memory.regions`, the JSON manifest, linker-script order,
  build evidence, flash plans, transport configuration, or published TestRun evidence.
- Preserve all existing error codes and security validation. A duplicate start, overlap, invalid
  size, or out-of-range interval must still fail at its existing validation owner.
- Preserve the opaque probe selector and target identity rules. Human-readable probe names remain
  informational and are not added to authorization bindings.

## Non-goals

- No change to PyOCD capability validation, attach frequency, connection mode, guarded flash,
  readback, mailbox framing, Monitor, CLI/MCP surface, schema, project files, or hardware firmware.
- No new backend, adapter, controller, runtime, provider, Python range, CI, or collaboration tooling.
- No weakening of the ascending/non-overlap Probe safety gate.
- No remote action and no additional physical operation as part of implementation.

## Acceptance

- A RED test exercises the real `_target_support_profile()` composition with the accepted
  IROM1/IRAM1/MAILBOX/IRAM2 ordering and proves the pre-correction writable list is not accepted by
  the existing capability gate.
- GREEN proves the exact normalized order and that the existing capability preflight accepts it.
- Existing physical Target workflow and PyOCD backend focused suites pass.
- The complete `5b2f1f5650c4166bcb64bfa6f361c8e4c080f27c..final-code-head` diff contains only the bounded
  product/test correction plus the approved specification and plan; `git diff --check` is clean.
- The Luna implementer does not accept its own diff. Sol reviews from a clean isolated worktree
  before any further Task 8 physical prepare/execute attempt.
