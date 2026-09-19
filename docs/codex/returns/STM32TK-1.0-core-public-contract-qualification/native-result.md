# Current native coverage result

Qualification accepted base: `ab2fd448a73a319b026a5a6da700b31c2535975f`.
Integrated code/test head before this report: `70b83fed927768ad9de3d75e75c884407186157f`.
Current runtime: `465249dba5560f7c08b1172794fec8fedd9b8d96`.
Native data verdict: **ACCEPTED**. Monitor overall 90%: **MET**.
Toolkit overall 90% and both preferred core 95% targets: **NOT MET**.

| Package | Covered / total branches | Overall and frozen core | More for 90% | More for 95% |
| --- | ---: | ---: | ---: | ---: |
| Toolkit | 11,440 / 13,578 | 84.2539% | 781 | 1,460 |
| Monitor | 2,646 / 2,940 | 90.0000% | 0 | 147 |
| UI (retained separately) | 784 / 810 | 96.7901% | 0 | 0 |

Union9 added accepted MCP root adapters, Project authorization and parser cases,
and DiagnosticStore composite evidence to each package's accepted union8 baseline.
The parser qualification passed all 34 items and reached all 35 intended arcs.
DiagnosticStore retains its 19 PASS before a fixture keyword failure and the
subsequent 10 PASS; the failed call occurred before the product and contributed
no otherwise-unqualified coverage. It is a composite result, not a clean 29-item run.

Union10 adds four Monitor public-boundary PASS to each package's own union9 raw:
invalid authentication endpoint, incompatible download provider result, body-bearing
WebSocket request, and invalid sampler listener. Public controls, exact error
responses, provider effects and lifecycle cleanup were checked. All four intended
arcs were observed in raw and JSON data. Product source did not change.

Independent review confirmed each complete 126-file raw arc union, the 108/18
report scopes, the frozen 97/16 core scopes, all input hashes and unchanged
13578/2940 branch denominators. Non-core forwarding files have zero branch
opportunities, so core and overall ratios coincide. UI is never pooled with Python.
Only old creation_environment.py measurements are purged from copied Toolkit
inputs; originals remain immutable. Native combine reruns no tests. Native summary
semantics, including the history.py no-branch loop, remain authoritative.

Native raw SHA-256: Toolkit `6CA7B8068735766AC3BE880D784E3BC017FE4E7D1C13D08DCE54B423A9585280`;
Monitor `82AA7681EC324EF73C568AABED2DC329FBFBF53DDA3FDB0DA5022B9013D9B28C`.
Evidence and independent review: `r10/e/n95/union9/` and `r10/e/n95/union10/`
under `D:/codex-tmp/v10b-0918`.

Target publication's pending batch is excluded. Two historical case PASS remain
valid; later runs exposed test-construction defects involving derived envelope IDs,
ArtifactRef roles and fixture/manifest run identity. The latest no-op control failed
before its negative mutation. A complete fixture-graph audit precedes correction;
none of these failures is claimed as a product or hardware failure.

Earlier physical acceptance and attempt 7 remain unchanged. Seven Windows native
security checks, remaining coverage qualification, final artifacts and final deployment
remain pending. No new physical PASS, remote delivery or 1.0 release acceptance is claimed.
