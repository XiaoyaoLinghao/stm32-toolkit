# Current native coverage result

Qualification accepted base: `ab2fd448a73a319b026a5a6da700b31c2535975f`.
Integrated code/test head before this report: `c2e92ac3439d83d2693768c9bb3b80b1f1b46045`.
Qualified runtime source: `465249dba5560f7c08b1172794fec8fedd9b8d96`.
Native data verdict: **ACCEPTED**. Monitor overall 90%: **MET**.
Toolkit overall 90% and both preferred core 95% targets: **NOT MET**.

| Package | Covered / total branches | Overall and frozen core | More for 90% | More for 95% |
| --- | ---: | ---: | ---: | ---: |
| Toolkit | 11,795 / 13,578 | 86.8685% | 426 | 1,105 |
| Monitor | 2,653 / 2,940 | 90.2381% | 0 | 140 |
| UI (retained separately) | 784 / 810 | 96.7901% | 0 | 0 |

Union20 combines each package's accepted union19 raw baseline with three complete
passing batches: probe ownership retry (4 tests, 7.43 seconds), lifecycle-event
and predecessor-chain qualification (2 tests, 17.72 seconds), and legacy analysis
plan input qualification (1 test, 25.94 seconds). The matrices verify valid
public prefixes, exact failures, persisted revision/event/root preservation and
resource ownership. Toolkit gains 26 native branches; Monitor is unchanged.

Five additional event decoder tests passed in the first event batch. Their test
bytes are unchanged, so the functional results remain valid without rerunning.
That batch stopped on a missing `copy.` qualifier in a new test. The first legacy
matrix stopped on an incorrect comparison of frozen result containers to JSON
lists, after the positive public operation succeeded. Luna/max corrected only
these test defects; the primary reviewed the complete diffs and ran only the
failed or unexecuted tests. Both initial failures are INFRASTRUCTURE, preserved,
and excluded wholesale from the native union. No product failure, physical PASS,
filtered raw data, or clean full-suite PASS is inferred.

The six executed test-file blobs match integration. All 148 product source files
across the three candidate roots and integration match the registry-pinned c96p
source after CRLF-to-LF normalization. Product bytes and dependencies did not
change. Independent review verified raw input/output hashes and exact normalized
native unions. Package scopes remain 108/18 files, core scopes 97/16, and branch
denominators 13578/2940. Non-core forwarding files have no branch opportunities,
so overall/core ratios coincide. Monitor's 2,652 literal JSON branch pairs and
2,653 native summary count retain their documented distinction. UI stays separate.
Residual branch counts are Toolkit 1,783 and Monitor 287.

Evidence: `r10/e/n95/union20/` under `D:/codex-tmp/v10b-0918`.
Independent review SHA-256: `CF3C390D405BFCADE2B2D275C7E40B31B5EA8F8795B340F9A8C51FEA5970E2B8`.
Primary review SHA-256: `70404C72507F93A01EC17E2AB82A221DCAA1960A299F551AB66F39D4DCA6CC84`.
Canonical coverage SHA-256: `502C20BE1EE4AF142CBAEF47A72B449032CD5A2409B9B8BD8523B9306D961452`.
The original union19 artifacts and all failed-run evidence remain preserved.

Overall 90% is mandatory; core95 is the user's preferred target. VS10-A/B
acceptance and attempt 7 remain valid. Seven Windows native security checks,
remaining coverage qualification, final artifacts and final deployment remain
pending. 1.0 is not accepted. This wave used no hardware, packaging, deployment
or remote action.

The small-batch verification/report overhead has become disproportionate. The
next primary design decision must cover complete public caller workflows, with
deduplicated reachable variants, first-guard/state/resource oracles and bounded
execution cost. Static residual counts do not prove reachability or future gains.
No automatic branch-sized implementation follows this report; no denominator
change or product edit solely for coverage is authorized.

One cleanup attempt for the six verified run-owned roots t/pr1, t/ec1, t/ec2,
t/la1, t/la2 and t/u20 was rejected by automatic approval before process start:
blocked by policy. Read-only verification confirms all remain present; zero
files were deleted and no retry or alternative deletion was used. Evidence and
the exact disposition are retained in union20/cleanup.json. Earlier rejected
cleanup roots remain untouched.
