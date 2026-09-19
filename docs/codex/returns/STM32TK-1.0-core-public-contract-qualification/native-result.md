# Current native coverage result

Qualification accepted base: `ab2fd448a73a319b026a5a6da700b31c2535975f`.
Integrated code/test head before this report: `5c34842afba3973007c85c6defae6ed55f977e8d`.
Current runtime: `465249dba5560f7c08b1172794fec8fedd9b8d96`.
Native data verdict: **ACCEPTED**. Coverage targets: **NOT MET**.

| Package | Covered / total branches | Overall and frozen core | More for 90% | More for 95% |
| --- | ---: | ---: | ---: | ---: |
| Toolkit | 11,237 / 13,578 | 82.7589% | 984 | 1,663 |
| Monitor | 2,625 / 2,940 | 89.2857% | 21 | 168 |
| UI (retained) | 784 / 810 | 96.7901% | 0 | 0 |

Union6 contains five native inputs per package: its own accepted union5
baseline, two Project NEXT10 runs, and two Monitor model/group runs. It adds
13 Toolkit and 16 Monitor branches. Project's ten cases reached all twelve
intended branches; Monitor's sixteen cases reached all sixteen intended branches.
The eight Project and eleven Monitor passes from the original partial runs were
retained. Only each failed/unrun remainder executed after its test-only correction:
Project two PASS and Monitor five PASS. Both corrective runs exited 0 without
timeout and with their child processes terminated.

The Project failure was an incorrect test expectation for a public adapter error
message. The Monitor failure was a snapshot helper that captured file topology
before its own read-only SQLite query created WAL/SHM sidecars. A warmed persistent
read-only observer and explicit connection close fixed the test while retaining
all error, logical-state, main-byte, and sidecar-identity assertions. Neither
correction changed product code. The original exit-1 records remain preserved.
Each failed-run exclusive audit found zero otherwise-unqualified branches or
statements: remaining Project arcs belong to the eight retained passes, and
remaining Monitor arcs are exactly the eleven retained model guards and bodies.

Original raw databases and hashes remain unchanged. Only copied old-source
Toolkit `creation_environment.py` data is purged from the two Monitor inputs;
both current-source Project inputs are retained intact. No Monitor data is purged.
All 126 measured raw files match the exact native arc-set union for each package.
Source identity covers 148 files and 592 comparisons. Overall scopes remain
108/18 files, core scopes 97/16; excluded Python forwarding files have zero branch
opportunities. UI branch coverage is separate and other UI metrics are not
relabeled as 95% or pooled with Python coverage. Multiline Python conditionals
can normalize raw trace arcs to different native JSON branch headers; coverage
JSON's native summaries remain authoritative for percentages.

Native raw SHA-256: Toolkit
`7804E3ACD500BC48929AC73E466B96D6216C0AC4A1052E0523DCF1720C14523A`;
Monitor `3FD064E584896B09A8EE1C859C5ABE93A49F0431F993640953CC8C87CE421356`.
Evidence and independent data review: `r10/e/n95/union6/` under approved
`D:/codex-tmp/v10b-0918`. Accepted historical baselines remain in `union5/`,
`union4/`, `union3/`, and `union-next/`; their valid passes, failure history,
withdrawn unsupported arc claims, and physical scope limits are preserved.
Native combination reruns no tests.

Target replay's next 22 cases are independently reviewed, executed PASS, and
integrated, but are deliberately outside this finite union6 and not included in
the table. Authority diagnostic-model qualification remains pending. Seven native
Windows security checks, final artifact builds, and final deployment remain pending.
Product runtime bytes and retained physical evidence are unchanged. The 90%
overall gate and 95% core target remain unmet; no new physical or release acceptance
is claimed.
