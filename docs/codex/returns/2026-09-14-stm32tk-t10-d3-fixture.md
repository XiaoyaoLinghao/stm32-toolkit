# T10 D3 fixture: offline implementation and review

The new before-firmware holds D3 on while preserving D4 main-loop blinking. It separates the intentional T10 heartbeat failure from the visible main-loop indicator. No deployment or hardware operation occurred. T10 and VS10-A remain incomplete; the latest diagnostic-03 remains terminal-stopped.

## Ownership and identity

- Specification and plan: `2026-09-14-stm32tk-t10-d3-fixture-design.md` and `2026-09-14-stm32tk-t10-d3-fixture.md`, approved by the user's instruction to execute the D3/D4 separation; integration document commit `adf6e31c8208791d9be301a562e0ddf880dcdae6`.
- Primary: design, integration, complete-diff independent review and review evidence. Firmware implementation/tests: Luna/max `t10_target_entry`; run-local entries/tests: Luna/max `t10_d3_entries`. Neither implementer accepts its own changes.
- Firmware accepted base `2bfa4bd81dc7474130e2d2c5acdad0162e15eb04`; final CodeHead `8755ba8fd0c678f32d7d23e7d827e84317026429`, tree `754acef4c5fa32a59631d1c178fb963fec0e2880`, branch `codex/t10-d3-fixture`, worktree `D:\codex-tmp\t10-d3-fw`.
- Toolkit branch remains `codex/STM32TK-1001-LEGACY-HARDWARE-CLOSED-LOOP-impl`; no Toolkit product code changes in this fixture slice, no new PR, no remote mutation authorized or performed.

## Electrical source and behavior

User-provided `D:\workspace\stm32-toolkit\BSMR-MC04.PDF`, page 1, SHA256 `e14a70e9e49f7ce6e0285a687f215f591bb1f53d6322f6d32a5e4052c92f1af1`: D3=LED0/PE3, MCU pin 2, R11 1k to VCC3.3, active-low. D4=LED1/PE4, pin 3, also active-low. The primary visually inspected the LED and MCU circuits; existing GPO mappings agree.

Only four firmware files changed: `Main/Main.c`, `USER/VS10/vs10_target.c`, `tools/task8_offline_verify.py`, and `tools/fixtures/task8_v2_frame_fixture.json`. Initial and periodic `LED0=0` hold D3 on; periodic `LED1=!LED1` restores D4 blinking relative to the old P3 baseline. Case `d3-heartbeat` checks PE3 using unchanged timer/edge thresholds and framing. A future authorized P4 changes only the periodic LED0 assignment to `LED0=!LED0`; the initialization and D4 toggle remain.

Run-local entries preserve the existing 30-second/100ms finite lifecycle and identity guards. Both sides require changing testtime and PE4={0,1}; before requires PE3={0}, after requires PE3={0,1}. Source declaration audits all changed paths and exact byte changes. Existing DataRoot `D:\stm32tk-data\fault-controlled-20260911` is retained; future session is `vs10a-t10-d3-20260914-01`. No actual session or hardware authorization was created by the offline checks.

## Evidence and independent review

Evidence root: `D:\codex-tmp\t10-d3-20260914`.

- Primary reviewed the complete four-file firmware base-to-CodeHead diff using clean detached worktree `D:\codex-tmp\t10-d3-review`. CRLF-preserving diff check passed with `git -c core.whitespace=cr-at-eol diff --check <base> HEAD`.
- Existing offline verifier independently passed against the reviewed source and archived ELF/MAP: `firmware-review-offline.json`. It verifies source role, ELF/map/symbol mailbox reservation (0x2002EFF0, 4112 bytes, alignment 16), and five synthetic protocol frames ending in the expected failed result. This is **PASS_OFFLINE_ONLY**, not physical emitter execution or an accepted P3 TestRun.
- ELF SHA256 `52b8e8a0bf474186d2d279efc416c944737d2931e2a859740f3b0d23ed254dff`; MAP SHA256 `31e34db4caf5ddc87c342b4630f44c8df86068beb85397fe378acfdd85a40028`. Final relink preserved ELF bytes. Case inventory digest `01d858cecb035a89df1e6c6b463e0ab815b3995ec17c55a8c929510a6c2bbcd5`.
- Primary reviewed both complete original-to-final entry diffs and independently ran the bounded entry selfcheck: `entry-review-selfcheck.json`, 6 source checks and 7 Monitor cases as expected, physical evidence deferred. Existing history checks did not cover the new source-change guard and role matrix, which is why the small run-local selfcheck was added. No generic diagnosis framework was added.
- Final Monitor SHA256 `6d8b95061ff881a35fc5821436d9adc657d819392868a07ad31dd6faa73375d5`; source helper SHA256 `7297cf8ef37c77f3f5b5086e45ca2c045290412d1d5f44b09a8bb14b00e90396`; selfcheck SHA256 `8d10074237cff2e426892226e8b77e0a3add893de0d42234abb010d7f06d568d`. The last Monitor delta changes only two help/error path descriptions; reversing those strings reproduces the independently tested SHA (`entry-review-final-delta.json`), so no behavior tests were repeated.

## Final handoff gate

**ACCEPTED for offline implementation; hardware acceptance remains pending.** The implementation cleanup initially removed the working build/identity set although the archived evidence remained intact. The existing `load_fresh_firmware_facts` correctly rejected the missing identity. Restoring the archives then exposed a Git dirty-state mismatch. The same implementation owner ran one necessary existing public build to restore a coherent current build set without editing identities, timestamps or pins. No other valid behavior checks were repeated.

The primary independently called the installed runtime's `load_fresh_firmware_facts(Path(r"D:\codex-tmp\t10-d3-fw"))`: exit 0, retained in `firmware-review-fresh-facts.json` with empty stderr. Build ID `96e92552c24c1351588d44df5a97f6402b2740294366b8a49f1d879a053f71ea`, input snapshot `97b4eef84dbbbe5a1f36dae26f2dd7988ba813079b41f7eec80000bd6ac6e6bc`, CodeHead and ELF SHA match the reviewed candidate. The retained generated build directory, build lock, build-result and build log make the current worktree legitimately untracked/dirty; `gitDirty=true` matches its identity. Do not clean these required delivery artifacts before use. This resolves the artifact-retention error and proves offline build freshness, not hardware readiness or resolution of diagnostic-03.

Independent document review accepted the electrical, behavior and historical-status clauses; the final freshness paragraph records the subsequent primary check. Future execution still requires current runtime/source bindings, the unresolved attach/state-verification boundary and fresh bounded hardware authorization. It must not reuse the terminated diagnostic or previous P3 action.

Historical T9, 100ms, FullFault and attempt 7 PASS remain valid in their original scopes. No new P3/P4 TestRun, Diagnostic/FixVerification, physical LED observation or acceptance completion is claimed. Installed runtime still uses source `70ed9c70075445d66d9229a1420817f604843fd2`; the separately reviewed LOCKUP mapping correction is integrated locally but not deployed and does not prove the previous board was in LOCKUP.

All new worktrees, build outputs, rendering and evidence are under `D:\codex-tmp`. Candidate and minimum review evidence are retained for the next step; source-controlled tests and original campaign artifacts are preserved. Earlier policy-rejected cleanup remains retained and was not retried.
