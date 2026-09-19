# Current native coverage result

Accepted wave base: `ab2fd448a73a319b026a5a6da700b31c2535975f`.
Integrated code/test head before this report: `a3d9cee5f3b4986a7ab22bbf520bf9118a85e3da`.
Current runtime: `465249dba5560f7c08b1172794fec8fedd9b8d96`.
Native data verdict: **ACCEPTED**. Coverage targets: **NOT MET**.

| Package | Covered / total branches | Overall and frozen core | More for 90% | More for 95% |
| --- | ---: | ---: | ---: | ---: |
| Toolkit | 11,079 / 13,578 | 81.5952% | 1,142 | 1,821 |
| Monitor | 2,571 / 2,940 | 87.4490% | 75 | 222 |
| UI (retained) | 784 / 810 | 96.7901% | 0 | 0 |

The native union contains four inputs per package: its own previously accepted
baseline and three additional execution databases (Authority model 15 PASS,
Backend 20 PASS, and one new iterator-budget PASS). Original hashes are unchanged.
Only the three copied old-source Toolkit inputs had `creation_environment.py`
arcs purged; the accepted current-source baseline supplies its valid data. The
purge record checks all unaffected arcs for equality. No Monitor data was purged.
Source identity was verified for 148 files and 592 comparisons; all differences
outside the accepted `creation_environment.py` correction are only line endings.
The 108/18 overall scopes and 97/16 core scopes remain unchanged; forwarding files
outside the Python core have zero branch opportunities.

Native raw SHA-256: Toolkit
`3B1F26FA7CCAAE527F6358DFDB6BB12ABC672839F870F6A596983A1875ED8276`;
Monitor `2C5426B9B83B3BB48DFA3D6F18910E1904F53300834D3113AE0CA24ACB9C00EE`.
Evidence and independent data review: `r10/e/n95/union3/` under the approved
`D:/codex-tmp/v10b-0918` run root. Its baseline retains the earlier nine-input
qualification history in `r10/e/n95/union-next/`.

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

The current Authority model batch passed all 15 cases and reached all 15 intended
arcs after two invalid test references were corrected before execution. Backend
passed 20 cases and initially reached 17 of 18 intended arcs. The remaining arc
requires exhausting eight iterable elements, not an empty iterable; one additional
public iterator-budget case passed and reached it. The previous 20 items were not
rerun. Together these batches add 33 Toolkit branches without changing runtime.

The remaining-native-qualification plan is active. Monitor replay boundaries,
Authority recovery wire boundaries, and Project regeneration preparation have
separate owners. Seven native Windows security checks, final artifact builds,
and final deployment remain pending. The 90% overall gate and 95% core target
remain unmet; no new physical or release acceptance is claimed.
