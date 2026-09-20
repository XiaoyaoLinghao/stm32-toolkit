# Current native coverage result

Accepted integration before this report: `2520ac61b56d521a8df88ad8a268cff1a4bfbd32`.
Tested candidate: `a695f397260ebb815059d3df598dadf4c884924c`.
Qualified product source: `8a11caef14df16c5e56c0be2363d4ef5530110eb`.
Union23 native data verdict: **ACCEPTED_NATIVE_DATA**. Release 1.0: **NOT_ACCEPTED**.

| Package | Covered / total branches | Overall and frozen core | More for 90% | More for 95% |
| --- | ---: | ---: | ---: | ---: |
| Toolkit | 11,616 / 13,580 | 85.5376% | 606 | 1,285 |
| Monitor | 2,653 / 2,940 | 90.2381% | 0 | 140 |
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
branches; recovery_workflows.py now has 399/860 current-source branches. The run
did not import Monitor, so its accepted union22 object and UI are retained unchanged.

Native scope remains 108/18 Python files overall and 97/16 core files. The excluded
forwarders have zero branches, so overall/core ratios coincide. Per-package native
summaries are authoritative; Monitor's 2,652 explicit JSON branch pairs versus
2,653 native summary count retain their documented distinction. No raw splicing,
denominator change, cross-package pooling or failed-batch reuse is used.

Evidence root: `D:/codex-tmp/v10b-0918/r10/e/n95/union23`.
Generic run raw SHA256: `C565BD64F56D1F25FF7DF3F2073D476D8D289FA6C05C9B8A5C7C823F4DCE9780`.
Union23 Toolkit raw SHA256: `3B4FEC0818FA7F176A5E936EB627E2AB5AE115666529D620956634B88110A51B`.
Native JSON SHA256: `8A04CDF8C0AF1833BC0A76F0362518F117C6B48185296537AFB258DE710C7852`.
Independent review SHA256: `604D2971C58B08BAC9E851E2C9D78B57BCDE57E5287E0160D0610D30D743BB73`.
Canonical snapshot SHA256: `1A1161097F4C2EA960C9E3C8B3005EF82050089853B51CD4C188DB42B5A450E6`.

Overall 90% is mandatory; core 95% remains the user's preferred target. VS10-A/B
acceptance and attempt 7 are retained. Coverage qualification, seven pending native
Windows checks, final artifact creation and final deployment remain incomplete.
No hardware, packaging, deployment or remote action occurred in these two offline
qualification batches. No clean full-suite PASS or physical PASS is inferred.

Further implementation requires one finite public-workflow scope and a reachability/
cost decision. This report does not authorize another branch-by-branch test sequence,
product changes solely for coverage, or another run of valid hardware evidence.

One cleanup attempt for the five verified success-run/copy roots t/dj4, t/u21,
t/u22, t/gq1 and t/u23 was rejected by automatic approval before process start
with `blocked by policy`. Zero files were deleted; all five remain present. No
retry or alternate deletion mechanism was used. Failure roots and authoritative
evidence remain preserved; disposition is recorded in union23/cleanup.json.
