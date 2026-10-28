# FLASH-PREPARATION — independent offline acceptance

Date: 2026-10-28. Verdict: **SOFTWARE_COMPLETE_HARDWARE_PENDING**.
The required offline software scope passes after bounded Claude review corrections.
The original board's HardFault cause and the fix's physical effectiveness remain
unverified. This is **Unreleased, planned v1.3.5**, not release acceptance.

## Ownership and frozen source

- Accepted base: `528528f9e00791a96effa3a3bdb069c875fa9508`.
- Final **CodeHead before this report/checkpoint commit**:
  `1bb95790dbe1552b700f588d56e5ef9301b839a2`.
- Core checkpoint: `f88295a0180355fdb052bf33d7ee01070371c87a`.
- Complete runtime/test checkpoint before the last Skill sentence correction:
  `4b85111d03d768d2d4b35cbce78db00e94f8b4a7`.
- Branch: `codex/v135-flash-preparation`; isolated implementation workspace:
  `C:/Users/zhy76/.codex/worktrees/v135-flash-preparation/STM32-Toolkit`.
- Clean independent exact-head review workspace:
  `C:/Users/zhy76/.codex/worktrees/post134-independent-review/STM32-Toolkit`.
- Primary Codex owns design, plan, orchestration, complete-diff review, independent
  verification, this verdict and the standard procedure. The local Claude Code CLI
  owns every product/test/guide/Skill/Changelog edit, retaining the configured
  `deepseek-v4.1-flash[1m]` route (observed CLI 2.1.308). No Codex implementation
  fallback, provider/model/authentication or global permission change occurred.
- Governing [design](../../../superpowers/specs/2026-10-28-flash-preparation-design.md),
  [plan](../../../superpowers/plans/2026-10-28-flash-preparation-plan.md) and
  [standard procedure](../../../testing/standard-test-procedure.md).
  The current procedure checkpoint and referenced execution evidence were read before
  planning/executing checks.
- No PR or remote action is authorized. No hardware/probe enumeration, device connection,
  physical reset/halt/resume, flash/readback, installation, packaging, push, merge, tag or
  release occurred. Test calls to reset/program/readback were deterministic substitutes;
  local loopback services and Windows child processes supplied software evidence only.

## Accepted behavior

Both managed and imported PyOCD programming now acquire their driver and enter shared
preparation before creating/calling the programmer. Existing service MODIFY/action
authorization, target identity and verified immutable-image admission remain earlier.
Imported native Flash-map admission also finishes before preparation.

Normal preparation requests exactly one
`target.reset_and_halt(Target.ResetType.SYSRESETREQ)`, using the actual pyOCD enum.
It then reads target state and requires HALTED. There is no default-reset selection,
repair halt, resume, fallback, reconnection, frequency change or retry loop. Missing/
non-callable reset support, reset exceptions, unknown/unreadable state and every
non-HALTED state stop programming. Under-reset recovery reuses its connection reset and
only rechecks HALTED; observe-preserve refuses programming without target control.

The closed schema-1 diagnostic adds `pre-program-reset` and `pre-program-halt`.
Preparation failures retain `PROBE_PROGRAM_FAILED` and bounded sanitized diagnostics,
survive worker IPC and managed/imported result mapping, and reach no programmer,
readback or success receipt. Existing owned cleanup remains; later control does not
follow the failure. Existing `driver-acquire`, `programmer-create` and `program-call`
boundaries retain their meaning.

`details.flashOptions` adds `preProgramReset=sysresetreq` for normal or
`under-reset-connect` for recovery, plus `preProgramHaltRequired=true`.
These are selected policy, including on an early failure, never proof that a reset
executed. Existing normal 1 MHz/default-or-explicit frequency, recovery 100 kHz,
sector erase, no auto-unlock, keep-unwritten, byte readback and receipt identities remain.
Ordinary/imported flash gains no post-flash run; `postFlash` stays
`targetState=unknown, runVerified=false`. Target execution inherits preparation through
the shared backend and retains its separately authorized post-flash control sequence.
Read-only Monitor/discovery/handoff behavior is unchanged.

Guide, Skill and Changelog disclose the side effect, normal/recovery distinction,
failure stop, selected-policy fields and unpublished status. Source version metadata
remains 1.3.4 pending the separate v1.3.5 release alignment. Published v1.3.4 bytes,
installed runtimes and existing POST134 acceptance are unaffected.

## Review and verification

Primary reviewed the complete accepted-base-to-final-CodeHead diff in the clean review
tree, including all product files, new/changed tests, guide, Skill, Changelog, plans,
reports and procedure changes. Final diff checks pass. Corrections applied by Claude:
a duplicate worker factory and EOF blank line; ambiguous normal/recovery and Changelog
wording; and an imported test's immutable-internal versus serialized-public comparison.
All resulting product and test changes were independently checked; no actionable
software finding remains.

Evidence root: `D:/codex-tmp/f135`. Existing source-bound runner:
`D:/codex-tmp/r132/run_checks.py`, selected by run-local wrappers. Verified interpreter:
`D:/codex-tmp/kx23/venv/Scripts/python.exe` (Python 3.12, pyOCD 0.45.1 environment).
Each execution binds its source head, tracked-file hashes, exact pytest argv, owner,
subprocess exit, explicit same-tree PYTHONPATH, unique short temp/cache/coverage/JUnit
paths and unchanged-source check. No dependencies were installed.

| Owner / source | Labels / coverage | Passing cases |
| --- | --- | --- |
| Claude / core checkpoint | cn1, ca1, cd1: new preparation, complete adapter and diagnostic contracts | 21 / 159 / 33 |
| Primary / core checkpoint | pn1, pa1, pd1: independent core checks | 21 / 159 / 33 |
| Primary / core checkpoint | ps1–ps3: complete service authorization/lifecycle partitions | 141 distinct |
| Primary / core checkpoint | pr1, pi1: worker settlement and imported integrity/map admission | 4 / 14 |
| Primary / core checkpoint | pt1–pt3 plus pcd1: complete Target cases, with the retained timing disposition below | 202 distinct |
| Claude / runtime-test checkpoint | cf1, ch1, ce2, cdo1: frequency/preparation policy, public hardware workflows, imported workflow/routing, guide/Skill contracts | 99 / 116 / 28 / 54 |
| Claude / runtime-test checkpoint | cw1–cw4, cfl1–cfl3: all worker and managed flash partitions | 64 / 53 |
| Primary / earlier public candidate | pf1: full frequency/preparation-policy group | 99 |
| Primary / runtime-test checkpoint | pn2, pnew1: all new backend and public/IPC cases | 21 / 12 |
| Claude / final CodeHead | cdo2: final guide/Skill contracts | 54 |
| Primary / final CodeHead | pall2, pdo2: all new cases and final guide/Skill contracts | 33 / 54 |

The affected matrix has **988 distinct test identities with passing execution evidence**,
with **627 distinct Claude-owned** and **761 distinct Primary-owned** passing identities.
Owners and repeated runs are not added together. All **33 new cases** independently pass
at final CodeHead, as do 54 final documentation contracts. No case in the final required
scope remains failed or skipped. This is an affected matrix with explicit reuse, not a
single full-repository final-head rerun or release coverage qualification.

Reuse is bounded: Git comparisons prove that core/probe implementations, core tests,
service, Target, map/integrity and settlement sources remain byte-identical to their
core checkpoint. Shared public workflow changes only add selected policy metadata;
review confirms the reused service/Target cases do not consume that helper. Runtime
and test bytes at final CodeHead exactly match the fully verified runtime-test
checkpoint; only one Skill authorization sentence changed afterward, and its 54
contracts were freshly rerun by both owners. The final 33 new cases were also rerun
independently. Exact commands and hashes are retained in each task/manifest/execution.

Three successful delegated verify invocations each registered exactly native PowerShell,
ran the matched harmless smoke, and matched all 15 designated test commands in total.
There were no unexpected commands or pending results. Native numeric exit fields were
absent and remain **null**; the separate bound pytest subprocess exits are recorded as 0.
JUnit hashes/counts and unchanged-source evidence were independently reconciled.

## Retained failures and invocation limitations

- The initial stopped read-only call, coordinator scope mistake and delayed interception
  remain in [the historical report](delegation-history.md), its Git history and edit-run.
  It made no edits. The user-approved core-edit-run then failed at the upstream thinking
  API after 14 read/search calls, also with no edits. The user explicitly authorized a
  restart; no model/provider/permission workaround was used.
- core-restart-run completed normally with 19 successful native edits but retained five
  read-scope audit flags. These include a literal Glob confined to the named test file,
  plus related Toolkit parent searches. public-edit-run retained two root-path audit
  flags (patterns/globs confined to the Toolkit module), made 23 successful edits and
  reached its 100-turn limit. Their launcher acceptance remains false; it is not
  retroactively rewritten as passing. The coordinator inspected actual targets/results
  under the user's approved related-module read/search allowance. All successful writes
  matched their exact allowed files; no unrelated project, credential, shell or hardware
  access was observed. Product acceptance rests on complete independent diff review,
  frozen source and actual checks, not a claimed successful invocation.
- review-fix-run, import-assert-fix-run and skill-auth-fix-run completed with matching
  native file tools, successful scoped edits and no audit discrepancies. File editing,
  test execution and passing are recorded separately. Normal model completion or CLI
  exit alone was never counted as proof.
- pe1 produced 26 pass / 2 fail: the two new imported stage tests compared nested immutable
  mapping/tuple data directly with JSON dict/list data. Claude corrected the assertions
  to use the public serialized result, preserving every stop/receipt/cleanup assertion.
  ce2 passed all 28 cases, and final independent new-case checks passed both stage cases.
  Product behavior was not weakened to satisfy the test.
- pt3 produced 62 pass / 1 fail in the unchanged
  `test_target_discovery_accepts_one_canonical_inventory_without_eof_at_deadline`.
  It has a real 30 ms deadline and uses FakeFlashWorkflow, not the changed PyOCD path.
  Its test and discovery implementation are unchanged from accepted base. One bounded
  serial baseline control (bd1, not counted in feature passes) and one serial candidate
  check (pcd1) both passed without changing code, deadlines or assertions. This supports
  environment/timing sensitivity; the precise scheduling cause is unproven. The original
  partition remains a failed run and is not relabeled PASS; its 62 passing cases and the
  separately passing case are reconciled by identity. No test was disabled, quarantined
  or given a relaxed timeout. Future full release qualification must retain this history.

## Delivery and pending physical work

Required offline software gates pass after review fixes. Changes are retained on the
local feature branch; no merge/remote publication or installation is implied. The old
integration checkout remains available as its baseline, and the exact final review tree
is retained for reproducibility.

Hardware acceptance remains owned by **Primary Codex in a separately authorized later
hardware qualification phase**. Before any device operation, that owner must bind the
actual packaged/runtime/source and firmware identities, known initial target state,
ownership and finite budget in the standard execution card. The procedure changes
require independent review by a reviewer who did not author the procedure (the local
Claude Code CLI may perform that review) before the dependent hardware step. This
offline report supplies neither that review nor hardware authority.

A future controlled comparison must establish that normal programming at the selected
frequency now completes reset/halt, programming and readback with real evidence. Recovery
reuse and no duplicate reset need their own applicable authorized check; there is no
automatic retry or recovery fallback. The original IPSR=3 fault may have another cause.
Packaging, version alignment, full release matrices/coverage, installation and physical
qualification are separate phases. Existing v1.3.4 exceptions/limitations do not transfer.

## Evidence integrity

The retained raw streams, tasks, manifests, execution records, source hashes, JUnit,
coverage and original failure outputs remain external; no credential is included here.

| Artifact under D:/codex-tmp/f135 | SHA-256 |
| --- | --- |
| final-reviewed.diff (accepted base to final CodeHead) | dd82c0a665c35970ea289b800bf83cd3c0b417d2994b99b333288228d08ccdc6 |
| matrix.json (deduplicated identities and retained failures) | b4a0b8e0a6ca2e633fb9305c2ff32520b59c922535f4574f259afbdc6013c643 |
| delegation-audit.json (native tools, scopes, edits and commands) | 68c5afa3d22c4ef2fb9d985228357b7a8ba2adfa35b9964c48b60dcbe595deb8 |
