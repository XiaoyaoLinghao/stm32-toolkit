# STM32TK-1001 VS10-A Software/Hardware Handoff Status

**Checkpoint date:** 2026-08-27

**Overall status:** `SOFTWARE_COMPLETE_HARDWARE_PENDING`

**VS10-A acceptance:** not yet accepted; the non-skippable physical scenarios
remain open.

## Ledger

- Module and phase: `STM32TK-1001-LEGACY-KEIL-REAL-BOARD-CLOSED-LOOP`, VS10-A,
  H2 stopped before target attachment and programming.
- Full accepted base: `9b7839bb01f88a9e3d2c13203f38aa0d11647232`.
- Specification owner and independent acceptor: GPT-5.6-sol primary agent.
- Product/test implementer: one GPT-5.6-luna agent at reasoning effort `max`.
- Implementation branch:
  `codex/STM32TK-1001-LEGACY-HARDWARE-CLOSED-LOOP-impl`.
- H2 build-to-flash product code head:
  `568f5028e279a393094c95f44403a4d03b28dcfd`.
- H2 implementation report head:
  `18959cc37b181633f550060f1685071c35a3a764`.
- Remote action authorized for this checkpoint: push this branch only. No PR,
  merge, tag, release, close, or remote-branch deletion is authorized.

## Accepted software checkpoint

The primary Sol verdict for the bounded H2 build-to-flash product correction is
`ACCEPTED`.

- Complete review range:
  `8149273677716840406987e342da1ccbd62969d3..568f5028e279a393094c95f44403a4d03b28dcfd`.
- The complete range contains only the approved specification and plan,
  `tools/stm32-toolkit/tests/test_flash.py`, and
  `tools/stm32-toolkit/src/stm32_toolkit/probe/flash.py`.
- RED is test-only at `689a20c779d36c337a8c72f363dcc71b372b84ca`;
  GREEN is product-only at
  `568f5028e279a393094c95f44403a4d03b28dcfd`.
- Independent complete-diff review found no unresolved product, security,
  compatibility, scope, or coverage defect.
- Fresh CPython 3.12 focused verification on the final product bytes ran
  `test_flash.py`, `test_build_runner.py`, and `test_debug_read.py`: all 137
  collected tests completed at `[100%]`, process exit `0`.
- `git diff --check` for the complete H2 review range exited `0`.
- The run-owned verification basetemp was resolved, inspected, and removed;
  it is absent after cleanup.

This verdict accepts only the software correction. It does not claim a target
attach, programming, readback, D4 observation, physical TestRun, Monitor
observation, handoff, diagnostic verification, or VS10-A acceptance.

## Current runnable outcome

The accepted software path now provides the exact public behavior needed to
resume H2:

- one CPython 3.12 Agent-neutral 0.9.0 runtime is installed from source head
  `568f5028e279a393094c95f44403a4d03b28dcfd`;
- the migrated STM32F429ZG project has a reproducible `arm-debug` build and
  firmware identity;
- genuine public build evidence is accepted by the guarded flash consumer
  without rewriting the build result or firmware identity;
- malformed, stale, cross-dialect, path-conflicting, and target-mismatched
  evidence remains fail-closed before programming; and
- wrong connected-target identity permits only the required initial attach and
  performs zero programming or readback.

There is no remaining evidence-based product-code change to make before the
physical transport becomes available. A future hardware failure must first be
classified from its own evidence before any product modification.

## Physical evidence and stop reason

The current exact CMSIS-DAP probe enumerated successfully, but target-level
communication did not reach an identity match:

- three public guarded-flash attempts returned `PROBE_ATTACH_FAILED`; none
  entered programming or readback;
- one 100 kHz SWD under-reset diagnostic returned `No ACK`;
- one 100 kHz default-chain JTAG diagnostic returned `WAIT ACK`;
- one 100 kHz JTAG diagnostic with the historically observed explicit IR
  lengths `[4, 5]` also returned `WAIT ACK`; and
- no `flash-result.json` was created and no debugger process remained.

Classification: `HARDWARE_OR_PROBE_COMPATIBILITY`. The explicit `[4, 5]` result
shows that the default IR-length hypothesis alone does not explain the current
CMSIS-DAP failure. These failed attempts are not physical PASS evidence and do
not justify a Toolkit code change.

## Resume boundary when J-Link is available

Resume without redesign and in this order:

1. enumerate and bind the exact replacement J-Link;
2. perform a low-speed read-only attach and verify STM32F429ZG identity;
3. only after identity match, run one separately authorized guarded flash with
   the frozen build ID, ELF SHA-256, project, runtime, and Probe pins;
4. complete H2 D4, `testtime`, PE4 ODR, Fault, and Monitor observations;
5. complete H3 physical Target test and Cortex-Debug handoff/reacquire; and
6. complete H4 physical failure, diagnosis, authorized fix, rebuild/reflash,
   and fixed-after verification.

Until those physical gates pass, the roadmap's 1.0.0 acceptance checkbox stays
open. The final implementation report and SDD ledger must later reconcile the
unchanged software heads with the J-Link evidence, project P0-P4 lineage,
cleanup, and final local/remote state.

## GitHub publication boundary

Immediately before this status change, remote `master` and the full accepted
base were both `9b7839bb01f88a9e3d2c13203f38aa0d11647232`; the VS10-A implementation
branch did not yet exist on the remote. This checkpoint authorizes publishing
the named implementation branch while preserving the worktree for later J-Link
evidence. It does not authorize a PR or any integration/release operation.
