# Public recovery workflow qualification plan

Accepted base: `8c819a150f4307564a04e1f92f38ef50ed5cef94`.
Governing specification: same-date public-recovery-workflow qualification.
The governing 2026-09-19 specification and ongoing implementation authority
cover this finite test-only plan. Product behavior does not change.

Primary owns specification, complete-diff review, integration, serial pytest
execution, evidence and cleanup. One Luna/max owner implements both recovery
test files in a clean `D:\codex-tmp\v10b-0918\r10\c106r` worktree on a
`codex/STM32TK-1.0-public-recovery-workflows` branch. No other writer owns these
files. A separately designed Diagnostic slice may proceed in its own file and
worktree; it may not alter these fixtures or execute pytest concurrently.

1. Add exactly two new journey selectors, one in each owned file. Build each
   graph once and reuse it across the specification's finite caller variants.
   No product source or existing test/helper changes. Add small local public
   call/snapshot helpers only when necessary; no general mutation framework.
2. Luna runs AST parsing, `git diff --check`, and installed Ruff's no-cache F821
   check against changed files with all environment temporary roots under the
   approved D root. It inspects every public wire container assertion and
   confirms the exact clock call chain, including :3721. It does not run pytest.
3. Return a local candidate commit, selectors, constructor/call counts, and a
   source-line map for each refusal. Primary reviews the complete base-to-head
   diff in a separate clean detached worktree and checks the public prefixes,
   effect oracles, reused fixture limitations and no-change resource claims.
4. After static acceptance the primary adapts the existing bounded launcher
   (event-chain/legacy-analysis launch-run2.ps1) for this two-selector batch;
   no new diagnostic or test runner framework. Use isolated native coverage,
   JUnit, pytest basetemp and Python caches under the registered `t/rw1` and
   `e/n95/public-recovery/run1` roots. Explicitly clear VS10B fixture overrides.
   Source bytes must match the pinned 465 source registry before execution.
5. Execute once with pytest first-failure stop. Hard total budget 600 seconds:
   120 continuation and 480 finalization planning reserves, not independent
   kill limits. Prior 17.72-second predecessor-only and 34–45-second complete
   finalization evidence do not prove this larger matrix's runtime. The larger
   finite budget accommodates one graph per journey and repeated real graph
   authentication. Record actual fixture and call durations; do not multiply
   fixtures through parametrization. Unexpected failure or total timeout stops
   this batch; classify and preserve evidence before any bounded correction.
6. Accept only complete selected PASS, exact result/resource oracles, matching
   test/source identity and full-diff review. Integrate locally, then reconcile
   native raw data once with other already-approved passing work. Failed raw
   never enters the accepted union; functional PASS preservation follows the
   existing policy. No full suite or packaging solely to regenerate coverage.

Evidence owner is primary, Windows PowerShell 7 / Python 3.12.10 / coverage
runtime in `r10\py`. Retain original result/JUnit/raw/source identity and minimum
failure evidence. Primary inventories only new attributed disposable roots
after acceptance; all previously policy-denied cleanup roots remain untouched.
If new cleanup is denied, record it once and do not retry or bypass the denial.

Acceptance of these two caller journeys does not by itself close Toolkit's
remaining 426-branch mandatory gap, the seven Windows platform checks, final
artifacts or bootstrap/upgrade/deployment evidence. VS10-A/B and attempt 7
historical physical PASS remain retained; 1.0 remains NOT_ACCEPTED.
