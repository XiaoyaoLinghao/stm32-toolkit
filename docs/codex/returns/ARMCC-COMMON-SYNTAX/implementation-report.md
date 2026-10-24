# ARMCC-COMMON-SYNTAX Implementation Report

## Ledger

- Module/phase: `ARMCC-COMMON-SYNTAX` implementation slice (bounded common ARMCC source migration).
- Branch: `codex/armcc-common-syntax`.
- Worktree root: `C:/Users/zhy76/.codex/worktrees/build-snapshot-review/STM32-Toolkit`.
- Accepted base: `07f5e1b7720f885f0e005935256ec9466e0af261`.
- Reviewed CodeHead: `d298757a36a8b106d02a5f133bdab51e87db1373`.
- Implementation route: local Claude Code CLI with the existing `deepseek-v4.1-flash[1m]` configuration.
- Reviewer/acceptance owner: primary Codex conversation agent. The author does not accept this diff.
- Remote authority: none requested or used; no push, PR, merge, tag, or remote branch mutation. Local branches and commits are made by the primary.

Machine-readable commands, JUnit hashes, argv and per-run results are recorded in `evidence.json` (primary places it next to this report); this report summarizes that ledger and the supplied evidence.

## Source change files

The accepted-base-to-CodeHead author scope is:

- `tools/stm32-toolkit/src/stm32_toolkit/migration/constant_context.py` — new bounded token-expression evaluator plus include/macro provenance and dependency evidence.
- `tools/stm32-toolkit/src/stm32_toolkit/migration/rules.py` — bounded rule recognition/rewrites (naked wrappers, `__align`, absolute placement, exact no-semihosting pragma), placement composition validation (alignment/address divisibility), symbolic-expression bounded diagnostics using identifier-token detection, dependency/link-spec evidence.
- `tools/stm32-toolkit/src/stm32_toolkit/migration/planner.py` — inspection-finding reconciliation using revalidated exact source bytes for the supported pragma (200-codepoint evidence cap no longer misclassifies long trailing comments), conservative fallback for unavailable/mismatched lines, manifest/newlib proposal plumbing and public preflight/PLAN exposure.
- `tools/stm32-toolkit/src/stm32_toolkit/migration/preflight.py` — additive public `sourceChanges`, remediation and dependency evidence.
- `tools/stm32-toolkit/src/stm32_toolkit/project_model.py` — optional bounded `build.newlibSpecs` model field/identity handling.
- `tools/stm32-toolkit/src/stm32_toolkit/generation/configure.py` and `generation/managed_files.py` — optional bounded newlib spec rendering and model/identity binding.
- `schemas/stm32-project.schema.json` and packaged `tools/stm32-toolkit/src/stm32_toolkit/schemas/stm32-project.schema.json` — the corresponding optional model field.
- `templates/cmake/CMakeLists.txt.j2` and packaged `tools/stm32-toolkit/src/stm32_toolkit/templates/cmake/CMakeLists.txt.j2` — the corresponding link-spec rendering.
- Three new modules: `tools/stm32-toolkit/tests/test_armcc_common_syntax.py` (unit and public preflight/PLAN coverage, alignment/address compatibility, diagnostics, long-comment pragma, fixtures), `test_armcc_common_compiler.py` (real GNU Arm O0/Og/O2 compile/link/objdump/ELF fixtures), and `test_armcc_common_newlib.py` (newlib spec/identity/schema cases).
- Adjusted `tools/stm32-toolkit/tests/test_memory_layout.py`, `test_memory_layout_migration.py`, and `test_migration_plan.py`; the final memory-layout change pins only the historical `generatedBy.version` `1.2.0` for the frozen legacy hash test, keeping both expected hashes and the explicit-layout comparison unchanged.
- `docs/user-guide.md` — precise public scope, composition, diagnostic and pragma wording.
- `skills/migrate-keil/SKILL.md` — guidance corrections (preflight camelCase `sourceChanges[].ruleIds` vs PLAN snake_case `patches[].rule_ids`, C-only new function/declaration rules vs retained C++ numeric placement and C/C++ pragma, unsupported ARMCC pragmas vs unchanged generic pragmas).

The governance specification and implementation plan under `docs/superpowers/` are primary-authored, not author product edits. The schema/model/template and additive output changes listed above were intentional parts of this slice; there is no new MCP tool or input argument, no version/dependency bump, no runtime or global installation, no release asset, and no hardware change.

## Accepted bounded behavior

- Exact `__asm void` wrappers: zero-argument `WFI`/`CPSID I`/`CPSIE I`, or a 32-bit-scalar `MSR MSP, R0` setter, each with explicit `BX LR`/`BX R14`, rewritten as GNU `naked` basic asm. No invented return, no C `__set_MSP` wrapper, and no generated C prologue/epilogue or stack access before return. (The MSP setter wrapper intentionally assigns MSP via `MSR MSP, R0`, i.e. it switches the stack pointer; that assignment is the reviewed behavior, not extra generated stack access.)
- New function/declaration rules are C-only. The historical numeric absolute-placement form remains for C++; no new C++ function/alignment rules.
- Exact standalone `#pragma import(__use_no_semihosting)` (optional preserved trailing comment, no continuation) is removed for both C and C++; the manifest proposal adds `build.newlibSpecs=["nosys.specs"]`, and the managed CMake link emits one `--specs=nosys.specs` with no implicit `nano.specs`. Unsupported ARMCC imports/pragmas remain blocked; generic pragmas such as `pack`/`once` keep existing behavior.
- Bounded `__align(n)` (positive power of two, ≤4096) on one plain object, composable with a supported fixed address only when the resolved address is a multiple of `n`; incompatible combinations block placement for the file with no partial fixed-section rewrite.
- Bounded absolute placement with a non-`eval` expression evaluator; symbolic resolution failures carry stable, path-free reasons (e.g. conditional/undefined/cycle/unavailable/limit), while literal grammar failures keep the legacy generic message.
- Macro evidence comes only from target defines and resolvable quoted guarded headers; used dependency bytes are bound into the plan and apply refuses changed/ambiguous inputs. Placements outside all declared memory regions are reported (`MIGRATION_FIXED_SECTION_OUTSIDE_MEMORY`, needs-user-input); no external regions are invented.
- Public surfaces: preflight `analysis.sourceChanges[].ruleIds` (camelCase) and PLAN `data.patches[].rule_ids` (snake_case), with blockers, diffs and the reviewed manifest proposal.

This slice does not claim arbitrary ARMCC translation, general C preprocessor equivalence, runtime/binary/ABI equivalence, or board behavior equality.

## Evidence

All results below come from native pytest JUnit output, not CLI exit status alone; no exit code is asserted where it was not recorded.

- First new-module run at `f6235276`: 40 cases, 37 passed, 3 failed — two incorrect `pool[64]` test expectations (the spec intentionally preserves `pool[SIZE]`) and one `FRAMEWORK_INCLUDE` import omission in a new test. Source behavior was not at fault.
- Second run at `8b601962`: 40 cases, 39 passed, 1 failed — the public configure path failed with `include directory is missing` because the helper inherited a default include list naming a nonexistent `Common` directory. Fixed only the fixture's explicit includes.
- New-module suite at `a2166956`: 47 cases, 47 passed, 0 failed/skipped (`final-new.xml`).
- Broad regression at `a2166956`: 1198 cases — 1194 passed, 3 skipped, 1 failed. The three skips are real symlink checks unavailable on this Windows host. The failure was the frozen legacy memory-layout hash (`10a807…` expected, `0b0cc6…` actual).
- The legacy failure was reproduced by the primary in isolation at both accepted base `07f5e1b` and final `2b439697`; it is not introduced by this slice. The frozen expectation was measured under `__version__ 1.2.0`, while the shared fixture now reports `1.3.0`; `generatedBy.version` legitimately participates in the model digest. Final correction pins the historical producer `1.2.0` in that one test only, retaining both hardcoded hashes and the explicit-layout comparison.
- Final affected modules (`test_memory_layout.py` + `test_armcc_common_newlib.py`) at `d298757a`: 22 passed by the author and independently 22 passed by the primary (`legacy-fixed.xml`, `legacy-fixed-review.xml`).
- Primary verification at earlier heads: 88 passed at `a2166956` (ARMCC syntax/compiler/newlib/scoped-includes/memory-layout-migration/startup command) and 47 passed at `2b439697` (ARMCC syntax/compiler/newlib). These reuse unchanged product/test bytes and are not a full 1198-case rerun at the final CodeHead.
- Skill frontmatter validator: `Skill is valid!`.
- Real GNU Arm compiler checks (O0/Og/O2) and generated-linker integration ran; real compile/link/objdump/ELF fixtures exercised. No full CMake build or ARMCC/board equivalence was exercised.

Exact argv examples:

- 88-case command: `D:/codex-tmp/kx23/venv/Scripts/python.exe -m pytest tools/stm32-toolkit/tests/test_armcc_common_syntax.py tools/stm32-toolkit/tests/test_armcc_common_compiler.py tools/stm32-toolkit/tests/test_armcc_common_newlib.py tools/stm32-toolkit/tests/test_scoped_includes.py tools/stm32-toolkit/tests/test_memory_layout_migration.py tools/stm32-toolkit/tests/test_startup_gcc_compiler.py -q --tb=short --basetemp=D:/codex-tmp/ac24/p-independent -o cache_dir=D:/codex-tmp/ac24/c-independent --junitxml=D:/codex-tmp/ac24/independent.xml`
- 47-case final-head command: `D:/codex-tmp/kx23/venv/Scripts/python.exe -m pytest tools/stm32-toolkit/tests/test_armcc_common_syntax.py tools/stm32-toolkit/tests/test_armcc_common_compiler.py tools/stm32-toolkit/tests/test_armcc_common_newlib.py -q --tb=short --basetemp=D:/codex-tmp/ac24/p-final-head -o cache_dir=D:/codex-tmp/ac24/c-final-head --junitxml=D:/codex-tmp/ac24/final-head.xml`
- 22-case final command: `D:/codex-tmp/kx23/venv/Scripts/python.exe -m pytest tools/stm32-toolkit/tests/test_memory_layout.py tools/stm32-toolkit/tests/test_armcc_common_newlib.py -q --tb=short --basetemp=D:/codex-tmp/ac24/p-legacy-fixed-review -o cache_dir=D:/codex-tmp/ac24/c-legacy-fixed-review --junitxml=D:/codex-tmp/ac24/legacy-fixed-review.xml`

The complete command list and JUnit digests are in `evidence.json`.

## Protocol anomaly

An earlier file-only session (`016bb…`) issued `Bash true`; the tool returned `No such tool available: Bash`. Nothing executed; that call ended and its edits/logs were retained. A later file-only session (`50ddee…`) used only allowed tools; native PowerShell inventory and `Get-Location` were separately reverified, then the exact authorized verification commands ran. There was no permission bypass, no retry of a denied operation in another shell, and no test result was credited from the anomaly. The supplied ledger is authoritative; logs were not revisited here.

## State and limitations

- Source-only state: product/test/doc/skill changes are committed on the branch; the original project, installed runtime, global skills, frozen release files and hardware were untouched; no packaging, deployment, or remote action occurred.
- Platform `DEFERRED`: the three real symlink escape checks remain release-qualification items for the primary in a symlink-capable Windows or Linux environment.
- Full CMake build and ARMCC/board behavioral equivalence were not exercised; GNU compiler/ELF evidence is offline syntax and image-level evidence only.

No acceptance verdict is asserted here; independent primary review and acceptance remain outstanding.
