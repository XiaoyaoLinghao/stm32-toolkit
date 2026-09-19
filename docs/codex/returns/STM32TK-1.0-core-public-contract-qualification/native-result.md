# Current native coverage result

Qualification accepted base: `ab2fd448a73a319b026a5a6da700b31c2535975f`.
Integrated code/test head before this report: `248c0a49a6c121331aff3a495b744fa953aba5e0`.
Current runtime: `465249dba5560f7c08b1172794fec8fedd9b8d96`.
Native data verdict: **ACCEPTED**. Monitor overall 90%: **MET**.
Toolkit overall 90% and both preferred core 95% targets: **NOT MET**.

| Package | Covered / total branches | Overall and frozen core | More for 90% | More for 95% |
| --- | ---: | ---: | ---: | ---: |
| Toolkit | 11,474 / 13,578 | 84.5043% | 747 | 1,426 |
| Monitor | 2,646 / 2,940 | 90.0000% | 0 | 147 |
| UI (retained separately) | 784 / 810 | 96.7901% | 0 | 0 |

Union11 combines each package's accepted union10 baseline with Target publication
run2, Target publication run4, and ProbeService5. Target is a composite of two
retained PASS and 24 later PASS; it is not a clean 26-item run. Run2's failure
reached an ArtifactRef role guard already covered in union10 and adds no
otherwise-unqualified coverage. Its only unique contribution beyond union10 plus
run4 is the two passing descriptor guards. Target run1 and run3 remain excluded.
Their fixture-construction failures are preserved, not product or hardware failures.

ProbeService5 passed all five metadata refusal cases, including missing optional
provider capability and public resource release. The aggregate adds 34 Toolkit
branches: 26 in publication, five in ProbeService, and three supporting branches
reached by the passing Target paths. Monitor remains unchanged. Product source
did not change. Multiline conditions use the native JSON branch identity while
retaining the verified raw tracing edges; literal line-pair equality is not assumed.

Independent review confirmed each complete 126-file raw arc union, 108/18 report
scopes, frozen 97/16 core scopes, input hashes and unchanged 13578/2940 branch
denominators. Non-core forwarding files have zero branch opportunities, so core
and overall ratios coincide. UI is never pooled with Python. Only older
creation_environment.py measurements are purged from copied Toolkit inputs;
originals remain immutable. Native combination reruns no tests.

Native raw SHA-256: Toolkit `89A401B1AEF334FD0526F20A2689F45E4C8E231222AE513D0F108CE43EA9F25F`;
Monitor `1B21BF9C441DC09D1A39CBB8AC3D93080ACB223410AB98B1FF451679F3183C2C`.
Evidence and independent review: `r10/e/n95/union11/` under
`D:/codex-tmp/v10b-0918`. Prior accepted unions and failure evidence remain retained.

The next Monitor replay batch is excluded: its first run stopped on an undefined
test assertion constant, with zero PASS and five unrun cases. Correction and
qualification remain pending. Recovery authorization and continuation terminal
scenarios are also pending; contradictory typed-state branches remain uncovered.

Earlier physical acceptance and attempt 7 remain unchanged. Seven Windows native
security checks, remaining coverage qualification, final artifacts and final deployment
remain pending. No new physical PASS, remote delivery or 1.0 release acceptance is claimed.
