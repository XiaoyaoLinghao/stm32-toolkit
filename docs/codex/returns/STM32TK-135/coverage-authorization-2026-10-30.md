# v1.3.5 coverage non-regression authorization — 2026-10-30

The user explicitly instructed: “可以豁免测试覆盖率，不低于上一版本测试覆盖率即可”.
Primary records this as a v1.3.5-only conditional coverage exception. It replaces
the higher permanent numeric floors for this release only, conditional on each
applicable coverage group being no lower than the published v1.3.4 baseline.
This is authorization of the comparison rule, not evidence that v1.3.5 passes it.

## Exact comparison baseline

Previous release source: `a7db6a8cc3ecdab53ef0b52cb80b54cbadcacead`.
The [v1.3.4 candidate record](../STM32TK-134/candidate-build.md) and
[implementation report](../STM32TK-134/implementation-report.md) bind these native
branch totals. Compare exact ratios, not rounded percentages or an average
across groups.

| Group | v1.3.4 covered / total | Display percentage |
| --- | --- | --- |
| Toolkit overall | 15336 / 18534 | 82.7452% |
| Toolkit risk-core-v2 | 14208 / 17194 | 82.6335% |
| Monitor overall | 3292 / 3564 | 92.3681% |
| Monitor risk-core-v2 | 3292 / 3564 | 92.3681% |
| UI overall | 2938 / 3147 | 93.3588% |

Use the same native branch measurement and responsibility-based membership rules;
include changed/new in-scope source. Do not remove files, branches or platforms,
change exclusions, or select favorable evidence to meet the comparison. Existing
UI per-file rules remain. Unchanged evidence may be reused only with explicit
source/configuration/dependency binding under the qualification contract.
Changed-source arcs cannot be reused as though still applicable.

## Scope and disposition

At recording, current source is `1ec93d7851611a30668add5ecfa8bb1469d348c5`.
No final v1.3.5 source/package or consolidated coverage result is frozen yet.
Authorization-time status: **AUTHORIZED_CONDITIONAL_COVERAGE_EXCEPTION / COMPARISON_PENDING**.
Current comparison at reviewed CodeHead `fa3613cb7b24a0f0532aff5248acb9ad919a112a` is **CONDITION_MET_NON_REGRESSION** for all groups; see [integration-evidence.json](integration-evidence.json). Permanent results, source reuse, platform skips and pending external acceptance remain separately disclosed.
If the comparison passes, report v1.3.5 as meeting this user-authorized coverage
condition; separately retain permanent-gate results and any unmet values. This
authorization does not claim a numeric permanent-gate PASS and does not transfer
to later releases.

Behavior regressions, failures, evidence integrity, applicable packaging,
installation and integration checks remain required. This grants no new hardware,
runtime replacement, installation, push, PR, tag, Release or publication authority.
Primary owns this governance record; no product code or tests change.
