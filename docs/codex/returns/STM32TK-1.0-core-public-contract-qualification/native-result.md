# Current native coverage result

Accepted wave base: `ab2fd448a73a319b026a5a6da700b31c2535975f`.
Integrated code/test head before this report: `f354e98b368ec2d522be52de1a61629bb05ac027`.
Current runtime: `465249dba5560f7c08b1172794fec8fedd9b8d96`.
Native data verdict: **ACCEPTED**. Coverage targets: **NOT MET**.

| Package | Covered / total branches | Overall and frozen core | More for 90% | More for 95% |
| --- | ---: | ---: | ---: | ---: |
| Toolkit | 11,177 / 13,578 | 82.3170% | 1,044 | 1,723 |
| Monitor | 2,589 / 2,940 | 88.0612% | 57 | 204 |
| UI (retained) | 784 / 810 | 96.7901% | 0 | 0 |

Union4 contains four inputs per package: its own accepted union3 baseline,
the two Monitor replay execution databases (7 retained PASS and 11 corrected/
previously unrun PASS), and Authority recovery-wire 94 PASS. It adds 98 Toolkit
and 18 Monitor branches. Originals are immutable and their hashes unchanged.
Only copied old-source Toolkit `creation_environment.py` data is purged;
all unaffected arcs are retained. No Monitor data is purged. The exact native
arc union is checked separately for both packages. Source identity covers 148
files and 592 comparisons; outside the accepted creation-environment correction,
source differences are only line endings. Overall scopes remain 108/18 files,
core scopes 97/16; excluded Python forwarding files have zero branch opportunities.

Native raw SHA-256: Toolkit
`22FF8DC936A02781E65BFB1C0BEF867D682C383441CA404DB1B24621B6794F90`;
Monitor `47A008E70E3015381FB6391EF9ED4D6822316D7F27D8F11B4604B5A091394053`.
Evidence and independent data review: `r10/e/n95/union4/` under approved
`D:/codex-tmp/v10b-0918`. Accepted historical baselines remain in `union3/`
and `union-next/`; no prior valid test was rerun to create this union.

The Monitor first run retains its NFC setup failure. Its corrected test changed
only whether the invalid text was canonicalized before the intended field guard;
the failed setup contributed no branch or statement absent from accepted evidence.
Authority's two test-structure errors were fixed before any execution; the final
94 cases reached all 94 intended guards. Project regeneration separately passed
26 cases and reached 27 intended guards after valid preview/path-oracle corrections;
these accepted results are integrated but deliberately outside the finite union4.
Runtime bytes and retained physical evidence are unchanged.

The Monitor continuation has twelve final functional PASS cases. Its first and
third runs remain historical exit-1 events with classified test defects; the
invalid-minimum second run is excluded. Project configuration has 135 unique
PASS cases; two affected cases passed again after the test helper captured
localized `mklink` output as bytes. Those reruns are not additional unique cases.
The Authority analysis-guards batch is now included in this native union.
Its five semantic cases passed and their intended refusal arcs were observed;
the unchanged tests are integrated at `cb36fd3ce6153423fa89706f1504e73e6a3d2368`.
The sixth, duplicate identity case was removed after proving that diagnostic
chain loading rejects its foreign workspace before the claimed analysis guard.
Its original exit-1 record remains in `r10/e/n95/a/analysis-guards/run1/`;
the missing `2269 -> 2270` arc remains unqualified, and no rerun was needed.

New accepted results also include four History fragmentation cases, seven
Project transaction cases, twelve distinct finalization cases, eighteen public
wire cases, and four provider-settlement cases. Finalization retains the first
run's interrupted exit-1 result with five completed passes; only the remaining
seven cases ran in bounded followups. Its sole exclusive coverage branch belongs
to the already-passed previous-checkpoint cases. The interruption contributes no
otherwise-unqualified branch gain.

Provider settlement passed functionally after static corrections, including a
previously missing async scenario invocation and positive stop/release assertions.
Six intended service arcs were subsequently proven to describe the opposite
predicate outcomes; their coverage claims are withdrawn and the branches remain
in the denominator. Only the intended lease arc was observed. No test was rerun
to repair that report mapping. The current continuation changes tests only;
runtime and retained physical evidence are unchanged.

The prior Authority model batch passed all 15 cases and reached all 15 intended
arcs after two invalid test references were corrected before execution. Backend
passed 20 cases and initially reached 17 of 18 intended arcs. The remaining arc
requires exhausting eight iterable elements, not an empty iterable; one additional
public iterator-budget case passed and reached it. The previous 20 items were not
rerun. Together these batches add 33 Toolkit branches without changing runtime.

The remaining-native-qualification plan is active. Target publication and Monitor
CLI/export boundaries are under read-only predicate review; they are not PASS.
Seven native Windows security checks, final artifact builds, and final deployment
remain pending. The 90% overall gate and 95% core target remain unmet; no new
physical or release acceptance is claimed.
