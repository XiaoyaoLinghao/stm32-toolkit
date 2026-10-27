# GCC delivery integration acceptance

Date: 2026-10-27. Verdict: **ACCEPTED_WITH_FIXES for the authorized offline integration scope**. This is not release, actual CubeMX generation, IDE installation or physical-hardware acceptance.

## Source and ownership

- Integration accepted-base/diff origin: `715f316e61821fc96c21a42ebefde213cfab6265`.
- Reviewed CodeHead before this report: `2d24028258c310afdfe76823e35ece48937880c8`.
- Local branch: `codex/gcc-integration`, independent final review in clean `gcc-delivery-review/STM32-Toolkit` at the exact CodeHead.
- Inputs: diagnostic/content `210ae1784571d66690a7db133cc0fd7938903103`, source-route `5db7c787d20df4ceada0c51e718fe240b92890ff`, regeneration `6139e391f9754fe7a3183c6ac6b33b6d96de3729`. The source route's M3b1 was accepted; its M3b2 guidance was explicitly still pending and is closed by this integration.
- Primary owns product specification, plans, orchestration, complete-diff reconciliation, independent review and acceptance. Local Claude Code CLI, using the unchanged configured provider/model, authored implementation, helpers, tests and guidance. No Codex implementation fallback.
- User authorized cross-branch integration, real local GCC builds and simulated flash only, and confirmed no offline STM32Cube F4 package is available. No original robot project, installed runtime, global configuration or physical probe was modified. No version change, packaging, push, tag or release action was authorized/performed.
- Plans: [integration](../../../superpowers/plans/2026-10-27-gcc-delivery-integration.md), [cache delivery correction](../../../superpowers/plans/2026-10-27-creation-cache-delivery.md), [native lock correction](../../../superpowers/plans/2026-10-27-creation-lock-initialization.md).

## Delivered behavior and review

Both product exits use independent GCC projects and the normal managed firmware route without requiring Git. Git remains optional traceability metadata; current declared inputs, model/debug target, successful build record and actual ELF/MAP determine content identity. No fake Git commit, placeholder identity, manual managed digest update or imported-firmware detour is used.

The combined Keil fixture exercises actual comment-normalizer preview/copy with declared GBK source/header encodings, complete prepared-source copying excluding `.git` directories and worktree-pointer files, scoped include merging, ARMCC startup generation, align/absolute placement expressions, explicit external SRAM capacity and multi-RAM placement, and explicit WFI normal-return intent. Original/prepared inputs remain byte-identical. Public migration PLAN/APPLY delivers a standalone output; real GCC builds it while source/prepared paths are unavailable, then builds an output-only relocated copy. ELF vectors, stack, sections, symbols and runtime literal bytes are checked.

New-project tests replace only external CubeMX generation/environment facts with a labeled synthetic adapter over the native F429 fixture. Public PLAN/PREPARE/APPLY, native parsing, managed configuration, debug/release GCC builds, activation, destination rebuild, independent output-only relocation, firmware identity and normal managed flash are real product code. The tracked native fixture stays unchanged. Real compiler evidence comes from CMake's generated compiler module, not an assumed cache variable.

Both journeys call the public hardware workflow with its default flash implementation and real lease/supervisor/client/receipt path. Only the explicitly supported test backend is replaced. Simulated memory starts empty and is populated from the exact programmed ELF's file-backed PT_LOAD segments, then read back. Tests compare build/ELF/input identities, target/probe/session, programmed/verified byte counts and released ownership. Negative checks cover authorization, source/header/model/ELF drift, pins/target mismatch and readback failure without automatic retries or imported-route fallback.

Two integration defects were corrected:

1. Creation delivered CMake caches still naming removed activation staging. `n2` recorded an actual `BUILD_CONFIGURE_FAILED` on the next ordinary build. After both successful staged builds, creation now validates and removes only its owned `CMakeCache.txt`/`CMakeFiles` under the two known presets before activation. Source, ELF/MAP/BIN/HEX, model, managed manifests, ownership and build evidence survive unchanged. Unsafe path shapes, links/reparse points or I/O failures stop with `CREATION_CACHE_PREPARATION_FAILED` before destination mutation. Unit tests verify preservation, all-candidate validation before deletion, failure boundaries and absent/empty destination handling.
2. The first use of an empty durable lock wrote a sentinel before native acquisition. An independent existing concurrency test failed at `p3`. Its public wrapper suppressed the original native cause, so no exact errno is claimed for that incident. Controlled old-source regression `l5` independently reproduces failure while a parent holds an empty native lock. The fix acquires the lock first, verifies identity/shape while held, initializes at offset zero only as owner, and unlocks only acquired locks. It preserves malformed nonempty locks and single-use authorization. Creation and regeneration consumers were rerun.

The complete integration diff was reconciled against accepted component reports and exact input commits. Automatic merges had no conflicts; overlapping context/MCP/workflow changes were independently read. All previously unaccepted M3b2 guidance and every new helper/test/guidance/product diff were independently reviewed, including the final cache and lock corrections. Since the initial integrated baseline `6c909e8a8154b271a14c6bec8e3cbd812782a77e`, the only changed product Python modules are `creation_apply.py` and `creation_authorization.py`; their direct creation/native/regeneration consumers received fresh checks. Other component evidence is retained with explicit source comparison, not described as a fresh full-repository run.

VS Code/AI guidance now distinguishes new-project creation from configure, names the actual creation PLAN/PREPARE/APPLY fields, distinguishes the project-relative creation destination from Keil's external absolute destination, binds subsequent work to the delivered root, and uses fresh normal-build pins for managed flash. It also retains explicit debug/executable configuration and complete diagnostic fields. Source-preparation documentation excludes Git metadata while preserving source/resources. Published v1.3.2 and these uninstalled source changes remain distinct.

## Verification and reproducibility

Evidence root: `D:/codex-tmp/gi27`. Each group retains exact argv/head, source hashes, real subprocess exit code, fresh JUnit and stdout, with `sourceUnchanged=true`. The native shell result may omit a numeric exit; it stays null. The bound Python subprocess record supplies the separately reported actual test exit.

The reconciled affected matrix contains **2,322 distinct passing tests and 3 platform skips**, after deduplicating JUnit `(classname,name)` and retaining latest applicable evidence. It combines source-specific runs and explicit reuse; it is not one final-head full repository matrix and does not establish release coverage thresholds. Earlier overlapping pass counts are not added again.

| Evidence | Owner | Result | Scope |
| --- | --- | --- | --- |
| `a1`, `b1`, `b2`, `c4` | Claude | 191 / 207 / 45 / 131 passed | Migration core/public/layout and encoding/ARMCC preparation |
| `c1` | Claude start; primary terminal reconciliation | 238 passed | Build/snapshot/stale/memory margin |
| `c2`, `c3`, `e1` | Claude | 207 / 24 / 229 passed | Flash/diagnostic consumers/public hardware interfaces |
| `e2` | Claude | 407 passed, 1 platform skip | CLI/configuration/VS Code generation |
| `g1`, `z2` | Claude | 155 / 34 passed | Context/IDE/debug guidance and final guide contracts |
| `l6`, `l7`, `l8` | Claude, final CodeHead | 138 passed + 1 skip / 132 passed + 1 skip / 151 passed | Creation, regeneration and creation public/native interfaces after lock fix |
| `z3` | Claude, final CodeHead | 14 passed | Both complete real-GCC / managed simulated-flash journeys |
| `p4`, `p5` | Primary, clean exact CodeHead | 138 passed + 1 skip / 14 passed | Independent creation and both complete journeys |
| Skill validation | Primary | 6 relevant skills valid | Five at reviewed guidance head, configure skill at `194e983e`; later lock-only changes leave these bytes unchanged |

`p1` (89), `a2` (122), `a3` (132+1), `b3` (151), `g2` (34), `k2` (13), `n4` (1), `f1` (136+1), `f2` (151), `p2` (14) and `z1` (14) remain component/earlier integration evidence, superseded where applicable rather than summed. `evidence-summary.json` contains exact per-case/run mapping and changed product paths; the tracked evidence summary accompanying this report records its hash.

The three skips require real symlink creation unavailable on this Windows host: regeneration destination symlink, VS Code redirect target, and linked cache entry. Deterministic reparse/shape/escape guards and other native Windows locking tests executed. Actual symlink cases remain deferred to the primary's later qualified release environment; they are not PASS. Vendor generation, installed VS Code/IDE and physical firmware behavior remain for later user-authorized validation.

Reproduce the key offline journeys using the verified development interpreter/source (no installed runtime or hardware):

```powershell
& 'D:/codex-tmp/kx23/venv/Scripts/python.exe' -X utf8 'D:/codex-tmp/gi27/run_checks.py' 'C:/Users/zhy76/.codex/worktrees/gcc-delivery-review/STM32-Toolkit' '2d24028258c310afdfe76823e35ece48937880c8' '<fresh-evidence-label>' journeys
```

The runner requires that exact clean head and a fresh evidence directory. The tracked tests are `test_prepared_gcc_delivery.py` and `test_created_gcc_delivery.py`, with `gcc_delivery_integration_helpers.py`. The development environment needs Toolkit test dependencies, ARM GCC, CMake and Ninja. This run used GCC14.3.1 from CubeCLT1.22.0, CMake4.3.1, Ninja1.13.2 and Python3.12.14. Missing real compilers fail rather than skip. CubeMX6.18.1 was found but its default firmware repository was absent; no package was downloaded or installed.

## Retained failures and delegation audit

Original results remain under the evidence root. `k0` failed fixture WFI selection; `k1` passed 11 checks but two cleanup assertions assumed the wrong lease filename. `n0`/`n1`/`n3` exposed test-side PLAN-field/compiler-record/public-result-type assumptions; these were corrected through Claude, with all actual earlier product stages retained as evidence. `n2` exposed the real creation cache defect. `p3` exposed the native concurrency issue. `l1`/`l2` initially read an empty locked file through a second handle, an invalid native test setup; they are not claimed as valid red/green evidence. Corrected `l5` on the old product source has exactly one intended failure and 48 passes; final fixed-source creation groups pass that same test. Original tests are not replaced by rerunning failures until green.

Initial `migration-integration` and `integration-guidance` runs made out-of-scope reads/searches; their audit failures remain and are not retroactively accepted. `migration-correction` was stopped after an undeclared dependency read, preserving logs and no edits; the replacement exact-file invocation stayed bounded. `creation-journey` read its allowed not-yet-created file before writing; `cache-test-review` had one ambiguous Edit failure. These are recorded separately from actual edits and test results. Primary reviewed all resulting changes and later corrections; no model/provider/permission change or implementation fallback occurred.

`regression-c` returned a structured native pending result after starting `c1`; the worker stopped and did not poll/restart/kill. The CLI also repeated `system/init` with the same PowerShell tools, which failed the launcher's strict event audit. Primary reconciled only the already-started command's terminal bound exit0/JUnit/source evidence (`c1-reconciliation.json`), without rerunning it. The proven-unexecuted remaining commands were separately dispatched. No runtime success or model claim alone is treated as test evidence.

## Remaining boundaries

This closes M3b2's complete-preparation fixture/guidance and the requested cross-branch offline GCC development integration. It does not claim universal ARMCC semantic equivalence or support for arbitrary unrecognized assembly/layouts. Real vendor-package generation, installation/VS Code interaction and physical flashing/readback are unverified. A later package/release requires its own authorization and qualification; previous release exceptions do not transfer. No release version was changed by this slice.
