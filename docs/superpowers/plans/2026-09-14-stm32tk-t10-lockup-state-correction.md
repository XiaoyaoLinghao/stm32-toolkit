# T10 attach state-name correction

Scope: existing PyOCD adapter bug correction under the user request on 2026-09-14 to diagnose and fix bugs. This implements the already approved four-state contract, not a new state model or recovery policy. Governing specifications: 2026-08-14-stm32tk-0601-test-evidence-design.md (state domain, line 384), 2026-09-09-stm32tk-1001-complete-attach-failure-contract-design.md (lastVerifiedTargetState, line 89).

Accepted implementation base: 65607593f30b81d28604bdbee163a2d461e00ea4, clean integration branch codex/STM32TK-1001-LEGACY-HARDWARE-CLOSED-LOOP-impl. T10 software accepted base remains 4b79ad97c51a3bc62f7c57c4637489ac9d5c6da1. Runtime source 70ed9c70075445d66d9229a1420817f604843fd2 is unchanged. Primary owns scope/design/integration and independent complete-diff review; one Luna/max owns implementation/tests. No remote or deployment authority in this slice.

Observed diagnostic-03: one prepare, 4796ms, exit2, no timeout. primary resume-verify/backend-code/PROBE_BACKEND_ERROR; cleanup candidate-resume succeeded, candidate-resume-verify failed with the same code. Last state null. No action, execute or flash. Registry released and root PID27516 descendants absent. Current hardware cause remains unproven.

Confirmed offline defect: installed PyOCD Target.State exposes LOCKUP, whereas PyOCDBackend._read_target_state maps only lockedup to faulted. This can classify a supported native lockup state as unavailable. Existing fakes use strings and do not cover the actual enum. It does not establish that the board actually returned LOCKUP in diagnostic-03.

Runnable scenarios:
1. Native PyOCD Target.State.LOCKUP normalizes to the existing faulted value. OBSERVE attach still fails its running postcondition and records lastVerifiedTargetState=faulted; it never passes as running.
2. Existing running/halted/reset states and lockedup compatibility continue unchanged. Native SLEEPING, unknown values and read exceptions remain fail-closed; no sleep-as-running policy is introduced.

Only product file: tools/stm32-toolkit/src/stm32_toolkit/probe/pyocd_backend.py. Only test file: tools/stm32-toolkit/tests/test_pyocd_backend.py. Reuse existing fake and connection-policy seam. Add lockup alias to the existing mapping; preserve lockedup. Do not change public error codes, schemas, cleanup counts, connection strategy, timeouts, sleep behavior or firmware. No logging framework or wrapper changes.

Verification: one targeted RED for actual enum mapping using installed PyOCD without constructing a session/probe; GREEN for the new mapping and affected OBSERVE failure diagnostic; run the existing backend test module once as related regression. Use isolated worktree at exact base and short basetemp under D:\codex-tmp. Hardware is prohibited. Native enum importing is offline. If the existing environment lacks pytest, discover an existing test interpreter; do not install or rebuild a runtime. Preserve minimal RED/GREEN evidence, remove only verified disposable outputs.

Primary reviews complete base-to-CodeHead diff in separate clean worktree. Integrate only after accepted; no hardware verification or deployment is implied. T10, VS10-A and actual board recovery remain incomplete; historical PASS unchanged.