# Current native coverage result

Accepted wave base: `ab2fd448a73a319b026a5a6da700b31c2535975f`.
Integrated code/test head before this report: `44b0ee58f5efca269513d6e1c3dae0e0673be9c5`.
Current runtime: `465249dba5560f7c08b1172794fec8fedd9b8d96`.
Native data verdict: **ACCEPTED**. Coverage targets: **NOT MET**.

| Package | Covered / total branches | Overall and frozen core | More for 90% | More for 95% |
| --- | ---: | ---: | ---: | ---: |
| Toolkit | 11,046 / 13,578 | 81.3522% | 1,175 | 1,854 |
| Monitor | 2,571 / 2,940 | 87.4490% | 75 | 222 |
| UI (retained) | 784 / 810 | 96.7901% | 0 | 0 |

The independent native union review verified exact file/arc sets for nine
inputs per package: its own accepted baseline and eight additional execution
databases. Original hashes are unchanged. Seven Toolkit copies contain zero
arcs for old `creation_environment.py`; the current-source baseline and Project
batch supply its valid measurements. The retained post-state proves that no old
arcs contribute, without claiming a separate purge invocation trace. Its accepted
optional-metadata correction adds two branch opportunities. No Monitor data was
purged. `generation/configure.py` source identity was
verified by equal Git blobs and LF-normalized text despite CRLF byte differences.
The 108/18 overall file scopes and 97/16 core file scopes remain unchanged;
the forwarding files outside the Python core have zero branch opportunities.

Native raw SHA-256: Toolkit
`A58BC0BDB4FF56156A402FBEA733FF988B53AABADF8BE505FCC8E82248AAF5E0`;
Monitor `4BFCF0275FDC8B98B5FD0DE284DB70B02176993E840411192326AE3665EF88A5`.
Evidence and independent review: `r10/e/n95/union-next/` under the approved
`D:/codex-tmp/v10b-0918` run root. `primary-result-review.json` supersedes the
historical prepared-entry state without rewriting executed data.

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

The remaining-native-qualification plan is active for four non-overlapping
Luna/max test owners. Source scope and denominators remain frozen. Seven native
Windows security checks, final artifact builds and final deployment remain
pending; no new physical or release acceptance is claimed.
