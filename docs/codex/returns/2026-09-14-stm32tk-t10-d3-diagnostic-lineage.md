# D3 stored physical evidence linked to Diagnostic

The existing deployed runtime successfully created Diagnostic `2781df6812f2dc0ba067e0b1b9d07b5a` from physical TestRun `target-v2-53b0c81ffeb50ab65bd6c0ad815ad273`. The session is revision 5, `INVESTIGATING`, event head `de6d8652e9cdd89803595795028f14e0095129ccfa0f4ee29615b1f32dcfcc32`. This continuation used stored evidence only: no probe enumeration, connection, target access, programming, build or deployment.

Primary owns this evidence continuation. Integration baseline is `eb0513b4769ec50671e981f94a38dfbc954ad63b`, branch `codex/STM32TK-1001-LEGACY-HARDWARE-CLOSED-LOOP-impl`. Existing Luna firmware and accepted Toolkit implementation are unchanged. No implementation delegation or remote action occurred.

## Actual results and limits

- Public `scenario attempt resume` reports `timedOut=true`, next stage `target-failure-observed`, for old attempt `e7a18456-0eb2-4df0-bd02-d0ec2c40716e`. It was not revived or modified.
- Public `diagnose start`, `begin`, `plan add`, `plan run`, and `hypothesis add` all returned OK. Plan `2a2222301d615bf052809b25f0749ad09f82844ec41e81cca332f11c1d5d8658` reused the existing stored-run selectors with case ID adapted to `d3-heartbeat`. Both run-state and case-state observed `failed`, matching expectations. These are offline observations of the original physical evidence, not another hardware run.
- Diagnostic binds the same workspace, project, session, build, ELF, input snapshot and evidence ID recorded in the [successful recovery flash](2026-09-14-stm32tk-t10-d3-recovery-flash.md). Evidence ID remains `1a89d89a06e815c6197e273f0a88a1bb3e8253b388c83d007f8c913086c28ab0`.
- Hypothesis `06b4053634342aef290bdfa11f8cd7bb` remains open/unrated: the intentionally held-on D3 is a candidate cause. `timer-or-pe3` does not isolate the predicate; no supporting assessment was fabricated from selectors that prove only failure. The user's D3-on/D4-blinking observation remains separate visual evidence.

## Recovery basis and next boundary

The approved physical recovery contract explicitly supports checkpointing an existing failed physical Target run. Current `tools/stm32-toolkit/src/stm32_toolkit/acceptance/recovery_workflows.py:1975` validates native TestRun integrity, physical mailbox provenance and current identity/build/ELF/input binding; it does not require the run to have been produced after a new attempt began. The expired attempt itself cannot advance (`:2587`); public resume reports its timeout (`:2756`). Thus preserving the original run in a fresh chain is supported, while altering deadlines or inventing replacement run IDs is not.

No fresh timed attempt or source-change authorization was created while Monitor evidence and the exact P4 action remain pending. Prepare those inputs and the bounded implementation/build sequence first; then begin a new attempt and immediately checkpoint existing evidence through public APIs. Source-change authorization and later Target programming keep their separate boundaries.

Next proposed hardware operation is the already reviewed failed-before Monitor entry: one normal OBSERVE connection, one 30-second group at 100 ms reading `testtime` and `GPIOE.ODR`, then stop/export/release. Required functional result: varying testtime, PE3 only 0, PE4 containing both 0 and 1 in complete batches. Existing performance checks remain unchanged. It cannot resolve the older board's fault root cause. No new programming, recovery attach, fallback or retry is included. New hardware authority is pending; the preceding flash execution card explicitly excluded Monitor sampling.

Evidence root: `D:\codex-tmp\t10-d3-lineage-20260914`. Retain public JSON responses, adapted observation steps and the next-operation card. The run temp directory is empty. T10 and VS10-A remain incomplete; previous accepted evidence is preserved.
