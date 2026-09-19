# Current native coverage result

Qualification accepted base: `ab2fd448a73a319b026a5a6da700b31c2535975f`.
Integrated code/test head before this report: `db6e547bff128d67ae018410fa96b188778ce69a`.
Current runtime: `465249dba5560f7c08b1172794fec8fedd9b8d96`.
Native data verdict: **ACCEPTED**. Monitor overall 90%: **MET**.
Toolkit overall 90% and both preferred core 95% targets: **NOT MET**.

| Package | Covered / total branches | Overall and frozen core | More for 90% | More for 95% |
| --- | ---: | ---: | ---: | ---: |
| Toolkit | 11,587 / 13,578 | 85.3366% | 634 | 1,313 |
| Monitor | 2,653 / 2,940 | 90.2381% | 0 | 140 |
| UI (retained separately) | 784 / 810 | 96.7901% | 0 | 0 |

Union15 combines each package's accepted union14 baseline with three batches:
two new Configure cases, five existing Configure selectors measured for missing
native evidence, and 50 MCP public contract cases. All 57 cases passed. This adds
54 Toolkit branches: 13 from Configure and 41 from MCP; Monitor is unchanged.
Product code and dependencies are unchanged. The MCP batch's nonfatal dependency
warning is retained in its log. No full suite or hardware check was rerun.

The earlier Configure functional PASS remains valid. Its retained subprocess
shards lack the needed parent-process arcs, so only five relevant selectors were
measured again; an unrelated cleanup control was not rerun. MCP error oracles were
corrected during static review before execution. Original evidence is preserved.

Independent review verified exact full raw unions (126 files), package-filtered
unions, input hashes, source identity, normalized branch mappings and residuals.
Overall file scopes remain 108/18, core scopes 97/16, and denominators 13578/2940.
Non-core forwarding files have no branch opportunities, so core and overall ratios
coincide. UI is never pooled with Python. Monitor history.py retains the known
representation difference: 2,652 explicit branch arrays versus native summary
2,653. No branches were removed from the denominator, and no raw input was purged.

The first review found stale remaining-branch fields in the derived report.
A separately reviewed report-only correction set Toolkit's gaps to 634 and 1,313;
raw data, test results, file scope and UI evidence stayed unchanged. No test or
coverage combination was repeated for that correction.

Native raw SHA-256: Toolkit `DBE9B3B86C9761262115B2DD646AACF78276E001D01176C3929728D9C8BA4C09`;
Monitor `5F09BF770154F9F39577A831BBD89598FDC43D338E3EC5185016987FCBEABBFB`.
Evidence and reviews: `r10/e/n95/union15/` under `D:/codex-tmp/v10b-0918`.
Independent correction addendum SHA-256:
`3235E15316CB1E231C01756C7AAA036C4FD6AB4A08E5E9DF965D15F621615F74`.

Overall 90% remains mandatory; core 95% remains the user's preferred target.
Earlier physical acceptance and attempt 7 remain unchanged. Seven Windows native
security checks, remaining coverage qualification, final artifacts and final
deployment remain pending. No new physical PASS, remote delivery or 1.0 release
acceptance is claimed.
