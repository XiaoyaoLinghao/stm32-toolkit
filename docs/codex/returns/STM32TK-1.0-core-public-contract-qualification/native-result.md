# Current native coverage result

Qualification accepted base: `ab2fd448a73a319b026a5a6da700b31c2535975f`.
Integrated code/test head before this report: `74eed9d9671f92fef2dd69994991677729e39f7e`.
Current runtime: `465249dba5560f7c08b1172794fec8fedd9b8d96`.
Native data verdict: **ACCEPTED**. Coverage targets: **NOT MET**.

| Package | Covered / total branches | Overall and frozen core | More for 90% | More for 95% |
| --- | ---: | ---: | ---: | ---: |
| Toolkit | 11,333 / 13,578 | 83.4659% | 888 | 1,567 |
| Monitor | 2,642 / 2,940 | 89.8639% | 4 | 151 |
| UI (retained) | 784 / 810 | 96.7901% | 0 | 0 |

Union8 contains four native inputs per package: its own accepted union7 baseline,
Project scan's seven PASS, and two Monitor analysis-workflow runs with nine
retained PASS plus six corrective PASS. This batch exercises the public scan,
analysis, continuation and export boundaries. All ten scan and sixteen unique
analysis target arcs were observed. No product source changed.

Monitor run1 failed during test collection and is excluded. Run2 stopped after
nine PASS because one test constructed a protocol-invalid provider error code.
That constructor raised inside the public query seam; the workflow's exception
mapping was reached, but the intended unknown-provider mapping was not. Run3
corrected the public input and ran only the failed and five unrun selectors.
It passed six items, exited zero and terminated normally. This is a composite
15-case qualification, not a clean single-run pass. Both original failures remain.

Only older creation_environment.py traces are purged from the two old-source
Toolkit copies. Original databases remain immutable; both complete 126-file raw arc sets equal their input unions. The failed run2 query-constructor path contributes no otherwise-unqualified branch. Native combine reruns no
tests. Overall scopes remain 108/18 files and frozen core scopes 97/16; forwarding
files outside core contain zero branch opportunities. UI stays separate. Native
coverage summaries remain authoritative, including multiline conditions and the
history.py no-branch loop. Source identity covers 148 files and 592 comparisons.

Native raw SHA-256: Toolkit `C6BC1E1C45399F0F1CEAD530B1DDE9188EE8D54A836C65C0B1538D4726D31DEE`;
Monitor `002CA092829AAC9DDDB10C3E97DC68E0C86A45DDE80672560A061519EC625389`.
Evidence and independent review: `r10/e/n95/union8/` under
`D:/codex-tmp/v10b-0918`. Earlier finite unions retain their valid passes,
historical failures, and physical acceptance scope.

The accepted MCP10, Project authorization29, Project parser3 and Authority
DiagnosticStore composite29 batches remain outside this finite union8 table.
Remaining Target publication and Project parser work continue separately. Seven
Windows native security checks, final artifact builds and final deployment remain
pending. The overall 90% gate and preferred core 95% target are not met; no new
physical or 1.0 release acceptance is claimed.
