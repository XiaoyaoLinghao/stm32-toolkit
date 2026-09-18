# VS10-B offline implementation — 2026-09-18

Status: **SOFTWARE_READY; HARDWARE_PENDING**. Real CubeMX creation and customized normal/fault builds are complete. This does not accept VS10-B or authorize installation, hardware access, or remote mutation.

Accepted base: `16a6e59dff7fed2999fae611e3d936b0b04bbabd`. Integrated product code head before this report: `f9c8ff7479f96ea799f6218f1c74efb90399424d`, branch `codex/STM32TK-1002-CUBEMX-REAL-BOARD-integration`. The primary owns design, integration, independent review and acceptance. Separate Luna/max owners implemented host behavior and native creation/firmware. User approval is “开始实施”; no ownership override or B hardware/remote authority was used. Current integration and evidence roots are `D:\codex-tmp\v10b-0918\integration` and `D:\codex-tmp\v10b-0918\evidence`.

## Product behavior and review

- Host adaptation, accepted head `8d4e6fd8da398ee553cb57bb9fae6a6451a9504d`: adds `new-cubemx-physical-repair/1`, attempt `/4`, policy `/3`, origin `cubemx`, physical/mailbox. It reuses the existing persisted recovery chain and exact authorization/CAS/expiry/source-intent rules; no B continuation or new hardware controller. Initial findings about non-string input, unknown-schema dispatch and B full-chain coverage were corrected by the original owner and independently accepted. Existing tests exercise the persisted A/B chain through revision 7.
- Native discovery, accepted head `7a6dcfa97b7595a147cfc5a35cf725fa924ba39d`: fixes `CUBEMX_MCU_DESCRIPTOR_INVALID` before generation. The installed `families.xml` explicitly maps leaf `STM32F429ZGTx` to grouped descriptor `STM32F429Z(E-G)Tx.xml`. Fallback occurs only when no exact descriptor exists; index path/hash and descriptor are bound to the environment, while the exact leaf remains the native command token. Old exact-mode payload/digest are unchanged.
- Native parser, accepted head `23f6d863ec14d319f36c34a0a8a6f2b1a6d3b210`: fixes `CUBEMX_NATIVE_OUTPUT_INVALID` at native validation. Retained actual IOC bytes contain grouped `Mcu.Name`, exact `Mcu.UserName` and matching `ProjectManager.DeviceId`; the old parser rejected parentheses in Name. Only authenticated indexed-MCU mode now cross-checks group, unique leaf, request and environment. Old exact/board/ioc routes and ownership remain unchanged. The retained real project parsed without changing any of its 1460 files.

The primary reviewed complete component differences; independent reviewers accepted host and native corrections. Owner checks and targeted independent/integration checks are retained in `host/`, `firmware/native-fix/`, `firmware/parser-fix-tests/`, `native-review-checks-result.json`, `parser-primary-checks-result.json` and `integration-checks-result.json`. A public scenario/policy output remained byte-identical to the accepted runtime, SHA256 `0cb7a5435d5ea0990225f0c42a033e950231b0bda88c4b8e5ec98bc184e24d5e`. These checks do not claim physical execution. A `/2`, continuation `/3`, replay `/1`, historical attempt 7 and VS10-A acceptance are preserved.

## Real native project and firmware

Fresh public `create-plan → create-prepare → create-apply` on source `f9c8ff74` actually ran CubeMX, passed native validation and Debug/Release creation builds, and activated `D:\codex-tmp\v10b-0918\p\b`. Apply attempt: `8b39293ef934805c0575e44a`. Independent provenance audit matched request/action/environment, native IOC/linker/startup, the 1460-entry ownership manifest and eight Toolkit managed outputs. Evidence: `native-creation-review/native-creation-provenance-review.json` and `firmware/create-apply-integrated-fresh.*`.

Creation staging builds bind parent Git `13735e863f5680d8a5ff0665e6b1ad0f559008e3` with dirty state; they prove only the creation gate. Final identities below were rebuilt at the activated project root after clean, independent project commits.

| Project state | Commit | Debug ELF SHA256 |
|---|---|---|
| Native baseline | `2f4531550c56e4b1fd3c93e6de12aa542a35a66f` | Creation provenance only |
| Normal | `3a34dfdaad97d29d47f1e5405b3dedfe52318d43` | `cebe2ca983fcd186111a7e7c675c2b211e2de2a4730ad2cb4e3fd6a34ef8c7ad` |
| Controlled fault | `822d75758f5a705fd9ef1093f3bf9d8101191570` | `dd8bd1cf4975d9302b1caf5e0139f7bc8f767e669e2e922d2d31be0c01bfb80b` |

Both final versions passed public Debug and Release builds with `gitDirty=false` and no build warnings. Full build IDs, InputSnapshots, ELF/MAP hashes, commands, stdout/stderr/exits, interpreter and Toolkit source attribution are in `firmware/final-firmware-identities.json`. Final normal snapshots are `firmware/normal-odr/`; `firmware/normal/` is an earlier candidate and must not be used as the final normal image.

Only USER CODE hooks add the application to native main. HAL/SysTick supplies the 10ms testtime increment and 500ms LED interval. Normal PE3/D3 and PE4/D4 alternate; fault changes only periodic D3 toggle to write-low, leaving D4, clock, emitter and configuration unchanged. Primary review caught IDR instead of the specified ODR; commit `3a34dfd` corrects it and final builds include the correction. `proposed-fix.diff` restores only the D3 statement. Actual fixed-after source/build has not been applied; the active project stays at the fault commit until the later authorized workflow selects a state.

The original IOC, native linker, startup and ownership inventory remain unchanged. Approved project-owned `App/Linker/vs10b.ld` reserves `0x2002EFF0..0x20030000` for one 4112-byte, 16-aligned NOLOAD/KEEP mailbox and lowers ordinary RAM/stack end accordingly. The exact linker derivation is in `firmware/linker-derived.diff`. Raw project manifest SHA256 is `37e174a4890415a5dab69c5e07dc1658b1cc2746dcb86daef2d3b3b7f67be7d3`; check it alongside Git/InputSnapshot because the existing managed model hash omits testing. Do not regenerate the customized project under an assumed overlay/preservation contract.

Primary full firmware source review is in `firmware-primary-source-review.json`. Independent full native-baseline-to-fault review returned **BOUNDED_ACCEPTED** for normal/fault software, closing the ODR finding, with no other actionable finding: `firmware-review/normal-fault-review.txt`. Separate independent artifact review passed for both Debug/Release versions: `firmware-artifact-review/normal-fault-artifact-review.json` (SHA256 `892166ac1645459351ef6daa797c7d4cad463acc239738a4f4d7c4cc793b4ef0`). It re-read actual ELF/MAP and build IDs and recomputed the current fault InputSnapshot. Normal InputSnapshot provenance uses its frozen build identity/stdout/exit; it was not recomputed on the fault tree. ELF qualifications are offline facts, not proof that the board ran these images.

## Remaining execution and evidence boundary

The installed A runtime served only as an unchanged Python/dependency provider for explicit candidate source execution. No B package/install/runtime switch, probe enumeration, connection, memory read, flash, reset, Target or Monitor operation occurred. Current physical state is not inferred from prior user reports. No GitHub mutation occurred.

Installed DFP 3.1.1 maps STM32F429ZGTx; VS Code 1.129.1 and Cortex-Debug 1.12.1 are present. These read-only facts do not prove backend or IDE operation. B still needs reviewed candidate deployment, a fresh bounded hardware card/authority and current site confirmation, normal Target plus one B-native IDE handoff, real failed-before observations, Diagnostic and single-use source-change authorization, then fixed-after Target/100ms Monitor/FixVerification and bundle acceptance. The proposed fix is not an actual diagnostic result.

Current facts and retained roots are in `implementation-ledger.json`; `hardware-readiness.md` records pending gates. Original failures remain separately attributed. The early `preflight-summary.json` is historical.

Seven verified disposable native-test roots were inventoried, but automatic approval review rejected the PowerShell deletion command before execution with only `blocked by policy`. No directory was deleted or retried through another mechanism; the specific policy rule was not returned. Inventory and rejection are `native-test-cleanup-inventory.json` and `native-test-cleanup-result.json`. Later run-owned test/temp roots are retained; source worktrees, final builds and needed evidence are explicitly preserved. This cleanup refusal does not invalidate passed checks.

### Checkout representation and later freshness

Git uses `core.autocrlf=true`: raw project manifest bytes hash to `37e174...be7d3`, whereas the normalized Git LF blob has another hash; independent review confirmed equal JSON semantics and clean commits. Source/manifest/linker checkout bytes and timestamps may change when selecting the normal state later. Before any hardware operation, use the existing exact freshness check against that active root. If it no longer matches, perform a new offline build and record the new identity; never rewrite old identities, reuse staging/old-normal metadata, or bypass provenance. This does not invalidate the archived source/build qualification in its original scope.
