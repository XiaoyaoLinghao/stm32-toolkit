# T10 D3 fault indicator with independent D4 liveness

## Approval, baseline and ownership

The user approved the proposed D4-blinking/D3-held-on fault fixture on 2026-09-14 with “开始执行吧”, and provided D:\workspace\stm32-toolkit\BSMR-MC04.PDF. This amendment supersedes only the D4 fault-injection target in scenario A2 of the 2026-08-25 legacy-keil-real-board-closed-loop design for future attempts. Historic d4-heartbeat firmware, TestRuns and acceptance identities remain unchanged.

Toolkit baseline: 28f9b8119a768c5ff0499af2852ff60b6826b9ea (local branch codex/STM32TK-1001-LEGACY-HARDWARE-CLOSED-LOOP-impl). Firmware baseline: 2bfa4bd81dc7474130e2d2c5acdad0162e15eb04, project-standard-math P3. Primary owns specification, orchestration, integration and independent review. Luna/max owns firmware implementation/tests and the separate run-local entry implementation/tests. No hardware, deployment, flash, remote or external recovery is authorized by this amendment.

## Verified electrical source

BSMR-MC04.PDF SHA256 e14a70e9e49f7ce6e0285a687f215f591bb1f53d6322f6d32a5e4052c92f1af1, page1. Visual review confirms MCU PE3 pin2 net LED0 -> D3 cathode; D3 anode -> R11 1K -> VCC3.3. D4 is LED1/PE4 pin3 via R13 1K. Both are active-low. Firmware GPO.h maps LED0=PEout(3), LED1=PEout(4). Set 0 means lit; 1 means dark. Earlier conversational shorthand that LED1=1 means lit is incorrect; historical electrical records and observed lamp reports are preserved separately.

## Scenarios and frozen behavior

1. Failed-before D3 fixture: immediately after GPO_Init and before vs10_target_init, set LED0=0. During this offline fixture preparation, explicitly restore the old P3 testtime>100 branch from LED1=1 to LED1=!LED1 and add periodic LED0=0. The resulting new D3-P3 candidate is the before-firmware for the future T10 attempt; old 2bfa4bd P3 is only its implementation baseline, never the before TestRun of that new attempt. D4 continues approximately 1.01-second toggles; D3 stays lit. Timer and the rest of the application remain unchanged. The native case ID is d3-heartbeat, with at least220 timer ticks, at least2 PE3 edges and PE3-change required over the existing2.2s terminal window; thus a running held-on fixture reports failed.
2. Fixed-after fixture: later, only after the actual T10 source-change authorization, replace the periodic LED0=0 with LED0=!LED0. Keep initial LED0=0 and D4 toggle unchanged. Same case/protocol and expected inventory, new firmware/build/input identities. D3 and D4 both toggle, d3-heartbeat passes.
3. Monitor confirmation: same30s/100ms budget and two values per batch (typed testtime + GPIOE.ODR). Require varying testtime and PE4={0,1} in BOTH roles. Failed-before requires PE3={0}; fixed-after requires PE3={0,1}. Constant testtime, constant PE4, wrong PE3 role, missing/invalid batches or nonempty nextCursor cannot pass. Offline fixture/replay never counts as physical evidence.

Non-goals: no changing Toolkit/Monitor public schemas, backends, runtime, sample period, mailbox layout, target identity, connection/recovery policies or external outputs; no editing golden source/current P3, relabeling previous evidence, or completing T10/VS10-A. No P4 physical execution or source-change checkpoint is manufactured during offline implementation.

## Identity and lifecycle

Create a new isolated firmware worktree and future session/attempt for the revised fixture; never reuse previous actions. Keep case_inventory_digest consistent with d3-heartbeat via the existing canonical digest function. Keep stm32-target-frame/2 framing/digest chain and 0x2002EFF0/4096-byte ring/4112-byte reservation unchanged. A physical TestRun, actual history, diagnostic, source-change intent and before/after bindings are still required by T10. Previous P3 source/build and wrappers remain preserved.

The source declaration helper must require exactly one periodic LED0=0 occurrence to change, preserving initial LED0=0 and LED1 toggle. Use the real future before TestRun/after Git diff/facts; no offline fixture declaration can authorize P4. The acquisition entry's configured session and all six code pins must be regenerated from actual future identities before any hardware step. This preparation does not assert READY for hardware while the attach-state failure remains unresolved.