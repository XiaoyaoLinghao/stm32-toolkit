# v1.3.1 qualification checkpoint

Latest supplement: [external firmware integrity](../FIRMWARE-INTEGRITY-REGRESSION/implementation-report.md) is ACCEPTED at `25b29d2e71009c1de7b45cc5fbd00b72a419a98f`: 14 new cases, 50 affected passes and 24 independent passes. It adds 23 Toolkit branches. The current reconciled cohort is 8,729 passes / 19 skips; Toolkit overall/risk is 15,292/17,502 (87.3729%) / 14,259/16,296 (87.5000%). Monitor is unchanged at 91.5666%. Permanent gates remain unmet; this is additive source-bound evidence, not a single final-head full rerun or release acceptance. Earlier checkpoints follow.

Previous supplement: [migration boundary regression](../MIGRATION-BOUNDARY-REGRESSION/implementation-report.md) records 60 new passes, a 264-case affected PASS and 81 independent passes at `d30b20ca7592ba433a88f7bfda6fb06ecc98caab`. Toolkit gains 51 native branches; the current reconciled cohort is 8,715 passes / 19 skips, with Toolkit overall/risk 87.2415%/87.3589% and unchanged Monitor values. Gates remain unmet. The sections below preserve the complete-matrix checkpoint before this supplement; neither record claims a single all-green final-head rerun.

Disposition: **NOT_QUALIFIED — numerical gates and external checks remain open**. This records software evidence, not permission to publish or operate hardware. Accepted integration base is `4ab88f1e7275a0375caaa18662e468531efaa1f8` (version alignment and the subsequent integration phase). Accepted software/test head is `bb027fd3d0663a4e3310a011ecfc7b21b416f44b`; the recipient-guide CodeHead before this report commit is `42d4f808eeaf97b781f2212000669fb2a0e22928`. The report does not contain its own commit SHA. Primary owns specification, full independent review and qualification; local Claude Code CLI with the user's configured provider owns implementation and implementation verification.

## Regression evidence

The original complete Python matrix collected8,674nodes at `4b0153964306fe9f0f727a33bf8ea0a014cf03d4`. Toolkit originally returned7,469passed/6failed/19skipped; Monitor1,180passed/0failed/0skipped. Original failures remain preserved. One unchanged250node shard passed with a shorter owned temporary path after a native254/260character hardlink diagnostic; the exact original errno was not observed, so that causal attribution remains an evidence-supported inference. Three complete original groups,617nodes, passed after four test-file corrections for localized Windows command output and discovery reads that must actually enter before crossing their supplied deadline. Primary independently ran11affected cases:11passed,0failures/errors/skips. No product Python guard or performance acceptance threshold was weakened.

The reconciled cohort is **8,655passed/19skipped**, with no unresolved executed-case failure. It is not one all-green rerun at a single commit. Applicable unchanged results are explicitly reused; unsuccessful raw aggregates are excluded. All144tracked Python source files (125Toolkit,19Monitor) map to unchanged product bytes through the reviewed software head;945native raw coverage files were reconciled and combined using native tooling with originals retained. Pytest8.4.2 naming, exact node multiplicities, argv/configuration, source identities, terminal results and raw hashes were checked. Replacement data covers complete original groups, with prior outcomes separately retained.

The19Toolkit skips comprise11symbolic-link privilege/capability cases, one Windows directory-handle rename limitation, and seven archived public-data cases whose external archive was not configured. They are not passed tests or silently excluded source. A capable environment/applicability decision or explicitly disclosed delivery decision remains necessary. UI has a separate optional external-data unit-test skip.

## Native branch fractions

| Scope | Covered / total | Percentage | Permanent floor | Result |
| --- | ---: | ---: | ---: | --- |
| Toolkit overall | 15218 / 17502 | 86.9501% | 90% | UNMET |
| Toolkit risk-core-v2,103files | 14185 / 16296 | 87.0459% | 90% | UNMET |
| Monitor overall | 3203 / 3498 | 91.5666% | 90% | PASS, numerical only |
| Monitor risk-core-v2,17files | 3203 / 3498 | 91.5666% | 95% | UNMET |

Full-source broad-core-v1 statistics equal the respective overall fractions and retain their separate historical disposition; they do not create a new accepted gate. Risk membership was fixed before measurement in [scope.md](scope.md) and the permanent qualification contract. No exclusions, favorable branch selection, denominator edits, old failed aggregates or rounding-based threshold decisions were used. The prior v1.2.0 exception does not transfer.

## UI and package evidence

Claude's unit/static/build execution at `0eaadcba1bd0024575304829c370b269ffa2775c` passed 526 unit cases with one optional external-data skip; native branches were 2,906/3,114 (93.32%), with every positive-denominator file at least 90%. Type checks, lint, a11y, build and dist verification passed. The subsequent generated bundle at `3f9654d98c0a0b844c68add33fb9d8d3f8ed049c` contains seven files byte-identical to that pinned build. Primary separately verified bundle equivalence at this bundle head.

Claude's real Edge 156.0.4314.42 execution at `3f9654d98c0a0b844c68add33fb9d8d3f8ed049c` passed 44/44 functional cases, with no skip or flaky case. Both unchanged five-minute performance cases passed: 1280-window P95 15.6 ms and heap +0.29756 MiB/min; 1024-window P95 15.3 ms and heap -0.05849 MiB/min. Both used 4,800 points and recorded no long tasks >=200 ms, queue growth or server drops. Original browser failures and bounded corrections remain retained.

Primary independently passed 10 affected workbench cases at `961d03d65a5a1e6670b7be3d8493129c677c96c5`. Their TypeScript source/test bytes were unchanged by the later CSS/E2E-only correction, so this focused result is reused with that exact scope. Claude native PowerShell session `ceb230e4-5d56-48ae-83a4-048651e69131` separately passed all 20 embedded-asset Python cases at `3f9654d98c0a0b844c68add33fb9d8d3f8ed049c` (command/evidence in the accompanying JSON; JUnit `D:/codex-tmp/r131/ui-assets-final.xml`). Its subsequent first package build failed the source-binding guard; that failure remains a failure, not DEFERRED or PASS. Subsequent accepted product Python/UI bytes remain unchanged, and applicable evidence reuse is explicit.

A validation-only13asset bundle at3f9654d9 passed independent checksums, source/wheel binding and official verify-bundle. WindowsZIP112727214bytes, SHA256`2cd05e26a7f0031715df68576c94e9d9347b512a2218bb91af9d71e3b94804fa`. It predates this reporting phase and is not the final release. A preceding build was correctly rejected because an old ignored build/lib directory retained retired UI assets; the successful build used a separate exact-source checkout without package build residue. The failed build was not rewritten as passed. Final exact-head reproducible artifacts and final manifest bindings remain pending. A read-only gap audit is planning meaningful offline tests before final source freeze; no numerical exception is assumed.

## Outstanding gates and boundaries

Actual isolated installation, installed-runtime VSCode/MCP and generated-task/IntelliSense checks remain pending. An initial Check invocation selected WindowsPowerShell5.1 and was refused by its execution policy before the setup script ran. No Bootstrap or alternate-interpreter retry occurred. The user was asked to authorize correcting the interpreter to the already configured PowerShell7 without changing execution policy, consistent with AGENTS.md; that response remains pending. Fixture-based setup tests are not actual candidate installation qualification.

Local noninteractive Git push authentication was unavailable; a separate GitHub connector session does not supply local Git credentials. Read-only ls-remote confirmed master `89f76ee5551dfdc313f3f37d2d9e760af47daac8`; no source push, tag or Release mutation occurred. No new physical-board qualification, original firmware-project edit, existing-runtime/global Skill promotion or hardware operation was performed. Historical physical evidence retains its original scope.

Normal release acceptance is not granted. Complete the pending installation/IDE and packaging gates, and resolve the unmet permanent numerical/platform gates through applicable work or a new explicit decision bound to a concrete final source, artifacts and disclosed limitations. Only observed publication may update public-Latest claims. The user-requested delivery goal remains incomplete.

## Evidence locations

Run-local originals (non-exhaustive; also `primary-ui-layout-review`, `primary-zoom-dist.stdout/.stderr`, `ui-assets-final.xml` and `candidate-ui-cli.jsonl`): `D:/codex-tmp/r131/` (full-d/full-e, full-short-tk24, full-native-fixed, primary-native*, coverage-final, ui-browser-d, ui-perf-1280, ui-perf-1024, ui-zoom-check-a, candidate-ui-primary-verification.json). Native reconciliation ledger SHA256`11a42514a7e5685f1332ef5ef18982f8262fae1b019f5d628e9b7b4327ec6479`; native coverage JSON SHA256`9b94366978c16e3306b214ea3f05278c500b9be3d151b518c9729149aa3786fd`; qualification arithmetic JSON SHA256`18879b390a7c6312d44c6fae7a74f2b0649eb5c6fd38d63996d27fa07ec61c0d`. Machine-readable summary accompanies this record; raw execution ownership and original failures are retained separately from primary acceptance.

Independent read-only governance review `78426192-2051-4e20-bfda-1c2e11678237` found no numerical, failure-preservation or permission/procedure relaxation blocker. Primary corrected its accepted-base, UI execution-head and embedded-asset traceability findings here; this documentation review is not product or release acceptance.
