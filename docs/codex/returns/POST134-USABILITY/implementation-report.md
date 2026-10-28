# POST134-USABILITY implementation and independent review

Date: 2026-10-28. Primary Codex owns specification, orchestration, complete-diff
review and acceptance; local Claude Code CLI owns all product/test edits and the
offline flash investigation. Configured route remained `deepseek-v4.1-flash[1m]`;
the CLI route is not described as an Anthropic model.

## Verdict and exact source ledger

**Overall: REVISION_REQUIRED. The requested work is not complete.**

| Requested item | Disposition |
| --- | --- |
| 1. Incremental preset switching | REVISION_REQUIRED. Retained WIP, not integrated; 9 new tests passed and 3 failed, with an additional path-redirection review finding |
| 3. CLI flash-region diagnostics | ACCEPTED as a local software artifact after complete-diff review and independent 90/90 tests; the original editing invocation remains rejected |
| 4 + 5. Migration/debug follow-up | NOT_IMPLEMENTED. Three bounded edit invocations ended without edits |
| 8. Release documentation additions | NOT_IMPLEMENTED; it belonged to the same guidance slice |
| 2. Standard flash failure | Offline investigation artifact accepted with the stated evidence limits; root cause unproven, no flash behavior change or hardware acceptance |

- Accepted base: `7e578ca1395ffa3b9743bef5a9fe55c40912eed6`.
- Approved scope/plan: [specification](../../../superpowers/specs/2026-10-28-post134-usability.md)
  and [plan](../../../superpowers/plans/2026-10-28-post134-usability.md).
- Governance source: `ccc5d9994ac93571227d204786f9cefdb4e66e2e`.
- Integrated CodeHead **before this report/checkpoint commit**:
  `42451ea3a374cc9cc435c56cee160c9fbf63f416`,
  branch `codex/v134-fixes-integration`.
- Integration workspace:
  `C:/Users/zhy76/.codex/worktrees/v134-fixes-integration/STM32-Toolkit`.
- Independent clean review workspace at that exact CodeHead:
  `C:/Users/zhy76/.codex/worktrees/post134-independent-review/STM32-Toolkit`.
- CLI implementation CodeHead:
  `0cb0ee497d460423ae161b2b248d3d303666652b`,
  branch `codex/post134-cli-diagnostics`; integrated as
  `54a2f25da088d8389686b9641894644fb7b56479`.
- Offline report source commit:
  `cb9dfa033e369b1144efab1d6ff2f2232ca66612`; integrated as
  `bfbd32c33b0b2136f2f703455f08d60c7a7d4946`.
- Unaccepted build WIP CodeHead:
  `42b4aa007445e27eb60c911d51817df1f385aaea`,
  branch `codex/post134-build-presets`, retained at
  `C:/Users/zhy76/.codex/worktrees/post134-build-presets/STM32-Toolkit`.
- Guidance branch `codex/post134-migration-guidance` remained at governance
  source with no product changes.
- Original `D:/WorkSpace/STM32-Toolkit` checkout was not used as the implementation
  source; it was on older `codex/flash-frequency-delivery` at
  `f5d8978a2a60c59ec5afee4fc014707311210fe5`.
- No PR, push, merge to master, tag, publication, installation, version change,
  hardware authority or ownership override was granted or exercised. Local slice
  commits and integration do not authorize those actions.

## Accepted local changes

CLI `firmware import --flash-regions` retains exit 2 and the historical
`stm32-toolkit: invalid arguments` first line. A second line reports only fixed
schema reasons and a bounded item index: valid JSON, array/count, object shape,
required fields, unsupported/duplicate keys and integer types excluding bool.
The accepted shape remains 1..32 objects with exactly `start` and `length`.
Help includes that schema and a concrete example; range/security validation is
unchanged. Caller values, secret markers and control characters are not echoed.
Unrelated argparse failures retain their sanitized message.

Changed product/test files:
- `tools/stm32-toolkit/src/stm32_toolkit/cli.py`
- `tools/stm32-toolkit/tests/test_cli_flash_regions.py` (new)
- `tools/stm32-toolkit/tests/test_external_firmware_routing.py`

[Offline flash investigation](flash-offline-investigation.md) separates source
inference from observed log evidence. Only the fresh log records normal-policy
configured 1 MHz. The two historical files are byte-identical and lack options
and runtime identity. The message matches the inspected pyOCD 0.45.1
non-running/non-halted flash-algorithm wait branch; IPSR=3 captures HardFault
context but does not determine the cause. The inspected source is not proven
to be the failing runtime. Neither a default-frequency change nor a hardware
recovery outcome is established.

The source snapshots and user logs were copied without changing originals.
Retained external copies: `D:/codex-tmp/f134/flash-inputs`; their identities are
listed in the investigation. No hardware command ran.

## Verification and evidence ownership

Before testing, the coordinator read `docs/testing/standard-test-procedure.md`,
its current checkpoint and the referenced STM32TK-134 implementation/publication
review records. Tests used the existing verified CPython environment
`D:/codex-tmp/kx23/venv/Scripts/python.exe`; no packages were installed.
Only the build WIP group used installed ARM GNU/CMake/Ninja on a synthetic project.
Every hardware-related test uses offline fakes or pure firmware admission.

| Owner | Head | Evidence directory under D:/codex-tmp/f134 | Result |
| --- | --- | --- | --- |
| Claude CLI | 0cb0ee497d460423ae161b2b248d3d303666652b | claude-cli-new | 34 passed, 0 skipped; 6.86 s |
| Claude CLI | same CLI head | claude-cli-reg | 56 passed, 0 skipped; 64.65 s |
| Primary Codex, independent clean review | 42451ea3a374cc9cc435c56cee160c9fbf63f416 | primary-cli-new | 34 passed, 0 skipped; 5.85 s |
| Primary Codex, independent clean review | same integrated CodeHead | primary-cli-reg | 56 passed, 0 skipped; 61.47 s |
| Claude CLI, retained build WIP | 42b4aa007445e27eb60c911d51817df1f385aaea | claude-build-new | **9 passed, 3 failed**, 0 skipped; 99.16 s |

Overlapping independent checks are not added to inflate coverage: the accepted
CLI set has 90 distinct tests, run by both owners. No full release matrix,
packaging, install/IDE or hardware result is claimed. Source hashes before/after
were equal in every completed run. The primary reviewed the entire accepted-base
to integrated CodeHead diff in the clean exact-head review tree. Final
`git diff --check <accepted-base> HEAD` passed after correcting coordinator-owned
specification trailing whitespace.

Each evidence directory contains `execution.json` (exact argv, head/root, owner,
all tracked source hashes, subprocess exit, timing, JUnit digest),
`junit.xml`, `stdout.log`, coverage data and native coverage JSON.
`D:/codex-tmp/f134/run_checks.py` only selects groups for the existing
`D:/codex-tmp/r132/run_checks.py` orchestrator; it adds no product/test assertions.
Fresh external JUnit and subprocess evidence were reconciled by the coordinator;
the dispatcher's own `test_report_paths` was empty because those reports are
outside each product checkout.

Exact verify commands are retained in
`claude-cli-new-v2.json`, `claude-cli-reg-v2.json` and `claude-build-new.json`
under `D:/codex-tmp/f134`. Their only main command calls the verified Python with
`run_checks.py <exact-root> <full-head> <unique-label> <group>`.
Primary runs used the same command form with `primary-cli-new` / `primary-cli-reg`
labels and a child-process-only evidence owner of `Primary Codex`.

All three verify launches had actual inventory `[PowerShell]`, matched native
`Write-Output 'CLAUDE_DISPATCH_SMOKE'` calls/results, and matched exact main commands.
Both CLI verification native success results lacked numeric exit codes, retained
as null; their subprocess evidence records exit 0. The build test command has
native executed-failure exit 1 and subprocess exit 1. No pending result was
misrepresented as completion. Two preliminary CLI verify task documents with an
empty read_scope were rejected by input validation before launch; the preserved
v2 documents only correct that metadata, with no prior test execution to retry.

## Build review findings, not accepted

At WIP `42b4aa007445e27eb60c911d51817df1f385aaea`:

1. **P1 — redirected receipt paths are not rejected.**
   `tools/stm32-toolkit/src/stm32_toolkit/build/runner.py:606` reads canonical
   JSON through normal file open; `:628` checks only the final canonical file
   with lstat. A redirected parent whose target lacks the leaf can look absent
   and admit the legacy global receipt. Publication also follows parent paths.
   Expected: selected log/result paths reject symlink/reparse/nonregular or
   uninspectable components before reuse/fallback/publication, without writing
   through a redirected parent. Static review finding; no exploit or hardware
   reproduction claimed. Required regression: redirected canonical plus
   redirected parent/absent canonical, no fallback and no redirected writes.
2. **P2 — receipt timestamp assertion is invalid.**
   `tools/stm32-toolkit/tests/test_build_preset_evidence.py:204` compares the
   debug receipt across a second debug build, although timestamps/duration may
   change. Actual test fails. Capture after debug_second and compare only across
   release_second, preserving semantic identity and no-clean checks.
3. **P2 — managed-admission fixture is not programmable.**
   Same test file `:526` passes the build-only fake ELF without PT_LOAD to
   `load_fresh_firmware_facts`, which correctly refuses FLASH_IMAGE_INVALID.
   Actual test fails. Exercise genuine managed admission with the real GCC ELF;
   do not weaken segment checks or mock the admission result.
4. **P2 — real GCC path assertions name the wrong output.**
   Same test file `:620` expects firmware.elf but this delivered fixture produces
   app.elf/app.map. Actual test fails before the complete preset journey.
   Derive exact paths from the model/identities and retain the real
   debug-release-debug no-clean and admission assertions.

Verification command for findings 2–4 is exactly the one in
`D:/codex-tmp/f134/claude-build-new.json`; failure stdout/JUnit are retained.
The product preset switching change is not accepted merely because nine cases
passed. Broader runner/stale/consumer groups were not run after this failing
gate, and no pure software failure is deferred as a platform limitation.

## Invocation audit and stop history

All local edit launches registered exactly `[Edit, Glob, Grep, Read, Write]`.
Actual registration is distinct from task authorization: the later briefs
expressly prohibited Grep/Glob even on otherwise permitted files.
No credentials, provider/model configuration or permission policy was changed.

| Run under D:/codex-tmp/f134 | Native/audit outcome |
| --- | --- |
| build-edit-run | Repeated read-scope violations (8); exact owned CLI stopped; no edits |
| guidance-edit-run | Repeated read-scope violations (10); exact owned CLI stopped; no edits |
| cli-edit-run | 8 read-scope violations discovered during full stream audit; exact owned CLI stopped; three-file implementation retained, invocation rejected |
| flash-edit-run | One src-root search outside read_scope; retained draft, invocation rejected |
| flash-review-fix-run | Bounded report-only correction completed, no scope violations |
| flash-review-fix2-run | Second bounded report-only correction completed, no scope violations |
| build-redelegate-run | User's first one-shot retry; 3 explicitly prohibited Grep calls plus one out-of-scope fixture Read; exact owned CLI stopped, WIP retained |
| guidance-redelegate-run | User's first one-shot retry; 2 out-of-scope searches; self-ended with no edits |
| build-correction-authorized-run | User's additional one-shot authorization; 2 prohibited exact-file Grep calls in one batch, then self-ended with no edits |
| guidance-authorized-final-run | Same additional authorization; 1 prohibited exact-file Grep call, then self-ended with no edits |

Each run retains task/manifest, inventory/main raw native events, analyses,
exit status and summary. The last two summaries have empty path-scope violation
lists because their Grep targets were within read_scope; the task-level tool
prohibition is independently recorded by the coordinator and ordinary worker
completion text. The coordinator stop audits found these invocations already
finished; they record null stoppedOwnedChild, not a claimed process kill.
Earlier forced stops were limited to the exact identified owned Claude child;
there is no guarantee about descendant termination, and no unrelated process
was stopped.

The coordinator's delayed detection of earlier stream violations is retained
as an audit limitation. These invocations are not retroactively accepted by
later tests, report corrections, source review or user retry authorization.
Retained product artifacts are assessed separately by the primary reviewer.

Both user-granted retry budgets are exhausted. No further implementation
invocation, ownership fallback or tool/permission expansion is authorized by
this report. The latest successful deliverable remains the CLI correction and
the bounded offline investigation; items 1, 4, 5 and 8 remain open.
