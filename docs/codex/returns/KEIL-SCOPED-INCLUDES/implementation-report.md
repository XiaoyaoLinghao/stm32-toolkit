# KEIL-SCOPED-INCLUDES implementation report

## Identity and ownership

- Repository: `https://github.com/XiaoyaoLinghao/stm32-toolkit.git`
- Module / slice: `KEIL-SCOPED-INCLUDES` (include-only group/file scope migration)
- Branch: `codex/keil-scoped-includes`
- Accepted base: `e9b242ec8f97f30135693ca5b0f3f9d8465a7615`
- CodeHead before this report commit: `22bbc94b2343327e6d4ca71764b495806d1d8f0a`
- Governing specification: [2026-10-24-keil-scoped-includes-design.md](../../superpowers/specs/2026-10-24-keil-scoped-includes-design.md)
- Approved plan: [2026-10-24-keil-scoped-includes-plan.md](../../superpowers/plans/2026-10-24-keil-scoped-includes-plan.md)
- Independent primary review: `docs/codex/returns/KEIL-SCOPED-INCLUDES/review.md` (written by the primary owner; not part of this report commit)

Ownership follows the repository contract. The primary conversation agent owns the specification, plan, task boundaries, independent complete-diff review, and acceptance. Implementation and implementation tests were authored through the local Claude Code CLI on the existing `deepseek-v4.1-flash[1m]` route; that route authored the product and test bytes and ran the native verification summarized below. This report does not approve its own diff and records no primary verdict.

No remote push, PR, merge, tag, release, package, installation, runtime/global-skill change, original-project access, probe, or hardware action was performed in this slice.

## Invocation and permission boundaries

- Native PowerShell registration and `Get-Location` were verified with process-only flags and a strict empty MCP configuration before authoring.
- File-only authoring (Read/Edit/Write/Glob/Grep) and exact-command native PowerShell verification were separate invocations. Verification used only coordinator-supplied single commands with a bound working directory.
- The initial author invocation reached its 65-turn bound; the same session was resumed with edits and logs preserved. No permission denials, absent tools, fallbacks, or rerouting occurred.
- Every native test result below was actually produced by native test execution; counts were reconciled by the coordinator from retained JUnit XML because not every terminal tally line appeared.

## Delivered behavior

- Preflight and conversion planning share one deterministic, Git-free, read-only include-only analysis.
- Only group/file scopes carrying `IncludePath` alone and covering included C/C++ compilation may contribute directories to the target include list. A scope with defines or misc controls retains its ordinary `ARMCC_OPTION_UNSUPPORTED` blocker. A scope that also compiles included assembly or an unknown (`other`) language retains that blocker. Listed headers and precompiled libraries do not invoke a compiler, so they are ignored for this decision: a C/C++ group that also lists headers merges, while header/library-only scopes are inert. Excluded file scopes and groups with no included source are inert.
- Inspection-normalized, root-relative scope paths are resolved exactly once against the canonical project root and never re-resolved against the `.uvprojx` directory.
- Contributed directories must exist, be real directories, stay inside the canonical root, be readable, and contain no unsupported symlink/reparse entry. Missing, non-directory, escaping, unreadable, redirect, and bounded-inventory failures produce stable actionable `MIGRATION_INCLUDE_*` blockers; an invalid analysis yields no partial merge.
- Target order is preserved; scoped directories are appended in inspection order and deduplicated by canonical directory with portable output.
- Conflict detection is conservative and key-based: case-insensitive full include-relative keys are compared across every existing and proposed search root, including nested paths. One key resolving to distinct physical files is a blocker even when bytes match; overlapping roots exposing the same physical files are not a conflict. Traversal, file, directory, depth, and hashed-byte budgets are aggregate across the analysis, identical directories are deduplicated before traversal, and exhaustion is a blocker rather than a sampled result.
- `added` directories record a bounded inventory digest. The evidence is exposed additively as preflight `analysis.includeMerges` (camelCase inventory fields), plan `include_merges` (snake_case), and apply-report `includeMerges`; the manifest proposal appends exactly the reviewed directories. The evidence binds the plan identity only when present, so historical no-scope plan identities are unchanged.
- Apply keeps the existing Git/authorization/transactional contract and revalidates with a fresh plan. Git-ignored header content changes, additions, or removals in a newly exposed directory are detected through the inventory digest; a new colliding file changes the fresh-plan blockers. Both fail the fresh-plan comparison instead of silently reusing the reviewed decision.
- `docs/user-guide.md` and `skills/migrate-keil/SKILL.md` direct the AI to inspect merge evidence and remaining blockers, review the exact patch/plan ID, and never edit managed hashes or remove defines/misc controls/scopes to force migration.

## Changed source files

Product:

- `tools/stm32-toolkit/src/stm32_toolkit/migration/scoped_includes.py` (new)
- `tools/stm32-toolkit/src/stm32_toolkit/migration/model.py`
- `tools/stm32-toolkit/src/stm32_toolkit/migration/planner.py`
- `tools/stm32-toolkit/src/stm32_toolkit/migration/preflight.py`
- `tools/stm32-toolkit/src/stm32_toolkit/migration/apply.py`

Tests:

- `tools/stm32-toolkit/tests/test_scoped_includes.py` (new)
- `tools/stm32-toolkit/tests/test_migration_plan.py`

Documentation / skill:

- `docs/user-guide.md`
- `skills/migrate-keil/SKILL.md`

## Verification evidence

Author implementation run at `5a8c652152bbef8e8b61cf34739f7313ef43659d`:

- `test-author.jsonl`; `author-tests.xml`: 347 cases, 321 passed, 26 failed, 0 errors, 0 skipped.
- All 26 failures were one test-code defect: the new disposable fixtures used `build_repo(commit=False)` and committed without initializing Git. This was not an environment or permission failure and required no product weakening.

Author final verification at `96fc36920dad0a1fa3746d46f210db3459bf805c`:

- `test-final.jsonl`; `final-tests.xml`: 350 cases, 349 passed, 1 failed, 0 errors, 0 skipped.
- The single failure was a test-only contract mismatch: after a successful apply, the assertion compared the frozen typed `OperationResult` data (`changedPaths`/`createdPaths` tuples) with JSON lists. The public `result.to_dict()["data"]` serialization is the JSON-list contract; the test was corrected accordingly, with no product change.
- `quick_validate.py skills/migrate-keil` passed at this head.

Coordinator frozen accept run after the test-only correction, product bytes unchanged from `96fc3692`:

- `test-accept.jsonl`; `accept-tests.xml`: 30 scoped cases passed, 0 failed, 0 skipped.
- The 320 remaining regression cases from the `96fc3692` run are reused for the final head because product code, those tests, and fixtures are byte-identical. This report does **not** claim a fresh full 350-case run at the final head.

Primary independent verification (primary-owned evidence, not author evidence):

- `review.xml` at `96fc3692`: 81 cases, 80 passed, 1 failed with the same typed-vs-JSON assertion mismatch.
- `review-accept.xml`: 30 cases passed after the correction.
- 51 unaffected primary integration/layout cases are reused. These results are not attributed to the implementer.

Test module group covered by the author final run:

`test_scoped_includes.py`, `test_migration_plan.py`, `test_migration_apply.py`, `test_keil_inspect.py`, `test_keil_preflight.py`, `test_mcp_migration_build.py`, `test_ai_call_guidance.py`. The primary additionally ran `test_plugin_layout.py`.

Known nonfatal observation: one pydantic lifespan `IncompleteFieldDefinitionWarning` appears in MCP tests; it is pre-existing and untouched by this slice.

Retained raw evidence (argv, logs, JUnit, isolated temp/cache) is under `D:/codex-tmp/ki24`: `test-author.jsonl`, `test-final.jsonl`, `test-accept.jsonl`, plus the corresponding XML. Environment: same-tree Toolkit/Monitor source, CPython 3.12.14, read-only installed 1.3.0 dependencies, isolated temporary and cache directories.

### Coordinator commands (verbatim)

Final author verification:

```
D:/codex-tmp/kx23/venv/Scripts/python.exe -m pytest tools/stm32-toolkit/tests/test_scoped_includes.py tools/stm32-toolkit/tests/test_migration_plan.py tools/stm32-toolkit/tests/test_migration_apply.py tools/stm32-toolkit/tests/test_keil_inspect.py tools/stm32-toolkit/tests/test_keil_preflight.py tools/stm32-toolkit/tests/test_mcp_migration_build.py tools/stm32-toolkit/tests/test_ai_call_guidance.py -q --tb=short --basetemp=D:/codex-tmp/ki24/p-final -o cache_dir=D:/codex-tmp/ki24/c-final --junitxml=D:/codex-tmp/ki24/final-tests.xml
```

```
D:/codex-tmp/kx23/venv/Scripts/python.exe C:/Users/zhy76/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/migrate-keil
```

Frozen accept run:

```
D:/codex-tmp/kx23/venv/Scripts/python.exe -m pytest tools/stm32-toolkit/tests/test_scoped_includes.py -q --tb=short --basetemp=D:/codex-tmp/ki24/p-accept -o cache_dir=D:/codex-tmp/ki24/c-accept --junitxml=D:/codex-tmp/ki24/accept-tests.xml
```

## Limitations

- The merge is an additive target-include-list representation that preserves target ordering and deduplicates physical directories. It is not general preprocessor equivalence, per-file macro semantics, or behavioral equivalence for arbitrary code.
- Scopes with defines or misc controls remain blocked; scopes that compile included assembly or an unknown (`other`) language remain blocked. Listed header/library entries are inert for this decision by design.
- Conflict detection is deliberately conservative: full case-insensitive include-relative keys are compared across all search roots. Overlapping roots exposing the same physical files are allowed, but any key resolving to distinct files is a blocker.
- Reparse points/symlinks inside contributed paths or inventories, non-regular entries, unreadable entries, and exhausted traversal/hash budgets are rejected rather than sampled or guessed.
- Physical identity is canonical-path based; hard-link aliases under different canonical paths are treated conservatively as distinct files.
- Fresh apply revalidates the reviewed evidence by re-planning and comparing the bound new-directory inventories (plus the ordinary Git/input/patch guards). Historical plans without a scoped include merge keep their prior identity payload.
- This change is source-only. It is not part of the installed/frozen 1.3.0 runtime or any package, and no release qualification, deployment, or hardware evidence is claimed.
- The implementer does not approve this diff. Independence, acceptance, and the verdict remain with the primary owner.
