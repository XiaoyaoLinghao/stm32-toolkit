# Current native coverage result

Qualification accepted base: `ab2fd448a73a319b026a5a6da700b31c2535975f`.
Integrated code/test head before this report: `1bbd6d57b99da8fa2a53687f8aefca77611a001e`.
Current runtime: `465249dba5560f7c08b1172794fec8fedd9b8d96`.
Native data verdict: **ACCEPTED**. Coverage targets: **NOT MET**.

| Package | Covered / total branches | Overall and frozen core | More for 90% | More for 95% |
| --- | ---: | ---: | ---: | ---: |
| Toolkit | 11,323 / 13,578 | 83.3923% | 898 | 1,577 |
| Monitor | 2,625 / 2,940 | 89.2857% | 21 | 168 |
| UI (retained) | 784 / 810 | 96.7901% | 0 | 0 |

Union7 contains four native inputs per package: its own accepted union6 baseline,
Target replay 22 PASS, and two Authority diagnostic-model runs with 15 retained
PASS plus 48 corrective PASS. These reach all 22 publication and 64 model guard
entries and add 86 Toolkit branches. Monitor coverage is unchanged. The first
Authority run exited 1 because a test tried to deepcopy a model containing
mappingproxy before calling the target product function. Four test snapshots were
corrected to compare public model projections, with mapping keys and tuple/element
identities preserved. Only the failed/unrun 48 cases executed afterward. The
corrective run exited 0 without timeout and its process terminated. The earlier
session-result-limit input error was corrected to the real 4097 bound before any
execution. Neither correction changed product behavior.

The historical failed-run audit retains exactly the 16 guard branches and 17
handler/body lines belonging to the 15 already-passed cases. It finds zero
otherwise-unqualified coverage after applying the existing source-identity
exclusion for old creation_environment.py. Only that file is purged on the three
old-source Toolkit input copies. No Monitor data is purged. Originals remain
immutable; both complete 126-file raw arc sets equal their native input unions.
Source identity covers 148 files and 592 comparisons. Overall scopes remain
108/18 files and core scopes 97/16; excluded forwarding files have zero branch
opportunities. UI stays separate. Native coverage summaries are authoritative,
including multiline-conditional normalization and history.py's no-branch loop.

Native raw SHA-256: Toolkit `245C33971079918199C922AB2E7E971CE89795FFF6A8D26F9163A78D1244F954`;
Monitor `9E6D8400A434FB7C74EE703509D129EC47EC0153A538EA9E18ACE3AAD02C2A54`.
Evidence and independent review: `r10/e/n95/union7/` under
`D:/codex-tmp/v10b-0918`. Accepted earlier baselines in `union6/`, `union5/`,
`union4/`, `union3/`, and `union-next/` preserve valid passes, original failures,
withdrawn unsupported claims, and physical acceptance scope. Native combination
reruns no tests; accepted product runtime and physical evidence remain unchanged.

Project scan's seven cases are independently reviewed, executed PASS with ten
guards, and integrated, but remain outside this finite union7 and outside the
table. The real NTFS name-collision case passed; symlink capability was not retried.
Monitor analysis workflow qualification and remaining public boundary work continue.
Seven native Windows security checks, final artifact builds, and final deployment
remain pending. Neither the overall 90% gate nor core 95% target is met, and no
new physical or release acceptance is claimed.
