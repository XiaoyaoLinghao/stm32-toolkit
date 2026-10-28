# POST134 usability corrections — independent acceptance

Date: 2026-10-28. Verdict: **ACCEPTED_WITH_FIXES (local offline software scope)**.
Items **1, 3, 4/5 and 8** are complete. Item **2** is complete only as an offline
investigation; its hardware failure remains unresolved. These changes belong to
**Unreleased, planned v1.3.5**. This is not release or hardware qualification.

Subsequent primary-owned issue 2 investigation is recorded in
[the offline follow-up](flash-offline-followup.md). It found a successful under-reset
receipt and confirmed that the normal API path lacks the CLI's pre-program reset.
The physical cause remains unproven; this is a new proposed correction, not an
implemented or hardware-qualified fix. The acceptance below covers the earlier scope.

The prior partial disposition, its failed calls and test results remain in
[partial-review-2026-10-28.md](partial-review-2026-10-28.md) and the original external
evidence. Later acceptance does not retroactively accept those invocations.

## Ownership and frozen source

- Accepted base: `7e578ca1395ffa3b9743bef5a9fe55c40912eed6`.
- Integrated **CodeHead before this report/checkpoint commit**:
  `29d13fc75881bfc771d81aa1c54f45948a6fa0f0`.
- Integration branch: `codex/v134-fixes-integration`, workspace
  `C:/Users/zhy76/.codex/worktrees/v134-fixes-integration/STM32-Toolkit`.
- Independent clean exact-head review workspace:
  `C:/Users/zhy76/.codex/worktrees/post134-independent-review/STM32-Toolkit`.
- Build implementation head:
  `cea47d13c0c7e75c8d8600b2e3c053c94f71b447`.
- Guidance implementation head:
  `f524ed2c602ba2afdbd540a8825c6504e02307a3`.
- Primary Codex owns specification, plans, orchestration, complete-diff review,
  independent verification and this verdict. Product code, tests and user-facing
  documentation were edited by the local Claude Code CLI using the user's existing
  `deepseek-v4.1-flash[1m]` route. No provider/model/authentication changes or Codex
  implementation fallback occurred.
- Scope: [specification](../../../superpowers/specs/2026-10-28-post134-usability.md),
  [initial plan](../../../superpowers/plans/2026-10-28-post134-usability.md),
  [resumption plan](../../../superpowers/plans/2026-10-28-post134-resumption.md).
  The latest user authorization permits related-module Read/Grep/Glob and continued
  bounded Claude implementation; exact write and command boundaries remain.
- No PR or remote action is authorized. No push, tag, release, installation, package
  build, version-number alignment, original-project modification or hardware access
  occurred. The original `D:/WorkSpace/STM32-Toolkit` checkout was not the implementation
  or test source.

## Accepted behavior and review

**1 — Per-preset evidence.** arm-debug retains
`artifacts/migration/build-result.json` and `build.log`; arm-release owns the same
filenames under `artifacts/migration/arm-release/`. Identities and ELF/MAP paths
remain under `build/<preset>/`. Stage errors, success/failure publication, result
payloads and stale guidance consistently name the selected preset. Paths are immutable
per-request values, not mutable global state. Normal preset switching needs no clean.

Legacy release reuse is allowed only when the canonical release receipt is truly absent.
Present invalid/failed/redirected canonical evidence never falls back to the old global
receipt, and debug evidence cannot become release evidence. Existing schema-1/schema-2
identity, input snapshot and artifact validation remain. Receipt/log components are
checked for ordinary file/directory types, symlinks and Windows reparse attributes before
reuse/fallback and publication. This is bounded path validation, not a claim of protection
against an adversarial concurrent filesystem replacement.

The real ARM GNU journey verifies debug -> release -> debug without clean. Immediately
after release, before the second debug build, the original debug context is fresh and
the genuine shared firmware admission accepts its original identity/hash/path/target.
Failure isolation and both evidence schemas are covered. A debug receipt already lost
to an old version's global release overwrite cannot be reconstructed; the guide discloses
the possible one-time, explicitly authorized debug clean rebuild.

**3 — CLI diagnostics.** The previously accepted change is retained unchanged. The exact
schema is 1..32 objects with only integer start/length; name/origin are unsupported.
Closed diagnostics preserve exit 2, identify a bounded region index where applicable,
and do not echo arbitrary caller bytes. Help shows the schema. Range/security validation
stays in the existing workflow.

**4/5 — Migration and debug guidance.** Destination PLAN and successful APPLY expose the
shared non-blocking post-migration debugConfiguration. Their followUp stays a string
derived from the same nextSteps. Guidance binds the destination root, names the paired
configure PLAN/exact-plan APPLY, places that edit before establishing firmware identities,
and uses the correct fresh-build response paths data.identity.buildId/elfSha256.
Preflight shares debugConfiguration; it does not promise followUp.

Migration remains valid with debug:{} and no inferred backend/target. Generated
launch.json deliberately keeps an empty configurations array. The guide explains that
an authorized handoff-begin supplies data.cortexDebugLaunch.configuration for an
independent external IDE workspace; the IDE detaches before handoff-end with the original
ticket. No static launch bypass, generated-byte change, plan/content hash input, new
tool, automatic action or hardware authority was added.

**8 — Release documentation.** Changelog records the already-implemented v1.3.3 legacy
runtime/producer recognition, explicit Repair/configure requirements and retained guards.
Frozen v1.3.4 package wording is distinguished from current publication records.
New build/CLI/guidance corrections are Unreleased, planned v1.3.5; published v1.3.4 tags
and assets remain frozen.

**2 — Offline investigation.** The accepted
[offline report](flash-offline-investigation.md) retains pinned evidence and separates
observations from hypotheses. IPSR=3 does not establish root cause. Frequency and
under-reset mode are independent variables; combined recovery success does not prove
a 100 kHz default would fix the normal path. No flash behavior was changed.

Primary review covered the complete accepted-base product/test/documentation diff.
In the clean integrated review tree, Git comparisons confirmed exact equality to the
reviewed build and guidance branch files and to the unchanged CLI files from
`42451ea3a374cc9cc435c56cee160c9fbf63f416`. Product/user-documentation diff checks pass.
No remaining actionable software finding is deferred.

## Verification evidence

Procedure/checkpoint and its referenced latest report were read before testing.
No dependencies were installed. Verified test interpreter:
`D:/codex-tmp/kx23/venv/Scripts/python.exe`.
The real synthetic project used the installed ARM GNU/CMake/Ninja tools under
`C:/ST/STM32CubeCLT_1.22.0/`; no probe or board was accessed.

Fresh evidence root: `D:/codex-tmp/f134r`. Each label below contains execution.json,
stdout.log, JUnit, source hashes and native coverage output. Reports bind exact source,
argv, owner, elapsed time and subprocess exit; all successful runs record sourceUnchanged.
The run-local run_checks.py selects existing tests and partitions; it adds no product
assertions. Its chain of hashes, JUnit digest checks and unique test identities are in
final-matrix.json; native tool audit is in delegation-audit.json.

| Owner / source | Labels and groups | Result |
| --- | --- | --- |
| Claude CLI / build head above | cbn: new preset cases including real GCC | 15 passed |
| Claude CLI / build head | cbr1/cbr2/cbr3/cbr4: complete runner partitions | 28/32/20/20 passed |
| Claude CLI / build head | cbs: snapshot; cbg: stale guidance | 50/27 passed |
| Claude CLI / build head | cbc: context; cba: firmware admission; cbf: flash with doubles | 49/27/51 passed |
| Claude CLI / guidance source | cgn2: public guidance/workflows; cg1b/cg2c: complete delivery partitions | 36/17/22 passed |
| Claude CLI / guidance source | cgwc: independent migration; cgcc: debug configuration | 10/51 passed |
| Claude CLI / unchanged guidance docs | cgd: AI/VS Code/task contracts | 93 passed, 1 platform skip |
| Primary Codex / exact integrated CodeHead | pin: all new preset/CLI/migration cases | 52 passed |
| Primary Codex / exact integrated CodeHead | pic: context/admission/debug workflows | 109 passed |
| Primary Codex / exact integrated CodeHead | pid: delivery partition containing new APPLY contract | 22 passed |

Build has **319 distinct passing tests**; guidance has **229 passing, 1 skipped**.
The unchanged CLI's **90 distinct tests** retain both Claude and independent evidence
under `D:/codex-tmp/f134/claude-cli-new`, `claude-cli-reg`, `primary-cli-new`,
`primary-cli-reg`, as detailed in the partial report. Its 34 new cases were also
rerun in pin at final CodeHead. Total affected matrix: **638 passed, 1 platform skip**;
repeated owners/runs are not added again. Primary final-head checks: **183/183 passed**.

Reuse is explicit: guidance checks at f213b5ad and 9ae8f5c7 cover unchanged product/docs
and selected tests; later changes only correct the two new test assertions, whose affected
groups were rerun. This is an affected matrix with unchanged-source reuse, not a final-head
full-repository rerun or release-coverage qualification.

The skipped preexisting VS Code test is test_redirect_targets_are_refused: this Windows
host cannot create the required file symlink. Real symlink execution remains DEFERRED
to a capable host in the next release qualification, owned by that qualification's
coordinator. New receipt reparse tests inject lstat evidence and pass; they are not
misrepresented as native-junction hardware/platform acceptance.

Representative command form (exact expanded commands are in each task/manifest):
`& 'D:/codex-tmp/kx23/venv/Scripts/python.exe' 'D:/codex-tmp/f134r/run_checks.py' '<root>' '<full-head>' '<label>' '<group>'`.
Primary independently uses the same bound runner with owner Primary Codex.

## Retained failures, native provenance and corrections

- Earlier f134 partial work and all failures remain unchanged; see the historical report.
- build-edit-run and guidance-edit-run reached the CLI 100-turn limit. Their edits were
  preserved and reviewed, not silently restarted or declared completed. Native inventories
  matched Read/Edit/Write/Glob/Grep; no shell or hardware tool was available in edit mode.
- build-edit-run records one attempted Edit to a mistyped, unallowed nonexistent path and
  one mistyped read path. The Edit failed before modifying that path. All successful edits
  are confined to the two allowed files; Git tracked/untracked review found no extra files.
- guidance-edit-run has eight read-scope audit mismatches; guidance-launch-test-edit-run
  has seven, including default-root searches and a relevant launch template path.
  The coordinator inspected those native outputs: they concern the requested modules,
  guidance/version metadata or nonexistent paths, with no credential, external-project,
  shell or hardware access. These invocations remain audit-rejected; later related-module
  permission does not rewrite their manifests or erase the scope discrepancies.
- Subsequent bounded product/test corrections retained implementation ownership. Fixed:
  wrong build-response identity paths; the missing immediate post-release real admission
  checkpoint; public JSON vs internal frozen mapping comparisons; and launch.json's
  top-level configurations assertion. A mistaken optional-name Changelog brief from the
  coordinator was corrected to the unchanged exact CLI schema before acceptance.
- cgn originally produced 35 pass/1 fail (frozen preflight mapping compared to public JSON).
  After the targeted serialized-response correction, cgn2 passed 36/36. cg2b produced
  21 pass/1 fail (incorrect nested launch key); cg2c passed 22/22 after that test fix.
  Original stdout/JUnit/native results remain; no pure code failure is deferred.
- Every verify launch passed matching actual PowerShell inventory and a real native
  harmless smoke. Each designated command has a matched native call; no unexpected shell
  command was accepted. Missing native numeric exit codes remain null. Model prose and
  CLI exit alone are never test evidence.
- cbg's native call returned structured background_pending with started=true and no
  terminal numeric exit. The worker reported pending and ended. Primary reconciled the
  same already-started bound execution.json/JUnit/source hashes: subprocess exit 0,
  27 passes, unchanged source, 189.13 s. No command rerun, polling by the worker, tool
  expansion or process interference occurred; the native pending result remains intact.

## Delivery limits and next phase

The local software slice is accepted with the above reviewed fixes. Source version
metadata remains 1.3.4; the new user-facing behavior is marked Unreleased for v1.3.5.
Version alignment, packaging, full release qualification, installation, remote publication
and hardware work are separate later phases and are not authorized by this report.
Existing v1.3.4 release limitations and candidate-specific exceptions do not transfer.

Implementation worktrees were clean after local commits; all current evidence is external
under f134/f134r. The integration checkout and exact-CodeHead independent review checkout
are retained. Completed build/guidance worktrees were recoverably archived after checking
that they had no untracked or ignored files; local Git commits and the external abnormal
logs remain the durable record.
