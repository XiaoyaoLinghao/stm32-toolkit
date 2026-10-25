# VSCODE-TASKS independent review

Verdict: **ACCEPTED_WITH_FIXES** for this bounded offline source slice.

Accepted base `e7614e49ba384117770ff8b01f57489da8676223`; final tested CodeHead `4c79ef53111408ae2f5071f6edb52cbadb8363fb`. Primary owns specification, orchestration, independent complete-diff review and acceptance; local Claude Code CLI with the existing `deepseek-v4.1-flash[1m]` configuration owns code, tests and product guidance. Author branch `codex/vscode-tasks`; review used the separate clean detached `build-snapshot-final/STM32-Toolkit` worktree at the recorded heads. No ownership exception or remote action. See [design](../../../superpowers/specs/2026-10-25-vscode-tasks-design.md), [plan](../../../superpowers/plans/2026-10-25-vscode-tasks-plan.md), [implementation evidence](implementation-report.md) and [machine evidence](evidence.json).

## Accepted result

Generated task commands use either explicit user-scope `${config:stm32-toolkit.executablePath}` bindings or the paired configure arguments' validated absolute native executable paths. IntelliSense uses the corresponding compilerPath. There is no bare-name PATH fallback or implicit host discovery. Unbound portable output is not ready to run. Windows explicit bindings require real .exe files and real lexical parent directories; links/reparse points, variables, partial pairs and invalid paths are refused before writes. Machine paths are part of the immutable plan/replay, not the project model. The same pair must accompany PLAN and APPLY. Existing configure transaction, drift checks and preserved-unowned editor files remain intact.

Five independent process tasks cover Debug/Release build, managed Flash Debug, Handoff Begin Debug and Handoff End Debug. Each binds the project explicitly; hardware tasks also prompt for DataRoot/session/probe and default to deny. There are no automatic dependencies, enumeration, stored authority, retries, builds before flash or recovery. `reevaluateOnRerun=true` expresses fresh input intent, while actual VS Code behavior remains deferred.

The narrow CLI adapter obtains exact current arm-debug identity through the existing complete freshness check for flash/begin and forwards it to unchanged workflows. Snapshot-only/no-Git evidence remains refused by managed hardware admission; the documented external import/admit/flash route is separate. End adds no adapter admission and preserves the original ticket, but underlying end still verifies firmware and flash evidence. Failed reclaim is reported as failure; the adapter promises no recovery or cleanup. All workflow result fields remain intact.

The guide covers runtime capability checks in addition to version (both source and frozen runtime still report 1.3.0), paired plan replay, separate IntelliSense/build compiler selection, exact session/probe/ticket continuity, external IDE workspace configuration, detach before end, first failure stop, managed/imported routes and applicable existing user authorization. Syntax diagrams are marked non-executable; the runnable example is a deny request with already verified variables. No new MCP tool was introduced.

## Findings resolved by Claude

| Area | Observed issue and accepted correction | Verification |
| --- | --- | --- |
| cli.py confirmation parser | Default deny made the duplicate-option action reject the first explicit value. Suppress parser default and use dispatch fallback; reject genuine repeats. | Rendered task argv through public CLI, omitted/explicit/duplicate values in test_ide_tasks. |
| vscode_configuration.py | Leaf-only checks could miss a redirected parent. Validate every lexical component and recheck on replay. | test_vscode_configuration leaf/parent mocks, invalid path diagnostics and revalidation. |
| ide_tasks.py DataRoot | Early resolve could hide the redirect that the existing hardware validator rejects. Use the existing lexical guard and retain diagnostics. | test_ide_tasks refusal before firmware admission or workflow. |
| Tests | Relative-path expected rule and MCP schema field list were stale. Correct exact public expectations. | Corrected 483-case core run. |
| Spec/guide/ide_tasks docstrings | Primary's initial reclaim-after-stale-source wording exceeded the underlying end contract. Correct the claim; do not relax the end guard. | Real begin/end with synthetic firmware and fake supervisor/client: stale ELF, exact original error, no supervisor restart, ownership still reacquiring. |
| New real-end test | Adapter DataRoot differed from the injected supervisor's origin. Bind to that origin and assert forwarded equality. | Final targeted test at 4c79ef53, both owners. |
| user-guide.md | Legacy 'use hardware requires Git' sentence could incorrectly exclude imported firmware. Narrow to managed hardware workflows. | Final AI-guidance checks and primary text review. |

Primary independently reviewed the entire accepted-base-to-CodeHead diff, including all incremental correction diffs, in the clean review worktree. No actionable finding remains in this slice. Product version, schema, probe backend, build identity and release files were unchanged.

## Evidence and reuse

| Exact source / each owner independently | Observed result |
| --- | --- |
| `3822571f69648949e10bffbc3bda2fec282c3e9e` | 469 core cases: 461 passed, 7 failed, 1 skipped |
| `3351f40ae83e90b908620a2ab196cace5340ef93` | 483 corrected core cases: 482 passed, 0 failed, 1 skipped; related regression: 539 passed |
| `210b16a4873d430290c76eae2f96000d5bb24f55` | 51 task and AI-guidance cases passed |
| Final CodeHead | 13 real-end binding and AI-guidance cases passed |

Effective evidence covers **1,022 distinct passing cases and one platform skip**, counting the renamed handoff test once. The 3351f40a-to-final product delta consists only of ide_tasks docstrings (executable AST equality checked); all other product source is byte-identical. Changed tests and guidance were rerun. This is deliberate bounded reuse, not a final full repository or release matrix. All initial failures subsequently passed. Full commands, JUnit hashes, source heads and actual native tool events are retained under `D:/codex-tmp/vs25` and indexed by evidence.json; reuse-evidence.json records the comparison.

The file-symlink test skipped with 'host cannot create a file symlink for this check'. Real symlink validation is **DEFERRED to primary-owned integration/release on a capable Windows/Linux environment**; mock leaf/parent reparse tests pass. This platform-only deferral does not waive release gates. Author native PowerShell registration and harmless Get-Location were verified; every verification invocation's init inventory and actual command were checked. Primary subprocess exit codes are recorded. A CLI exit0 alone is never taken as a test pass.

Non-failing pydantic_settings warnings originate from the intentionally borrowed dependency path. The author verifier's earlier inference that this meant an old Toolkit source was incorrect: import-binding.json proves Toolkit/CLI source imports from the review checkout. The dependency path and source code path are distinct and recorded.

Fresh read-only guidance simulation correctly identified bindings, source-versus-runtime capability, paired plans, no-Git managed refusal versus import route, ticket continuity, downstream end refusal and authorization reuse. It also echoed the legacy all-hardware Git wording; the final narrow wording correction resolves that source ambiguity. This is a simulated client reading check, not live VS Code UI acceptance. Static VS Code variable behavior was checked against [official variables documentation](https://code.visualstudio.com/docs/reference/variables-reference), [C++ configuration documentation](https://code.visualstudio.com/docs/cpp/customize-cpp-settings) and the installed cpptools 1.34.4 bundle's resolveVariables implementation (read-only hash in preflight.json). These do not prove a real IDE session.

## Delivery boundaries

The initial read-only audit and two author sessions reached turn limits; retained work was continued within the same bounded scope. No shell permission denial, absent-tool fallback, provider change or permission widening occurred in this slice. File-only editing and native PowerShell testing stayed separate. The primary wrote governance/evidence only and did not implement product code or tests.

Original project `D:/WorkSpace/mobile-robot-controller`, physical hardware, installed runtime, global Skills and frozen release assets were untouched. No packaging, remote publication or version bump. Local delivery is recorded separately after the report commit; this report intentionally names the preceding tested CodeHead rather than its own commit.

Product remains 1.3.0. Remaining sequence: doctor readiness/extension and Keil toolchain reporting, flash frequency/failure guidance, memory margin warnings, combined regression and v1.3.1 version/release work. Real VS Code/IntelliSense/handoff UI and authorized physical qualification remain integration obligations. Prior release limitations remain; no v1.2.0 exception is reused.

Cleanup preflight retained four passed-fixture roots containing reparse entries and the first failed-run fixtures. It found 14 contained, non-reparse cache/passed-fixture directories eligible for removal. Automatic approval policy rejected the native PowerShell cleanup before process creation, returning only `blocked by policy`. No deletion executed, no alternate tool or retry was used, and all outputs remain. See run-local cleanup-checked.json and cleanup.json. Previous bs25/ab25 policy-held directories were untouched.
