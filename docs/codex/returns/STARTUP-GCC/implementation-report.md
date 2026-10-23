# STARTUP-GCC Implementation Report

Status: implementation evidence returned to the primary conversation agent for independent review and acceptance. This report is written by the implementation route and does not approve its own implementation. No acceptance verdict is recorded here. The memory-layout slice remains outstanding.

## Ledger

| Item | Value |
| --- | --- |
| Module / slice | STARTUP-GCC (bounded CMSIS GCC startup generation) |
| Branch | `codex/startup-gcc` |
| Accepted base | `6ab4cf819a7b624fab612954dfbac617107d7f79` |
| Final CodeHead before this report | `c76f03c3af852a5f156f915e7bf8f17d783657d2` (clean tree) |
| Product-code freeze | `8ec3ff9e078e9f47be36f77360805d995a9bc617` |
| Post-freeze commits | `c76f03c3` changes only two compatibility-test expectations |
| Specification / plan / orchestration / Git / full-diff review / acceptance | Primary conversation agent |
| Implementation and authored tests | Local Claude Code CLI route (configured provider reported as `deepseek-v4.1-flash[1m]`; not claimed to be an Anthropic model) |
| Codex-hosted implementation agents | None used |
| Remote / release / install actions | None |

This report deliberately omits the future report commit and any acceptance identity.

## Delivered scope

- Public `startupStrategy` value `generate-cmsis-gcc` and public `startupSource`, exposed consistently through CLI and MCP (registered camelCase tool contracts included).
- Full conventional ARMASM startup grammar validation, bounded to Cortex-M3/M4/M7 targets: stack/heap symbols, vector-table shape, handler/reserved entries, Reset_Handler tracking, weak/strong and newlib/Thumb forms, comment-safe metadata handling, and bounded decimal/hex parsing. No generic ARMASM translator.
- Immutable plan/replan behavior, generated-parent-file collision detection, and original-source preservation. The pre-existing no-option path retains its exact bytes and hash.
- Deterministic generated `Startup/stm32tk_startup_gcc.S`, with stack/heap byte fields and `runtimeInitialization` value `cmsis-gcc-v1`.
- Managed linker updates: constructors, aliases, `.data` copy alignment, and no-leading-padding guards. Both linker templates now assert `ADDR(.data) == _sdata`, `SIZEOF(.data) == _edata - _sdata`, and endpoint/LMA alignment.
- Guidance distinguishing current project source from the published/managed runtime, and retention of the exact user options in `nextSteps`, plus candidate CLI examples.
- Test fixtures cover a real SystemInit/BSS/compiler shape, every vector, Thumb/weak-strong/newlib forms, the metadata opener, PyElftools binding labels, and a public registered camelCase MCP schema test.

## Corrections and review findings completed

- Completed Reset_Handler tracking and bounded decimal/hex parsing.
- Added generated-parent-file collision handling and comment-safe metadata parsing.
- Added Microlib CODE-area context and corrected the metadata test opener and PyElftools binding-label assumptions.
- Added exact-option retention in `nextSteps` and candidate CLI examples.
- Fixed the two broad-suite compatibility-test expectations (workflow stub option acceptance; MCP property allowlists) in `c76f03c3`.
- Primary independently reproduced an odd RAM origin that corrupted the `.data` copy despite endpoint alignment (`primary-alignment-review/result.json`): `.data` VMA `0x20000001`, 3 leading bytes, `_sdata` `0x20000004`, runtime copied `00000078` instead of `78563412`. The negative GNU link refuses the offending layout, and both templates now carry the assertions above. This is offline synthetic ELF evidence only, not hardware execution.

## CLI verification evidence

Commands below are transcribed exactly from the coordinator's verification request files; no ellipses.

### Initial four-module run (verify1)

```powershell
python -m pytest tools/stm32-toolkit/tests/test_startup_gcc.py tools/stm32-toolkit/tests/test_startup_gcc_generation.py tools/stm32-toolkit/tests/test_startup_gcc_compiler.py tools/stm32-toolkit/tests/test_startup_gcc_routing.py --basetemp=D:/codex-tmp/sg23/b1 -o cache_dir=D:/codex-tmp/sg23/c1 -ra
```

Result: 62 tests, 18 failures, exit code 1. Failures were primarily startup/reset recognition. Console output was truncated; only the failed-node list from the cache/lastfailed state was summarized. No unseen traces were invented.

### After correction round 1 (verify2)

```powershell
python -m pytest tools/stm32-toolkit/tests/test_startup_gcc.py tools/stm32-toolkit/tests/test_startup_gcc_generation.py tools/stm32-toolkit/tests/test_startup_gcc_compiler.py tools/stm32-toolkit/tests/test_startup_gcc_routing.py --basetemp=D:/codex-tmp/sg23/b2 -o cache_dir=D:/codex-tmp/sg23/c2 -q --tb=short --junitxml=D:/codex-tmp/sg23/verify2.xml
```

Result: `verify2.xml`, 73 tests, 71 passed, 2 failed, 0 skipped, 35.691s. The two failures were a metadata-test opener and PyElftools binding-label assumptions. They are recorded as failures, not claimed as passes.

### Final broad proportional suite on product freeze `8ec3ff9e` (verify3)

```powershell
python -m pytest tools/stm32-toolkit/tests/test_startup_gcc.py tools/stm32-toolkit/tests/test_startup_gcc_generation.py tools/stm32-toolkit/tests/test_startup_gcc_compiler.py tools/stm32-toolkit/tests/test_startup_gcc_routing.py tools/stm32-toolkit/tests/test_migration_plan.py tools/stm32-toolkit/tests/test_migration_apply.py tools/stm32-toolkit/tests/test_keil_preflight.py tools/stm32-toolkit/tests/test_generation.py tools/stm32-toolkit/tests/test_regeneration.py tools/stm32-toolkit/tests/test_regeneration_workflows.py tools/stm32-toolkit/tests/test_project_model.py tools/stm32-toolkit/tests/test_workflows.py tools/stm32-toolkit/tests/test_mcp_migration_build.py tools/stm32-toolkit/tests/test_cli.py tools/stm32-toolkit/tests/test_mcp_server.py tools/stm32-toolkit/tests/test_mcp_roots.py tools/stm32-toolkit/tests/test_public_inventory.py --basetemp=D:/codex-tmp/sg23/b3 -o cache_dir=D:/codex-tmp/sg23/c3 -q --tb=short --junitxml=D:/codex-tmp/sg23/verify3.xml
```

Result: `verify3.xml`, 1058 tests, 1053 passed, 2 failed, 3 skipped, 504.822s. Failure 1: the old workflow stub did not accept `startup_options`. Failure 2: the old exact MCP property allowlists omitted two new options. The CLI then edited only those two tests, producing `c76f03c3`.

### Targeted rerun at exact `c76f03c3` (verify4)

```powershell
python -m pytest tools/stm32-toolkit/tests/test_workflows.py::test_convert_workflow_translates_stable_inspection_and_plan_errors tools/stm32-toolkit/tests/test_mcp_migration_build.py::test_new_tool_schemas_expose_only_declared_properties --basetemp=D:/codex-tmp/sg23/b4 -o cache_dir=D:/codex-tmp/sg23/c4 -q --tb=short --junitxml=D:/codex-tmp/sg23/verify4.xml
```

Result: `verify4.xml`, 2 tests, 2 passed, 0 skipped, 3.710s; the coordinator parsed the XML and found no exit/failure markers. Session `3592109b-66ea-482b-a1fa-6fb4cfbe020b`.

The historical broad 1058-test run was not repeated after these test-only corrections. It is not relabeled as a fresh all-pass full-suite result: the 1053-pass/2-fail/3-skip counts stand for that run at `8ec3ff9e`, and the two corrected expectations are separately evidenced at `c76f03c3`.

## Primary independent evidence (attributed to the primary agent, not the implementation route)

- Clean review worktree `C:/Users/zhy76/.codex/worktrees/build-snapshot-final/STM32-Toolkit` at `8ec3ff9e`: four startup modules, 76 passed, 0 skipped, 43.331s, retained as `primary-final.xml`/log.
- Clean exact-`c76f03c3` worktree: the two corrected compatibility tests, 2 passed, 3.673s, retained as `primary-compat.xml`/log.
- Product files were identical between the two reviewed heads.
- Full accepted-base-to-final diff reviewed and retained as `primary-complete-final.diff`.
- `git diff --check` passed; schema and linker root/packaged copies have equal Git blobs.

## Original-source read-only check

`Startup_config/startup_stm32f429_439xx.s` was read only and passed the grammar/metadata checks: SHA-256 `3265ff864ce96074f384e178b35acdbbd33ebdffe45716ccba8d55544b9db0ae`, 31136 bytes, 107 vectors, 5 reserved entries, stack 4096, heap 1024. `primary original-source-preservation.json` checked 54 registered source files with 0 changed. The entire original project at `D:/WorkSpace/mobile-robot-controller` was untouched.

## Skips and deferrals

Three broad-suite skips are unchanged and are not passes:

- `tools/stm32-toolkit/tests/test_regeneration.py::test_destination_symlink_is_rejected_before_resolution`
- `tools/stm32-toolkit/tests/test_project_model.py::test_file_symlink_cannot_escape_project_root`
- `tools/stm32-toolkit/tests/test_project_model.py::test_directory_symlink_parent_cannot_escape_project_root`

These are platform-only checks deferred to the primary-led next platform/release qualification in a symlink-capable environment. Windows symbolic-link privilege was unavailable; no privilege or settings changes were made.

## Warnings observed

- Pydantic-settings lifespan incomplete annotation warning.
- Broad `test_cli` runpy preimport warning.

Both were visible in output and are not suppressed.

## Execution-boundary record

- Scratch space: `D:/codex-tmp/sg23`.
- The initial combined implementation invocation hit a denied compound PowerShell schema-hash command. The coordinator stopped it and retained the logs. The denied discovery operation was never bypassed or retried through another shell or tool.
- Subsequent implementation and fixes used file-only Read/Edit/Write/Glob/Grep. Verification used separate Read/PowerShell invocations with the exact supplied single-command forms and bound paths. Global and project `AGENTS.md` now codify this split.
- The file-only initial and fix-1 stages were coordinator-ended with edits retained; that was not test success. Fix 2 resumed with concrete reviewer findings and returned tests NOT RUN; execution evidence is owned solely by the separate verification invocations above.
- No further denials occurred in the fix or verification stages. No credentials, raw thinking, or permission-bypass settings appear in this report.

## Boundaries and retained limitations

- No generic ARMASM translation and no claim of ARMCC/Microlib ABI or behavioral equivalence.
- No multi-RAM support in this slice.
- No apply, build, or hardware execution against the original project.
- No remote, release, runtime installation, or version changes.
- No hardware execution of the generated startup; evidence is offline synthetic/compiled and read-only source inspection.
- Memory-layout slice remains outstanding.
- Acceptance remains with the primary conversation agent.
