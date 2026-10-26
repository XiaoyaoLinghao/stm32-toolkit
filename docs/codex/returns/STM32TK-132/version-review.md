# v1.3.2 version alignment and independent review

Software verdict: **ACCEPTED_WITH_FIXES**. Release qualification remains
**NOT_QUALIFIED** pending the explicit disposition below; no v1.3.2 publication
or coverage exception is implied.

Accepted base: `cb2a1d2c78fcc4a5c886e77fb06d0ac01eddbab5`.
CodeHead before this report commit: `c1985337bb1b74eab38deb12509ace22f191ab07`.
Implementation branch: `codex/v132-guidance`. The primary owns specification,
orchestration, independent full-diff review and acceptance. Implementation and
test corrections were authored by the local Claude Code CLI, using the existing
`deepseek-v4.1-flash[1m]` configuration. No Codex implementation subagent was used.

The primary reviewed the entire accepted-base-to-CodeHead diff in the separate
clean `v132-review/STM32-Toolkit` worktree. The advisory behavior is described in
[phase 1](implementation-report.md). Active package, plugin, launcher, setup,
policy/schema and UI root metadata now agree on 1.3.2. Existing 1.3.1 installations
and generated manifests enter the existing legacy path; repair, identity,
quarantine, rollback and downgrade guards are retained. Dependency pins, historical
fixtures, UI implementation/dependencies and hardware behavior are unchanged.

README, Skills and VS Code guidance distinguish current public Latest 1.3.1 from
the local 1.3.2 candidate. They explain distribution metadata versus PATH evidence,
the supported executable-setting/explicit-path choices, and retained user tasks.
Active setup examples and isolated test launchers use existing PowerShell7 with
no execution-policy override. Utility/policy integrity pins were recalculated
from canonical committed bytes and checked independently.

## Executed verification

Evidence root: `D:/codex-tmp/r132`. Each successful run records actual argv, owner,
HEAD, all tracked source hashes before/after, stdout, JUnit and exit status.
Claude verification had native `PowerShell` initialization, actual tool-use/result
events for the one supplied command, and no permission denials. File authoring
and shell verification were separate. The primary's review group ran in the
independent worktree, not the implementation tree.

| Run / owner | Source | Actual terminal result |
| --- | --- | --- |
| guidance-b / Claude | 978a723574a9db6933b70937cabbbc8946086690 | 837 passed, 3 skipped |
| review-a / primary | 978a723574a9db6933b70937cabbbc8946086690 | 156 passed, 1 skipped |
| version-meta-b / Claude | c1985337bb1b74eab38deb12509ace22f191ab07 | 212 passed, 1 skipped |
| version-build-b / Claude | c1985337bb1b74eab38deb12509ace22f191ab07 | 534 passed |
| setup-a1 / Claude | b06f2dbe9f5a26647565c48d4f7c6aa13e9889b6 | 15 passed, complementary 30 deselected |
| setup-b2 / Claude | c1985337bb1b74eab38deb12509ace22f191ab07 | 30 passed, complementary 15 deselected |
| monitor-b / Claude | c1985337bb1b74eab38deb12509ace22f191ab07 | 288 passed |
| review-version-b / primary | c1985337bb1b74eab38deb12509ace22f191ab07 | 76 passed |

The version groups partition all 747 cases in the original version group: 746
passed and one native Windows symlink case skipped. The setup groups partition
all 45 setup cases; the first group's implementation/tests did not change in
c1985337. Those are isolated fixture executions, not final package installation.
They collect no product Python branch data, as explicitly warned by coverage.py.
Independent and phase-1 groups overlap other groups; do not sum these rows as a
unique complete regression count. The three phase-1 native symlink cases remain
deferred to the primary release-qualification owner on a suitably privileged
Windows host; no host-policy change was made to run them.

## Retained failures and corrections

- `guidance-a`: 836 passed, one failed, three skipped. A new test's unrelated
  `setup-stm32-env` substring assertion was corrected; the behavior was unchanged.
- `version-a` at b06f2db: 744 passed, two failed, one skipped. README prerequisite
  wording was checked with the correct case/language; the real UI e2e fixture's
  imported protocol versions are now checked without entering its server/main.
  Historical static TypeScript mock identities remain historical.
- `monitor-a` at b06f2db: three failure markers followed by an unfinished cleanup
  wait, not a completed matrix and not zero executed tests. The primary verified
  the exact run-owned process PID/executable/command and stopped only that process.
  Its partial logs, coordinator stop/reconciliation and missing-JUnit outcome
  remain retained. A stale 1.3.1 FakeEndpoint and expected current-version value
  were corrected to 1.3.2; the complete affected Monitor group then passed.
- Independent review restored a Windows-only skip marker to its actual test,
  rather than its helper. No product assertion or guard was weakened.

Failed/incomplete aggregate coverage was not imported. No old result was rewritten
as PASS. There are no unresolved software findings in the reviewed scope.

## Native qualification and limits

`coverage-v132/qualification.json` reconciles native branch data. Every changed
source file's old arcs were removed; only identical source bytes from the retained
v1.3.1 native aggregate and successful current runs were accepted. Each changed
file has current executed arcs. Full source membership/branch denominators and
permanent floors are unchanged. This is explicit source-bound reuse, not a
single final-head full-suite rerun. The old aggregate's platform/historical-data
skips remain limitations, not newly executed checks.

| Scope | Native branches | Percentage | Permanent floor | Result |
| --- | --- | --- | --- | --- |
| Toolkit overall / broad-core-v1 | 15381 / 17618 | 87.3028% | 90% | UNMET |
| Toolkit risk-core-v2 | 14310 / 16354 | 87.5015% | 90% | UNMET |
| Monitor overall / broad-core-v1 | 3227 / 3498 | 92.2527% | 90% | PASS |
| Monitor risk-core-v2 | 3227 / 3498 | 92.2527% | 95% | UNMET |

UI source, coverage configuration and dependency versions are unchanged; only
root package-version metadata changed. Prior applicable UI evidence is reused,
not presented as a fresh browser execution. Final bundle assets still require
the independent official verifier.

The user authorized v1.3.2 delivery, but the v1.3.1 frozen-candidate exception does
not transfer. Next: freeze the reviewed source, perform two independent official
builds and all 13-file checks, then present that exact candidate and remaining
limits for qualification disposition. Final installation and VS Code validation
remain user-owned, **USER_VALIDATION_PENDING**. No original firmware-project,
installed runtime, global settings/Skills or hardware was changed. No v1.3.2
remote write has occurred at this checkpoint.
