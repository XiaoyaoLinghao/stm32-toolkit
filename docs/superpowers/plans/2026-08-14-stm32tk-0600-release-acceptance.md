# STM32TK-0600 Release Acceptance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate the three accepted 0.6 modules, prove one frozen final CodeHead with one logical multi-platform release matrix, create a report-only acceptance commit, and stop before any unauthorized remote release action.

**Architecture:** Each module enters through an accepted report commit and immutable evidence inventory. The 0603 product commit is the only final CodeHead. A non-executing readiness phase proves environment and inventory without duplicating product tests. Windows, Linux, and hardware shards then bind the same `finalRunId`, CodeHead, catalogs, locks, and support profiles; each shard is fail-fast, and only one pre-enumerated external infrastructure interruption may resume its affected shard. Reporting is a separate child commit and cannot repair product or evidence.

**Tech Stack:** Git/worktrees, PowerShell 5.1, Python 3.10/3.12, Node/npm, Playwright browsers, pytest/coverage, wheel/pip offline install, real STM32 board/probe/transports, SHA-256 artifact inventories.

## Global Constraints

- Program base is exactly `bb6bc5e9ee937e4ce53996b31f25bf1109ffe13f` (`v0.5.0`).
- Follow all four 2026-08-14 STM32TK-0600/0601/0602/0603 design specifications.
- This plan starts only after acceptance-feasibility PASS, 0601 and 0602 accepted report commits,
  and 0603 candidate reconciliation PASS with final catalog/node/performance digests at one product
  CodeHead.
- No product, test, helper, dependency, version, generated dist, documentation, Skill, gate, or
  threshold edit is allowed after final freeze. Any such edit invalidates the CodeHead and sends
  work back to the owning module plan.
- Test logs/results/screenshots/traces/wheels/coverage/manifests live in an external evidence root.
- Every required platform/hardware result is PASS or the release is BLOCKED/FAIL; no fake, skip,
  deferred, or another owner's stale evidence is promoted to PASS.
- All product-framework retries are disabled (`pytest` reruns absent and Playwright `retries: 0`).
  Scheduling targets only warn; they are never acceptance thresholds or child-process timeouts.
- `RECOVERABLE_INFRA_ERROR` is limited to host power/reboot, runner loss before a child result,
  physical USB/probe removal, or target power loss. After reviewer classification, only the
  affected shard may resume once with identical frozen inputs and evidence root; both attempts are
  retained. A repeat is BLOCKED. Product/test/security/coverage/performance/timeout/corruption/
  dependency failures are not recoverable and any repository edit creates a new CodeHead.
- Remote push/PR/merge/tag/branch deletion requires a new explicit user authorization.

## Execution Order and Requirement Coverage

| Phase | Plan tasks | Required result before the next phase |
|---|---|---|
| feasibility | 0601 Task 1 | named owners/profiles and real capture/browser-launch proof before product code |
| 0601 contract foundation | 0601 Tasks 2--12 | frozen schema/families and 0601 nodes, evidence/test schemas, Project v3, Host/Target tests, four real transports |
| 0601 acceptance | 0601 Task 13 | candidate PASS and report-only accepted-base commit |
| 0602 diagnostic product | 0602 Tasks 1--11 | hash chain, hypotheses, observations, controls, fix verification, bundle, real-board loop |
| 0602 acceptance | 0602 Task 12 | candidate PASS and report-only accepted-base commit |
| 0603 analytics product | 0603 Tasks 1--12 | history v2, comparison/quality, annotations, UI, bundles, version 0.6.0 |
| 0603 handoff | 0603 Task 13 | candidate PASS plus final catalog/node/performance digests at one product CodeHead |
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
  state, remote actions (none unless separately authorized), current-task hardware action
  authorizations, and bounded overrides (none unless explicitly restated by the user). Load the
  feasibility report and record non-empty Windows, Linux, and
  physical-hardware evidence-owner IDs plus the exact host/board/MCU/probe/UART/RTT/semihosting/
  browser/power profiles and support/firmware digests.

- [ ] Audit tracked/untracked, committed/uncommitted, pushed/unpushed state for the source workspace
  before creating an acceptance worktree. Preserve unrelated state and never clean/delete it.

- [ ] Require the offline advisory snapshot to record source/database version/generated UTC/digest
  and be no older than seven calendar days. If stale, the named support owner may refresh only that
  external support-manifest segment before the ledger freezes. Record old/new segment digests and
  prove every other support entry unchanged; do not change dependencies/locks or use a network
  audit as release evidence.

- [ ] Hash the feasibility profile/report, four design specs, four implementation plans, gate and
  performance catalogs, controllers, verifier, dependency locks, source inventory, platform
  support manifests, and firmware fixture into `release-ledger.json` in the external evidence root.

## Task 2: Create a clean isolated final worktree

**Files:** none in the repository.

- [ ] Resolve explicit new directories under `C:\tmp` on Windows and the feasibility-profile path
  on Linux. Verify neither exists, then create detached worktrees at the same full 0603 CodeHead.
  If the commit is not locally present on one host, stop for the separately authorized cross-machine
  Git handoff; this plan itself does not authorize a push or fetch.

```powershell
git worktree add --detach C:\tmp\stm32tk-0600-final-<short-codehead> <full-0603-codehead>
git -C C:\tmp\stm32tk-0600-final-<short-codehead> rev-parse HEAD
git -C C:\tmp\stm32tk-0600-final-<short-codehead> status --porcelain=v1 --untracked-files=all
```

```bash
git worktree add --detach /tmp/stm32tk-0600-final-<short-codehead> <full-0603-codehead>
git -C /tmp/stm32tk-0600-final-<short-codehead> rev-parse HEAD
git -C /tmp/stm32tk-0600-final-<short-codehead> status --porcelain=v1 --untracked-files=all
```

Expected on both hosts: exact full SHA and no status output.

- [ ] Verify the worktree's Git common directory/repository identity, no symlink/junction/reparse
  point within the tracked tree, accepted-base ancestry, `git diff --check`, expected path list,
  exact source inventory, package/dist manifest closure, dependency lock digests, and no extra
  tracked release artifacts.

- [ ] Generate one unique `finalRunId`. Under a run directory containing that ID and the full
  CodeHead, create separate `readiness/windows`, `readiness/linux`, `readiness/hardware`,
  `results/windows`, `results/linux`, and `results/hardware` shard roots; refuse any existing file.
  Also create an empty `imports` directory for owner-delivered non-aggregator shard packages.
  Record absolute tools and versions for Git, shells, Python 3.10/3.12, Node, npm, pip/build,
  browsers, probe tools, and hardware identifiers. Every shard metadata file must bind the same
  `finalRunId`, CodeHead, final gate/performance catalog digests, dependency locks, and the correct
  platform support-manifest digest.

- [ ] Verify the performance owner matches the frozen Ryzen 7 5800U/16 GB/WDC PC SN530 NVMe/
  Windows 11 x64 High performance reference profile. Record the exact OS build, AC/battery,
  antivirus state, free disk, and background-load preflight. If a calibrated component differs,
  require the pre-implementation prior-CodeHead calibration evidence; do not calibrate now.

## Task 3: Run non-executing final readiness

**Files:** none.

- [ ] From the frozen catalog, verify that final gate IDs cover all of these partitions without
  executing their test bodies:

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

- [ ] Run readiness independently for the clean Windows, Linux, and hardware shards. It may run Git/source/
  inventory checks, controller/verifier self-tests, `pytest --collect-only`, Vitest/Playwright test
  listing, support-manifest verification, owner/profile availability, evidence-root emptiness/
  writability, hardware identity/connectivity, and offline dependency availability. It must not run
  a product test body, browser flow, performance workload, build, flash, or diagnostic action.

```powershell
py -3.12 tools/release/verify_0600_release.py final-readiness --shard windows --repo C:\tmp\stm32tk-0600-final-<short-codehead> --catalog tools/release/gates_0600.json --performance tools/release/performance_0600.json --support-profile C:\tmp\stm32tk-0600-support\feasibility\profile.json --final-run-id <finalRunId> --evidence-root C:\tmp\stm32tk-0600-final-<finalRunId>\readiness\windows --result-root C:\tmp\stm32tk-0600-final-<finalRunId>\results\windows
py -3.12 tools/release/verify_0600_release.py final-readiness --shard hardware --repo C:\tmp\stm32tk-0600-final-<short-codehead> --catalog tools/release/gates_0600.json --performance tools/release/performance_0600.json --support-profile C:\tmp\stm32tk-0600-support\feasibility\profile.json --final-run-id <finalRunId> --evidence-root C:\tmp\stm32tk-0600-final-<finalRunId>\readiness\hardware --result-root C:\tmp\stm32tk-0600-final-<finalRunId>\results\hardware
```

```bash
python3.12 tools/release/verify_0600_release.py final-readiness --shard linux --repo /tmp/stm32tk-0600-final-<short-codehead> --catalog tools/release/gates_0600.json --performance tools/release/performance_0600.json --support-profile /tmp/stm32tk-0600-support/feasibility/profile.json --final-run-id <finalRunId> --evidence-root /tmp/stm32tk-0600-final-<finalRunId>/readiness/linux --result-root /tmp/stm32tk-0600-final-<finalRunId>/results/linux
```

- [ ] Require exact CodeHead/catalog/performance/dependency/support/tool/profile equality, exact
  collect-only node inventory with no missing/extra/duplicate/deselected/skip/xfail required node,
  clean trees, empty shard result directories, available named owners, connected matching hardware,
  and current-task authorization digests for every reset/flash/modify action in the hardware shard.
  Record readiness metadata separately from final gate results; it cannot satisfy a final product gate.

- [ ] If readiness fails, stop before final. An environment-only mismatch may be corrected outside
  the repository and readiness repeated. Any repository correction returns to the owning module,
  creates a new CodeHead, and requires candidate plus readiness again.

- [ ] Only after all three readiness shards PASS, freeze the recorded product SHA as the sole final
  `0.6.0` CodeHead. From this point no repository file may change before final reconciliation.

## Task 4: Run one logical complete final matrix

**Files:** none; controller outputs only to the external evidence root.

- [ ] Confirm immediately before launch: both isolated worktrees clean, product SHA exact, shard
  result directories empty except immutable ledger/readiness inputs, no coverage environment
  leakage, local package/browser/probe support present, named real hardware connected, and no
  remote Git/network action in controller commands.

- [ ] Start only resource-disjoint Windows and Linux work in parallel where their named owners can
  retain evidence. Start the hardware shard when the user hardware owner confirms the frozen
  fixture, but serialize it against absolute Windows performance if it shares that host/probe/board/
  UART/port. All
  commands use the same `finalRunId`, CodeHead, gate/performance catalog digests, dependency locks,
  support profile, and immutable run root:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File tools/release/run_0600_final.ps1 -Shard windows -FinalRunId <finalRunId> -EvidenceRoot C:\tmp\stm32tk-0600-final-<finalRunId>\results\windows -ExpectedCodeHead <full-codehead> -Catalog tools/release/gates_0600.json -Performance tools/release/performance_0600.json -SupportProfile C:\tmp\stm32tk-0600-support\feasibility\profile.json
```

```bash
./tools/release/run_0600_final.sh --shard linux --final-run-id <finalRunId> --evidence-root /tmp/stm32tk-0600-final-<finalRunId>/results/linux --expected-code-head <full-codehead> --catalog tools/release/gates_0600.json --performance tools/release/performance_0600.json --support-profile /tmp/stm32tk-0600-support/feasibility/profile.json
```

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File tools/release/run_0600_final.ps1 -Shard hardware -FinalRunId <finalRunId> -EvidenceRoot C:\tmp\stm32tk-0600-final-<finalRunId>\results\hardware -ExpectedCodeHead <full-codehead> -Catalog tools/release/gates_0600.json -Performance tools/release/performance_0600.json -SupportProfile C:\tmp\stm32tk-0600-support\feasibility\profile.json
```

Expected: each fail-fast shard exits zero and says PASS; their union contains every final gate and
exact node once. The 120-minute wall-clock target assumes platform parallelism and only emits a
warning if exceeded.

- [ ] The Linux owner returns `results/linux/shard-package.zip` and its separately communicated
  SHA-256 through the user-designated evidence channel. Place it unchanged at
  `C:\tmp\stm32tk-0600-final-<finalRunId>\imports\linux.zip`; record transfer owner/UTC/digest. No
  controller fetches, uploads, or opens a network connection. The final verifier reads the import
  without extracting over another shard or rewriting any member.

- [ ] On a nonzero shard exit, preserve every file and classify from primary evidence. For an
  eligible external event only, a reviewer records `RECOVERABLE_INFRA_ERROR` and may resume that
  affected shard once; do not restart completed gates or any other shard:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File tools/release/run_0600_final.ps1 -ResumeFinalRun -Shard <windows-or-hardware> -FinalRunId <finalRunId> -EvidenceRoot C:\tmp\stm32tk-0600-final-<finalRunId>\results\<shard> -ExpectedCodeHead <full-codehead> -Catalog tools/release/gates_0600.json -Performance tools/release/performance_0600.json -SupportProfile C:\tmp\stm32tk-0600-support\feasibility\profile.json -RecoveryRecord C:\tmp\stm32tk-0600-final-<finalRunId>\results\<shard>\recovery-classification.json
```

```bash
./tools/release/run_0600_final.sh --resume-final-run --shard linux --final-run-id <finalRunId> --evidence-root /tmp/stm32tk-0600-final-<finalRunId>/results/linux --expected-code-head <full-codehead> --catalog tools/release/gates_0600.json --performance tools/release/performance_0600.json --support-profile /tmp/stm32tk-0600-support/feasibility/profile.json --recovery-record /tmp/stm32tk-0600-final-<finalRunId>/results/linux/recovery-classification.json
```

Expected: resumed metadata proves identical inputs, names one enumerated event, records reviewer/UTC,
and retains both attempts. A repeated infrastructure event is BLOCKED. Any deterministic gate
failure is FAIL: do not resume, change thresholds, patch the final worktree, or write a report;
return to the owning module, create a new CodeHead, and repeat candidate/readiness before a new
logical final run.

- [ ] On PASS, verify both worktree statuses are clean and HEADs unchanged. Hash every shard
  summary and retained result/log/screenshot/trace/coverage/performance/wheel/manifest, including
  both attempts and recovery classification when recovery occurred.

## Task 5: Reconcile final evidence and release truth

**Files:** none yet.

- [ ] Independently run the read-only verifier over the final evidence root and frozen catalog:

```powershell
py -3.12 tools/release/verify_0600_release.py final-evidence --repo C:\tmp\stm32tk-0600-final-<short-codehead> --evidence C:\tmp\stm32tk-0600-final-<finalRunId> --import-shard C:\tmp\stm32tk-0600-final-<finalRunId>\imports\linux.zip --final-run-id <finalRunId> --expected-code-head <full-codehead> --catalog tools/release/gates_0600.json --performance tools/release/performance_0600.json
```

Expected: PASS with zero missing/extra/duplicate gates, nodes, artifacts, hashes, or platforms; all
shards bind one logical run and any recovery has exactly two retained, policy-valid attempts.

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
  fields. Include elapsed duration as scheduling evidence only, plus recovery classification and
  both attempt inventories when applicable. A verifier discrepancy changes overall result to FAIL.

## Task 6: Create the report-only acceptance commit

**Files:**

- Create: `docs/openclaw/returns/STM32TK-0600-EVIDENCE-DIAGNOSTICS/r001-implementation-report.md`

- [ ] Only after final reconciliation PASS, return to the module branch/worktree at the frozen
  product CodeHead and create the report from verified facts. Record accepted base, 0601/0602
  report SHAs, final product CodeHead, scope, per-gate owner/platform/tools/versions/cwd/UTC/command/
  result, performance/coverage values, `finalRunId`, scheduling duration/warnings, recovery attempts
  if any, external evidence relative paths/bytes/SHA-256, and verdict.

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
