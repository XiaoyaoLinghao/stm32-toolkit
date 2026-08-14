# STM32TK-0600 Release Acceptance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate the three accepted 0.6 modules, prove the frozen final CodeHead once with the complete release matrix, create a report-only acceptance commit, and stop before any unauthorized remote release action.

**Architecture:** Each module enters through an accepted report commit and immutable evidence inventory. The 0603 product commit is the only final CodeHead. Ordered preflight must already prove every final gate at that CodeHead; the final controller then performs one fail-fast run in a clean isolated worktree. Reporting is a separate child commit and cannot repair product or evidence.

**Tech Stack:** Git/worktrees, PowerShell 5.1, Python 3.10/3.12, Node/npm, Playwright browsers, pytest/coverage, wheel/pip offline install, real STM32 board/probe/transports, SHA-256 artifact inventories.

## Global Constraints

- Program base is exactly `bb6bc5e9ee937e4ce53996b31f25bf1109ffe13f` (`v0.5.0`).
- Follow all four 2026-08-14 STM32TK-0600/0601/0602/0603 design specifications.
- This plan starts only after 0601 and 0602 have accepted report commits and 0603 has a candidate
  PASS plus ordered preflight PASS at one frozen product CodeHead.
- No product, test, helper, dependency, version, generated dist, documentation, Skill, gate, or
  threshold edit is allowed after final freeze. Any such edit invalidates the CodeHead and sends
  work back to the owning module plan.
- Test logs/results/screenshots/traces/wheels/coverage/manifests live in an external evidence root.
- Every required platform/hardware result is PASS or the release is BLOCKED/FAIL; no fake, skip,
  deferred, or another owner's stale evidence is promoted to PASS.
- Remote push/PR/merge/tag/branch deletion requires a new explicit user authorization.

## Execution Order and Requirement Coverage

| Phase | Plan tasks | Required result before the next phase |
|---|---|---|
| 0601 contract foundation | 0601 Tasks 1--10 | frozen gate catalog, evidence/test schemas, Project v3, Host/Target tests, four real transports |
| 0601 acceptance | 0601 Task 11 | candidate PASS and report-only accepted-base commit |
| 0602 diagnostic product | 0602 Tasks 1--10 | hash chain, hypotheses, observations, controls, fix verification, bundle, real-board loop |
| 0602 acceptance | 0602 Task 11 | candidate PASS and report-only accepted-base commit |
| 0603 analytics product | 0603 Tasks 1--12 | history v2, comparison/quality, annotations, UI, bundles, version 0.6.0 |
| 0603 freeze | 0603 Task 13 | candidate and ordered-preflight PASS at one immutable product CodeHead |
| release closure | this plan Tasks 1--8 | one final matrix, reconciliation, report-only commit, remote-action stop |

No task from a later row begins before the preceding row's required result. Software fakes own
unit/integration evidence; named external owners must separately supply Windows, Linux, browser,
and real-board results. A missing external owner or platform blocks that module instead of
shrinking the matrix.

---

## Task 1: Reconstruct and freeze the release ledger

**Files:** none; write the ledger into external evidence metadata, not a product file.

- [ ] Record full SHAs for v0.5.0 base, 0601 product/report, 0602 product/report, and 0603 product
  CodeHead. Verify each parent/ancestry relationship and that every report commit changes only its
  declared report path.

```powershell
git merge-base --is-ancestor bb6bc5e9ee937e4ce53996b31f25bf1109ffe13f <0601-product>
git diff-tree --no-commit-id --name-only -r <0601-report>
git diff-tree --no-commit-id --name-only -r <0602-report>
git merge-base --is-ancestor <0602-report> <0603-product>
```

Expected: each ancestry check exits zero; each report tree lists exactly one implementation report.

- [ ] Record specification owner, implementer, reviewer, module branches/PRs if any, exact remote
  state, authorized actions (none for this plan), and bounded overrides (none unless explicitly
  restated by the user).

- [ ] Audit tracked/untracked, committed/uncommitted, pushed/unpushed state for the source workspace
  before creating an acceptance worktree. Preserve unrelated state and never clean/delete it.

- [ ] Hash the four design specs, four implementation plans, gate catalog, controllers, verifier,
  dependency locks, source inventory, and support manifest into `release-ledger.json` in the
  external evidence root.

## Task 2: Create a clean isolated final worktree

**Files:** none in the repository.

- [ ] Resolve an explicit new directory under `C:\tmp` on Windows and an equivalent external path
  on Linux. Verify it does not exist, then create a detached worktree at the full 0603 CodeHead.

```powershell
git worktree add --detach C:\tmp\stm32tk-0600-final-<short-codehead> <full-0603-codehead>
git -C C:\tmp\stm32tk-0600-final-<short-codehead> rev-parse HEAD
git -C C:\tmp\stm32tk-0600-final-<short-codehead> status --porcelain=v1 --untracked-files=all
```

Expected: exact full SHA and no status output.

- [ ] Verify the worktree's Git common directory/repository identity, no symlink/junction/reparse
  point within the tracked tree, accepted-base ancestry, `git diff --check`, expected path list,
  exact source inventory, package/dist manifest closure, dependency lock digests, and no extra
  tracked release artifacts.

- [ ] Create a unique external evidence root containing the full CodeHead in its name. Refuse reuse
  if it already contains files. Record absolute tools and versions for Git, PowerShell, Python
  3.10/3.12, Node, npm, pip/build, browsers, probe tools, and hardware identifiers.

- [ ] Verify the performance owner matches the frozen Ryzen 7 5800U/16 GB/WDC PC SN530 NVMe/
  Windows 11 x64 High performance reference profile. Record the exact OS build, AC/battery,
  antivirus state, free disk, and background-load preflight. If a calibrated component differs,
  require the pre-implementation prior-CodeHead calibration evidence; do not calibrate now.

## Task 3: Reconcile ordered preflight rather than rerunning product tests ad hoc

**Files:** none.

- [ ] Load 0603 ordered-preflight results and verify every final gate ID appears exactly once,
  every result is PASS, and every result binds the final CodeHead, gate catalog digest, support
  manifest, dependency locks, platform, tool versions, command, cwd, UTC, node inventory, exit,
  duration, and retained evidence bytes/SHA-256.

- [ ] Verify preflight includes all of these partitions:

  1. whole-ancestry Git/source/scope/inventory/immutability/clean-tree;
  2. Windows/Linux CPython 3.10/3.12 complete Toolkit and Monitor suites;
  3. changed product file branch coverage >=90%, with controller tests excluded;
  4. all unchanged 0.5 performance thresholds plus 0601/0602/0603 absolute and <=15% regressions;
  5. Node typecheck/E2E typecheck/lint/unit/a11y/coverage/build/dist/audit;
  6. Chromium both viewports/security/a11y/isolation/five-minute performance;
  7. Linux Firefox/WebKit core flows;
  8. four real Target transports and real failed-before/fixed-after diagnostic/Monitor scenario;
  9. deterministic evidence/diagnostic/analysis bundles and corruption/security mutations;
  10. two-workspace isolation across Toolkit, Probe, Monitor, browser, evidence, and exports;
  11. reproducible wheels, offline dual-Python install/smoke, managed launchers, plugin/Skills;
  12. version/schema/docs/non-goal/release artifact inventories.

- [ ] Compare node inventories to fresh `--collect-only`/test-list outputs without running test
  bodies. Missing, extra, renamed, duplicated, deselected, skipped, xfailed, or blocked required
  nodes fail reconciliation.

- [ ] Verify no preflight result predates the final CodeHead or came from a superseded CodeHead.
  If any requirement fails, stop: do not run final and do not patch the final worktree.

## Task 4: Run the one complete final matrix

**Files:** none; controller outputs only to the external evidence root.

- [ ] Confirm immediately before launch: isolated worktree clean, product SHA exact, evidence root
  empty except immutable ledger/preflight inputs, no coverage environment leakage, local package/
  browser/probe support present, named real hardware connected, and no remote Git/network action in
  controller commands.

- [ ] Run exactly once:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File tools/release/run_0600_final.ps1 -EvidenceRoot C:\tmp\stm32tk-0600-final-evidence-<full-codehead> -ExpectedCodeHead <full-codehead>
```

Expected: fail-fast controller exits zero and its summary says overall PASS. It runs the complete
matrix, not a cached-result-only shortcut; preflight merely authorizes the attempt.

- [ ] On failure, preserve the full external evidence root and report one concise failure summary.
  Do not rerun final, edit thresholds, patch a test/helper/product, or write a report. Classify the
  owner and return to the appropriate module plan; the correction creates a new CodeHead and
  requires candidate plus ordered preflight again.

- [ ] On PASS, verify post-run worktree status is clean and HEAD unchanged. Hash the controller
  summary and every retained result/log/screenshot/trace/coverage/performance/wheel/manifest.

## Task 5: Reconcile final evidence and release truth

**Files:** none yet.

- [ ] Independently run the read-only verifier over the final evidence root and frozen catalog:

```powershell
py -3.12 tools/release/verify_0600_release.py final-evidence --repo C:\tmp\stm32tk-0600-final-<short-codehead> --evidence C:\tmp\stm32tk-0600-final-evidence-<full-codehead> --expected-code-head <full-codehead>
```

Expected: PASS with zero missing/extra/duplicate gates, nodes, artifacts, hashes, or platforms.

- [ ] Recompute SHA-256/bytes for every retained artifact, compare source/package/dist inventories,
  confirm wheel repeatability and offline installed smoke results, and verify before/after clean
  status evidence.

- [ ] Inspect hardware evidence identities: each transport has a real independent run; diagnostic
  before/after identities differ as expected; authorized actions form a single-use chain; final
  Target test and Monitor assertion bind the new firmware.

- [ ] Inspect browser evidence: both required viewports, keyboard workflow, exact security headers,
  DOM/storage/URL/console checks, real second-origin zero requests, axe results, isolation, and
  complete five-minute performance samples are present.

- [ ] Produce external `final-reconciliation.json` and `artifact-inventory.json` with stable sorted
  entries, bytes/SHA-256, ownership, and no credentials/absolute user-private data in shareable
  fields. A verifier discrepancy changes overall result to FAIL.

## Task 6: Create the report-only acceptance commit

**Files:**

- Create: `docs/openclaw/returns/STM32TK-0600-EVIDENCE-DIAGNOSTICS/r001-implementation-report.md`

- [ ] Only after final reconciliation PASS, return to the module branch/worktree at the frozen
  product CodeHead and create the report from verified facts. Record accepted base, 0601/0602
  report SHAs, final product CodeHead, scope, per-gate owner/platform/tools/versions/cwd/UTC/command/
  result, performance/coverage values, external evidence relative paths/bytes/SHA-256, and verdict.

- [ ] Do not put the report commit's own SHA, moving commit counts, unverifiable claims, another
  actor's evidence, skipped hardware PASS, or credentials in the report.

- [ ] Validate sole-change and report facts before committing:

```powershell
git diff --check
git status --short
git diff --name-only <full-codehead>
git add docs/openclaw/returns/STM32TK-0600-EVIDENCE-DIAGNOSTICS/r001-implementation-report.md
git diff --cached --name-only
git diff --cached --check
```

Expected: exactly the one report path and no formatting error.

- [ ] Commit locally:

```powershell
git commit -m "docs(STM32TK-0600): record accepted version 0.6.0"
```

- [ ] Verify the new commit's parent is exactly the final product CodeHead, its tree diff is only
  the report, the report still names the parent CodeHead, and the external evidence hashes verify.

## Task 7: Prepare, but do not execute, remote release actions

**Files:** none.

- [ ] Determine current remote default branch and fetch status read-only only if a later user turn
  explicitly authorizes network access. Until then, use the already-recorded remote ledger and do
  not contact GitHub.

- [ ] Prepare a concise proposed action list containing exact source/ref/full SHAs for push,
  PR/merge if needed, `v0.6.0` annotated tag target, and obsolete branch deletions. Treat each as
  pending user authorization, not as implied by acceptance.

- [ ] Confirm the intended tag semantic before execution: the program spec says `v0.6.0` points to
  the accepted head; recommend the report-only acceptance commit so the released tree includes
  the verified report while its parent remains the tested product CodeHead.

- [ ] Stop and ask the user in the new development/release conversation for the exact remote
  action authorization. Do not push, merge, tag, close, or delete anything in this plan.

## Task 8: Handoff package for the new conversation

**Files:** none beyond the already committed design, plans, reports, and product.

- [ ] Provide the repository URL, module/program IDs, program base, full design-plan commit,
  accepted module/report SHAs, final product/report SHAs, branch/worktree state, evidence root
  inventory digest, verdict, and pending remote decisions.

- [ ] State the invariant for resumed work: commits are the cross-machine truth; reconstruct the
  ledger first; never reuse evidence across CodeHeads; preserve unrelated state; no implementation
  correction is authorized unless the user names exact files/behavior.

- [ ] Ensure the handoff does not depend on collapsed commentary or local-only prose. Every product
  requirement and test instruction must be reachable from committed specs/plans/reports and full
  SHAs.

- [ ] End with one of the exact outcomes: `ACCEPTED` and awaiting remote authorization, `FAIL` with
  owning failed gate, or `BLOCKED` with the unavailable required external platform/hardware. Do not
  call the release complete merely because the matrix budget elapsed.
