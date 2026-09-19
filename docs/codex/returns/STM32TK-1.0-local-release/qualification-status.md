# STM32 Toolkit 1.0 local qualification status

Status: **NOT ACCEPTED**. This is a release qualification status, not a new
hardware acceptance, publication approval, or a replacement for historical logs.

VS10-A and VS10-B remain locally accepted. The B acceptance base is
`1df30a0f4070805488687a67f907dbaa1867d681`. Retained artifacts were built from
`15b1a70e9bd684285da5557104deff529f537e49`. Runtime package source remains
byte-identical to that revision. Later qualification tests and the accepted
deployment-guide/trusted-utility-pin correction are not in that source ZIP.
No replacement artifact or deployment is claimed by this document.

The Diagnostic public-refusal slice was independently accepted from
`04bdd539597ec8dcb38bca34eb2256e970ecaa25` to
`4a39eb1cb96b1f674adef77461810842d9e6043f`. Its final 15 cases passed against
the frozen product. The primary complete-diff verdict is retained at
`r10/e/diagnostic-public-refusals/independent-review-final.md` beneath the
local release root `D:\codex-tmp\v10b-0918`.

The current original-order named backend performance run passed: append p95
25.0313ms, query p95 42.3386ms, export p95 1638.8022ms, retention p95 322.4248ms,
and retention ticker maximum 16.4967ms. Actual D-drive execution provenance and
independent qualification are in `r10/e/performance-final-followup`. The stdout's
old C-drive command text was not executed; it is a retained report-field defect.

The earlier retention failure remains unresolved: the caller timed out after
180ms, a worker interruption followed, and 512 values were durably deleted.
BUSY does not promise rollback after a write starts. The failed stage is still
unknown; the later passing run does not establish a repair. No timeout increase
or another blind benchmark repetition is approved by this status.

Python package branch coverage remains below the approved 90% gate. The native
aggregates currently record Toolkit 10817/13564 and Monitor 2490/2936 branches.
A separately accepted official Diagnostic JSON projection brings Toolkit to
10830/13564 (79.8437%); Monitor is 2490/2936 (84.8093%). It is supplementary
JSON evidence, not a native coverage database: the implementer deleted the raw
Diagnostic database before primary aggregation. No raw database has been
fabricated or restored. Future raw coverage and shards
are durable evidence subject to primary-only cleanup and a preservation hold.

The three Monitor lifecycle cases were accepted and integrated, with their raw
coverage included once in the current aggregates. The separate retention
cancellation experiment is not accepted: its first two passing cases omitted
the actual writer outcome; the corrected run reported one pass and one failure
at an internal-exception identity assertion. That failure does not establish
storage corruption. Its PowerShell launcher also assigned the read-only PID
variable, so the recorded launcher exit and timestamps do not prove the pytest
child's exit status. Preserve the JUnit/stdout and return to contract design;
do not aggregate that run or repeat the performance benchmark.

The release delivery audit found two portability omissions: standalone
PowerShell installation examples and unambiguous archive-relative instructions
for finding the IDE guide. The bounded correction was independently accepted and
integrated at 45b09455f469a423a45ee933d575364a8b5bf040. Separate Check, Bootstrap
and Repair examples preserve host-adapter paths and legacy upgrade semantics.
The final artifacts will need one refresh;
the existing 15b artifacts and deployment checks remain retained evidence, not
artifacts of the corrected candidate. No runtime or hardware change is implied.

The original full Toolkit suite was not a clean pass. Scoped accepted corrections
and their retained successful checks do not rewrite its historical output. In
particular, the continuation integrity failure remains nonreproduced/indeterminate
despite its successful isolated follow-up. It requires separate disposition.

Valid UI, browser, deterministic packaging, isolated fresh/upgrade deployment,
state-preservation, workspace-composition and A/B hardware evidence are retained.
Do not repeat them solely for test/report changes. New verification is limited
to meaningful uncovered public contracts and discriminating failure hypotheses;
the mandatory release coverage requirement is the reason for this qualification
work, not a reason to invent tests for impossible private states.

No push, PR mutation, merge, tag or release is authorized by this status.
