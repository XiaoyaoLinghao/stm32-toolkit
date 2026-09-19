# Current native coverage result

Qualification accepted base: `ab2fd448a73a319b026a5a6da700b31c2535975f`.
Integrated code/test head before this report: `18b987b86e6547f28a5971459b5a17418bc37f33`.
Current runtime: `465249dba5560f7c08b1172794fec8fedd9b8d96`.
Native data verdict: **ACCEPTED**. Monitor overall 90%: **MET**.
Toolkit overall 90% and both preferred core 95% targets: **NOT MET**.

| Package | Covered / total branches | Overall and frozen core | More for 90% | More for 95% |
| --- | ---: | ---: | ---: | ---: |
| Toolkit | 11,533 / 13,578 | 84.9389% | 688 | 1,367 |
| Monitor | 2,653 / 2,940 | 90.2381% | 0 | 140 |
| UI (retained separately) | 784 / 810 | 96.7901% | 0 | 0 |

Union14 combines each package's accepted union13 baseline with five successful
batches: 19 replay wire cases, one legal failed-sample control, retained Diagnostic
completion evidence, two corrected Diagnostic plan cases, and two continuation
reference functions containing ten variants. The five batches contain 28 executed
PASS cases, including two plan selectors run before and after correction; this is
not a claim of 28 distinct selectors. Original failures and accepted inputs remain
retained. No previously valid completion or replay selector was rerun.

This aggregate adds 38 Toolkit branches and no Monitor branches. Replay contributes
19 new branches, Diagnostic contributes six, and continuation contributes 13.
The original replay negative case correctly rejects at 659->660, already covered;
the separate positive case covers the intended legal path at 659->661. Diagnostic's
first plan variants stopped at a stale cross-root digest; an opt-in fixture repair
preserved the transcript and synchronized its root digest, allowing the two
corrected cases to reach 2156->2157 and 2175->2176. No product behavior changed.
Overall 90% remains mandatory; core 95% remains the user's preferred target.

Primary verified each complete 126-file raw arc union; independent review verified
the exact package-filtered unions, 108/18 report scopes, frozen 97/16 core scopes,
input hashes and unchanged 13578/2940 branch denominators. Non-core forwarding
files have zero branch opportunities, so core and overall ratios coincide. UI is
never pooled with Python. The known Monitor history.py no-branch representation
has 2,652 explicit branch arrays and a native summary of 2,653; the native summary
is retained consistently. These current-source inputs require no copy purge.
Source proof covers 148 files across four roots; differences are line endings
only. Native combination reruns no tests and originals remain immutable.

Native raw SHA-256: Toolkit `73EEA83137CFBF16FDF6C823F6E2B0DB1D14395992BFC917C0C595C1C8CB16D8`;
Monitor `DF589252E5A32A7B9BDE49892E033BA1A39015E9971CAB4CA42A97DE889D937D`.
Evidence and independent review: `r10/e/n95/union14/` under
`D:/codex-tmp/v10b-0918`. Prior accepted unions and failure evidence remain retained.

Earlier continuation timeout and collection failures remain excluded exactly as
recorded in union13. The new continuation tests passed in 46.90 seconds after a
missing fixture field was caught and corrected during static review. Native
multiline mappings are verified rather than inferred from literal line equality.
Contradictory typed-state and other unqualified branches remain uncovered.

Earlier physical acceptance and attempt 7 remain unchanged. Seven Windows native
security checks, remaining coverage qualification, final artifacts and final deployment
remain pending. No new physical PASS, remote delivery or 1.0 release acceptance is claimed.
