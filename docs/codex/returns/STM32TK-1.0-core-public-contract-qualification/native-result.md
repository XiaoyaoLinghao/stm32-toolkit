# Current native coverage result

Qualification accepted base: `ab2fd448a73a319b026a5a6da700b31c2535975f`.
Integrated code/test head before this report: `057126eb9fff494086593f0df7690edd2836284e`.
Current runtime: `465249dba5560f7c08b1172794fec8fedd9b8d96`.
Native data verdict: **ACCEPTED**. Monitor overall 90%: **MET**.
Toolkit overall 90% and both preferred core 95% targets: **NOT MET**.

| Package | Covered / total branches | Overall and frozen core | More for 90% | More for 95% |
| --- | ---: | ---: | ---: | ---: |
| Toolkit | 11,495 / 13,578 | 84.6590% | 726 | 1,405 |
| Monitor | 2,653 / 2,940 | 90.2381% | 0 | 140 |
| UI (retained separately) | 784 / 810 | 96.7901% | 0 | 0 |

Union13 combines each package's accepted union12 baseline, Monitor journal-mode
rejection, the isolated continuation timeout case, and 13 tool-support cases.
The new batches all passed. Tool-support run1 failed collection and executed no
tests; its raw is excluded. The three continuation progress PASS markers from
its earlier timed-out run remain preserved without native coverage attribution.
Original failures and all earlier accepted inputs remain retained.

This aggregate adds 17 Toolkit and one Monitor branch. Tool support contributes
15 selected target arcs plus one incidental nested-schema edge; continuation
contributes one timeout edge and storage one journal-mode refusal edge. Product
source did not change. Conditions retain verified native raw-to-JSON mappings;
literal line-pair equality is not assumed. Overall 90% remains mandatory and
core 95% remains the user's preferred target.

Independent review confirmed each complete 126-file raw arc union, 108/18 report
scopes, frozen 97/16 core scopes, input hashes and unchanged 13578/2940 branch
denominators. Non-core forwarding files have zero branch opportunities, so core
and overall ratios coincide. UI is never pooled with Python. Only older
creation_environment.py measurements are purged from copied Toolkit inputs;
originals remain immutable. Native combination reruns no tests.

Native raw SHA-256: Toolkit `B61B9AEAF6D41077D33186BF17C9F175A0A9654DA30FB00A3C60162D7273ABE3`;
Monitor `A4B798963D8FCF324291FF5FA77FC2DCA37E754A0D69DC2518190B28A7B20EAE`.
Evidence and independent review: `r10/e/n95/union13/` under
`D:/codex-tmp/v10b-0918`. Prior accepted unions and failure evidence remain retained.

Continuation's first four-case run exhausted its 300-second serial wall budget.
The fourth fixture started after about 230 seconds; its separate run passed in
78.76 seconds with JUnit and raw coverage. Only that separate run is included.
Diagnostic workflow qualification remains pending after reconciling the logical
checkpoint key with its hashed storage filename. Contradictory typed-state
branches remain uncovered.

Earlier physical acceptance and attempt 7 remain unchanged. Seven Windows native
security checks, remaining coverage qualification, final artifacts and final deployment
remain pending. No new physical PASS, remote delivery or 1.0 release acceptance is claimed.
