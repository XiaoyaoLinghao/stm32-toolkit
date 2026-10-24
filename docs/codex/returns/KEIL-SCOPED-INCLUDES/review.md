# KEIL-SCOPED-INCLUDES independent review

2026-10-24 verdict: **ACCEPTED_WITH_FIXES**, for the bounded offline slice.

Accepted base `e9b242ec8f97f30135693ca5b0f3f9d8465a7615`; final CodeHead `22bbc94b2343327e6d4ca71764b495806d1d8f0a`; branch `codex/keil-scoped-includes`. Primary owns specification, plan, orchestration, independent complete-diff review and acceptance. Claude Code CLI using the existing configured provider/model authored every product/test/guide change. No PR, remote authorization or ownership exception.

The complete diff was reviewed in clean `build-snapshot-final/STM32-Toolkit` at the exact CodeHead. Binary diff SHA-256: `88a55c51717b54e3ec937ba3331fe230b523cabc42fd60a386862aa789740b38`, retained at `D:/codex-tmp/ki24/reviewed.diff`. Governing [specification](../../../superpowers/specs/2026-10-24-keil-scoped-includes-design.md) and [plan](../../../superpowers/plans/2026-10-24-keil-scoped-includes-plan.md); raw identities, counts and hashes in [evidence.json](evidence.json).

## Accepted behavior

Included C/C++ group/file include-only options can append existing contained directories without modifying uvprojx. Inspection already resolves paths relative to uvprojx; analysis uses its project-relative paths exactly once. Target ordering is preserved and repeated canonical directories deduplicated. Listed headers/libraries do not invoke compilation and do not make a C/C++ scope unsupported. Assembly/unknown compiled entries, defines and misc controls retain explicit blockers.

Conflict checks compare full case-insensitive include-relative keys, including nested paths, and reject distinct file resolutions. `USER` plus `USER/IWDG` is allowed when there is no actual key collision. Invalid paths, redirects/nonregular entries, unreadability and aggregate limits fail without partial merge. Newly appended directory content inventories enter the plan identity and fresh-APPLY comparison, including Git-ignored additions/changes. Preflight remains Git-free/read-only; conversion PLAN/APPLY retain all Git, authorization, identity and transactional guards. Empty merge evidence preserves the historical no-scope plan payload.

The AI guide distinguishes preflight/report camelCase `includeMerges` from PLAN snake_case `include_merges`, including the nested inventory fields. It requires reviewing actual evidence and forbids editing hashes or deleting unsupported options to force migration. This slice does not add an MCP tool, request argument, version, dependency or hardware route.

## Findings closed

| Path | Finding and correction | Evidence |
| --- | --- | --- |
| `migration/scoped_includes.py` | Draft basename comparison and blanket parent/child rejection incorrectly blocked safe `USER/IWDG` merges. Compare full lookup keys and actual normalized file paths; preserve genuine same-key conflicts. | Positive overlap/distinct-key tests and negative overlapping-root collision tests. |
| Same module | Per-directory scan budgets could be multiplied by many scopes; use shared entries/files/directories/hash-byte bounds and canonical-root dedupe. | Aggregate directory and zero-byte file exhaustion tests. |
| Same module and `planner.py` | Do not drop assembly scope semantics; listed headers/libraries are not compiler invocations and should not block a C/C++ group. | C+header, inert header/library, excluded file, mixed C+asm and file-asm tests. |
| `test_scoped_includes.py` | New fixtures called `git add` before initialization; the existing `build_repo(commit=False)` deliberately did not initialize Git. Reuse the shared fixture initializer. This was a test-code defect, not an environment failure. | Initial 26 failures retained; final cases execute real preflight/plan/apply assertions. |
| Same test and migrate-keil skill | List/tuple assertions confused typed OperationResult and public JSON; one PLAN paragraph used camelCase inventory fields. Test both typed and serialized forms and correct the guide. | Final actual manifest/report and public-response assertions pass; full skill diff reviewed. |

## Verification

Windows CPython 3.12.14, same-tree Toolkit/Monitor source, read-only installed 1.3.0 dependencies, isolated temp/cache paths under `D:/codex-tmp/ki24`. Native PowerShell inventory and actual Get-Location were verified; file-only authoring and exact-command verification used empty MCP configuration. First author turn hit its 65-turn bound and was resumed with all edits/logs retained. No permission denial, fallback shell or primary-authored product patch.

| Owner / source | Result |
| --- | --- |
| Claude / `5a8c6521` | 347 tests: 321 pass, 26 fixture failures. |
| Claude / `96fc3692` | 350 tests: 349 pass, 1 typed-vs-JSON assertion failure. Skill validator passed. |
| Claude / final `22bbc94b` | 30 new scoped-include tests pass, zero errors/skips. |
| Primary / clean `96fc3692` | 81 tests: 80 pass, the same assertion failure. |
| Primary / clean final `22bbc94b` | 30 scoped-include tests pass, process exit 0. |

The final delta from `96fc3692` changes only the one test assertion; all product bytes and other fixtures/tests are identical. Reuse 320 passing related regression cases and 51 passing independent integration/layout cases from that head. Thus 350 unique author cases and 81 independent cases have passing evidence, **not** a new full 350-case run at final CodeHead. Counts are reconciled from JUnit because the native shell did not always return the terminal tally line. Exact argv and raw tool results are retained in the implementation report/logs and primary execution JSONs. The existing MCP dependency `lifespan` warning is nonfatal and unchanged.

No blocking findings remain for this slice. The additive target search list is a reviewed conversion, not a proof of general preprocessing or firmware behavior equivalence. Hard-link aliases are conservatively distinct paths; nested roots share the global budget but are traversed separately. Compiler ABI, arbitrary assembly, encoding, external memory, baseline comparison and hardware remain separate work.

The original project, installed runtime, global skills and frozen release files were not changed. No build/package/install, VS Code restart, probe, hardware or remote action occurred. This source patch is not in the frozen or installed 1.3.0 runtime. Continue with a separately specified common ARMCC syntax slice from this accepted result.
