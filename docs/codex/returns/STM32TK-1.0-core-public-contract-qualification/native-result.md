# Current native coverage result

Qualification accepted base: `ab2fd448a73a319b026a5a6da700b31c2535975f`.
Integrated code/test head before this report: `64e9f6640f151a810c572b5e0ccf5f1a23cb7209`.
Current runtime: `465249dba5560f7c08b1172794fec8fedd9b8d96`.
Native data verdict: **ACCEPTED**. Monitor overall 90%: **MET**.
Toolkit overall 90% and both preferred core 95% targets: **NOT MET**.

| Package | Covered / total branches | Overall and frozen core | More for 90% | More for 95% |
| --- | ---: | ---: | ---: | ---: |
| Toolkit | 11,478 / 13,578 | 84.5338% | 743 | 1,422 |
| Monitor | 2,652 / 2,940 | 90.2041% | 0 | 141 |
| UI (retained separately) | 784 / 810 | 96.7901% | 0 | 0 |

Union12 combines each package's accepted union11 baseline, Monitor replay run2,
and physical recovery runs1/2. The six Monitor cases passed. Physical recovery
is a composite of one retained PASS and two later PASS, not a clean three-item
run. The original second case failed on a nonexistent test response key; its
execution adds no otherwise-unqualified branches or lines. The first PASS alone
accounts for run1's two unique arcs. Monitor run1 had zero PASS and is excluded.
Original failures and all earlier accepted inputs remain retained.

This aggregate adds four Toolkit and six Monitor branches. Product source did
not change. Multiline conditions retain verified native raw-to-JSON mappings;
literal line-pair equality is not assumed. Overall 90% remains mandatory and
core 95% remains the user's preferred target.

Independent review confirmed each complete 126-file raw arc union, 108/18 report
scopes, frozen 97/16 core scopes, input hashes and unchanged 13578/2940 branch
denominators. Non-core forwarding files have zero branch opportunities, so core
and overall ratios coincide. UI is never pooled with Python. Only older
creation_environment.py measurements are purged from copied Toolkit inputs;
originals remain immutable. Native combination reruns no tests.

Native raw SHA-256: Toolkit `392554160B4EAF1B4E3F9A30CC939F4E7FAE2CA1D9A8E173A120C633ADC9B211`;
Monitor `483C5DFD3AF3F11B077697E155891BC39965D6DDFD3022373E048BF1C1928291`.
Evidence and independent review: `r10/e/n95/union12/` under
`D:/codex-tmp/v10b-0918`. Prior accepted unions and failure evidence remain retained.

Continuation's first four-case run reached the 300-second wall budget and its
owned process was terminated. Three progress PASS markers survive, but no final
JUnit or coverage raw was produced. This batch contributes no aggregate coverage;
timeout diagnosis remains pending. Contradictory typed-state branches remain uncovered.

Earlier physical acceptance and attempt 7 remain unchanged. Seven Windows native
security checks, remaining coverage qualification, final artifacts and final deployment
remain pending. No new physical PASS, remote delivery or 1.0 release acceptance is claimed.
