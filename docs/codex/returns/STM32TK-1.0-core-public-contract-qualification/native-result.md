# Current native coverage result

Accepted base for this wave: `bf4b070f29dec6a25a3e30ba3fad29ce268c6492`.
Integrated test code head: `2cba63f2808d27cb4c2ec1dbba041e9633d830e5`.
Existing recovery candidate: `a695f397260ebb815059d3df598dadf4c884924c`.
Qualified product source: `8a11caef14df16c5e56c0be2363d4ef5530110eb`.
Union27 native data verdict: **ACCEPTED_NATIVE_DATA**. Release 1.0: **NOT_ACCEPTED**.

| Package | Covered / total branches | Overall and broad core v1 | More for 90% | More for v1 95% |
| --- | ---: | ---: | ---: | ---: |
| Toolkit | 11,831 / 13,580 | 87.1208% | 391 | 1,070 |
| Monitor | 2,666 / 2,940 | 90.6803% | 0 | 127 |
| UI (retained separately) | 784 / 810 | 96.7901% | 0 | 0 |

The repeat-bind product correction remains accepted with its seven current-source
PASS. Source changes invalidate old coverage for recovery_workflows.py, so union21
removed that file's old-source arcs and incorporated only accepted current-source
evidence. The historical union20 result, 11,795/13,578 on source 465249d, remains
archived and must not be presented as the current product's coverage.

The two complete Diagnostic caller journeys passed in 90.370 seconds: lifecycle
through resolution/retry, and twelve authority-refusal variants with exact graph
preservation. Union22 incorporated the complete run and added 23 native branches.
Its three failed construction batches remain excluded, with diagnostic evidence
retained. See diagnostic-public-journeys.md for the accepted implementation scope.

An explicit primary source-qualification decision then reused three existing
generic recovery selectors: build-provider failure, six build-output refusals and
six target-replay refusals. All **13 PASS in 8.541 seconds**, exit 0, no timeout or
forced termination. No tests or product code changed. Union23 adds 87 Toolkit
branches; recovery_workflows.py then had 399/860 current-source branches. The run
did not import Monitor, so its accepted union22 object and UI are retained unchanged.

The risk-layered wave then qualified the remaining existing generic-recovery
group (36 PASS, 10.944 seconds) and the continuation/software physical-protocol
chain group (10 PASS, about 175 seconds). Both completed with exit 0 and no
timeout/forced termination. Union24 adds 138 current-source Toolkit branches;
recovery_workflows.py reached 537/860. Monitor counts and UI remained unchanged.
These software protocol checks are not hardware evidence. Finalization7,
Diagnostic2 and generic13 were retained, not repeated.

Three separate Luna/max owners then added the frozen M/P/A contract groups:
M5 PASS at 7744cf83 (2.661s), P4 PASS at d8b7a328 (3.02s), A5 PASS at 79323b98
(24.06s). M's final 2d4ea2c is formatting/docstring-only, so its earlier runtime
result remains valid. Primary reviewed complete accepted-base diffs in clean
separate review worktrees; all final test files passed Ruff and diff checks.
P/A's initial fixture failures remain classified as test defects, with failed
raw databases excluded. No product source changed.

Union25 adds four Toolkit and three Monitor native branches. The accepted
source recovery file reaches 539/860. Most new cases strengthen observable
rejection, exact rollback and resource settlement assertions over already
covered paths; fourteen PASS cases do not mean fourteen new covered branches.

Union26 adds the complete SVD2, recovery7 and creation-settlement P6 groups:
2 PASS in 1.673s, 7 PASS in 378.276s and 6 PASS in 1.224s (JUnit durations),
all exit 0 without timeout. The full P diff was independently reviewed at
33c299ae before integration. Its first run observed a file after successful
cleanup; that test defect was corrected and the failed raw remains excluded.
The independent native review verified all 148 product source identities,
eight native inputs, per-file totals and frozen scope arithmetic. Toolkit gains
62 branches with no denominator change or coverage regression; Monitor is
unchanged. The immutable candidate and prior accepted union25 are preserved.
The following Monitor/sampler results were outside union26.

Union27 adds accepted M6 plus the corrected same-store WAL case, Target prepare7,
Diagnostic authority6 and sampler overlap4: 24 complete PASS across five inputs.
Primary reviewed each full diff in clean exact-head worktrees; independent native
review verified all input/copy hashes, source148 and frozen scope arithmetic.
Toolkit gains11 and Monitor gains10 branches, with no denominator or coverage
regression. Earlier failed construction/timing batches remain excluded. M's
oversized input proves the earlier safe-read refusal, not the later value limit;
its original WAL case proves cold start and the corrected case proves trusted
same-store refusal. Sampler's public consumer is armed before start; its earlier
late-subscription timeout was a test error. All product bytes remain unchanged.

Risk-core v2 was selected by whole-file responsibility and independently frozen
at scope commit 9fff3f43 before scoring. Its 90 Toolkit and 16 Monitor files are
reported separately; the 108/18 overall files and old v1 statistics remain.

| Risk-core v2 | Covered / total branches | Coverage | More for 95% |
| --- | ---: | ---: | ---: |
| Toolkit | 11,213 / 12,906 | 86.8821% | 1,048 |
| Monitor | 2,666 / 2,940 | 90.6803% | 127 |

Native v1 scope remains 108/18 Python files overall and 97/16 core files. The excluded
forwarders have zero branches, so overall/core ratios coincide. Per-package native
summaries are authoritative; the previously recorded distinction between literal
JSON branch pairs and native summaries remains applicable. No raw splicing,
denominator change, cross-package pooling or failed-batch reuse is used.

Historical union23 evidence: `D:/codex-tmp/v10b-0918/r10/e/n95/union23`.
Generic run raw SHA256: `C565BD64F56D1F25FF7DF3F2073D476D8D289FA6C05C9B8A5C7C823F4DCE9780`.
Union23 Toolkit raw SHA256: `3B4FEC0818FA7F176A5E936EB627E2AB5AE115666529D620956634B88110A51B`.
Native JSON SHA256: `8A04CDF8C0AF1833BC0A76F0362518F117C6B48185296537AFB258DE710C7852`.
Independent review SHA256: `604D2971C58B08BAC9E851E2C9D78B57BCDE57E5287E0160D0610D30D743BB73`.
Historical snapshot SHA256: `1A1161097F4C2EA960C9E3C8B3005EF82050089853B51CD4C188DB42B5A450E6`.

Current evidence: `D:/codex-tmp/v10b-0918/r10/e/risk-v2/union27`.
Toolkit native raw: `E821F87FA2FE268DC1A4F4B1626A1E07D4B100B78AA4876E4867703FCFF157C8`.
Toolkit native JSON: `369D67199B5F95A363E3650C05DDA68E6CE4DC2069D945F2B979E16E3B513115`.
Monitor native raw: `5F4DDC3EDB73F6EC823E8BAF33EE16149345C153F956EC6BEF996A517758DC27`.
Monitor native JSON: `17C74D02E946040919C1916A2B7C8F34F73517649F9332D945998CDBDB2B1239`.
Immutable candidate: `4BE1C1D7FC929A78EC7BB1C3BD93F9E5F282F808B68F7A73BA791CF9A22DA738`.
Independent review: `C1EDB4A7406A0216500C8E24DE3429385D6A0F0C966B3298E885EC4AB9E3EF9A`.
Accepted canonical snapshot: `A2406BCD1C8EF73C59C53F793E6DD27D9943B863EEC309CF560861668AFDE143`.
The accepted prior union26 snapshot is retained in this evidence directory.

Overall 90% remains mandatory. The approved risk-layered redesign keeps broad-core
v1 statistics and introduces separately reviewed risk-core v2; its scope and
critical-scenario matrix are now frozen. All three numeric views remain visible. VS10-A/B
acceptance and attempt 7 are retained. Coverage qualification, seven pending native
Windows checks, final artifact creation and final deployment remain incomplete.
No hardware, packaging, deployment or remote action occurred in this offline
qualification batches. No clean full-suite PASS or physical PASS is inferred.

Supplementation follows the 2026-09-20 risk-layered specification and plan with
disjoint A/P/M ownership. No product changes solely for coverage, repeated valid
hardware evidence or branch-by-branch task sequence is authorized.

A metadata-only PowerShell variable-type error overwrote the local work ledger
during this wave. Its current authoritative state was recovered from the original
tool-output snapshot and the complete new run evidence. Some obsolete top-level
historical fields were not reconstructed; original raw evidence, source and
tracked historical reports were unchanged. The failure and recovery limits are
explicitly recorded in `risk-v2/ledger-write-failure.json` and `work-ledger.json`.

One cleanup attempt for the five verified success-run/copy roots t/dj4, t/u21,
t/u22, t/gq1 and t/u23 was rejected by automatic approval before process start
with `blocked by policy`. Zero files were deleted; all five remain present. No
retry or alternate deletion mechanism was used. Failure roots and authoritative
evidence remain preserved; disposition is recorded in union23/cleanup.json.

This wave's cleanup for vr1/vr2/u24/v2m-run1/v2a-run2 was likewise rejected before
process start with only `blocked by policy`; zero files were removed and there
was no retry. Later P-run2 and u25 roots remain pending cleanup, not relabeled as
explicitly rejected. Raw evidence and source/review worktrees remain retained.
See `risk-v2/cleanup-success.json` for the precise attempted targets.

Union27 cleanup of six new accepted-run/copy roots was rejected before process
start with blocked by policy. All roots remain, zero files were deleted, and no
retry or alternative deletion was attempted. See union27/cleanup.json.
