# Current native coverage result

Qualification accepted base: `ab2fd448a73a319b026a5a6da700b31c2535975f`.
Integrated code/test head before this report: `c2e906bb0221eadfb7c5b8f1d2f2a7f07caa0a19`.
Current runtime: `465249dba5560f7c08b1172794fec8fedd9b8d96`.
Native data verdict: **ACCEPTED**. Coverage targets: **NOT MET**.

| Package | Covered / total branches | Overall and frozen core | More for 90% | More for 95% |
| --- | ---: | ---: | ---: | ---: |
| Toolkit | 11,224 / 13,578 | 82.6631% | 997 | 1,676 |
| Monitor | 2,609 / 2,940 | 88.7415% | 37 | 184 |
| UI (retained) | 784 / 810 | 96.7901% | 0 | 0 |

Union5 contains four inputs per package: its own accepted union4 baseline,
Project regeneration 26 PASS, Monitor CLI/export 10 new PASS plus 6 retained
functional PASS cases with newly captured missing native evidence, and Host
publication/repository 20 PASS. It adds 47 Toolkit and 20 Monitor branches.
Project reached all 27 intended arc entries; Monitor reached all 13 new and
9 recaptured entries (overlaps are not additional unique branches); Host reached
all 20 intended guards. All three runs exited 0 with no timeout or live child.
The Monitor six-case acquisition repairs a documented absence of raw coverage
from the original functional run; it is not six new cases or a full-suite replay.

Original raw databases and hashes remain unchanged. Only copied old-source
Toolkit `creation_environment.py` data is purged from the Monitor/Host inputs;
the current-source Project input is retained intact. No Monitor data is purged.
The exact native arc union is checked separately for both packages. Source
identity covers 148 files and 592 comparisons; outside the accepted creation
environment correction, source differences are only line endings. Overall scopes
remain 108/18 files, core scopes 97/16; excluded Python forwarding files have zero
branch opportunities. UI branch coverage is retained separately; other UI metrics
are not relabeled as 95% or pooled with Python coverage.

Native raw SHA-256: Toolkit
`3D028DE84D375B753621CAD9397EFA1F51651D8783AACD07DE843D04998858D6`;
Monitor `3BB72543D93C2F1FFDDD66E3FAA58275F14B72FBD75B8BCE7876F02E6812EF86`.
Evidence and independent data review: `r10/e/n95/union5/` under approved
`D:/codex-tmp/v10b-0918`. Accepted historical native baselines remain in
`union4/`, `union3/`, and `union-next/`. Native combination reruns no tests.

Historical failures and evidence boundaries remain preserved in those baselines:
Monitor replay's first NFC setup failure adds no otherwise-unqualified branch
or statement; only its remaining 11 cases ran after correction. Authority
recovery's structural/setup errors were corrected before execution and its
94 PASS/94 guard results remain included. Project's valid preview/path-oracle
corrections preceded the current 26-case run. Monitor's protocol-envelope and
no-write snapshot corrections preceded the current 16-case run. The older
six-class CLI result was missing raw coverage, while its separate PermissionError
case already reached the correct true branch and was not rerun.

Earlier accepted functional evidence remains valid, including Project configuration
135 unique PASS (two environmental reruns are not new cases), Monitor continuation
12 final functional PASS with its historical exit-1 records preserved, Authority
analysis guards five PASS with the sixth upstream-masked claim withdrawn, History
four cases, Project transactions seven, finalization twelve, public wire eighteen,
provider settlement four, Authority model fifteen, and backend twenty plus one
bounded iterator-budget case. Provider settlement's six incorrect service-arc
claims remain withdrawn. Original interrupted/failed runs and their exclusive-
coverage audits remain in the retained evidence roots; none is presented as a
clean full-suite PASS. Product runtime bytes and accepted physical evidence are
unchanged by this test-only continuation.

The remaining-native-qualification plan is active. The next Project selection
contains ten reviewed public request/plan/preview cases; it excludes the IOC-row
case masked by the earlier unknown-path guard. Monitor model/group and Authority
diagnostic-model boundaries remain unaccepted work. Seven native Windows security
checks, final artifact builds, and final deployment remain pending. The 90%
overall gate and 95% core target remain unmet; no new physical or release
acceptance is claimed.
