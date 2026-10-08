# VS10-B Diagnostic deployment and SVD stop — 2026-09-18

Status: **DIAGNOSTIC_SOFTWARE_ACCEPTED_AND_DEPLOYED; FAULT_TARGET_EXPECTED_FAILURE_CONFIRMED; MONITOR_PRE_DEVICE_STOPPED; VS10-B NOT ACCEPTED**.

Later update: CFG-001 has been corrected and independently accepted offline; see [configuration repair](2026-09-18-stm32tk-vs10b-svd-configuration-fix.md). The stopped hardware outcome and old identity below remain historical evidence; this update does not resume that card.

## Baseline, ownership and retained passes

Accepted Diagnostic base: `907b17094d7d6192f68735c470ca0bb73c1c7e23`; implementation `df88a0ad7109353fee7a7bf6d42a67de0d45cb25`; integrated/deployed code head before this report: `12df4fe0569104d6f0e7a827496341d999e1f3ea`. Integration branch is `codex/STM32TK-1002-CUBEMX-REAL-BOARD-integration`. Primary owns design, independent full-diff review, integration and hardware; Luna/max owns implementation, deployment and firmware. No ownership exception or remote action.

The closed v2 fresh failed-before selector correction was independently accepted across its five existing modules and two test modules. Existing v1 behavior remains. Separate-process replay after active-source change and the real historical physical evidence reader passed offline. Neither is B hardware acceptance. Evidence: `evidence/fresh-facts-review/acceptance.json` and `independent-review.md`.

One authorized deployment completed at `D:\codex-tmp\v10b-0918\dgdep\data\runtime\0.9.0`. Package/build/install/Check and final launchers exited 0; healthy/matching. Bundle SHA256 `383adf4866e9e44b3c283aa510fa5f71370627a48e9722c674717708c21ec90d`; runtime-state SHA256 `c878c9a6e8db4ad878d0a27061a3b65e19f630b3edc2867b7aa36c62ae58fd9e`. Original907 runtime is preserved. See `evidence/diagnostic-deployment/diagnostic-package-final.json`.

NORMAL recovery physical Target PASS and actual IDE/CLI/MCP PASS were not repeated. Historical attempt7 and accepted VS10-A remain valid. User authority for this remaining card was one fault and one fixed under-reset/100kHz flash plus one 30s/100ms window per role, stopping at the first unexpected error.

## Actual B execution

Fault project is clean `822d75758f5a705fd9ef1093f3bf9d8101191570`, build `57f804184efc8cf1a7b44e11cf3f797df2cf55a670f01b0986b41391834a2e18`, ELF `dd8bd1cf4975d9302b1caf5e0139f7bc8f767e669e2e922d2d31be0c01bfb80b`, input snapshot `f752358f59c731b44561370488ea81db6fdda314cf20784a6b3bde5134fdff31`. Installed12df freshness and entry pin preflight passed. Actual ELF Reset_Handler is `0x08001AAD`; testtime is `0x20000038` (the firmware owner's return text misstated these; the original machine capture is correct).

Attempt `b10b0918-0752-4ab3-8d7a-e0e82dfe7a98` reached revision3 after project/build/failure checkpoints. One recovery action `bbda78ebb6cf1125596acf11a2c242fdbd14b3be1d467b010b856f4afc1dd51d` was consumed. Flash/readback succeeded, verified7812 bytes; physical mailbox run `target-v2-bbda78ebb6cf1125596acf11a2c242fd` contains only d3-heartbeat failed, message `timer-or-pe3`, no error/timeout/skipped result. Evidence ID `e587a965b672e2720ac96f9a82227d8d498187e4fd03e7c5a0bfdc562d704365`. This confirms the intended Target failure; it does not itself distinguish timer from D3 or replace the missing Monitor window.

The single failed-before Monitor invocation exited1 after5663ms at `probe.connect`: `MONITOR_PROVENANCE_CHANGED`, details empty. Its source/ELF/runtime pins match and gitDirty=false. It never started sampling. Runtime stopped, registry lease `lease-e87b457bb1e54f72aaba936e9988eb0b` remained released and the relevant process audit was empty. No fixed source/build, source authorization, second flash, after Monitor or retry occurred. The board's last programmed image is FAULT. The user subsequently confirmed D3 steady-on and D4 blinking; this is operator evidence, not a machine Monitor window.

Execution is stopped. Persisted attempt revision3 was ACTIVE at its last checkpoint, deadline `2026-09-18T08:09:14.268292Z`; do not relabel it a terminal accepted attempt or alter its clock. There is no B continuation. Monitor single-use marker is preserved.

## Exact cause, reproduced without hardware

Frozen deployed source root: `D:\codex-tmp\v10b-0918\dgdep\source-lf`.

| Check / source | Expected | Actual |
| --- | --- | --- |
| `tools/stm32-toolkit/src/stm32_toolkit/debug/svd.py:1041-1053`, invoked at1097 | Every parsed register interval is contained in at least one trusted readable region | 1535 of1536 intervals are outside |
| B `p/b/.stm32-project.json:105-114`, debug.readableRegions | Current only permitted interval `[0x40021014,0x40021018)`, GPIOE_ODR,4bytes | Full `svd/STM32F429.svd` first register RNG.CR is `[0x50060800,0x50060804)` |
| SVD document device vs configured svdDevice | STM32F429 | STM32F429: matches |

SVD SHA256 `2b7de1e383ee415f45339b776942fe01f7b48215316629c3cc280e12661c2400`; manifest SHA256 `37e174a4890415a5dab69c5e07dc1658b1cc2746dcb86daef2d3b3b7f67be7d3`. GPIOE.ODR is the sole in-range register.

The installed existing `_prepare` succeeded; calling existing `select_svd` reproduced `SVD_ADDRESS_OUT_OF_RANGE` at range line1050. `monitor_observation.py:1395-1415` performs this selection before supervisor construction/start at1447-1449; `_failure_code:710-712` maps SVD errors to the public provenance code. The outer Monitor `_connect_probe` in `runtime.py:1125-1148` first lists probes and resolves current firmware, then calls this observation factory. Thus enumeration DID occur; the earlier primary statement that no enumeration occurred was incorrect. Given the unchanged pinned inputs, the offline mandatory SVD failure occurs before observation lease acquisition, receipt binding, attach or target read. The original physical response did not capture the inner exception, so this phase attribution uses the deterministic offline reproduction and source order; it is not a captured physical traceback. The earlier Target operation accessed and programmed the board successfully.

Classification: **ENVIRONMENT / B project configuration incompatible with the existing product SVD contract**; independent review calls this PRODUCT/PROJECT-CONFIG BLOCKER, identifying the same invalid configuration rather than a parser defect. The process omission is that offline readiness checked pins but did not execute the SVD semantic validator before flashing. This is not evidence of a new board failure, stale receipt, probe identity mismatch or gitDirty problem. No parser or generic error-code change is justified. Independent review: `evidence/closed-loop-03/provenance-review.md`.

Exact command/stdout/traceback and field comparisons: `evidence/closed-loop-03/provenance-offline-svd.*` and `provenance-field-comparison.*`. First read-only test-show invocation included an unsupported --mode argument and was corrected using the retained prior argv; it made no hardware call or state change. An offline proposal import typo was likewise corrected, with both original errors retained.

## Minimal correction prepared; not applied

Keep the exact full vendor SVD and range guard. Proposed file scope is only B `.stm32-project.json`: replace its single debug.readableRegions entry with the12 existing trusted STM32F429 ranges already used by accepted A. A and B SVD hashes are identical. Passing those exact candidate parameters to the installed `select_svd` returned SvdSelection offline, without editing either project. Evidence: `svd-existing-ranges-proposal-validated.stdout.json`. Sampling scope stays testtime and GPIOE.ODR; no additional hardware reads are proposed.

The original Luna/max firmware owner must apply any subsequently approved configuration change and independently verify it. Necessary checks: existing select_svd on actual edited manifest, current InputSnapshot/fresh Debug build, review of the exact configuration diff and new firmware/probe evidence chain. No Toolkit package/deployment, NORMAL/IDE repetition or general test matrix is needed for this configuration-only correction. Never reuse old hashes, action digests, source intent or the consumed Monitor marker; a changed manifest requires new evidence identities and an explicitly bounded next attempt.

Before any later fault flash, readiness must invoke the existing offline SVD selector using that same active manifest, full SVD and readable ranges, in addition to existing firmware freshness/pins. A changed SVD/device/range contract triggers this check; unrelated report/naming changes do not.

All work and evidence remain under `D:\codex-tmp\v10b-0918`. Active project/runtime, accepted review trees, raw failure evidence and single-use markers are preserved. The one native PowerShell cleanup of five verified run-owned scratch roots was rejected before process creation with only `blocked by policy`; no root was deleted, no specific policy explanation was returned, and no alternative deletion was attempted. Inventory and rejection are in `scratch-cleanup-inventory.json` and `scratch-cleanup-result.json`. Reusable t/fw03 firmware capture/intent scripts are deliberately retained. No hardware retry, cleanup bypass or GitHub mutation.
