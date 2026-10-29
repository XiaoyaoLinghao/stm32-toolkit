# ATTACH-PROGRESS — independent offline acceptance

Date: 2026-10-29. Verdict: **SOFTWARE_COMPLETE_HARDWARE_PENDING**.
The required offline scope passes after bounded Claude review corrections.
The earlier physical attach timeout and IPSR=3 cause remain unverified.
This is **Unreleased, planned v1.3.5**, not release acceptance.

## Ownership and source

- Accepted base: `e4d9118e1c83f139db2959acbd4076a357c37992`.
- Final **CodeHead before this report/checkpoint commit**:
  `e8d7e16436dc7130ec70b6fea0efdc8650ce791a`.
- Runtime/guide checkpoint: `9f7c142d9237fdc24b3eb14b02029f232c377e5d`.
- Branch: `codex/v135-attach-progress`; implementation workspace:
  `C:/Users/zhy76/.codex/worktrees/v135-attach-progress/STM32-Toolkit`.
- Clean exact-head independent review workspace:
  `C:/Users/zhy76/.codex/worktrees/post134-independent-review/STM32-Toolkit`.
- Primary Codex owns architecture, design, plan, orchestration, complete-diff
  review, independent verification, this verdict and the standard procedure.
  Local Claude Code CLI owns all runtime/test/guide/Changelog changes, retaining
  the configured `deepseek-v4.1-flash[1m]` route. No implementation fallback,
  provider/authentication/global-permission or execution-policy change occurred.
- Governing [design](../../../superpowers/specs/2026-10-29-attach-progress-design.md),
  [plan](../../../superpowers/plans/2026-10-29-attach-progress-plan.md), including
  its bounded baseline-test correction, and
  [standard procedure](../../../testing/standard-test-procedure.md).
  The procedure, current checkpoint and latest execution report were read before
  planning/executing checks.
- No PR or remote action authorized. No real probe enumeration/connection,
  target reset/halt/resume/read/programming, original firmware access, hardware
  experiment, installation, packaging, push, merge, tag or publication occurred.
  Loopback services, owned Windows children and fake driver/Session objects
  supplied software evidence only. Installed runtime and version metadata remain
  unchanged; source metadata is still 1.3.4 pending separate release alignment.

## Accepted behavior

An existing attach timeout/cancellation diagnostic may now include optional
`attachDiagnostic.progress`. Its closed version-1 object contains only
`clock=parent-receipt`, bounded integer `elapsedMs` and ordered stage-entry events.
Absent progress retains the exact old five-field diagnostic. Success/ready/error
result envelopes and public successful attachment payloads retain their contract.

Stages cover parent dispatch, driver acquisition, probe enumeration, prior close,
Session creation/open, target resolution/identity and the existing halt or resume
branch. Enumeration is marked only after the existing lazy driver acquisition
returns, before the existing single enumeration. A scoped callback emits nothing
for ordinary discovery outside open_attach. There is no warmup, extra import,
enumeration, hardware call, state repair, connection or control action.

Small frames use the existing owned IPC stream and match the exact active
open_attach worker request ID. The parent timestamps receipt under the original
absolute deadline; progress never renews it. Unknown, wrong-ID, malformed,
reordered, duplicate, nonattach, excessive and post-freeze frames fail closed
through existing worker cleanup. Raw child diagnostics cannot provide public
progress or parent timestamps.

A fresh private service token scopes each attempt. The local detached snapshot
does not acquire the blocking call lock or perform IPC/target reads. It survives
owned abort and is omitted for missing/invalid/mismatching snapshots or an
undispatched queue. Existing primary diagnostic, late-error/cleanup merging,
cancellation, normal 5-second/Monitor 35-second budgets, terminal wait,
frequencies, authorization and flash preparation remain unchanged.

These are approximate observed software entry markers, not exact hardware
durations, phase-completion or target-state proof. Unreceived buffered markers
are not invented. The trace contains no token, probe/target identity, path,
address, register or raw exception text. User guide and Unreleased Changelog
describe availability and limits; no new CLI option or telemetry file sink exists.

## Independent review and corrections

Primary reviewed the complete accepted-base-to-final-CodeHead diff in the clean
review tree, including every runtime/test/document change. No actionable finding
remains. Claude applied these bounded corrections:

1. Driver/enumeration markers originally both preceded actual acquisition, which
   would mislabel an import stall. They now straddle real operations. Tests
   verify one lazy fake-factory construction, the unchanged two cached helper
   lookups, one enumeration and the actual interleaving; acquisition failure
   produces no enumeration marker or operation.
2. Frozen metadata originally silently discarded later frames before order checks.
   It now rejects them while preserving the frozen snapshot. Hostile IPC,
   immutable snapshots, queued-token isolation and deadline behavior are checked.
3. Coverage now includes recursive hostile values, real Windows spawned fake
   MODIFY attach timeout, owned abort and retained last stage with no late
   program/control. Test setup waits for parent receipt within a finite budget.
   Primary caught helper-count/prefix and setup-race assertion problems before
   execution; Claude corrected them without relaxing product deadlines.
4. Final new partition cf4 exposed one actual failing assertion: it tested a
   bound `is_alive` method instead of calling it. The output showed a stopped
   thread. Claude changed only that expression; fresh cfr4 and all final Primary
   cases pass. The original failed run remains failed.
5. Complete Monitor regression exposed an unchanged `git_calls == 8` assertion.
   Candidate cmo1 and accepted-base e4d9118e control bm1 both failed with zero.
   Source confirms Git is optional stored traceability, not live admission.
   The plan bounded a Claude test-only correction to require zero runtime Git
   calls; all other guard, load, DWARF/SVD, attach, read-order and lifecycle
   assertions remain. Final complete Monitor checks and independent fixed-case
   execution pass; Monitor runtime was not edited.

## Verification and bounded reuse

Evidence root: `D:/codex-tmp/ap135`. Existing verified interpreter:
`D:/codex-tmp/kx23/venv/Scripts/python.exe`, Python 3.12.14/pyOCD 0.45.1 environment.
Source-bound runners pin HEAD/tracked hashes, actual filtered pytest argv before
launch, owner, fresh short temp/cache/coverage/JUnit paths, actual subprocess exit
and unchanged-source check. No dependencies were installed.

| Owner / evidence | Coverage | Passing distinct cases |
| --- | --- | --- |
| Claude / cr1-cr3 | Complete adapter, diagnostic/protocol and client suites | 159 / 157 / 75 |
| Claude / cr4-cr13 | All worker and service partitions | 64 / 141 |
| Claude / cr14, cr16-cr20 | Public hardware workflows, frequency, managed flash, guide contracts | 116 / 99 / 53 / 54 |
| Claude / cmf1-cmf2 | Complete final Monitor observation module | 79, plus 1 platform skip |
| Claude / cf1-cf3 and cfr4 | All final new attach-progress cases | 66 |
| Primary / pf1-pf4 | All new cases freshly at exact final CodeHead | 66 |
| Primary / pm1 | Fixed Monitor guard case freshly at exact final CodeHead | 1 |

Final affected matrix: **1,063 distinct passing cases**, with **1 named platform
gate deferred**. Claude has passing evidence for all 1,063; Primary independently
ran 67 distinct cases. Owners/reruns are not added. Two service selector-prefix
overlaps are deduplicated by JUnit identity (143 executions, 141 distinct cases).
The earlier 59-case draft passes remain historical and are not added to this count.
This is not a single final-head full-repository run or release coverage qualification.

Reuse is explicit and source-checked. All runtime, guide and existing regression
test bytes are unchanged from runtime checkpoint 9f7c142d; later changes affect
only the new test file, the one Monitor test and the plan addendum. Existing
regressions do not import the new test module. Monitor was fully rerun at final
CodeHead. cf1-cf3 ran at 7cae3825; the only subsequent source change is the queued
test's one-line liveness assertion, outside those selected cases. AST comparison
proves all other module nodes/globals unchanged. cfr4 freshly covers the changed
partition, and Primary freshly reran every new case at final CodeHead.

Primary reconciled matched native commands/results, fresh JUnit hashes/counts,
actual argv sidecars and recorded source hashes. LF/CRLF checkout variants are
handled only as Git line-ending variants; unexpected source changes fail the
reconciliation. Successful verify invocations registered exactly native
PowerShell and executed the matched harmless startup smoke. Native numeric
success exit fields were absent and remain null; actual pytest exits are recorded
separately. No execution was inferred from CLI exit/model claims alone.

The unchanged skipped case is
`test_real_supervisor_thread_swap_after_identity_check_writes_no_replacement_state`,
reason **Windows directory handles deny rename**. Owner: **Primary Codex**;
deferred phase: **release qualification on a rename-capable Linux host**.
The test was not changed, disabled or marked PASS. No pure code failure is deferred.

## Retained invocation failures and limitations

- The original stopped typo search, its unauthorized path correction and zero
  writes remain in [delegation history](delegation-history.md) and edit-run.
  The user explicitly authorized the one replacement.
- replacement-run reached error_max_turns (CLI exit 1, 101 turns) after 43
  successful native file edits. It retains three read-scope audit flags: default
  Glob path, docs-directory search and Toolkit src-parent search. review-fix-run
  finished normally (CLI 0, 19 native edits) but retains one Toolkit-parent read
  flag. Neither invocation is retroactively marked accepted. Actual outputs were
  inspected; observed extra reads were within this repository's related source,
  tests and connection documentation. All successful writes matched the exact
  task file lists, with no shell/hardware/credential or unrelated-project access
  observed. Product acceptance rests on full independent review and bound checks,
  not invocation success claims.
- Later test-only edit invocations completed with matching native tools, scoped
  writes and no audit discrepancy. File editing and test execution are separate.
  Normal review-fix tasks applied concrete findings; failed invocations were not
  resumed/restarted or hidden, and no unavailable-tool workaround was used.
- cr15 was a coordinator-owned pre-pytest routing error: inherited runner group
  `monitor` selects another package. No Monitor pytest process/JUnit was produced.
  The failed starter is retained. A tiny separate run-local adapter selected the
  correct Toolkit module, leading to cmo1's real stale-assertion failure. Only
  genuinely unexecuted checks were scheduled; passing regressions were not rerun.
- cmo1, baseline bm1 and cf4 retain their actual failed results. Subsequent
  changed-source checks pass; original failures are not relabeled. No assertion
  was removed, skipped, or given a relaxed deadline to obtain a pass.
- External source-bound selectors record actual pytest argv in a sidecar; the
  inherited execution record itself contains the base argv. Both are retained.
  Dispatch provides prompt/audit boundaries, not an OS sandbox or guaranteed
  pre-execution interceptor. Its raw scope discrepancies remain visible.

## Delivery and next phase

Changes are retained locally on the feature branch. Required non-deferred
software gates pass, with the named platform gate above assigned to later release
qualification. No remote, installation or packaging action is implied. Previous
v1.3.4 publication exceptions/limitations do not transfer to planned v1.3.5.

Physical validation remains owned by Primary in a **separately authorized later
hardware phase**. It must bind the actual source/runtime/firmware/probe identities,
current target state/ownership, a new finite budget and the updated entry contract
in a fresh execution card. The Primary-authored procedure change needs independent
review before that dependent hardware step. The earlier single authorization is
consumed; these software tests grant no connection, read, reset, flash or recovery.

| Artifact under evidence root | SHA-256 |
| --- | --- |
| matrix.json | 21c690819757cae4b80621a0999ac7a48707509c2eb17168bb997922d9b4621f |
| delegation-audit.json | f1e82e6a3268942f19aa071f62c3201923f52bb776d2eb1e228b50eb5d564614 |
| final-reviewed.diff | a4b0330bf4c392b7d6e7e81e0761c0b6e27417235d087c9a0d3e1e778955215f |
| draft-reconciled.json | 5bb4c75b6bcec129984846c9a310d5052702f0555276071cb97bec42d1bb396d |
