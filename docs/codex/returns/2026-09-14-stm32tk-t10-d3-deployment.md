# D3 candidate deployed; programming stopped at prepare

Deployment passed. The one newly authorized Target prepare failed its running-state postcondition after resume: the captured state was **faulted**. No execute, flash, readback, Monitor or P4 followed. This is a terminal stop, not a programming success or proof of a defective board. T10 and VS10-A remain incomplete.

## Scope and deployment

User authorization: "开始进行部署和烧录吧". Primary owns deployment and the sole hardware invocation; firmware and state-mapping implementation/review evidence is unchanged from the [offline D3 delivery](2026-09-14-stm32tk-t10-d3-fixture.md). No remote action occurred. Actual integration branch is `codex/STM32TK-1001-LEGACY-HARDWARE-CLOSED-LOOP-impl`; deployed source is `6250ef14035c053caa5ddc98c072c4be5b5e3650`, including the accepted `lockup -> faulted` correction.

The existing release builder ran once from clean LF checkout `D:\codex-tmp\t10-d3pkg` using the existing closed wheelhouse `D:\codex-tmp\stm32tk-1d461f23-candidate-20260909\build-wheelhouse`. Checksums and bundle verification passed. Existing setup followed Check missing → Bootstrap exit0 → Check exit0, reporting bundle=ok, runtime=healthy and runtimeState=matching. Manifest SHA256 `2c8dba3842752e359a3a1f031af6ab5cf5bd3bbdd3649618707b27b16acac763`; candidate runtime-state SHA256 `ff67f69bd877892271a2e3effc0c2b2493efea64af1050ecc1b974bb962d9702`.

Independent candidate installation is within the already retained data root:

- Install DataRoot: `D:\stm32tk-data\fault-controlled-20260911\candidates\lockup-20260914`.
- Actual runtime: that root's `runtime\0.9.0`; all invocations explicitly used its `Scripts\python.exe`.
- Business DataRoot remains `D:\stm32tk-data\fault-controlled-20260911`, preserving the shared probe registry and existing data. No session/action/lease/runtime-state was copied, and the parent runtime-state SHA stayed unchanged.

This explicit interpreter/data split uses existing CLI contracts; standard launchers deriving Python from the business DataRoot would still select the old runtime and must not be used for this candidate. The run-local Monitor entry's configuration explicitly pins the candidate runtime-state path/hash; this is an entry field, not a Monitor product CLI option. Its offline preflight passed; no sampling occurred.

All 145 installed Toolkit/Monitor package files matched the verified wheels. Final pyocd.exe reports 0.45.1. Installed `_target_state` and `load_fresh_firmware_facts` passed offline for `D:\codex-tmp\t10-d3-fw`, CodeHead `8755ba8fd0c678f32d7d23e7d827e84317026429`, build `96e92552c24c1351588d44df5a97f6402b2740294366b8a49f1d879a053f71ea`, ELF SHA256 `52b8e8a0bf474186d2d279efc416c944737d2931e2a859740f3b0d23ed254dff`. No firmware rebuild or unchanged regression matrix was run.

## Actual invocation and exact failure

New session `vs10a-t10-d3-20260914-01`, workspace `d7b137149685154d159f2f0ded85852248e4a2de1fe2813a788aa9bb54c2fd74`, new attempt `ce48d192-4876-4046-b5c0-c6144b7c9716`. Its local begin/project-materialized/firmware-built-before transitions succeeded; the last completed checkpoint is revision2. The execution ledger is terminal-stopped even if the acceptance store still represents that unfinished attempt as ACTIVE. No continuation/action is authority for a retry.

Only one normal `test target prepare --case-id d3-heartbeat` ran, through the unchanged reviewed capture entry SHA256 `e25b59830330d18ff339ccbfca414294c9b9279c9ea942f2d2bbd06c85f19de4`. It exited2 in 5,269ms, no outer timeout. Public code `TEST_EXECUTION_FAILED`; preserved exception `PROBE_ATTACH_FAILED`.

Installed `probe/pyocd_backend.py:981-988` calls resume, reads state at line983 and requires **running** at line984. The captured `attachDiagnostic.primary` is `{stage:resume-verify, reason:postcondition-failed, sourceCode:PROBE_ATTACH_FAILED}` and `lastVerifiedTargetState` is **faulted**. Expected state comes from the normal OBSERVE attach contract; actual state comes from the backend's state read, preserved in the same invocation's exception evidence. The code at lines736-749 obtains `target.get_state().name` and maps `lockup`/`lockedup` to `faulted`; the installed PyOCD enum defines `LOCKUP` at `core/target.py:50`. Raw enum/DHCSR bytes were not independently captured. The previous diagnostic-03 cannot retrospectively be relabeled as this observation.

This proves session opening/target resolution and the resume call were reached, followed by a non-running state observation. It is not a connector-not-found failure. Prepare did not complete its subsequent target-identity read at `testing_workflows.py:514`, so do not claim a fresh complete board-identity result. No action digest was produced and no firmware programming was attempted. The new D3 image therefore cannot be the cause of this particular observed state.

Cleanup's existing candidate-resume call succeeded, but candidate-resume-verify again failed its postcondition; session close, probe-open checks and worker-parent-abort succeeded. Lease `lease-f521409184b441999435d50b0c04496d` is released. PID37976, its direct descendants and relevant Python/debug consumers were absent from the final OS snapshot. Lease release does not prove target running; no post-operation LED observation has been supplied.

Classification: observed target execution-state prerequisite failure. Whether the underlying cause is the previously programmed firmware, reset state or electrical hardware remains unproven; no physical damage or flash lock diagnosis is made. The mapping correction exposed a specific state rather than silently fixing it. Further work can prepare a bounded recovery-programming contract offline; any new connection/control/recovery after this stop requires fresh authorization and cannot silently switch to under-reset or unlock.

## Evidence retention

Run root `D:\codex-tmp\t10-d3-deploy-20260914`: execution-card.md, execution-ledger.json, bundle/installation checks, installed-offline-verification.json, target-offline-preflight.json, monitor-offline-preflight.json, prepare argv/PID/exit/stdout/stderr/exceptions, attempt-after-stop.json, registry-after.json and consumers-after.json. The original runtime-state, candidate ELF and firmware identity remain byte-identical to the saved preimages.

Keep the firmware build set, clean source checkout, repair bundle/build provenance and minimum failure evidence for the next step; install temporary directory is empty. Cleanup disposition is recorded; prior policy-rejected cleanup was not retried. Historical T9, 100ms, FullFault and attempt7 PASS retain their original scopes.
