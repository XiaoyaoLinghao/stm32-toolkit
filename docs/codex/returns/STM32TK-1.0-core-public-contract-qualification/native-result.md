# Current native coverage result

Qualification accepted base: `ab2fd448a73a319b026a5a6da700b31c2535975f`.
Integrated code/test head before this report: `e78ad0cda699253670f53db3b07615fbb59dbd5f`.
Current runtime: `465249dba5560f7c08b1172794fec8fedd9b8d96`.
Native data verdict: **ACCEPTED**. Monitor overall 90%: **MET**.
Toolkit overall 90% and both preferred core 95% targets: **NOT MET**.

| Package | Covered / total branches | Overall and frozen core | More for 90% | More for 95% |
| --- | ---: | ---: | ---: | ---: |
| Toolkit | 11,659 / 13,578 | 85.8668% | 562 | 1,241 |
| Monitor | 2,653 / 2,940 | 90.2381% | 0 | 140 |
| UI (retained separately) | 784 / 810 | 96.7901% | 0 | 0 |

Union16 combines each package's accepted union15 baseline with lease 12 PASS,
regeneration 31 composite PASS, and physical-recovery rev0 2 offline PASS. This
adds 72 Toolkit native branches: lease 13, regeneration 5, regeneration workflows
33, recovery workflows 15, and Configure 6. Monitor is unchanged. These are
software contract tests, not new physical acceptance.

Regeneration's 31 final passing selectors span four runs (5+23+2+1), not a single
clean run. Two Windows fixture path-length failures and one JSON wire-boundary
assertion failure were classified and corrected. Only the affected or not-yet-run
selectors continued; earlier PASS remains valid. The failed attempts, their logs,
and original evidence are retained and are not counted as PASS. Product code,
dependencies and physical evidence remain unchanged.

Independent review verified all 22 declared input hashes, exact full raw unions
(126 files per package), source identity, branch mappings, metrics and residuals.
Overall file scopes remain 108/18, core scopes 97/16, and denominators 13578/2940.
Non-core forwarding files have no branch opportunities, so core and overall
ratios coincide. UI is never pooled with Python. Monitor retains 2,652 explicit
executed-branch entries alongside native summary 2,653; the known history.py
representation difference does not change the metric or denominator.

The report addendum clarifies that old creation_environment.py purge rows are
historical provenance already handled upstream. All union16 inputs declare
oldCreation false. No new input purge, test rerun or recombination was needed.
Original prepared reports are preserved separately from the accepted report.

Native raw SHA-256: Toolkit `88E87F44623F8195BDC2824D2F6DC5231B555EFA9CC63D6D472A130720B30618`;
Monitor `C4BC10CAF84620D3E7DAC8E9CDFD471B11A9761A4542848214EC8DEC1EDA158A`.
Evidence and reviews: `r10/e/n95/union16/` under `D:/codex-tmp/v10b-0918`.
Independent review SHA-256:
`367CB8CD1406FD6EF670CEE811848AFC0F61BD437D008B931B462B86B7107299`.
Clarification addendum SHA-256:
`22D4389522C51ECC64DF431A756C91C82B69D75DB5A5A6D29A7EEC773F15A25F`.

Overall 90% remains mandatory; core 95% remains the user's preferred target.
Earlier physical acceptance and attempt 7 remain unchanged. Seven Windows native
security checks, remaining coverage qualification, final artifacts and final
deployment remain pending. No remote delivery or 1.0 release acceptance is claimed.
The seven new disposable test roots remain after cleanup was rejected before
process start by automatic approval review (blocked by policy); no retry occurred.
