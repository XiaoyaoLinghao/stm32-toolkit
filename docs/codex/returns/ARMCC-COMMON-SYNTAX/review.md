# ARMCC-COMMON-SYNTAX independent review

2026-10-24 verdict: **ACCEPTED_WITH_FIXES**, for the bounded offline source slice.

Accepted base `07f5e1b7720f885f0e005935256ec9466e0af261` (accepted include-only slice); final CodeHead `d298757a36a8b106d02a5f133bdab51e87db1373`; branch `codex/armcc-common-syntax`. Primary Codex owns the specification, plan, orchestration, complete-diff review and acceptance. Local Claude Code CLI using the existing `deepseek-v4.1-flash[1m]` configuration authored all product, test, skill and user-guide changes. No ownership exception, PR or remote action is authorized by this verdict.

Governing [design](../../../superpowers/specs/2026-10-24-armcc-common-syntax-design.md) and [plan](../../../superpowers/plans/2026-10-24-armcc-common-syntax-plan.md). Independent review used clean `build-snapshot-final/STM32-Toolkit` at the exact CodeHead. Full binary diff SHA-256 `7333323caece52bae7233e05f63b2b79a275a8af3a77f561743eecea43a0e9b4`, retained at `D:/codex-tmp/ac24/reviewed.diff`; exact commands, JUnit counts, source identities and native tool events are in [evidence.json](evidence.json).

## Accepted behavior and review

The included C-source rules recognize four precise `__asm void` wrappers ending in BX LR/R14. They emit GNU naked basic asm, including the MSP setter, avoiding a C stack-switch wrapper. Unknown instructions, prototypes, storage forms and missing returns remain blocked. Bounded object alignment and absolute placements compose only when an explicitly requested alignment divides the resolved fixed address. The original array expression is preserved; no arbitrary typedef natural alignment is inferred.

Constant resolution is a bounded token evaluator, without eval/exec, with textual macro expansion preserving C operator precedence. It supports explicit target integer definitions and contained quoted header chains, structural guards and dependency hashes. Conditional, redefined, undefined, function-like, unavailable or cyclic definitions, redirects/escapes and budget exhaustion remain diagnostics. Literal-only rules do not read unnecessary headers. Ignored dependency changes and newly shadowing headers fail input revalidation or fresh apply planning before writes. This is a deliberately restricted subset, not a full C preprocessor.

Only the exact standalone no-semihosting pragma is removed (C and C++); a retained trailing comment and newline survive. Its proposal explicitly adds bounded `build.newlibSpecs=["nosys.specs"]`. Managed templates emit it once without implicit nano; native defaults remain unchanged. Nonempty specs participate in the managed model identity, while missing/empty specs preserve historical output and identity. Root/packaged schemas and CMake templates match byte-for-byte. No-semihosting conversion does not provide I/O stubs or prove runtime equivalence.

Preflight remains Git-free/read-only and exposes additive proposed `analysis.sourceChanges` with exact rule IDs and hashes. PLAN keeps complete patches and its snake_case fields; Git, explicit authorization, drift protection and transactional APPLY guards remain intact. The guide and skill distinguish these response shapes and supported versus unsupported constructs. A fixed address outside every declared region is a `needs-user-input` blocker; no external SRAM size or region is invented.

The preceding accepted include-only behavior is retained and rerun in this slice: contained group/file directories append in order, dedupe and bind inventories; unsupported scoped defines/misc/assembly semantics remain blockers. Neither source conversion nor additive includes prove general preprocessing, ARMCC ABI, Microlib or board behavior equivalence.

## Findings closed

| Path | Observed problem and correction | Verification |
| --- | --- | --- |
| `migration/rules.py` | A known alignment could disagree with the exact fixed address. Reject incompatible pairs, retain explicit diagnostics and no partial placement rewrite. | Unit and public-flow mismatch/aligned cases. |
| `migration/planner.py` | Inspection capped pragma evidence at 200 characters, falsely blocking a supported pragma with a long trailing comment. Match the verified full source line, with conservative fallback. | Long supported and unknown pragma public-flow tests. |
| `migration/rules.py` | Symbolic failures lacked useful bounded reasons; then the diagnostic selector mistook hex `x`/suffix letters for identifiers. Preserve stable macro reasons and legacy literal messages. | Conditional/undefined/alignment and hex-overflow regression cases. |
| Tests | Early assertions wrongly expected macro array dimensions to be rewritten; the stale-input test missed an import, and a custom fixture declared a nonexistent Common include. Correct test evidence/fixture contracts rather than weaken product rules. | All final new tests execute and pass; earlier failures retained below. |
| `test_memory_layout.py` | A historical fixed hash measured with producer 1.2.0 was compared to the shared fixture now using 1.3.0. Primary reproduced the identical failure at accepted base and final source. Pin only this historical fixture to 1.2.0; preserve both fixed hashes and all assertions. | Author and primary 22 affected cases pass at final CodeHead. |
| `docs/user-guide.md`, `skills/migrate-keil/SKILL.md` | Clarify C-only new function/declaration rules versus the C++ pragma, actual PLAN `rule_ids`, unchanged text versus rewritten comments, and unsupported ARMCC versus generic pragmas. | Entire guide/skill delta reviewed; skill validator passes. |

## Verification evidence

Windows CPython 3.12.14 and GNU Arm GCC 14.3.1; same-worktree Toolkit/Monitor source with installed 1.3.0 packages used only as read-only dependencies. Temporary fixtures, cache, compiler products and evidence are isolated below `D:/codex-tmp/ac24`.

| Owner / source | Result |
| --- | --- |
| Claude / `f62352764c049f0a59ca35ba002512ab59f80836` | 40 tests: 37 pass, 3 test-code failures. |
| Claude / `8b6019621c4b515caecd74edfeb1a89f8fc7fb06` | 40 tests: 39 pass, 1 fixture failure. |
| Claude / `a2166956e56987917412e038ed102c77714addb0` | 47 new tests pass. 1198 related regressions: 1194 pass, 1 historical-fixture failure, 3 platform skips. Native skill validation passes. |
| Primary / clean `a2166956e56987917412e038ed102c77714addb0` | 88 focused rule/public-flow/compiler/include/layout cases pass, process exit 0. |
| Primary / clean `2b4396979fddbef48f65316eaacbc24c424e7827` | 47 new rule/compiler/schema cases pass, process exit 0. |
| Primary / accepted base and clean `2b439697` | The same historical-hash case fails once in each isolated run; root cause is the producer-version test input, not new product behavior. |
| Claude and primary / final `d298757a36a8b106d02a5f133bdab51e87db1373` | Each passes 22 memory-layout/newlib identity cases; primary process exit 0. |

The final delta after a2166956 is one user-guide sentence and the historical producer-version pin in one test. All product code, schemas, templates, skill and other test bytes are identical. Author regression and validator evidence are reused explicitly, with the affected module rechecked, not described as another final-head full run. There is passing evidence for 1195 unique regression cases and 47 new cases. Three existing real-symlink checks are PLATFORM DEFERRED to release qualification owned by primary in a symlink-capable Windows/Linux environment: project-model file escape, directory-parent escape and regeneration destination-link rejection. Current new redirect checks use controlled metadata seams, not proof that those skipped platform cases ran. Counts come from JUnit and actual native events; Claude exit status alone is not treated as pytest evidence. The unchanged dependency lifespan warning is nonfatal.

Real GCC tests compile all four wrappers at O0/Og/O2 and inspect disassembly through the return, proving no executed stack prologue in those fixtures. A combined public preflight/PLAN/APPLY/configure fixture uses actual generated startup/linker output, explicit nosys, compilation, linking and ELF inspection for fixed placement/alignment. This is real GNU compile/link evidence, not a complete CMake invocation, ARMCC baseline comparison or physical target execution. Other build-runner regressions use their declared synthetic doubles.

Native PowerShell inventory and actual harmless Get-Location were verified. File-only authoring and exact-command native verification were separated with empty MCP configuration. One earlier file-only call attempted `Bash true`; the tool returned `No such tool available: Bash` and did not execute it. That ended invocation/log was retained, no test was credited, and subsequent corrections used a fresh file-only session; verification used separately checked, already authorized PowerShell calls. No permission bypass, alternate-shell retry or global setting change occurred. Earlier turn-budget exits retained all edits and logs.

No blocking findings remain for this bounded source slice. Original `D:/WorkSpace/mobile-robot-controller`, installed runtime, global skills, frozen release assets and hardware were not changed or accessed for validation. No release package/install, VS Code restart, probe, remote push/PR/tag or publication occurred. These patches are not yet in installed/frozen v1.3.0; restarting VS Code alone does not install them. External memory regions/linker customization, broader ABI/Keil behavior and real-board qualification remain separate work.
