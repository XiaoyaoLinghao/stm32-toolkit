# STM32TK-1001 complete attach failure contract review

Status: **ACCEPTED**

## Ledger

- Accepted base: `776c052d43544ba599f16dde74f1264fd69cdb10`
- Approved design: `docs/superpowers/specs/2026-09-09-stm32tk-1001-complete-attach-failure-contract-design.md`
- Approved plan: `docs/superpowers/plans/2026-09-09-stm32tk-1001-complete-attach-failure-contract-plan.md`
- Implementer: GPT-5.6-luna/max
- Independent reviewer: GPT-5.6-sol
- Reviewed CodeHead: `d523516379dbd61640dbdd05a412933f14415337`
- Code tree: `ccbd2ac7579f4e9514318467e1770819fb93a0c6`
- Local branch: `codex/STM32TK-1001-LEGACY-HARDWARE-CLOSED-LOOP-impl`
- Remote action: none authorized or performed

## Result

The accepted-base-to-CodeHead diff implements the approved bounded `attachDiagnostic` contract through the pyOCD backend, worker, service, debug/flash wrappers, hardware workflows, and Monitor observation. The outer error code/message, legacy attach stage, worker deadline/abort behavior, hardware call order, success evidence format, and privacy boundary remain compatible.

Independent review returned one bounded revision round. The final code now records a still-open probe as a failed close postcondition, distinguishes explicit halt/resume postcondition failures, rejects out-of-order cleanup groups and contradictory legacy/nested stage pairs, normalizes unallowlisted Toolkit source codes, and preserves existing safe result siblings when hardware cleanup succeeds. The complete final diff has no remaining correctness, lifecycle, privacy, or scope finding.

## Evidence

The Luna implementation evidence is retained at `D:\codex-tmp\stm32tk-attach-contract-impl-20260909-evidence\implementation-return.md`. Its valid GREEN results include 131 pyOCD tests, 45 worker tests, 125 service tests, 326 wrapper tests with one existing Windows skip, and 102 unchanged STM32 Monitor forwarding tests. The correction round added focused tests and then passed 307 direct-module regression tests; the final three-node IPC test was added afterward and passed separately with no later product-byte change.

The Sol reviewer checked the complete `776c052d43544ba599f16dde74f1264fd69cdb10..d523516379dbd61640dbdd05a412933f14415337` diff in the clean detached worktree `D:\codex-tmp\stm32tk-attach-contract-review-628a99d3`. The final focused command selected 33 contract nodes across pyOCD, worker, service, supervisor, debug, flash, hardware workflows, and Monitor observation; parametrization expanded this to **66 passed in 36.10 seconds**. `git diff --check` passed and the final review worktree remained clean before this report.

The single implementation-suite skip was the pre-existing unchanged Windows-only node `tools/stm32-toolkit/tests/test_monitor_observation.py::test_real_supervisor_thread_swap_after_identity_check_writes_no_replacement_state`, whose source marker reason is `Windows directory handles deny rename`. The retained pytest output proves one skip but did not retain `-rs`, so the node/reason attribution is source-derived. This slice adds no new external verification requirement; packaging, deployment, runtime replacement, and hardware remain outside this acceptance.

## Cleanup and preserved status

The implementation cleanup request for 69 run-owned `D:\codex-tmp\stm32tk-attach-contract-*` test/cache directories was rejected before execution with `exec_command failed: CreateProcess ... rejected: blocked by policy`; it was not retried. The independent review cleanup request for the exact paths `D:\codex-tmp\stm32tk-attach-contract-review-final-basetemp` and `D:\codex-tmp\stm32tk-attach-contract-review-final-cache` used `Remove-Item -LiteralPath ... -Recurse -Force` after absolute-path containment checks and was rejected before execution with the same policy reason; it was also not retried. These cleanup failures are REPORT/ENVIRONMENT housekeeping and do not alter the passing product evidence.

Historical attempt 7 remains PASS. The later hardware failure evidence and old workspace evidence remain unchanged. The three physical observations, Task 9, Task 10, and VS10-A remain incomplete. This acceptance authorizes no claim about those gates.
