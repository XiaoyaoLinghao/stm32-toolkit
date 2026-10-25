# BUILD-STALE-GUIDANCE independent review

Verdict: **ACCEPTED_WITH_FIXES** for this bounded offline source slice.

Accepted base `fefa21fe14de1a3710799e9cf39f33f3a41815d0`; final tested CodeHead `eb7bacb705b812e217998e063f8db5fb88725feb`. Primary owns specification, orchestration, independent complete-diff review and acceptance. Local Claude Code CLI with the existing `deepseek-v4.1-flash[1m]` configuration owns implementation, tests and product guidance. Author branch `codex/build-stale-guidance`; review used the separate clean detached `build-snapshot-final/STM32-Toolkit` tree at each exact test head. No remote action or ownership override. See [design](../../../superpowers/specs/2026-10-25-build-stale-guidance-design.md), [plan](../../../superpowers/plans/2026-10-25-build-stale-guidance-plan.md), [author report](implementation-report.md) and [machine evidence](evidence.json).

## Accepted behavior

`BUILD_OUTPUT_STALE` retains its code and legacy path/rule. The existing first failed freshness comparison now supplies a bounded reason and fixed evidenceField/evidenceSource where applicable. Missing/unreadable/malformed prior JSON remains intentionally combined by the existing reader; an input digest mismatch does not prove which file changed. Recorded values and absolute roots are not echoed. The predicate order, changed-output path, accepted no-op builds, success/failure artifact schemas, immutable OperationResult, managed drift checks, Git/snapshot boundaries, locks and authorization are preserved.

Unchanged unverifiable outputs with clean=false carry clean-rebuild advice preserving the actual preset and timeout. Required output unavailable, or stale output after clean=true, instead directs log/configuration inspection with no repeated rebuild invocation. Advice never executes. CLI arguments are a command tail: callers must supply the verified executable and the required explicit absolute project root from the same binding. The public CLI rejects a bare tail even from project cwd; the synthetic replay test proves correct metadata-based composition, --clean-first argv, timeout preservation and success. MCP parameters match the registered public camelCase schema and omit authorized. Existing applicable authorization is reusable; advice does not grant it.

The Skill and VS Code guide distinguish failure paths (`details.logPath/resultPath/identityPath`) from successful response fields, preserve the full failed response before replacement, and route managed drift to supported configure/fragment repair. Clean invokes CMake's clean target before rebuilding and can remove generated outputs; it does not recursively delete the whole build directory/cache and is not a guaranteed repair. The installed CMake manual at `C:/ST/STM32CubeCLT_1.22.0/CMake/share/cmake-4.3/Help/manual/cmake.1.rst:828` was checked read-only.

## Review findings and verification

Primary complete-diff review found a missing CLI project-binding requirement: cwd alone cannot satisfy the parser. Claude added structured projectRoot metadata, corrected guidance, and verified omitted-binding refusal plus a successful composed invocation. Runtime admission was not loosened.

| Exact source / owner | Observed result |
| --- | --- |
| `111495b48a53bff36a57b65ef5644edfb31b1407` / each owner independently |242 tests:230 passed,12 failed,0 skipped. |
| `0e287de3f05054d65beff8600a08b8eb63040f6e` / each owner independently |51 targeted tests:50 passed,1 failed,0 skipped. |
| Final CodeHead / each owner independently |13 final guidance/description checks passed,0 failed/skipped. |
| Primary / final CodeHead |Skill structural validation and full diff whitespace check passed. |

The initial12 failures were test defects:8 tuple-versus-list expectations and2 direct JSON serializations of immutable mappings,1 expected gitHead mismatch masked by an earlier record buildId mismatch, and1 line-wrapped description phrase. Tests now inspect public to_dict JSON without altering immutability; the fixture's first failure is preserved, and an additional aligned-record case exercises the later identity gitHead comparison. The remaining second-run failure was an obsolete literal in the newly added description test, removed while retaining the actual root-binding contract checks. All failed cases subsequently passed.

There are **243 distinct applicable passing cases**, with230 unchanged case results reused at the final head. All changed test functions/parameter groups and guidance-dependent checks were rerun. Product source is byte-identical across the three tested heads; later changes are tests/Skill/docs only. This is not a final full repository or release matrix. Evidence records actual argv, heads, JUnit and hashes. Author runs are backed by native PowerShell tool_use/tool_result; CLI exit0 is not treated as pytest exit0. Primary final subprocess exit0 is recorded. The author verifier initially overcounted tuple failures as9; XML establishes8. Non-failing pydantic_settings/runpy warnings come from the intentionally borrowed dependency path and module test; they do not establish a wrong Toolkit source/runtime binding.

Fresh read-only Claude scenarios selected the intended authorized clean/log-inspection/configuration-repair routes. Follow-ups exposed overbroad cleanup wording and confusion between success/failure path names; narrow Skill clarification fixed both. The final scenario correctly used details paths, stopped repeat clean, described generated-output removal and retained existing exact authorization. These are synthetic guidance checks, not an actual VS Code installation/session or hardware qualification.

## Process and delivery limits

The first file-only author attempted disabled Bash `echo no` and continued instead of stopping. The tool returned “No such tool available”; no shell executed. Primary discovered this during complete log reconciliation after the sessions ended, preserved edits/logs, stopped resuming that session and used fresh file-only correction calls. This deviation is recorded rather than treated as successful execution. One65-turn limit also preserved edits. All actual tests used separate exact-command native PowerShell calls; no permissions/model/provider/authentication settings were widened or changed.

Original project and hardware were not accessed. No runtime/global Skill installation, packaging, version bump or remote publication occurred. Product remains1.3.0; the requested integrated release target is **v1.3.1 after all agreed improvements**. Remaining sequence: generated VS Code paths/tasks, doctor readiness, flash frequency/failure guidance, memory margin warnings, combined integration and later authorized release/IDE/hardware verification. Existing deferred release obligations remain.

Automatic approval policy rejected native PowerShell cleanup of eight resolved, contained, non-reparse cache/passed-fixture directories under `D:/codex-tmp/bs25`, returning only `blocked by policy`. No deletion executed or alternate tool was used. All temporary directories, raw logs/JUnit and failed fixtures remain; previous ab25 policy-held directories were untouched. See cleanup.json and cleanup-checked.json in the run root.
