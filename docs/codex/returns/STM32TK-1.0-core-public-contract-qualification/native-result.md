# Current native coverage result

Qualification accepted base: `ab2fd448a73a319b026a5a6da700b31c2535975f`.
Integrated code/test head before this report: `c78dfb84ec8c2481d7a74c911f05cafb7967e131`.
Current runtime: `465249dba5560f7c08b1172794fec8fedd9b8d96`.
Native data verdict: **ACCEPTED**. Monitor overall 90%: **MET**.
Toolkit overall 90% and both preferred core 95% targets: **NOT MET**.

| Package | Covered / total branches | Overall and frozen core | More for 90% | More for 95% |
| --- | ---: | ---: | ---: | ---: |
| Toolkit | 11,706 / 13,578 | 86.2130% | 515 | 1,194 |
| Monitor | 2,653 / 2,940 | 90.2381% | 0 | 140 |
| UI (retained separately) | 784 / 810 | 96.7901% | 0 | 0 |

Union17 combines each package's accepted union16 baseline with two complete
passing offline batches: testing workflows 13 PASS and finalization wire parsing
25 PASS. It adds 47 Toolkit native branches: testing workflows 22 and finalization
25. Monitor is unchanged. These are software contract tests; product bytes,
dependencies and earlier physical evidence remain unchanged.

Independent review verified input hashes, 38 passing JUnit cases, source identity,
raw-to-JSON branch mappings and exact full raw unions: Toolkit 126 files / 86,522
arcs, Monitor 126 files / 58,472 arcs. Package-filtered file scopes remain 108/18,
core scopes 97/16, and denominators 13578/2940. Non-core forwarding files have no
branch opportunities, so overall and core ratios coincide. UI is never pooled
with Python. Monitor retains its known 2,652 explicit executed-branch entries
alongside native summary 2,653; the summary remains the branch metric.

The independent review's base/candidate blob sentence is clarified in the primary
result review: finalization candidate `2616afbb74a8b32158ff4f11369ab88177874716`
and integration `c78dfb84ec8c2481d7a74c911f05cafb7967e131` have identical test bytes.
The accepted base `7f66a2a9eb4b0ee8ab61dfdf0ed9525aa3f704ec` intentionally lacks
the new tests. This is a report clarification; no test or combine was repeated.
Original prepared reports and the independent review remain preserved.

Historical creation_environment.py purge entries were handled upstream. All
union17 inputs are source-compatible with runtime 465; there is no new purge.
Native raw SHA-256: Toolkit `A170BF795796F4E304BD904087F5BA292D36F926F4442F914DF2E52BE45FFCA1`;
Monitor `931D9D5FCF0BE2D4792DE70F00D3BCCE8F4A8ADD93F473FA916729A5117FE8E1`.
Evidence and reviews: `r10/e/n95/union17/` under `D:/codex-tmp/v10b-0918`.
Independent review SHA-256: `4BD2DA7E21662268970E5FC31F89B031EDD1D9D77E03E9B5D85EC8856E7D75C6`.
Primary clarification/review SHA-256: `A8FDDF47C3B274E86487B3E5A48C08DB117D1F1B8DDB4F272DE8D58BA3F5CC03`.

Overall 90% remains mandatory; core 95% remains the user's preferred target.
Earlier physical acceptance and attempt 7 remain unchanged. Seven Windows native
security checks, remaining coverage qualification, final artifacts and final
deployment remain pending. No remote delivery or 1.0 release acceptance is claimed.
Earlier rejected cleanup paths remain untouched. A single attempt to remove the
three verified union17 disposable roots (t/w1, t/f1, t/u17) was rejected before
process start by automatic approval review: blocked by policy. Nothing was
deleted and no retry occurred; original evidence remains preserved.
