# v1.3.3 version alignment and release review

Date: 2026-10-27. Version/documentation changes: **ACCEPTED_WITH_FIXES**.
Release qualification: **NOT_QUALIFIED**, pending a concrete frozen-package decision;
historical candidate exceptions do not transfer. No remote mutation has occurred.

## Source, scope and ownership

- Accepted base: `39497f89e1ad2e2b5af27181af08385b755961b6`.
- Reviewed CodeHead before this report: `d281addbbdb70e36c270e24828868d7e936dc6e1`.
- Branch: `codex/v133-delivery`; independent clean review tree at the applicable source heads.
- Primary owns plan, orchestration, full diff review and acceptance. Local Claude Code CLI,
  retaining `deepseek-v4.1-flash[1m]`, authored product/test/documentation changes.
- The user explicitly authorizes v1.3.3 source/tag push and Release Latest after validation.
  Final actual installation and VS Code acceptance are user-owned, **USER_VALIDATION_PENDING**.
  Original firmware projects, installed runtime, global settings and physical hardware stay untouched.

The accepted [GCC integration](../GCC-DELIVERY-INTEGRATION/implementation-report.md)
supplies both independent GCC project exits and normal managed flash with optional Git.
This release aligns Toolkit/Monitor/UI/plugin/setup/release identities to 1.3.3,
retains older upgrade guards, recognizes 1.3.2 legacy inputs, and updates current guidance.
Dependency versions and schema/template semantics were not indiscriminately replaced.
Setup's official utility/policy SHA-256 pins were recomputed from canonical Git bytes.
Both READMEs remain short and equivalent; installation details live in the user guide/skill.

The primary reviewed the complete accepted-base-to-CodeHead diff and reconciled earlier
integration changes with their accepted report. The only final correction after `1b08d5a0`
is one stale setup documentation assertion: it now verifies the supported setup skill's
explicit absolute-path commands and guide link instead of requiring removed README examples.
It preserves Check-before-Bootstrap/Repair, namespace, staging/quarantine and ignore guards.
No installer or product behavior changed in that correction.

## Executed checks

Evidence root: `D:/codex-tmp/r133`. Every bound run retains actual argv/head, source
hashes, actual subprocess exit and fresh JUnit. Native PowerShell often omits its numeric
exit; that field remains null and is not confused with the separate bound subprocess exit.
All completed verification invocations had actual PowerShell registration and matched native
calls. The primary independently reviewed source/evidence; implementer claims are not approval.

| Run | Head | JUnit counts | Bound exit |
| --- | --- | --- | --- |
| a1 | 59dd2b93 | {'failed': 0, 'errors': 0, 'skipped': 0, 'cases': 324, 'passed': 324} | 0 |
| a2 | 59dd2b93 | {'failed': 0, 'errors': 0, 'skipped': 0, 'cases': 98, 'passed': 98} | 0 |
| a3 | 59dd2b93 | {'failed': 0, 'errors': 0, 'skipped': 0, 'cases': 114, 'passed': 114} | 0 |
| b1 | 59dd2b93 | {'failed': 0, 'errors': 0, 'skipped': 0, 'cases': 574, 'passed': 574} | 0 |
| b2 | 59dd2b93 | {'failed': 0, 'errors': 0, 'skipped': 0, 'cases': 787, 'passed': 787} | 0 |
| c1 | 1b08d5a0 | {'failed': 0, 'errors': 0, 'skipped': 0, 'cases': 161, 'passed': 161} | 0 |
| c2 | 1b08d5a0 | {'failed': 0, 'errors': 0, 'skipped': 1, 'cases': 94, 'passed': 93} | 0 |
| c3 | 1b08d5a0 | {'failed': 0, 'errors': 0, 'skipped': 0, 'cases': 14, 'passed': 14} | 0 |
| s1 | 1b08d5a0 | {'failed': 0, 'errors': 0, 'skipped': 0, 'cases': 16, 'passed': 16} | 0 |
| s2 | 1b08d5a0 | {'failed': 1, 'errors': 0, 'skipped': 0, 'cases': 30, 'passed': 29} | 1 |
| d1 | d281addb | {'failed': 0, 'errors': 0, 'skipped': 0, 'cases': 4, 'passed': 4} | 0 |
| p1 | 1b08d5a0 | {'failed': 1, 'errors': 0, 'skipped': 0, 'cases': 2, 'passed': 1} | 1 |
| p2 | acb71b9f | {'failed': 0, 'errors': 0, 'skipped': 0, 'cases': 1, 'passed': 1} | 0 |
| p3 | 1b08d5a0 | {'failed': 0, 'errors': 0, 'skipped': 0, 'cases': 1, 'passed': 1} | 0 |
| u1 | 59dd2b93 | {'failed': 0, 'errors': 0, 'skipped': 1, 'cases': 535, 'passed': 534} | 0 |
| u2 | 59dd2b93 | None | 0 |

`a1/a2/a3` are generation/build/migration-version; `b1/b2` cover all Monitor Python
test files except performance. `c1/c2` cover version/release/MCP/CLI and complete current
AI/VS Code guidance groups. `c3` re-executes both complete real-GCC independent-delivery
and normal managed simulated-flash journeys. `u1` is full UI typecheck/lint/unit/native
coverage; `u2` verifies all seven tracked bundle outputs against the build.

`s1/s2` passed all 45 installation-behavior cases; `s2` retained one failed documentation
assertion. After Claude corrected that single function, `d1` passed it plus three related
documentation contracts. The 45 unchanged behavior results are reused explicitly, not
reported as a fresh final-head 46-case file run. Source and fixtures for those cases are
unchanged. The earlier failure remains preserved. Setup generated no usable branch arcs;
its empty dataset is excluded from coverage, not treated as missing test execution.

`p1` passed named export performance but failed Monitor append p95 (124.9428 ms against
50 ms); later stages in that test did not execute. Exactly one controlled monitor-only
comparison per version, with the same interpreter/fixture/D-drive root policy and no other
coordinator test/build workload, passed at 21.4292 ms for v1.3.2 (`p2`) and 19.5793 ms
for the candidate (`p3`), including subsequent query/export/retention/HTTP assertions.
The cause of the initial failure is not established; no code regression was reproduced.
This is separate bounded evidence, not a silent conversion of `p1` to PASS. No thresholds
were relaxed and no further performance rerun occurred. The embedded old acceptance-command
string in benchmark output is historical; execution.json contains the actual argv/environment.

## Coverage and retained limitations

Native branch aggregation uses 79 accepted integration/component runs and eight fresh
release groups plus still-applicable v1.3.2 native evidence. Only exact current source
hashes are admitted; old arcs for changed files are removed. Every current Python source
remains in the denominator. The risk-membership amendment preceded measurement and removed
no files or thresholds. This is source-specific reuse, **not a single final-head full rerun**.
The native source mapping, raw hashes and fractions are in `release-evidence.json` and
`D:/codex-tmp/r133/coverage-v133/qualification.json`.

- toolkit-overall: 15211/18418 = 82.5877%, floor 90%, **UNMET**.
- toolkit-risk-core-v2: 14157/17176 = 82.4231%, floor 90%, **UNMET**.
- monitor-overall: 3292/3564 = 92.3681%, floor 90%, **PASS**.
- monitor-risk-core-v2: 3292/3564 = 92.3681%, floor 95%, **UNMET**.
- UI: 2938/3147 = 93.3588%; every positive-denominator file meets 90%.

The lower Toolkit percentage than v1.3.2 reflects the larger current denominator and
discarded obsolete arcs on changed source; it is not filled with mismatched historical data.
The current guide symlink skip, UI historical-batch fixture skip, and earlier platform/data gaps
remain unpassed. Integration's three actual-symlink cases need a host with that capability.
Real vendor CubeMX generation remains unverified because the user has no offline firmware
package; the creation journey substitutes only its external generation adapter. Real GCC,
project independence and normal managed simulated flash are executed product behavior.
No hardware, installed IDE, actual final install/upgrade/rollback or new physical qualification
is inferred from fixtures. Final install/VS Code belongs to the user.

## Invocation and reconciliation audit

The first version edit invocation performed out-of-scope searches/one dependency read;
the coordinator stopped its own CLI handle and retained all edits/logs. It is not marked
compliant retroactively. Independent complete-diff review found no edits outside the allowed
files; subsequent bounded corrections and native tests supply acceptance evidence.
The docs invocation retained an Edit string-not-found failure; already-applied changes were
reviewed and the bounded follow-up completed. No Bash substitution, permission bypass,
provider change or Codex implementation fallback occurred. Two invalid verification task
descriptions were rejected before CLI startup and corrected in new bounded descriptions.
Intermittent API transport retries delayed final checks but eventual native evidence was
reconciled without restarting executed tests. The first coverage reconciliation stopped on
the empty setup branch dataset; that intermediate directory was retained and a new aggregate
excluded only that non-branch input. Original test and invocation failures are not erased.

Next: freeze these reviewed bytes, perform two clean canonical official offline builds,
verify all 13 files and extracted bundle, then resolve unmet gates for that exact candidate.
The release plan and permanent qualification contract govern publication; user-owned final
installation/VS Code stays pending even if a candidate-specific release exception is approved.
